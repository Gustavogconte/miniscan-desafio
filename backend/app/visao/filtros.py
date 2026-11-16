"""Filtros de imagem: original, escala de cinza (CLAHE) e preto e branco adaptativo."""

from typing import Literal, get_args

import cv2
import numpy as np

from app.visao.layout import DetectorLayout, Regiao, preservar_regioes

# Os mesmos valores aceitos pela coluna document_pages.filter_applied.
Filtro = Literal["original", "grayscale", "bw"]
FILTROS: tuple[str, ...] = get_args(Filtro)

CLAHE_LIMITE = 2.0
CLAHE_GRADE = (8, 8)
LIMIAR_CONSTANTE = 12  # quanto o pixel precisa ser mais escuro que a vizinhança para virar tinta


def _para_cinza(imagem: np.ndarray) -> np.ndarray:
    if imagem.ndim == 2:
        return imagem
    return cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)


def _tamanho_bloco(imagem: np.ndarray) -> int:
    """Vizinhança da limiarização proporcional à página (sempre ímpar, mínimo 11)."""
    lado = min(imagem.shape[:2]) // 30
    return max(11, lado | 1)


def _filtrar(imagem: np.ndarray, filtro: Filtro) -> np.ndarray:
    if filtro == "original":
        return imagem

    cinza = _para_cinza(imagem)

    if filtro == "grayscale":
        clahe = cv2.createCLAHE(clipLimit=CLAHE_LIMITE, tileGridSize=CLAHE_GRADE)
        return clahe.apply(cinza)

    if filtro == "bw":
        # A limiarização por blocos compara cada pixel com a sua vizinhança,
        # por isso apaga sombras da mão ou do celular sobre o papel.
        return cv2.adaptiveThreshold(
            cinza,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            _tamanho_bloco(cinza),
            LIMIAR_CONSTANTE,
        )

    raise ValueError(f"Filtro desconhecido: {filtro!r}. Use um de {FILTROS}.")


def aplicar_filtro(
    imagem: np.ndarray, filtro: Filtro, preservar_graficos: bool = True
) -> np.ndarray:
    """Aplica um dos filtros do MiniScan sobre a página já retificada.

    Com `preservar_graficos`, fotos, figuras e assinaturas detectadas pelo modelo de
    layout continuam com a imagem original sobre o fundo filtrado. Sem o modelo
    instalado, o filtro é aplicado na página inteira.
    """
    return aplicar_filtro_com_regioes(imagem, filtro, preservar_graficos)[0]


def aplicar_filtro_com_regioes(
    imagem: np.ndarray, filtro: Filtro, preservar_graficos: bool = True
) -> tuple[np.ndarray, list[Regiao] | None]:
    """Como `aplicar_filtro`, mas devolve também as regiões gráficas usadas.

    As regiões voltam como None quando a detecção não foi feita (filtro original
    ou preservação desligada), para quem chama saber que ainda precisa detectar.
    """
    filtrada = _filtrar(imagem, filtro)
    if filtro == "original" or not preservar_graficos or imagem.ndim != 3:
        return filtrada, None
    regioes = DetectorLayout.obter().detectar(imagem)
    return preservar_regioes(filtrada, imagem, regioes), regioes


def formato_saida(filtro: Filtro) -> tuple[str, str]:
    """Extensão e tipo MIME de cada filtro: PNG preserva o P&B sem artefatos, JPEG para fotos."""
    if filtro == "bw":
        return ".png", "image/png"
    return ".jpg", "image/jpeg"
