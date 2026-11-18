"""Detecção de bordas em fotos parecidas com as de celular (tests/fotos_realistas.py)."""

import numpy as np
import pytest

from app.visao.bordas import detectar_cantos, detectar_cantos_opencv
from tests.fotos_realistas import (
    cenarios_dificeis,
    cenarios_ocre,
    cenarios_ocre_dificeis,
    erro_maximo,
)

CENARIOS = cenarios_dificeis()
# Canto a no máximo 3% da diagonal do lugar certo.
ERRO_MAXIMO = 0.03
# O híbrido (modelo e, quando ele não acha, OpenCV) é o que a API usa. O OpenCV sozinho
# é a reserva do híbrido e também não pode regredir.
DETECTORES = {"hibrido": detectar_cantos, "opencv": detectar_cantos_opencv}
com_cada_detector = pytest.mark.parametrize(
    "detectar", list(DETECTORES.values()), ids=list(DETECTORES)
)


@com_cada_detector
@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_encontra_a_folha(nome, detectar):
    foto, verdadeiros = CENARIOS[nome]
    cantos, detectado = detectar(foto)
    assert detectado, f"{nome}: a folha não foi encontrada"
    assert erro_maximo(cantos, verdadeiros) < ERRO_MAXIMO


@com_cada_detector
@pytest.mark.parametrize(
    "fundo",
    [
        np.full((800, 600, 3), 200, np.uint8),
        np.random.default_rng(0).integers(0, 255, (800, 600, 3), dtype=np.uint8),
    ],
    ids=["cinza-liso", "ruido"],
)
def test_sem_folha_nao_inventa_documento(fundo, detectar):
    _, detectado = detectar(fundo)
    assert not detectado


CENARIOS_OCRE = {**cenarios_ocre(), **cenarios_ocre_dificeis()}


@com_cada_detector
@pytest.mark.parametrize("nome", sorted(CENARIOS_OCRE))
def test_encontra_a_folha_em_fundo_ocre_ou_bege(nome, detectar):
    foto, verdadeiros = CENARIOS_OCRE[nome]
    cantos, detectado = detectar(foto)
    assert detectado, f"{nome}: a folha não foi encontrada"
    assert erro_maximo(cantos, verdadeiros) < ERRO_MAXIMO
