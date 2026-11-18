"""Detector de cantos DocAligner: pós-processamento, recusa e queda para o OpenCV."""

import numpy as np
import pytest

from app.visao import bordas, docaligner
from app.visao.docaligner import (
    CONFIANCA_MINIMA,
    LIMIAR_MAPA,
    DetectorDocAligner,
    ModeloIndisponivelError,
    cantos_dos_mapas,
    detectar_cantos_docaligner,
    preparar_entrada,
)
from tests.fotos_realistas import cenarios, erro_maximo

# Cantos em pixels do mapa de 128x128: sup. esq., sup. dir., inf. dir., inf. esq.
CANTOS_MAPA = [(20, 30), (100, 25), (110, 100), (15, 105)]
CANTOS_ESPERADOS = (np.array(CANTOS_MAPA, dtype=np.float32) + 0.5) / 128
FOTO = np.full((400, 300, 3), 128, np.uint8)


def _mapas(pontos, pico=0.9) -> np.ndarray:
    """Um mapa por canto, com uma mancha gaussiana de altura `pico` em cada ponto."""
    ys, xs = np.mgrid[0:128, 0:128]
    return np.stack(
        [pico * np.exp(-((xs - x) ** 2 + (ys - y) ** 2) / 8.0) for x, y in pontos]
    ).astype(np.float32)


@pytest.fixture
def modelo_devolve(monkeypatch):
    """Troca a inferência por mapas prontos."""

    def usar(mapas):
        monkeypatch.setattr(DetectorDocAligner, "mapas", classmethod(lambda cls, entrada: mapas))

    return usar


class TestCantosDosMapas:
    def test_devolve_os_cantos_ordenados_e_normalizados(self):
        embaralhados = [CANTOS_MAPA[i] for i in (2, 0, 3, 1)]
        cantos, confianca = cantos_dos_mapas(_mapas(embaralhados))
        np.testing.assert_allclose(cantos, CANTOS_ESPERADOS, atol=1e-3)
        assert confianca == pytest.approx(0.9, abs=1e-3)

    def test_mapa_sem_mancha_nao_devolve_cantos(self):
        mapas = _mapas(CANTOS_MAPA)
        mapas[2] *= (LIMIAR_MAPA - 0.05) / 0.9
        cantos, confianca = cantos_dos_mapas(mapas)
        assert cantos is None
        assert confianca < LIMIAR_MAPA


class TestPrepararEntrada:
    def test_formato_e_escala(self):
        entrada = preparar_entrada(np.full((300, 400, 3), 255, np.uint8))
        assert entrada.shape == (1, 3, 256, 256)
        assert entrada.dtype == np.float32
        assert entrada.max() == pytest.approx(1.0)

    def test_aceita_foto_em_tons_de_cinza(self):
        assert preparar_entrada(np.zeros((300, 400), np.uint8)).shape == (1, 3, 256, 256)


class TestDetectarCantosDocAligner:
    def test_aceita_quando_tem_certeza(self, modelo_devolve):
        modelo_devolve(_mapas(CANTOS_MAPA, pico=CONFIANCA_MINIMA + 0.1))
        np.testing.assert_allclose(detectar_cantos_docaligner(FOTO), CANTOS_ESPERADOS, atol=1e-3)

    def test_recusa_quando_nao_tem_certeza(self, modelo_devolve):
        modelo_devolve(_mapas(CANTOS_MAPA, pico=CONFIANCA_MINIMA - 0.1))
        assert detectar_cantos_docaligner(FOTO) is None

    def test_recusa_quadrilatero_que_o_recorte_nao_aceitaria(self, modelo_devolve):
        alinhados = [(20, 20), (64, 21), (108, 22), (60, 100)]  # três cantos quase em linha
        modelo_devolve(_mapas(alinhados))
        assert detectar_cantos_docaligner(FOTO) is None

    def test_modelo_indisponivel_nao_quebra(self, monkeypatch):
        def falhar(cls, entrada):
            raise ModeloIndisponivelError("sem modelo")

        monkeypatch.setattr(DetectorDocAligner, "mapas", classmethod(falhar))
        assert detectar_cantos_docaligner(FOTO) is None

    def test_erro_na_inferencia_nao_quebra(self, monkeypatch):
        def falhar(cls, entrada):
            raise RuntimeError("onnxruntime falhou")

        monkeypatch.setattr(DetectorDocAligner, "mapas", classmethod(falhar))
        assert detectar_cantos_docaligner(FOTO) is None


class TestCarga:
    def test_modelo_ausente_fica_indisponivel(self, monkeypatch, tmp_path):
        monkeypatch.setattr(docaligner, "CAMINHO_MODELO", tmp_path / "ausente.onnx")
        monkeypatch.setattr(DetectorDocAligner, "_sessao", None)
        monkeypatch.setattr(DetectorDocAligner, "_ultima_falha", None)
        assert not docaligner.docaligner_disponivel()
        # Depois da falha, não tenta carregar de novo a cada chamada.
        with pytest.raises(ModeloIndisponivelError):
            DetectorDocAligner.obter()


class TestDetectarCantosHibrido:
    def test_usa_o_modelo_quando_ele_acha(self, monkeypatch):
        monkeypatch.setattr(bordas, "detectar_cantos_docaligner", lambda imagem: CANTOS_ESPERADOS)
        monkeypatch.setattr(
            bordas, "detectar_cantos_opencv", lambda imagem: pytest.fail("chamou o OpenCV")
        )
        cantos, detectado = bordas.detectar_cantos(FOTO)
        assert detectado
        np.testing.assert_allclose(cantos, CANTOS_ESPERADOS)

    def test_cai_no_opencv_quando_o_modelo_nao_acha(self, monkeypatch):
        do_opencv = (bordas.CANTOS_PADRAO * 0.5, True)
        monkeypatch.setattr(bordas, "detectar_cantos_docaligner", lambda imagem: None)
        monkeypatch.setattr(bordas, "detectar_cantos_opencv", lambda imagem: do_opencv)
        assert bordas.detectar_cantos(FOTO) is do_opencv


@pytest.mark.skipif(not docaligner.CAMINHO_MODELO.is_file(), reason="modelo não baixado")
class TestModeloReal:
    """Com o .onnx de verdade (na CI ele é obrigatório, ver conftest.py)."""

    def test_acha_a_folha_sobre_madeira(self):
        foto, verdadeiros = cenarios()["madeira"]
        cantos = detectar_cantos_docaligner(foto)
        assert cantos is not None
        assert erro_maximo(cantos, verdadeiros) < 0.01

    def test_folha_ocupando_a_foto_toda_fica_com_o_opencv(self):
        foto, verdadeiros = cenarios()["ocupa_quase_tudo"]
        assert detectar_cantos_docaligner(foto) is None
        cantos, detectado = bordas.detectar_cantos(foto)
        assert detectado
        assert erro_maximo(cantos, verdadeiros) < 0.03
