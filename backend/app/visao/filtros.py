"""Filtros de imagem: original, cinza (CLAHE), preto e branco adaptativo e quadro branco."""

from typing import Literal, get_args

import cv2
import numpy as np

from app.visao.layout import DetectorLayout, Regiao, preservar_regioes

# Os mesmos valores aceitos pela coluna document_pages.filter_applied.
Filtro = Literal["original", "grayscale", "bw", "whiteboard"]
FILTROS: tuple[str, ...] = get_args(Filtro)

CLAHE_LIMITE = 2.0
CLAHE_GRADE = (8, 8)
LIMIAR_CONSTANTE = 15  # quanto o pixel precisa ser mais escuro que a vizinhança para virar tinta
BLOCO_MINIMO = 35  # vizinhança mínima da limiarização (ímpar)
QUADRO_REALCE_COR = 1.6  # quanto a saturação das canetas é reforçada
QUADRO_GAMA_TRACO = 1.8  # escurece os traços sem escurecer o fundo já branco
# Filtros que não passam pela detecção de figuras (não há o que preservar ou já é a foto).
SEM_PRESERVACAO = frozenset({"original", "whiteboard"})


def _para_cinza(imagem: np.ndarray) -> np.ndarray:
    if imagem.ndim == 2:
        return imagem
    return cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)


def _tamanho_bloco(imagem: np.ndarray) -> int:
    """Vizinhança da limiarização: no mínimo 35 px, crescendo com a página (sempre ímpar).

    Um bloco grande o bastante limpa o papel sem engrossar as letras; crescer com a
    página evita que títulos grossos fiquem ocos em fotos de alta resolução.
    """
    return max(BLOCO_MINIMO, (min(imagem.shape[:2]) // 60) | 1)


def _quadro_branco(imagem: np.ndarray) -> np.ndarray:
    """Realça quadro branco: tira reflexo e sombra do fundo e reforça a cor das canetas.

    O fundo é estimado com uma dilatação (que apaga os traços finos) seguida de
    mediana. Dividir a foto por esse fundo deixa o quadro uniformemente branco,
    mesmo com o reflexo da lâmpada; depois a saturação e o contraste dos traços sobem.
    """
    if imagem.ndim == 2:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
    lado = max(15, (min(imagem.shape[:2]) // 25) | 1)
    nucleo = cv2.getStructuringElement(cv2.MORPH_RECT, (lado, lado))
    fundo = cv2.medianBlur(cv2.dilate(imagem, nucleo), 21)
    uniforme = cv2.divide(imagem, fundo, scale=255)

    hsv = cv2.cvtColor(uniforme, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * QUADRO_REALCE_COR, 0, 255)
    hsv[:, :, 2] = 255 * (hsv[:, :, 2] / 255) ** QUADRO_GAMA_TRACO
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def _filtrar(imagem: np.ndarray, filtro: Filtro) -> np.ndarray:
    if filtro == "original":
        return imagem

    if filtro == "whiteboard":
        return _quadro_branco(imagem)

    cinza = _para_cinza(imagem)

    if filtro == "grayscale":
        clahe = cv2.createCLAHE(clipLimit=CLAHE_LIMITE, tileGridSize=CLAHE_GRADE)
        return clahe.apply(cinza)

    if filtro == "bw":
        # A limiarização por blocos compara cada pixel com a sua vizinhança, por isso
        # apaga sombras da mão ou do celular. A suavização leve antes evita letras
        # serrilhadas e pontinhos de ruído no papel. Este filtro é só visual (tela e
        # PDF): o OCR lê a página retificada original, nunca a binarizada.
        suave = cv2.GaussianBlur(cinza, (3, 3), 0)
        return cv2.adaptiveThreshold(
            suave,
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
    if filtro in SEM_PRESERVACAO or not preservar_graficos or imagem.ndim != 3:
        return filtrada, None
    regioes = DetectorLayout.obter().detectar(imagem)
    return preservar_regioes(filtrada, imagem, regioes), regioes


def formato_saida(filtro: Filtro) -> tuple[str, str]:
    """Extensão e tipo MIME de cada filtro: PNG preserva o P&B sem artefatos, JPEG para fotos."""
    if filtro == "bw":
        return ".png", "image/png"
    return ".jpg", "image/jpeg"
