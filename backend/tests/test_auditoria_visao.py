"""Regressões dos casos achados na auditoria do pipeline de visão (2026-11-18)."""

import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ocr import ordenar_em_linhas
from app.visao.filtros import aplicar_filtro
from app.visao.perspectiva import corrigir_perspectiva

cliente = TestClient(app)
A4 = 297 / 210  # altura/largura


def _foto_inclinada(inclinacao, giro_lateral=0.0, foco_relativo=0.75, largura=1800, altura=2400):
    """Cantos normalizados de uma folha A4 vista por uma câmera pinhole inclinada."""
    foco = foco_relativo * max(largura, altura)
    folha = np.array(
        [[-105, -148.5, 0], [105, -148.5, 0], [105, 148.5, 0], [-105, 148.5, 0]], float
    )
    x, y = np.radians(inclinacao), np.radians(giro_lateral)
    giro_x = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    giro_y = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    pontos = folha @ (giro_y @ giro_x).T + np.array([0, 0, 520.0])
    u = foco * pontos[:, 0] / pontos[:, 2] + largura / 2
    v = foco * pontos[:, 1] / pontos[:, 2] + altura / 2
    cantos = np.stack([u / (largura - 1), v / (altura - 1)], axis=1).astype(np.float32)
    return np.zeros((altura, largura, 3), np.uint8), cantos


def _proporcao(pagina: np.ndarray) -> float:
    return pagina.shape[0] / pagina.shape[1]


class TestProporcaoDaPagina:
    @pytest.mark.parametrize("inclinacao", [10, 20, 30])
    def test_folha_fotografada_inclinada_sai_em_a4(self, inclinacao):
        # Antes saía achatada: -7% a 10°, -16% a 20°, -25% a 30°.
        foto, cantos = _foto_inclinada(inclinacao)
        assert _proporcao(corrigir_perspectiva(foto, cantos)) == pytest.approx(A4, rel=0.02)

    def test_folha_girada_para_o_lado_sai_em_a4(self):
        foto, cantos = _foto_inclinada(10, giro_lateral=25)
        assert _proporcao(corrigir_perspectiva(foto, cantos)) == pytest.approx(A4, rel=0.02)

    def test_foco_diferente_do_previsto_ainda_erra_menos_que_medir_os_lados(self):
        # Lente mais aberta que a prevista (24 mm equivalentes em vez de 26).
        foto, cantos = _foto_inclinada(20, foco_relativo=0.69)
        assert _proporcao(corrigir_perspectiva(foto, cantos)) == pytest.approx(A4, rel=0.05)

    def test_folha_de_frente_mantem_a_proporcao_medida(self):
        foto = np.zeros((1000, 800, 3), np.uint8)
        cantos = np.array([[0.1, 0.1], [0.9, 0.1], [0.9, 0.7], [0.1, 0.7]], np.float32)
        largura, altura = 0.8 * 799, 0.6 * 999
        assert _proporcao(corrigir_perspectiva(foto, cantos)) == pytest.approx(
            altura / largura, rel=0.01
        )


class TestPretoEBranco:
    def test_mantem_area_escura_grande(self):
        # Tarja preta (ou a foto 3x4 de um RG) virava só um contorno, com o miolo branco.
        pagina = np.full((1400, 1000), 235, np.uint8)
        pagina[200:360, 150:750] = 25
        cv2.putText(pagina, "TEXTO", (150, 700), cv2.FONT_HERSHEY_SIMPLEX, 3, 30, 6)
        resultado = aplicar_filtro(cv2.cvtColor(pagina, cv2.COLOR_GRAY2BGR), "bw")
        escala = resultado.shape[0] / pagina.shape[0]
        miolo = resultado[
            int(250 * escala) : int(310 * escala), int(300 * escala) : int(600 * escala)
        ]
        papel = resultado[
            int(1000 * escala) : int(1300 * escala), int(100 * escala) : int(900 * escala)
        ]
        assert miolo.mean() < 60
        assert papel.mean() > 245

    def test_ainda_tira_a_sombra_da_mao(self):
        pagina = np.full((1400, 1000), 235, np.float32)
        pagina[:, 500:] *= 0.6  # sombra de 40% na metade direita
        pagina = pagina.astype(np.uint8)
        cv2.putText(pagina, "TEXTO", (560, 700), cv2.FONT_HERSHEY_SIMPLEX, 3, 20, 6)
        resultado = aplicar_filtro(cv2.cvtColor(pagina, cv2.COLOR_GRAY2BGR), "bw")
        escala = resultado.shape[0] / pagina.shape[0]
        papel_na_sombra = resultado[
            int(1000 * escala) : int(1300 * escala), int(600 * escala) : int(950 * escala)
        ]
        assert papel_na_sombra.mean() > 240


class TestOrdemDoOcr:
    @pytest.mark.parametrize("graus", [0, 1.5, 2, 3, 5])
    def test_tabela_em_pagina_levemente_torta(self, graus):
        angulo = np.radians(graus)
        giro = np.array([[np.cos(angulo), np.sin(angulo)], [-np.sin(angulo), np.cos(angulo)]])
        caixas, textos = [], []
        for linha in range(14):
            y = 100 + linha * 40
            for x, texto in ((50, f"Item {linha:02d}"), (1220, f"R$ {linha},00")):
                caixa = np.array([[x, y], [x + 120, y], [x + 120, y + 24], [x, y + 24]], float)
                caixas.append(caixa @ giro)
                textos.append(texto)
        linhas = ordenar_em_linhas(caixas, textos).splitlines()
        assert linhas == [f"Item {i:02d} R$ {i},00" for i in range(14)]


def _png(imagem: np.ndarray) -> bytes:
    return cv2.imencode(".png", imagem)[1].tobytes()


def test_imagem_com_lado_de_poucos_pixels_responde_422():
    # Antes dava 500: a redução para a análise chegava a um lado de zero pixels.
    resposta = cliente.post(
        "/detectar-cantos",
        files={"imagem": ("fina.png", _png(np.full((1, 2000), 255, np.uint8)), "image/png")},
    )
    assert resposta.status_code == 422
    assert "pequena demais" in resposta.json()["detail"]


def test_pdf_com_carimbo_aceita_png_de_16_bits():
    pagina = np.full((560, 400), 60000, np.uint16)
    for nome, conteudo in (("cinza", pagina), ("com_alfa", np.dstack([pagina] * 4))):
        resposta = cliente.post(
            "/gerar-pdf",
            files=[("paginas", (f"{nome}.png", _png(conteudo), "image/png"))],
            data={"carimbo": "18/11/2026 06:30"},
        )
        assert resposta.status_code == 200, (nome, json.loads(resposta.content or b"{}"))
        assert resposta.content.startswith(b"%PDF")
