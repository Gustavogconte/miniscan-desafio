"""Fotos sintéticas difíceis de documento, parecidas com as de celular.

Cada cenário devolve (foto BGR, cantos verdadeiros normalizados). Servem para medir a
detecção de bordas em condições reais: mesa clara, textura de madeira, sombra,
texto denso, desfoque, compressão JPEG e folha ocupando quase a foto inteira.
"""

import cv2
import numpy as np

LARGURA, ALTURA = 1080, 1440  # foto em pé, proporção 3:4 como a câmera do celular


def _pagina(rng: np.random.Generator, largura=850, altura=1100, cor=(238, 240, 236)) -> np.ndarray:
    """Folha com cabeçalho, parágrafos densos e uma tabela, como um documento comum."""
    pagina = np.full((altura, largura, 3), cor, np.uint8)
    cv2.putText(pagina, "DECLARACAO", (70, 120), cv2.FONT_HERSHEY_DUPLEX, 2.0, (25, 25, 25), 4)
    y = 200
    while y < altura - 120:
        x = 70
        while x < largura - 90:
            palavra = int(rng.integers(30, 110))
            cv2.line(pagina, (x, y), (min(x + palavra, largura - 70), y), (45, 45, 45), 6)
            x += palavra + int(rng.integers(12, 22))
        y += 34 if rng.random() > 0.12 else 70
    return pagina


def _fundo(tipo: str, rng: np.random.Generator) -> np.ndarray:
    if tipo == "escuro":
        base = np.full((ALTURA, LARGURA, 3), (55, 55, 60), np.float32)
    elif tipo == "madeira":
        xx = np.arange(LARGURA, dtype=np.float32)[None, :]
        yy = np.arange(ALTURA, dtype=np.float32)[:, None]
        veios = 18 * np.sin(xx / 9 + 6 * np.sin(yy / 140)) + 10 * np.sin(xx / 3.1)
        base = np.dstack([90 + veios, 130 + veios, 170 + veios]).astype(np.float32)
    elif tipo == "mesa_clara":  # bege claro: pouco contraste com o papel
        base = np.full((ALTURA, LARGURA, 3), (196, 206, 214), np.float32)
    elif tipo == "tecido":
        base = np.full((ALTURA, LARGURA, 3), (120, 95, 80), np.float32)
        base += rng.normal(0, 22, base.shape).astype(np.float32)
    else:
        raise ValueError(tipo)
    base += rng.normal(0, 6, base.shape).astype(np.float32)
    return np.clip(base, 0, 255)


def _fotografar(pagina, fundo, cantos_px, sombra=0.0, desfoque=0, jpeg=80, seed=0):
    h, w = pagina.shape[:2]
    origem = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    matriz = cv2.getPerspectiveTransform(origem, np.float32(cantos_px))
    folha = cv2.warpPerspective(pagina, matriz, (LARGURA, ALTURA)).astype(np.float32)
    mascara = cv2.warpPerspective(np.ones((h, w), np.float32), matriz, (LARGURA, ALTURA))[..., None]
    mascara = cv2.GaussianBlur(mascara, (3, 3), 0)[..., None] if mascara.ndim == 2 else mascara
    foto = fundo * (1 - mascara) + folha * mascara
    if sombra:
        # Sombra da mão/celular: degradê forte sobre um lado da foto inteira.
        xx = np.linspace(0, 1, LARGURA, dtype=np.float32)[None, :, None]
        yy = np.linspace(0, 1, ALTURA, dtype=np.float32)[:, None, None]
        foto *= 1 - sombra * np.clip(1.4 * xx + 0.6 * yy - 0.7, 0, 1)
    foto += np.random.default_rng(seed).normal(0, 4, foto.shape)
    foto = np.clip(foto, 0, 255).astype(np.uint8)
    if desfoque:
        foto = cv2.GaussianBlur(foto, (desfoque, desfoque), 0)
    foto = cv2.imdecode(
        cv2.imencode(".jpg", foto, [cv2.IMWRITE_JPEG_QUALITY, jpeg])[1], cv2.IMREAD_COLOR
    )
    return foto, np.float32(cantos_px) / np.float32([LARGURA - 1, ALTURA - 1])


