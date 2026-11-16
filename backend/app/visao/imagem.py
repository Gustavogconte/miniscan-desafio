"""Leitura e escrita de imagens a partir de bytes."""

import cv2
import numpy as np

QUALIDADE_JPEG = 90


class ImagemInvalidaError(ValueError):
    """O arquivo enviado não é uma imagem que o OpenCV consiga ler."""


def decodificar_imagem(dados: bytes) -> np.ndarray:
    """Converte bytes (JPEG, PNG, WebP...) em uma matriz BGR.

    O `IMREAD_COLOR` já aplica a orientação EXIF, o que corrige fotos tiradas
    com o celular na vertical.
    """
    if not dados:
        raise ImagemInvalidaError("O arquivo enviado está vazio.")
    imagem = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise ImagemInvalidaError("Não foi possível ler a imagem enviada.")
    return imagem


def codificar_imagem(imagem: np.ndarray, formato: str = ".jpg") -> bytes:
    """Converte uma matriz em bytes no formato pedido (`.jpg` ou `.png`)."""
    parametros = [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE_JPEG] if formato == ".jpg" else []
    sucesso, buffer = cv2.imencode(formato, imagem, parametros)
    if not sucesso:
        raise RuntimeError(f"Falha ao codificar a imagem em {formato}.")
    return buffer.tobytes()
