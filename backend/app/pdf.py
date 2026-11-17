"""Montagem do PDF único a partir das páginas processadas."""

import re

import cv2
import img2pdf
import numpy as np

from app.visao.imagem import codificar_imagem, decodificar

ASSINATURA_JPEG = b"\xff\xd8\xff"
ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"

TAMANHO_A4 = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
LAYOUT_A4 = img2pdf.get_layout_fun(TAMANHO_A4, fit=img2pdf.FitMode.into, auto_orient=True)

# O carimbo é desenhado com as fontes Hershey do OpenCV, que só têm ASCII: aceita
# apenas o que uma data/hora precisa (dígitos, barras, dois-pontos, hífen e espaço).
CARIMBO_PERMITIDO = re.compile(r"^[0-9/:. \-hH]{1,40}$")


class CarimboInvalidoError(ValueError):
    """O texto do carimbo tem caracteres que não podem ser desenhados."""


def validar_carimbo(carimbo: str | None) -> str | None:
    if carimbo is None or not carimbo.strip():
        return None
    carimbo = carimbo.strip()
    if not CARIMBO_PERMITIDO.match(carimbo):
        raise CarimboInvalidoError("O carimbo aceita só data e hora, como 16/11/2026 14:32.")
    return carimbo


def carimbar(imagem: np.ndarray, carimbo: str) -> np.ndarray:
    """Escreve data e hora no canto inferior direito, sobre uma faixa branca legível."""
    resultado = imagem.copy()
    altura, largura = resultado.shape[:2]
    escala = max(0.5, largura / 2000)
    espessura = max(1, round(escala * 2))
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), base = cv2.getTextSize(carimbo, fonte, escala, espessura)
    margem = round(18 * escala)
    x = largura - tw - 2 * margem
    y = altura - 2 * margem
    branco = 255 if resultado.ndim == 2 else (255, 255, 255)
    cinza = 60 if resultado.ndim == 2 else (60, 60, 60)
    cv2.rectangle(
        resultado,
        (x - margem // 2, y - th - margem // 2),
        (x + tw + margem // 2, y + base + margem // 2),
        branco,
        -1,
    )
    cv2.putText(resultado, carimbo, (x, y), fonte, escala, cinza, espessura, cv2.LINE_AA)
    return resultado


def _normalizar_pagina(dados: bytes, numero: int, carimbo: str | None) -> bytes:
    """Garante que a página seja JPEG ou PNG sem transparência, formatos que o img2pdf embute.

    JPEG e PNG válidos passam direto, sem recompressão. Outros formatos (WebP) e
    PNG com canal alfa são convertidos para JPEG. Com carimbo, a página é redesenhada
    mantendo o formato (PNG continua PNG, para o P&B não ganhar artefatos).
    """
    imagem = decodificar(dados, cv2.IMREAD_UNCHANGED, f"A página {numero} não é uma imagem válida.")

    tem_alfa = imagem.ndim == 3 and imagem.shape[2] == 4
    if tem_alfa:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_BGRA2BGR)
    if carimbo:
        formato = ".png" if dados.startswith(ASSINATURA_PNG) else ".jpg"
        return codificar_imagem(carimbar(imagem, carimbo), formato)
    if dados.startswith((ASSINATURA_JPEG, ASSINATURA_PNG)) and not tem_alfa:
        return dados
    return codificar_imagem(imagem, ".jpg")


def gerar_pdf(paginas: list[bytes], carimbo: str | None = None) -> bytes:
    """Junta as páginas, na ordem recebida, em um PDF A4 com uma imagem por folha."""
    if not paginas:
        raise ValueError("Envie ao menos uma página para gerar o PDF.")
    carimbo = validar_carimbo(carimbo)
    normalizadas = [
        _normalizar_pagina(dados, numero, carimbo) for numero, dados in enumerate(paginas, 1)
    ]
    return img2pdf.convert(normalizadas, layout_fun=LAYOUT_A4)
