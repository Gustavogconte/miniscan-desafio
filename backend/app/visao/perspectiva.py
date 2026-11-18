"""Ordenação dos cantos e correção de perspectiva (homografia de 4 pontos)."""

import cv2
import numpy as np

LADO_MAXIMO_SAIDA = 3000  # evita páginas gigantes vindas de câmeras de alta resolução
LADO_MINIMO_SAIDA = 10
AREA_MINIMA_RELATIVA = 0.01
# Apara as bordas depois da retificação: tira a faixa fina de mesa que sobra
# nas laterais, que no filtro P&B vira uma moldura pontilhada.
MARGEM_APARO = 0.008
# Ângulo interno máximo de um canto: acima disso, três cantos estão quase alinhados.
ANGULO_MAXIMO = 170
# Distância focal da câmera principal do celular (~26 mm equivalentes), em fração do
# lado maior da foto. Usada para achar a proporção real da folha fotografada inclinada.
FOCO_RELATIVO = 0.75
# Se a proporção pela câmera divergir mais que isto da medida pelos lados, a foto não
# segue o modelo e vale a medida pelos lados. Medido em fotos sintéticas: a 30° de
# inclinação a divergência já é de 31%, a 40° de 52%; e mesmo com lente diferente,
# zoom de 2x ou foto recortada, a câmera erra menos que os lados.
DIVERGENCIA_MAXIMA_PROPORCAO = 0.6
CANTOS_IMAGEM_INTEIRA = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)


class CantosInvalidosError(ValueError):
    """Os cantos enviados não formam um quadrilátero utilizável."""


def ordenar_cantos(pontos: np.ndarray) -> np.ndarray:
    """Ordena 4 pontos: superior esquerdo, superior direito, inferior direito, inferior esquerdo.

    Ordena pelo ângulo em relação ao centro (sentido horário na tela, onde o eixo y
    cresce para baixo) e começa pelo ponto com menor x + y. Funciona mesmo com a
    folha bem girada, caso em que o método clássico de soma/diferença repete pontos.
    """
    pontos = np.asarray(pontos, dtype=np.float32).reshape(4, 2)
    centro = pontos.mean(axis=0)
    angulos = np.arctan2(pontos[:, 1] - centro[1], pontos[:, 0] - centro[0])
    horario = pontos[np.argsort(angulos)]
    inicio = int(np.argmin(horario.sum(axis=1)))
    return np.roll(horario, -inicio, axis=0)


def validar_cantos_normalizados(cantos: np.ndarray) -> np.ndarray:
    """Confere formato (4x2), intervalo 0..1 e área mínima do quadrilátero."""
    cantos = np.asarray(cantos, dtype=np.float32)
    if cantos.shape != (4, 2):
        raise CantosInvalidosError("Envie exatamente 4 cantos com coordenadas x e y.")
    if np.any(cantos < 0) or np.any(cantos > 1):
        raise CantosInvalidosError("As coordenadas dos cantos devem estar entre 0 e 1.")
    ordenados = ordenar_cantos(cantos)
    if cv2.contourArea(ordenados) < AREA_MINIMA_RELATIVA:
        raise CantosInvalidosError("Os cantos formam uma área pequena demais para recortar.")
    if not _quadrilatero_valido(ordenados):
        raise CantosInvalidosError(
            "Os cantos não formam um quadrilátero: afaste os pontos que estão alinhados."
        )
    return ordenados


def _quadrilatero_valido(cantos: np.ndarray) -> bool:
    """Convexo e sem ângulo quase raso (três cantos quase alinhados viram um triângulo)."""
    if not cv2.isContourConvex(cantos.reshape(-1, 1, 2)):
        return False
    for i in range(4):
        anterior = cantos[i - 1] - cantos[i]
        seguinte = cantos[(i + 1) % 4] - cantos[i]
        cosseno = float(np.dot(anterior, seguinte)) / (
            float(np.linalg.norm(anterior) * np.linalg.norm(seguinte)) + 1e-9
        )
        if cosseno < np.cos(np.radians(ANGULO_MAXIMO)):
            return False
    return True


