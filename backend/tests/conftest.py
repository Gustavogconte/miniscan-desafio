"""Fotos sintéticas de documento para os testes, sem depender de arquivos externos."""

import cv2
import numpy as np
import pytest

LARGURA_FOTO = 900
ALTURA_FOTO = 1200

# Folha inclinada dentro da foto (pixels), na ordem sup. esq., sup. dir., inf. dir., inf. esq.
CANTOS_FOLHA = np.array([[150, 170], [760, 220], [800, 1050], [110, 1000]], dtype=np.float32)
CANTOS_FOLHA_NORMALIZADOS = CANTOS_FOLHA / np.array(
    [LARGURA_FOTO - 1, ALTURA_FOTO - 1], dtype=np.float32
)

LINHAS_TEXTO = ["MINISCAN", "VISAO COMPUTACIONAL", "DOCUMENTO DE TESTE"]


def _pagina_plana() -> np.ndarray:
    """Folha A4 vista de frente, com texto preto grande."""
    pagina = np.full((1120, 800, 3), 245, dtype=np.uint8)
    for indice, linha in enumerate(LINHAS_TEXTO):
        cv2.putText(
            pagina,
            linha,
            (60, 180 + indice * 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.8,
            (20, 20, 20),
            5,
            cv2.LINE_AA,
        )
    return pagina


def _foto_documento() -> np.ndarray:
    """Projeta a página plana em ângulo sobre uma mesa escura, como numa foto de celular."""
    pagina = _pagina_plana()
    altura, largura = pagina.shape[:2]
    origem = np.array(
        [[0, 0], [largura - 1, 0], [largura - 1, altura - 1], [0, altura - 1]], dtype=np.float32
    )
    matriz = cv2.getPerspectiveTransform(origem, CANTOS_FOLHA)
    fundo = np.full((ALTURA_FOTO, LARGURA_FOTO, 3), 55, dtype=np.uint8)
    return cv2.warpPerspective(
        pagina,
        matriz,
        (LARGURA_FOTO, ALTURA_FOTO),
        dst=fundo,
        borderMode=cv2.BORDER_TRANSPARENT,
    )


@pytest.fixture
def pagina_plana() -> np.ndarray:
    return _pagina_plana()


@pytest.fixture
def foto_documento() -> np.ndarray:
    return _foto_documento()


@pytest.fixture
def foto_documento_jpeg(foto_documento: np.ndarray) -> bytes:
    return cv2.imencode(".jpg", foto_documento)[1].tobytes()


@pytest.fixture
def pagina_plana_png(pagina_plana: np.ndarray) -> bytes:
    return cv2.imencode(".png", pagina_plana)[1].tobytes()