INCLINADA = [[170, 210], [905, 260], [960, 1250], [120, 1200]]
QUASE_RETA = [[120, 140], [960, 150], [970, 1300], [110, 1290]]
OCUPA_TUDO = [[25, 30], [1050, 45], [1060, 1410], [15, 1395]]  # folha quase encostando nas bordas
PEQUENA_AO_LONGE = [[330, 420], [760, 440], [780, 1010], [310, 990]]


def cenarios() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(7)
    pagina = _pagina(rng)
    return {
        "mesa_escura": _fotografar(pagina, _fundo("escuro", rng), INCLINADA),
        "madeira": _fotografar(pagina, _fundo("madeira", rng), INCLINADA, seed=1),
        "mesa_clara": _fotografar(pagina, _fundo("mesa_clara", rng), INCLINADA, seed=2),
        "mesa_clara_sombra": _fotografar(
            pagina, _fundo("mesa_clara", rng), QUASE_RETA, sombra=0.45, seed=3
        ),
        "madeira_sombra_desfoque": _fotografar(
            pagina, _fundo("madeira", rng), INCLINADA, sombra=0.35, desfoque=7, jpeg=60, seed=4
        ),
        "tecido": _fotografar(pagina, _fundo("tecido", rng), QUASE_RETA, seed=5),
        "ocupa_quase_tudo": _fotografar(pagina, _fundo("madeira", rng), OCUPA_TUDO, seed=6),
        "pequena_ao_longe": _fotografar(pagina, _fundo("tecido", rng), PEQUENA_AO_LONGE, seed=7),
    }


def erro_maximo(detectados: np.ndarray, verdadeiros: np.ndarray) -> float:
    """Maior distância entre um canto detectado e o verdadeiro (fração da diagonal)."""
    escala = np.float32([LARGURA, ALTURA]) / np.hypot(LARGURA, ALTURA)
    return float(np.max(np.linalg.norm((detectados - verdadeiros) * escala, axis=1)))


def _ondular(foto_sem_onda: np.ndarray, amplitude: float = 9.0) -> np.ndarray:
    """Entorta levemente a imagem (papel não perfeitamente plano): bordas deixam de ser retas."""
    yy, xx = np.mgrid[0:ALTURA, 0:LARGURA].astype(np.float32)
    mapa_x = xx + amplitude * np.sin(yy / 95)
    mapa_y = yy + amplitude * np.sin(xx / 120)
    return cv2.remap(foto_sem_onda, mapa_x, mapa_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def cenarios_dificeis() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(11)
    pagina = _pagina(rng)
    base = cenarios()

    ondulada, verdade_ondulada = _fotografar(pagina, _fundo("madeira", rng), INCLINADA, seed=8)
    ondulada = _ondular(ondulada)

    com_dedo, verdade_dedo = _fotografar(pagina, _fundo("tecido", rng), QUASE_RETA, seed=9)
    # Polegar (cor de pele) cobrindo o canto inferior esquerdo da folha.
    cv2.ellipse(com_dedo, (150, 1270), (95, 160), 35, 0, 360, (120, 150, 205), -1)
    cv2.ellipse(com_dedo, (150, 1270), (95, 160), 35, 0, 360, (95, 120, 170), 6)

    dobrada, verdade_dobrada = _fotografar(pagina, _fundo("escuro", rng), QUASE_RETA, seed=10)
    # Canto superior direito dobrado para dentro: um triângulo cinza no lugar da ponta.
    canto = np.int32([[960, 150], [880, 148], [962, 235]])
    cv2.fillPoly(dobrada, [canto], (55, 55, 60))
    cv2.fillPoly(dobrada, [np.int32([[880, 148], [962, 235], [890, 230]])], (205, 205, 200))

    return {
        **base,
        "borda_ondulada": (ondulada, verdade_ondulada),
        "dedo_no_canto": (com_dedo, verdade_dedo),
        "canto_dobrado": (dobrada, verdade_dobrada),
    }
