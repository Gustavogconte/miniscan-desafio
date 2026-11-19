"""Modo RG ou CNH: monta frente e verso de um documento numa folha A4, ampliados."""

from dataclasses import dataclass
from typing import Literal, get_args

import cv2
import numpy as np

DPI = 300
MM_POR_POLEGADA = 25.4
A4_MM = (210.0, 297.0)
COR_FOLHA = (255, 255, 255)
COR_CONTORNO = (200, 200, 200)
# O dobro do tamanho real: em tamanho real (8,6 cm numa folha de 21 cm) o documento
# ficava pequeno na tela do celular e quase metade da folha sobrava em branco.
AMPLIACAO_MAXIMA = 2.0
MARGEM_MM = 15.0
ESPACO_ENTRE_LADOS_MM = 12.0

FormatoCartao = Literal["id", "passaporte"]
FORMATOS_CARTAO: tuple[str, ...] = get_args(FormatoCartao)


@dataclass(frozen=True)
class Formato:
    largura_mm: float
    altura_mm: float
    lados: int
    # Raio dos cantos arredondados do documento de verdade.
    raio_mm: float


# ID-1 (ISO/IEC 7810): RG novo, CNH, cartões bancários. Passaporte: página de dados (TD3).
FORMATOS = {
    "id": Formato(85.6, 54.0, 2, 3.18),
    "passaporte": Formato(125.0, 88.0, 1, 3.18),
}


class CartaoInvalidoError(ValueError):
    """Faltou um lado do cartão ou o formato não existe."""


def _px(mm: float) -> int:
    return round(mm / MM_POR_POLEGADA * DPI)


def _ajustar(imagem: np.ndarray, largura: int, altura: int) -> np.ndarray:
    """Gira para a orientação do cartão (deitado) e redimensiona para o tamanho na folha."""
    if imagem.ndim == 2:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
    if imagem.shape[0] > imagem.shape[1]:
        imagem = cv2.rotate(imagem, cv2.ROTATE_90_COUNTERCLOCKWISE)
    reduzindo = imagem.shape[1] >= largura
    interpolacao = cv2.INTER_AREA if reduzindo else cv2.INTER_CUBIC
    return cv2.resize(imagem, (largura, altura), interpolation=interpolacao)


def _mascara_arredondada(largura: int, altura: int, raio: int) -> np.ndarray:
    """Máscara (255 dentro) de um retângulo com os cantos arredondados."""
    mascara = np.zeros((altura, largura), np.uint8)
    cv2.rectangle(mascara, (raio, 0), (largura - 1 - raio, altura - 1), 255, -1)
    cv2.rectangle(mascara, (0, raio), (largura - 1, altura - 1 - raio), 255, -1)
    for cx, cy in [
        (raio, raio),
        (largura - 1 - raio, raio),
        (largura - 1 - raio, altura - 1 - raio),
        (raio, altura - 1 - raio),
    ]:
        cv2.circle(mascara, (cx, cy), raio, 255, -1, cv2.LINE_AA)
    return mascara


def _contorno_arredondado(folha: np.ndarray, x: int, y: int, largura: int, altura: int, raio: int):
    """Linha fina e clara em volta do documento, seguindo os cantos arredondados."""
    direita, baixo = x + largura - 1, y + altura - 1
    linhas = [
        ((x + raio, y), (direita - raio, y)),
        ((x + raio, baixo), (direita - raio, baixo)),
        ((x, y + raio), (x, baixo - raio)),
        ((direita, y + raio), (direita, baixo - raio)),
    ]
    for inicio, fim in linhas:
        cv2.line(folha, inicio, fim, COR_CONTORNO, 3, cv2.LINE_AA)
    arcos = [
        ((x + raio, y + raio), 180),
        ((direita - raio, y + raio), 270),
        ((direita - raio, baixo - raio), 0),
        ((x + raio, baixo - raio), 90),
    ]
    for centro, inicio in arcos:
        cv2.ellipse(
            folha, centro, (raio, raio), 0, inicio, inicio + 90, COR_CONTORNO, 3, cv2.LINE_AA
        )


def compor_cartao(lados: list[np.ndarray], formato: FormatoCartao) -> np.ndarray:
    """Folha A4 (300 dpi) com os lados do documento ampliados, um embaixo do outro.

    A ampliação é a maior que cabe na folha, com margens, até o dobro do tamanho real.
    Os cantos de cada lado são arredondados como no documento: as pontas da foto
    retificada, que mostravam a mesa, ficam brancas.
    """
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

    quantidade = len(lados)
    largura_util = A4_MM[0] - 2 * MARGEM_MM
    altura_util = A4_MM[1] - 2 * MARGEM_MM - (quantidade - 1) * ESPACO_ENTRE_LADOS_MM
    ampliacao = min(
        AMPLIACAO_MAXIMA,
        largura_util / especificacao.largura_mm,
        altura_util / (quantidade * especificacao.altura_mm),
    )

    folha_l, folha_a = _px(A4_MM[0]), _px(A4_MM[1])
    folha = np.full((folha_a, folha_l, 3), COR_FOLHA, dtype=np.uint8)
    cartao_l = _px(especificacao.largura_mm * ampliacao)
    cartao_a = _px(especificacao.altura_mm * ampliacao)
    raio = _px(especificacao.raio_mm * ampliacao)
    espaco = _px(ESPACO_ENTRE_LADOS_MM)
    altura_total = quantidade * cartao_a + (quantidade - 1) * espaco
    y = (folha_a - altura_total) // 3  # um pouco acima do centro
    x = (folha_l - cartao_l) // 2
    mascara = _mascara_arredondada(cartao_l, cartao_a, raio)[:, :, None] / 255.0

    for lado in lados:
        ajustado = _ajustar(lado, cartao_l, cartao_a).astype(np.float32)
        area = folha[y : y + cartao_a, x : x + cartao_l].astype(np.float32)
        folha[y : y + cartao_a, x : x + cartao_l] = np.round(
            ajustado * mascara + area * (1 - mascara)
        ).astype(np.uint8)
        # 2 px para dentro: com o anti-aliasing, a linha não passa da borda do documento.
        _contorno_arredondado(folha, x + 2, y + 2, cartao_l - 4, cartao_a - 4, raio - 2)
        y += cartao_a + espaco
    return folha
