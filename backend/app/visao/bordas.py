"""Detecção automática dos 4 cantos da folha.

Fotos reais de celular têm mesa clara (pouco contraste), sombra, papel ondulado,
dedo segurando a folha e canto dobrado. Por isso a detecção:

1. gera candidatos por três caminhos: Canny com limiar normal, Canny com limiar
   baixo (bordas fracas) e segmentação pelo brilho do papel (Otsu);
2. transforma cada contorno num quadrilátero pela envoltória convexa; quando ela
   tem mais de 4 lados (canto coberto, dobrado ou borda curva), prolonga os 4 lados
   mais longos até se cruzarem, recuperando o canto que não aparece;
3. escolhe o maior candidato com borda contínua ao longo dos 4 lados ("apoio de
   borda"). Só conta o gradiente perpendicular a cada lado: a borda do papel é
   perpendicular ao lado, enquanto o contorno de um bloco de texto cruza o topo e a
   base das linhas, cujo gradiente corre paralelo ao lado e por isso não conta.
"""

import cv2
import numpy as np

from app.visao.perspectiva import ordenar_cantos

LADO_PROCESSAMENTO = 500  # lado maior da imagem reduzida usada só para detectar
AREA_MINIMA_RELATIVA = 0.10  # a folha precisa ocupar ao menos 10% da foto
CONTORNOS_POR_ESTRATEGIA = 6
LIMIARES_CANNY = ((50, 150), (20, 60))  # normal e sensível (mesa clara, pouca luz)
TOLERANCIAS_APROXIMACAO = (0.01, 0.015, 0.02, 0.03, 0.04, 0.05)
# Apoio de borda: fração dos pontos de cada lado com gradiente perpendicular acima do
# limiar (vale o lado mais fraco). O limiar é baixo para pegar folha branca em mesa clara.
GRADIENTE_MINIMO = 8
APOIO_MINIMO = 0.7
BUSCA_PERPENDICULAR = 3  # tolera até 3 px de erro na posição de cada lado
MARGEM_DOS_CANTOS = 0.12  # ignora o trecho perto dos cantos, que pode estar coberto/dobrado
# O quadrilátero obtido prolongando os lados pode crescer além da envoltória (canto
# escondido), mas não muito: acima disso a interseção é de retas quase paralelas.
CRESCIMENTO_MAXIMO = 1.35

CANTOS_PADRAO = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)


def _reduzir(imagem: np.ndarray) -> np.ndarray:
    altura, largura = imagem.shape[:2]
    escala = LADO_PROCESSAMENTO / max(altura, largura)
    if escala >= 1:
        return imagem
    return cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)


