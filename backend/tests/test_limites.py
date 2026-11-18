"""Limites de entrada que protegem a memória da API e a geometria do recorte."""

import json
import threading
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ocr import MotorOcr, ocr_disponivel
from app.visao.perspectiva import CantosInvalidosError, corrigir_perspectiva

cliente = TestClient(main.app)


def _png(altura: int, largura: int) -> bytes:
    return cv2.imencode(".png", np.full((altura, largura), 255, np.uint8))[1].tobytes()


def test_recusa_imagem_com_pixels_demais_antes_de_decodificar():
    # ~120 KB no disco, mas 10000x10000 px: decodificada ocuparia ~300 MB.
    resposta = cliente.post(
        "/detectar-cantos", files={"imagem": ("bomba.png", _png(10000, 10000), "image/png")}
    )
    assert resposta.status_code == 413
    assert "megapixels" in resposta.json()["detail"]


def test_pdf_recusa_pagina_com_pixels_demais():
    resposta = cliente.post(
        "/gerar-pdf", files=[("paginas", ("bomba.png", _png(10000, 10000), "image/png"))]
    )
    assert resposta.status_code == 413


@pytest.fixture
def cliente_com_teto_pequeno(monkeypatch):
    monkeypatch.setattr(main, "TAMANHO_MAXIMO_REQUISICAO", 1024)
    return TestClient(main.criar_app())


def test_recusa_corpo_grande_pelo_content_length(cliente_com_teto_pequeno):
    resposta = cliente_com_teto_pequeno.post(
        "/detectar-cantos", files={"imagem": ("f.png", b"x" * 4096, "image/png")}
    )
    assert resposta.status_code == 413


def test_recusa_corpo_grande_enviado_em_partes(cliente_com_teto_pequeno):
    def partes():
        for _ in range(8):
            yield b"x" * 512

    resposta = cliente_com_teto_pequeno.post(
        "/detectar-cantos",
        content=partes(),
        headers={"Content-Type": "multipart/form-data; boundary=limite"},
    )
    assert resposta.status_code == 413


@pytest.mark.parametrize(
    "cantos",
    [
        [(0, 0), (0.5, 0), (1, 0), (0, 1)],  # três cantos alinhados: é um triângulo
        [(0, 0), (1, 0), (0.55, 0.05), (0, 1)],  # um canto quase sobre o lado oposto
    ],
)
def test_recusa_cantos_que_nao_formam_quadrilatero(cantos):
    imagem = np.full((400, 300, 3), 200, np.uint8)
    with pytest.raises(CantosInvalidosError):
        corrigir_perspectiva(imagem, np.array(cantos, np.float32))


def test_cantos_fora_de_ordem_continuam_validos():
    # A ordem enviada não importa: ordenar_cantos desfaz o "cruzamento".
    imagem = np.full((400, 300, 3), 200, np.uint8)
    cantos = np.array([(0.1, 0.1), (0.9, 0.9), (0.9, 0.1), (0.1, 0.9)], np.float32)
    assert corrigir_perspectiva(imagem, cantos).size > 0


def test_processar_pagina_responde_422_para_cantos_alinhados():
    foto = cv2.imencode(".jpg", np.full((400, 300, 3), 200, np.uint8))[1].tobytes()
    cantos = json.dumps([{"x": 0, "y": 0}, {"x": 0.5, "y": 0}, {"x": 1, "y": 0}, {"x": 0, "y": 1}])
    resposta = cliente.post(
        "/processar-pagina",
        files={"imagem": ("f.jpg", foto, "image/jpeg")},
        data={"cantos": cantos},
    )
    assert resposta.status_code == 422


def test_imagem_inteira_nao_e_aparada():
    # A folha A4 do Cartão ID volta com os cantos na imagem inteira: aparar a borda
    # deixaria o cartão maior que o real no PDF.
    imagem = np.zeros((3508, 2480, 3), np.uint8)
    cantos = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32)
    altura, largura = corrigir_perspectiva(imagem, cantos).shape[:2]
    assert largura / altura == pytest.approx(2480 / 3508, rel=1e-3)
    assert altura >= 2990


def test_saude_nao_espera_a_leitura_do_ocr(monkeypatch):
    monkeypatch.setattr(MotorOcr, "_instancia", object())
    resultado = []
    with MotorOcr._trava_leitura:  # um OCR em andamento
        consulta = threading.Thread(target=lambda: resultado.append(ocr_disponivel()))
        consulta.start()
        consulta.join(timeout=2)
    assert resultado == [True]


def test_nao_tenta_carregar_o_ocr_de_novo_logo_depois_de_uma_falha(monkeypatch):
    tentativas = []

    def falhar():
        tentativas.append(1)
        raise main.OcrIndisponivelError("sem modelos")

    monkeypatch.setattr(MotorOcr, "_instancia", None)
    monkeypatch.setattr(MotorOcr, "_ultima_falha", None)
    monkeypatch.setattr(MotorOcr, "_carregar", staticmethod(falhar))
    assert ocr_disponivel() is False
    assert ocr_disponivel() is False
    assert len(tentativas) == 1


def test_carrega_o_ocr_logo_depois_do_boot_da_maquina(monkeypatch):
    # Depois de um reinício da VPS, o contêiner sobe uns 20 s após o boot, e o relógio
    # monotônico conta desde o boot. Sem nenhuma falha anterior, o OCR tem que carregar.
    tentativas = []

    def carregar():
        tentativas.append(1)
        return object()

    monkeypatch.setattr(MotorOcr, "_instancia", None)
    monkeypatch.setattr(MotorOcr, "_ultima_falha", None)
    monkeypatch.setattr(MotorOcr, "_carregar", staticmethod(carregar))
    monkeypatch.setattr(time, "monotonic", lambda: 20.0)
    assert ocr_disponivel() is True
    assert tentativas == [1]
