"""Filtros de imagem: original, escala de cinza (CLAHE) e preto e branco adaptativo."""

from typing import Literal, get_args

import cv2
import numpy as np

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


def aplicar_filtro(imagem: np.ndarray, filtro: Filtro) -> np.ndarray:
    """Aplica um dos filtros do MiniScan sobre a página já retificada."""
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


def formato_saida(filtro: Filtro) -> tuple[str, str]:
    """Extensão e tipo MIME de cada filtro: PNG preserva o P&B sem artefatos, JPEG para fotos."""
    if filtro == "bw":
        return ".png", "image/png"
    return ".jpg", "image/jpeg"
