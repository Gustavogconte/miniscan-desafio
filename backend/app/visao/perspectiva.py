"""Ordenação dos cantos e correção de perspectiva (homografia de 4 pontos)."""

import cv2
import numpy as np

LADO_MAXIMO_SAIDA = 3000  # evita páginas gigantes vindas de câmeras de alta resolução
LADO_MINIMO_SAIDA = 10
AREA_MINIMA_RELATIVA = 0.01
# Apara as bordas depois da retificação: tira a faixa fina de mesa que sobra
# nas laterais, que no filtro P&B vira uma moldura pontilhada.
MARGEM_APARO = 0.008


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
    return ordenados


def corrigir_perspectiva(imagem: np.ndarray, cantos_normalizados: np.ndarray) -> np.ndarray:
    """Recorta a folha e a deixa ortogonal, como se tivesse sido escaneada de frente."""
    altura, largura = imagem.shape[:2]
    cantos = validar_cantos_normalizados(cantos_normalizados)
    origem = cantos * np.array([largura - 1, altura - 1], dtype=np.float32)
    sup_esq, sup_dir, inf_dir, inf_esq = origem

    largura_saida = max(np.linalg.norm(inf_dir - inf_esq), np.linalg.norm(sup_dir - sup_esq))
    altura_saida = max(np.linalg.norm(sup_dir - inf_dir), np.linalg.norm(sup_esq - inf_esq))

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
    aparo_x = round(largura_saida * MARGEM_APARO)
    aparo_y = round(altura_saida * MARGEM_APARO)
    return retificada[aparo_y : altura_saida - aparo_y, aparo_x : largura_saida - aparo_x]