def proporcao_pela_camera(origem: np.ndarray, largura: int, altura: int) -> float | None:
    """Altura/largura real da folha, a partir dos 4 cantos na foto (em pixels).

    Medir os lados na foto engana quando ela é tirada inclinada: os lados mais longe da
    câmera encolhem, e a página sairia achatada (cerca de 7% a 10° e 16% a 20°). Com o
    modelo da câmera (distância focal e centro da foto), a homografia dá a proporção
    real do retângulo (Zhang e He, "Whiteboard scanning and image enhancement", 2007).
    Devolve None se a geometria for degenerada.
    """
    sup_esq, sup_dir, inf_dir, inf_esq = (np.array([x, y, 1.0]) for x, y in origem)
    base_2 = np.dot(np.cross(sup_dir, inf_dir), inf_esq)
    base_3 = np.dot(np.cross(inf_esq, inf_dir), sup_dir)
    if abs(base_2) < 1e-9 or abs(base_3) < 1e-9:
        return None
    k2 = np.dot(np.cross(sup_esq, inf_dir), inf_esq) / base_2
    k3 = np.dot(np.cross(sup_esq, inf_dir), sup_dir) / base_3
    lado_horizontal = k2 * sup_dir - sup_esq
    lado_vertical = k3 * inf_esq - sup_esq
    foco = FOCO_RELATIVO * max(largura, altura)
    camera = np.array([[foco, 0, largura / 2], [0, foco, altura / 2], [0, 0, 1.0]])
    inversa = np.linalg.inv(camera)
    metrica = inversa.T @ inversa
    vertical = lado_vertical @ metrica @ lado_vertical
    horizontal = lado_horizontal @ metrica @ lado_horizontal
    if not (vertical > 0 and horizontal > 0):
        return None
    proporcao = float(np.sqrt(vertical / horizontal))
    return proporcao if np.isfinite(proporcao) else None


def corrigir_perspectiva(imagem: np.ndarray, cantos_normalizados: np.ndarray) -> np.ndarray:
    """Recorta a folha e a deixa ortogonal, como se tivesse sido escaneada de frente."""
    altura, largura = imagem.shape[:2]
    cantos = validar_cantos_normalizados(cantos_normalizados)
    origem = cantos * np.array([largura - 1, altura - 1], dtype=np.float32)
    sup_esq, sup_dir, inf_dir, inf_esq = origem

    largura_saida = max(np.linalg.norm(inf_dir - inf_esq), np.linalg.norm(sup_dir - sup_esq))
    altura_saida = max(np.linalg.norm(sup_dir - inf_dir), np.linalg.norm(sup_esq - inf_esq))
    # Corrige a proporção pela câmera, aumentando o lado encurtado (nunca reduzindo,
    # para não perder resolução).
    proporcao = proporcao_pela_camera(origem, largura, altura)
    medida = altura_saida / largura_saida
    if proporcao is not None and abs(proporcao / medida - 1) <= DIVERGENCIA_MAXIMA_PROPORCAO:
        if proporcao > medida:
            altura_saida = largura_saida * proporcao
        else:
            largura_saida = altura_saida / proporcao

    reducao = min(1.0, LADO_MAXIMO_SAIDA / max(largura_saida, altura_saida))
    largura_saida = int(round(largura_saida * reducao))
    altura_saida = int(round(altura_saida * reducao))
    if min(largura_saida, altura_saida) < LADO_MINIMO_SAIDA:
        raise CantosInvalidosError("O recorte resultante é pequeno demais.")

    destino = np.array(
        [
            [0, 0],
            [largura_saida - 1, 0],
            [largura_saida - 1, altura_saida - 1],
            [0, altura_saida - 1],
        ],
        dtype=np.float32,
    )
    matriz = cv2.getPerspectiveTransform(origem, destino)
    retificada = cv2.warpPerspective(
        imagem,
        matriz,
        (largura_saida, altura_saida),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    # Com os cantos na imagem inteira ("Foto inteira" ou a folha A4 do Cartão ID) não
    # há mesa na borda: aparar só encolheria a página (o cartão sairia 1,6% maior).
    if np.allclose(cantos, CANTOS_IMAGEM_INTEIRA, atol=1e-4):
        return retificada
    aparo_x = round(largura_saida * MARGEM_APARO)
    aparo_y = round(altura_saida * MARGEM_APARO)
    return retificada[aparo_y : altura_saida - aparo_y, aparo_x : largura_saida - aparo_x]
