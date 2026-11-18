"""Leitura e escrita de imagens a partir de bytes."""

import io
import warnings

import cv2
import numpy as np
from PIL import Image

# A página já chega em JPEG do celular: regravar com 90 somava uma segunda perda visível
# nas letras pequenas. Com 95, a página cresce cerca de 45% (perto de 1 MB numa folha
# A4 de 3000 px) e a perda some.
QUALIDADE_JPEG = 95
# Teto de pixels de uma imagem enviada. Cobre a foto de 48 MP dos celulares mais
# recentes; acima disso, um PNG de poucos KB (10000x10000 px de uma cor só) ocuparia
# centenas de MB na memória ao ser decodificado.
MAXIMO_PIXELS = 50_000_000
# Menor lado aceito, em pixels: abaixo disso não há documento para ler, e a redução
# da imagem para a análise chegaria a um lado de zero pixels.
LADO_MINIMO = 16


class ImagemInvalidaError(ValueError):
    """O arquivo enviado não é uma imagem que o OpenCV consiga ler."""


class ImagemGrandeDemaisError(ImagemInvalidaError):
    """A imagem descreve mais pixels do que a API aceita decodificar."""


def conferir_dimensoes(dados: bytes) -> None:
    """Recusa a imagem pelo cabeçalho, antes de decodificar os pixels.

    O Pillow lê só o cabeçalho para saber largura e altura. Formatos que ele não
    reconhece seguem para o OpenCV, que também tem um teto (`app/__init__.py`).
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(dados)) as imagem:
                largura, altura = imagem.size
    except Image.DecompressionBombError as erro:
        raise ImagemGrandeDemaisError(_mensagem_grande_demais()) from erro
    except Exception:
        return
    if largura * altura > MAXIMO_PIXELS:
        raise ImagemGrandeDemaisError(_mensagem_grande_demais())


def _mensagem_grande_demais() -> str:
    return f"A imagem tem pixels demais. O limite é {MAXIMO_PIXELS // 1_000_000} megapixels."


def decodificar(dados: bytes, modo: int, mensagem_invalida: str) -> np.ndarray:
    """Decodifica com o teto de pixels; qualquer falha do OpenCV vira ImagemInvalidaError."""
    if not dados:
        raise ImagemInvalidaError("O arquivo enviado está vazio.")
    conferir_dimensoes(dados)
    try:
        imagem = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8), modo)
    except cv2.error as erro:
        raise ImagemInvalidaError(mensagem_invalida) from erro
    if imagem is None:
        raise ImagemInvalidaError(mensagem_invalida)
    return imagem


def decodificar_imagem(dados: bytes) -> np.ndarray:
    """Converte bytes (JPEG, PNG, WebP...) em uma matriz BGR.

    O `IMREAD_COLOR` já aplica a orientação EXIF, o que corrige fotos tiradas
    com o celular na vertical.
    """
    imagem = decodificar(dados, cv2.IMREAD_COLOR, "Não foi possível ler a imagem enviada.")
    if min(imagem.shape[:2]) < LADO_MINIMO:
        raise ImagemInvalidaError(
            f"A imagem é pequena demais: o menor lado precisa ter pelo menos {LADO_MINIMO} pixels."
        )
    return imagem


def codificar_imagem(imagem: np.ndarray, formato: str = ".jpg") -> bytes:
    """Converte uma matriz em bytes no formato pedido (`.jpg` ou `.png`)."""
    parametros = [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE_JPEG] if formato == ".jpg" else []
    sucesso, buffer = cv2.imencode(formato, imagem, parametros)
    if not sucesso:
        raise RuntimeError(f"Falha ao codificar a imagem em {formato}.")
    return buffer.tobytes()
