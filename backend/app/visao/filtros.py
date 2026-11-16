"""Filtros de imagem: original, cinza (CLAHE), preto e branco suave e quadro branco."""

from typing import Literal, get_args

import cv2
import numpy as np

from app.visao.layout import DetectorLayout, Regiao, preservar_regioes

# Os mesmos valores aceitos pela coluna document_pages.filter_applied.
Filtro = Literal["original", "grayscale", "bw", "whiteboard"]
FILTROS: tuple[str, ...] = get_args(Filtro)

CLAHE_LIMITE = 2.0
CLAHE_GRADE = (8, 8)
BLOCO_MINIMO = 35  # vizinhança mínima (ímpar) usada para estimar o papel sem tinta
# P&B: páginas menores que isto são ampliadas antes, para as letras saírem lisas.
LADO_MINIMO_PB = 2000
# Depois de nivelar a iluminação (papel ~255), abaixo de PB_PRETO é tinta, acima de
# PB_BRANCO é papel, e no meio fica a borda suave da letra (antisserrilhado).
PB_PRETO = 150
PB_BRANCO = 215
QUADRO_REALCE_COR = 1.6  # quanto a saturação das canetas é reforçada
QUADRO_GAMA_TRACO = 1.8  # escurece os traços sem escurecer o fundo já branco
# Filtros que não passam pela detecção de figuras (não há o que preservar ou já é a foto).
SEM_PRESERVACAO = frozenset({"original", "whiteboard"})


def _para_cinza(imagem: np.ndarray) -> np.ndarray:
    if imagem.ndim == 2:
        return imagem
    return cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)


def _tamanho_bloco(imagem: np.ndarray) -> int:
    """Vizinhança no mínimo de 35 px, crescendo com a página (sempre ímpar).

    Grande o bastante para cobrir a largura do traço das letras; crescer com a página
    evita que títulos grossos fiquem ocos em fotos de alta resolução.
    """
    return max(BLOCO_MINIMO, (min(imagem.shape[:2]) // 60) | 1)


def _preto_e_branco(imagem: np.ndarray) -> np.ndarray:
    """P&B de scanner: papel branco, tinta preta e contorno das letras liso.

    Um corte seco (limiarização) em página de baixa resolução, como a de um quadro de
    vídeo do celular, deixa as letras quebradas e serrilhadas. Aqui a página pequena é
    ampliada, a iluminação é nivelada dividindo pela estimativa do papel sem tinta
    (o que apaga a sombra da mão) e uma curva íngreme leva papel a branco e tinta a
    preto, mantendo os tons intermediários só na borda das letras.
    """
    cinza = _para_cinza(imagem)
    fator = LADO_MINIMO_PB / max(cinza.shape[:2])
    if fator > 1:
        cinza = cv2.resize(cinza, None, fx=fator, fy=fator, interpolation=cv2.INTER_CUBIC)
    cinza = cv2.GaussianBlur(cinza, (3, 3), 0)
    lado = (_tamanho_bloco(cinza) // 2) | 1
    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (lado, lado))
    papel = cv2.medianBlur(cv2.dilate(cinza, nucleo), 21)  # dilatar apaga a tinta
    nivelada = cv2.divide(cinza, papel, scale=255).astype(np.float32)
    curva = (nivelada - PB_PRETO) * (255 / (PB_BRANCO - PB_PRETO))
    return np.clip(curva, 0, 255).astype(np.uint8)


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
        # Só visual (tela e PDF): o OCR lê a página retificada original, nunca esta.
        return _preto_e_branco(imagem)

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
    if not regioes:
        return filtrada, regioes
    # O P&B pode ampliar a página: as figuras são coladas na mesma escala. As regiões
    # devolvidas continuam na escala da página retificada, a mesma que o OCR lê.
    fator = filtrada.shape[1] / imagem.shape[1]
    base = imagem
    escaladas = regioes
    if fator != 1:
        base = cv2.resize(
            imagem, (filtrada.shape[1], filtrada.shape[0]), interpolation=cv2.INTER_CUBIC
        )
        escaladas = [
            Regiao(
                round(r.x0 * fator),
                round(r.y0 * fator),
                round(r.x1 * fator),
                round(r.y1 * fator),
                r.classe,
                r.confianca,
            )
            for r in regioes
        ]
    return preservar_regioes(filtrada, base, escaladas), regioes


def formato_saida(filtro: Filtro) -> tuple[str, str]:
    """Extensão e tipo MIME de cada filtro: PNG preserva o P&B sem artefatos, JPEG para fotos."""
    if filtro == "bw":
        return ".png", "image/png"
    return ".jpg", "image/jpeg"
