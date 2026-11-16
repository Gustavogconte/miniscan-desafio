"""Detecção automática dos 4 cantos da folha."""

import cv2
import numpy as np

from app.visao.perspectiva import ordenar_cantos

LADO_PROCESSAMENTO = 500  # lado maior da imagem reduzida usada só para detectar
AREA_MINIMA_RELATIVA = 0.10  # a folha precisa ocupar ao menos 10% da foto
CONTORNOS_AVALIADOS = 10
TOLERANCIA_APROXIMACAO = 0.02

CANTOS_PADRAO = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)


def _reduzir(imagem: np.ndarray) -> np.ndarray:
    altura, largura = imagem.shape[:2]
    escala = LADO_PROCESSAMENTO / max(altura, largura)
    if escala >= 1:
        return imagem
    return cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)


def detectar_cantos(imagem: np.ndarray) -> tuple[np.ndarray, bool]:
    """Procura o maior quadrilátero convexo da foto.

    Retorna os cantos normalizados (0..1) na ordem superior esquerdo, superior
    direito, inferior direito, inferior esquerdo, e se a detecção deu certo.
    Quando não encontra a folha, devolve a imagem inteira para o ajuste manual.
    """
    reduzida = _reduzir(imagem)
    altura, largura = reduzida.shape[:2]

    cinza = cv2.cvtColor(reduzida, cv2.COLOR_BGR2GRAY)
    suavizada = cv2.GaussianBlur(cinza, (5, 5), 0)
    bordas = cv2.Canny(suavizada, 50, 150)
    # O fechamento morfológico une bordas quebradas quando a folha está sobre fundo claro.
    nucleo = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    bordas = cv2.morphologyEx(bordas, cv2.MORPH_CLOSE, nucleo, iterations=2)

    contornos, _ = cv2.findContours(bordas, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area_minima = AREA_MINIMA_RELATIVA * largura * altura

    for contorno in sorted(contornos, key=cv2.contourArea, reverse=True)[:CONTORNOS_AVALIADOS]:
        if cv2.contourArea(contorno) < area_minima:
            break
        perimetro = cv2.arcLength(contorno, True)
        aproximado = cv2.approxPolyDP(contorno, TOLERANCIA_APROXIMACAO * perimetro, True)
        if len(aproximado) == 4 and cv2.isContourConvex(aproximado):
            pontos = aproximado.reshape(4, 2).astype(np.float32)
            normalizados = pontos / np.array([largura - 1, altura - 1], dtype=np.float32)
            return ordenar_cantos(np.clip(normalizados, 0, 1)), True

    return CANTOS_PADRAO.copy(), False
