"""Montagem do PDF único a partir das páginas processadas."""

import cv2
import img2pdf
import numpy as np

from app.visao.imagem import ImagemInvalidaError, codificar_imagem

ASSINATURA_JPEG = b"\xff\xd8\xff"
ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"

TAMANHO_A4 = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
LAYOUT_A4 = img2pdf.get_layout_fun(TAMANHO_A4, fit=img2pdf.FitMode.into, auto_orient=True)


def _normalizar_pagina(dados: bytes, numero: int) -> bytes:
    """Garante que a página seja JPEG ou PNG sem transparência, formatos que o img2pdf embute.

    JPEG e PNG válidos passam direto, sem recompressão. Outros formatos (WebP) e
    PNG com canal alfa são convertidos para JPEG.
    """
    imagem = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if imagem is None:
        raise ImagemInvalidaError(f"A página {numero} não é uma imagem válida.")

    tem_alfa = imagem.ndim == 3 and imagem.shape[2] == 4
    if dados.startswith((ASSINATURA_JPEG, ASSINATURA_PNG)) and not tem_alfa:
        return dados
    if tem_alfa:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_BGRA2BGR)
    return codificar_imagem(imagem, ".jpg")


def gerar_pdf(paginas: list[bytes]) -> bytes:
    """Junta as páginas, na ordem recebida, em um PDF A4 com uma imagem por folha."""
    if not paginas:
        raise ValueError("Envie ao menos uma página para gerar o PDF.")
    normalizadas = [_normalizar_pagina(dados, numero) for numero, dados in enumerate(paginas, 1)]
    return img2pdf.convert(normalizadas, layout_fun=LAYOUT_A4)