def _contornos_candidatos(suavizada: np.ndarray) -> list[np.ndarray]:
    nucleo = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    contornos: list[np.ndarray] = []
    for baixo, alto in LIMIARES_CANNY:
        bordas = cv2.Canny(suavizada, baixo, alto)
        # O fechamento morfológico une bordas quebradas.
        bordas = cv2.morphologyEx(bordas, cv2.MORPH_CLOSE, nucleo, iterations=2)
        encontrados, _ = cv2.findContours(bordas, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contornos += sorted(encontrados, key=cv2.contourArea, reverse=True)[
            :CONTORNOS_POR_ESTRATEGIA
        ]

    # Papel é mais claro que quase toda mesa: Otsu separa a folha, e o fechamento
    # grande preenche as linhas de texto para a folha virar uma mancha só.
    _, claro = cv2.threshold(suavizada, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    nucleo_grande = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    claro = cv2.morphologyEx(claro, cv2.MORPH_CLOSE, nucleo_grande)
    claro = cv2.morphologyEx(claro, cv2.MORPH_OPEN, nucleo)
    encontrados, _ = cv2.findContours(claro, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contornos += sorted(encontrados, key=cv2.contourArea, reverse=True)[:CONTORNOS_POR_ESTRATEGIA]
    return contornos


def _intersecao(p1, p2, p3, p4) -> np.ndarray | None:
    """Ponto onde a reta p1-p2 cruza a reta p3-p4 (None se forem quase paralelas)."""
    d1, d2 = p2 - p1, p4 - p3
    denominador = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(denominador) < 1e-6 * np.linalg.norm(d1) * np.linalg.norm(d2):
        return None
    t = ((p3[0] - p1[0]) * d2[1] - (p3[1] - p1[1]) * d2[0]) / denominador
    return p1 + t * d1


def _quatro_lados_mais_longos(poligono: np.ndarray) -> np.ndarray | None:
    """Prolonga os 4 lados mais longos do polígono até se cruzarem (recupera cantos escondidos)."""
    n = len(poligono)
    comprimentos = [np.linalg.norm(poligono[(i + 1) % n] - poligono[i]) for i in range(n)]
    escolhidos = sorted(sorted(range(n), key=lambda i: comprimentos[i], reverse=True)[:4])
    cantos = []
    for k in range(4):
        a, b = escolhidos[k], escolhidos[(k + 1) % 4]
        ponto = _intersecao(poligono[a], poligono[(a + 1) % n], poligono[b], poligono[(b + 1) % n])
        if ponto is None:
            return None
        cantos.append(ponto)
    return np.array(cantos, dtype=np.float32)


def _quadrilatero(contorno: np.ndarray) -> np.ndarray | None:
    envoltoria = cv2.convexHull(contorno).reshape(-1, 2).astype(np.float32)
    area_envoltoria = cv2.contourArea(envoltoria)
    perimetro = cv2.arcLength(envoltoria, True)
    for tolerancia in TOLERANCIAS_APROXIMACAO:
        poligono = cv2.approxPolyDP(envoltoria, tolerancia * perimetro, True).reshape(-1, 2)
        poligono = poligono.astype(np.float32)
        if len(poligono) < 4:
            return None
        quad = poligono if len(poligono) == 4 else _quatro_lados_mais_longos(poligono)
        if quad is None or not cv2.isContourConvex(quad.reshape(-1, 1, 2)):
            continue
        if area_envoltoria * 0.9 <= cv2.contourArea(quad) <= area_envoltoria * CRESCIMENTO_MAXIMO:
            return quad
    return None


def _apoio_de_borda(quad: np.ndarray, gx: np.ndarray, gy: np.ndarray) -> float:
    """Fração de pontos com borda perpendicular forte, no lado mais fraco do quadrilátero."""
    altura, largura = gx.shape
    t = np.linspace(MARGEM_DOS_CANTOS, 1 - MARGEM_DOS_CANTOS, 60)[:, None]
    apoios = []
    for i in range(4):
        inicio, direcao = quad[i], quad[(i + 1) % 4] - quad[i]
        normal = np.array([-direcao[1], direcao[0]]) / (np.linalg.norm(direcao) + 1e-6)
        base = inicio + t * direcao
        intensidade = np.zeros(len(base), dtype=np.float32)
        for deslocamento in range(-BUSCA_PERPENDICULAR, BUSCA_PERPENDICULAR + 1):
            pontos = base + deslocamento * normal
            x = np.clip(np.round(pontos[:, 0]).astype(int), 0, largura - 1)
            y = np.clip(np.round(pontos[:, 1]).astype(int), 0, altura - 1)
            perpendicular = np.abs(gx[y, x] * normal[0] + gy[y, x] * normal[1])
            intensidade = np.maximum(intensidade, perpendicular)
        apoios.append(float((intensidade > GRADIENTE_MINIMO).mean()))
    return min(apoios)


def detectar_cantos(imagem: np.ndarray) -> tuple[np.ndarray, bool]:
    """Procura a folha na foto.

    Retorna os cantos normalizados (0..1) na ordem superior esquerdo, superior
    direito, inferior direito, inferior esquerdo, e se a detecção deu certo.
    Quando não encontra a folha, devolve a imagem inteira para o ajuste manual.
    """
    reduzida = _reduzir(imagem)
    altura, largura = reduzida.shape[:2]
    cinza = cv2.cvtColor(reduzida, cv2.COLOR_BGR2GRAY) if reduzida.ndim == 3 else reduzida
    suavizada = cv2.GaussianBlur(cinza, (5, 5), 0)

    # Sobel 3x3 dividido por 4: aproximadamente a diferença de brilho através da borda.
    gx = cv2.Sobel(suavizada, cv2.CV_32F, 1, 0, ksize=3) / 4
    gy = cv2.Sobel(suavizada, cv2.CV_32F, 0, 1, ksize=3) / 4

    area_minima = AREA_MINIMA_RELATIVA * largura * altura
    melhor, melhor_area = None, 0.0
    for contorno in _contornos_candidatos(suavizada):
        if cv2.contourArea(cv2.convexHull(contorno)) < area_minima:
            continue
        quad = _quadrilatero(contorno)
        if quad is None:
            continue
        area = cv2.contourArea(quad)
        if area > melhor_area and _apoio_de_borda(quad, gx, gy) >= APOIO_MINIMO:
            melhor, melhor_area = quad, area

    if melhor is None:
        return CANTOS_PADRAO.copy(), False
    normalizados = melhor / np.array([largura - 1, altura - 1], dtype=np.float32)
    return ordenar_cantos(np.clip(normalizados, 0, 1)), True
