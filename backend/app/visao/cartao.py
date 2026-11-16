"""Modo cartão: monta frente e verso de um documento numa folha A4, em tamanho real."""

from dataclasses import dataclass
from typing import Literal, get_args

import cv2
import numpy as np

DPI = 300
MM_POR_POLEGADA = 25.4
A4_MM = (210.0, 297.0)
COR_FOLHA = (255, 255, 255)
COR_CONTORNO = (210, 210, 210)

FormatoCartao = Literal["id", "passaporte"]
FORMATOS_CARTAO: tuple[str, ...] = get_args(FormatoCartao)


@dataclass(frozen=True)
class Formato:
    largura_mm: float
    altura_mm: float
    lados: int


# ID-1 (ISO/IEC 7810): RG novo, CNH, cartões bancários. Passaporte: página de dados (TD3).
FORMATOS = {
    "id": Formato(85.6, 54.0, 2),
    "passaporte": Formato(125.0, 88.0, 1),
}


class CartaoInvalidoError(ValueError):
    """Faltou um lado do cartão ou o formato não existe."""


def _px(mm: float) -> int:
    return round(mm / MM_POR_POLEGADA * DPI)


def _ajustar(imagem: np.ndarray, largura: int, altura: int) -> np.ndarray:
    """Gira para a orientação do cartão (deitado) e redimensiona para o tamanho real."""
    if imagem.ndim == 2:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
    if imagem.shape[0] > imagem.shape[1]:
        imagem = cv2.rotate(imagem, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return cv2.resize(imagem, (largura, altura), interpolation=cv2.INTER_AREA)


def compor_cartao(lados: list[np.ndarray], formato: FormatoCartao) -> np.ndarray:
    """Folha A4 (300 dpi) com os lados do cartão centralizados, um embaixo do outro."""
    if formato not in FORMATOS:
        raise CartaoInvalidoError(
            f"Formato desconhecido: {formato!r}. Use um de {FORMATOS_CARTAO}."
        )
    especificacao = FORMATOS[formato]
    if not 1 <= len(lados) <= especificacao.lados:
        raise CartaoInvalidoError(
            f"O formato {formato!r} aceita de 1 a {especificacao.lados} lado(s); "
            f"foram enviados {len(lados)}."
        )

    folha_l, folha_a = _px(A4_MM[0]), _px(A4_MM[1])
    folha = np.full((folha_a, folha_l, 3), COR_FOLHA, dtype=np.uint8)
    cartao_l, cartao_a = _px(especificacao.largura_mm), _px(especificacao.altura_mm)
    espaco = _px(20)
    altura_total = len(lados) * cartao_a + (len(lados) - 1) * espaco
    y = (folha_a - altura_total) // 3  # um pouco acima do centro, como numa cópia autenticada
    x = (folha_l - cartao_l) // 2

    for lado in lados:
        folha[y : y + cartao_a, x : x + cartao_l] = _ajustar(lado, cartao_l, cartao_a)
        cv2.rectangle(folha, (x - 1, y - 1), (x + cartao_l, y + cartao_a), COR_CONTORNO, 2)
        y += cartao_a + espaco
    return folha
