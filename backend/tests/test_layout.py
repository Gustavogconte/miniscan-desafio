from pathlib import Path

import numpy as np
import pytest

from app.visao import layout
from app.visao.filtros import aplicar_filtro
from app.visao.layout import (
    DetectorLayout,
    Regiao,
    _decodificar,
    letterbox,
    mascarar_regioes,
    preservar_regioes,
)


class SessaoFalsa:
    """Imita uma InferenceSession devolvendo detecções fixas no espaço 1024x1024."""

    def __init__(self, saida: np.ndarray) -> None:
        self.saida = saida

    def run(self, _nomes, _entradas):
        return [self.saida]


def detector_com(saida: np.ndarray, nomes: dict[int, str]) -> DetectorLayout:
    detector = DetectorLayout(Path("nao-existe.onnx"))
    detector._sessao = SessaoFalsa(saida)
    detector._nomes = nomes
    detector._entrada = "images"
    return detector


def test_letterbox_mantem_proporcao_e_centraliza():
    imagem = np.zeros((500, 1000, 3), np.uint8)
    quadrada, escala, borda_x, borda_y = letterbox(imagem, 1024)
    assert quadrada.shape == (1024, 1024, 3)
    assert escala == pytest.approx(1.024)
    assert (borda_x, borda_y) == (0, 256)


def test_decodifica_formato_yolov10_e_yolov8():
    v10 = np.array([[[10, 20, 110, 220, 0.9, 3]]], np.float32)
    caixas, confiancas, classes = _decodificar(v10)
    np.testing.assert_allclose(caixas, [[10, 20, 110, 220]])
    assert classes.tolist() == [3] and confiancas[0] == pytest.approx(0.9)

    v8 = np.zeros((1, 4 + 2, 1), np.float32)
    v8[0, :, 0] = [60, 120, 100, 200, 0.1, 0.8]  # cx, cy, w, h, classe0, classe1
    caixas, confiancas, classes = _decodificar(v8)
    np.testing.assert_allclose(caixas, [[10, 20, 110, 220]])
    assert classes.tolist() == [1] and confiancas[0] == pytest.approx(0.8)


def test_sem_modelo_o_detector_fica_desligado():
    detector = DetectorLayout(Path("nao-existe.onnx"))
    assert not detector.disponivel
    assert detector.detectar(np.zeros((100, 100, 3), np.uint8)) == []


def test_detecta_so_classes_graficas_e_volta_para_a_escala_da_pagina():
    # Página 2000x1000: no letterbox a escala é 0,512 e a borda vertical é 256 px.
    saida = np.array(
        [
            [
                [102.4, 307.2, 512.0, 614.4, 0.92, 3],  # figure -> mantém
                [0, 256, 300, 300, 0.95, 1],  # plain text -> ignora
                [600, 300, 700, 400, 0.10, 3],  # figure com confiança baixa -> ignora
            ]
        ],
        np.float32,
    )
    detector = detector_com(saida, {1: "plain text", 3: "figure"})
    regioes = detector.detectar(np.zeros((1000, 2000, 3), np.uint8))
    assert len(regioes) == 1
    r = regioes[0]
    assert r.classe == "figure"
    assert (r.x0, r.y0, r.x1, r.y1) == (200, 100, 1000, 700)


def test_reconhece_nomes_de_outros_modelos():
    saida = np.array([[[0, 256, 512, 768, 0.9, 0]]], np.float32)
    assert detector_com(saida, {0: "Picture"}).detectar(np.zeros((1024, 1024, 3), np.uint8))
    assert detector_com(saida, {0: "Signature"}).detectar(np.zeros((1024, 1024, 3), np.uint8))


def test_preservar_e_mascarar_regioes():
    original = np.full((100, 100, 3), (0, 0, 255), np.uint8)  # vermelho
    filtrada = np.full((100, 100), 255, np.uint8)  # P&B todo branco
    regiao = Regiao(10, 20, 50, 60, "figure", 0.9)

    combinada = preservar_regioes(filtrada, original, [regiao])
    assert combinada.shape == (100, 100, 3)
    assert combinada[30, 30].tolist() == [0, 0, 255]  # dentro: cor original
    assert combinada[90, 90].tolist() == [255, 255, 255]  # fora: filtro

    mascarada = mascarar_regioes(original, [regiao])
    assert mascarada[30, 30].tolist() == [255, 255, 255]
    assert mascarada[90, 90].tolist() == [0, 0, 255]


def test_filtro_preserva_figura_detectada(monkeypatch, pagina_plana):
    regiao = Regiao(100, 600, 400, 900, "figure", 0.9)

    class DetectorFixo:
        def detectar(self, _imagem):
            return [regiao]

    monkeypatch.setattr(layout.DetectorLayout, "obter", classmethod(lambda cls: DetectorFixo()))
    pagina = pagina_plana.copy()
    pagina[600:900, 100:400] = (40, 120, 200)  # "foto" colorida no meio da folha

    com = aplicar_filtro(pagina, "bw", preservar_graficos=True)
    sem = aplicar_filtro(pagina, "bw", preservar_graficos=False)
    assert com[750, 250].tolist() == [40, 120, 200]
    assert sem.ndim == 2 and sem[750, 250] in (0, 255)


def test_cache_evita_inferir_duas_vezes_a_mesma_pagina():
    chamadas = []

    class SessaoContadora(SessaoFalsa):
        def run(self, nomes, entradas):
            chamadas.append(1)
            return super().run(nomes, entradas)

    detector = detector_com(np.zeros((1, 0, 6), np.float32), {3: "figure"})
    detector._sessao = SessaoContadora(np.zeros((1, 0, 6), np.float32))
    pagina = np.full((200, 100, 3), 255, np.uint8)
    detector.detectar(pagina)
    detector.detectar(pagina.copy())
    assert len(chamadas) == 1
    outra = pagina.copy()
    outra[0, 0] = 0
    detector.detectar(outra)
    assert len(chamadas) == 2
