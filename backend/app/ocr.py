"""Extração de texto com Tesseract em português."""

import numpy as np
import pytesseract

from app.visao.filtros import aplicar_filtro

IDIOMA_OCR = "por"
CONFIGURACAO_TESSERACT = "--oem 1 --psm 3"


class OcrIndisponivelError(RuntimeError):
    """O Tesseract ou o pacote de idioma português não está instalado no servidor."""


def ocr_disponivel() -> bool:
    try:
        return IDIOMA_OCR in pytesseract.get_languages(config="")
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, OSError):
        return False


def extrair_texto_ocr(imagem: np.ndarray) -> str:
    """Lê o texto da página sempre sobre a versão em preto e branco adaptativo.

    Tirar as sombras antes da leitura melhora bastante a taxa de acerto do Tesseract.
    """
    binaria = aplicar_filtro(imagem, "bw")
    try:
        texto = pytesseract.image_to_string(binaria, lang=IDIOMA_OCR, config=CONFIGURACAO_TESSERACT)
    except pytesseract.TesseractNotFoundError as erro:
        raise OcrIndisponivelError("O Tesseract não está instalado no servidor.") from erro
    except pytesseract.TesseractError as erro:
        raise OcrIndisponivelError(f"Falha ao executar o Tesseract: {erro}") from erro
    return texto.strip()
