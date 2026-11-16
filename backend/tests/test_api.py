import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import TAMANHO_MAXIMO_ARQUIVO
from app.main import app
from app.ocr import ocr_disponivel
from tests.conftest import CANTOS_FOLHA_NORMALIZADOS

cliente = TestClient(app)

CANTOS_JSON = json.dumps([{"x": float(x), "y": float(y)} for x, y in CANTOS_FOLHA_NORMALIZADOS])


def arquivo(dados: bytes, nome: str = "foto.jpg", tipo: str = "image/jpeg"):
    return (nome, dados, tipo)


def test_saude():
    resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"


def test_detectar_cantos(foto_documento_jpeg):
    resposta = cliente.post("/detectar-cantos", files={"imagem": arquivo(foto_documento_jpeg)})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["detectado"] is True
    recebidos = np.array([[p["x"], p["y"]] for p in corpo["cantos"]])
    np.testing.assert_allclose(recebidos, CANTOS_FOLHA_NORMALIZADOS, atol=0.02)


@pytest.mark.parametrize(
    ("filtro", "tipo_mime", "canais"),
    [("original", "image/jpeg", 3), ("grayscale", "image/jpeg", 1), ("bw", "image/png", 1)],
)
def test_processar_pagina(foto_documento_jpeg, filtro, tipo_mime, canais):
    resposta = cliente.post(
        "/processar-pagina",
        files={"imagem": arquivo(foto_documento_jpeg)},
        data={"cantos": CANTOS_JSON, "filtro": filtro},
    )
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == tipo_mime
    pagina = cv2.imdecode(np.frombuffer(resposta.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert (pagina.shape[2] if pagina.ndim == 3 else 1) == canais


@pytest.mark.parametrize(
    "cantos",
    ["nao e json", json.dumps([{"x": 0.1, "y": 0.1}]), json.dumps([{"x": 2, "y": 0}] * 4)],
)
def test_processar_pagina_rejeita_cantos_invalidos(foto_documento_jpeg, cantos):
    resposta = cliente.post(
        "/processar-pagina",
        files={"imagem": arquivo(foto_documento_jpeg)},
        data={"cantos": cantos},
    )
    assert resposta.status_code == 422


def test_processar_pagina_rejeita_filtro_desconhecido(foto_documento_jpeg):
    resposta = cliente.post(
        "/processar-pagina",
        files={"imagem": arquivo(foto_documento_jpeg)},
        data={"cantos": CANTOS_JSON, "filtro": "sepia"},
    )
    assert resposta.status_code == 422


def test_rejeita_arquivo_que_nao_e_imagem():
    resposta = cliente.post(
        "/detectar-cantos", files={"imagem": arquivo(b"texto qualquer", "a.txt", "text/plain")}
    )
    assert resposta.status_code == 422
    assert "imagem" in resposta.json()["detail"]


def test_rejeita_arquivo_grande_demais():
    grande = b"0" * (TAMANHO_MAXIMO_ARQUIVO + 1)
    resposta = cliente.post("/detectar-cantos", files={"imagem": arquivo(grande)})
    assert resposta.status_code == 413


def test_gerar_pdf(pagina_plana_png):
    resposta = cliente.post(
        "/gerar-pdf",
        files=[
            ("paginas", arquivo(pagina_plana_png, "p1.png", "image/png")),
            ("paginas", arquivo(pagina_plana_png, "p2.png", "image/png")),
        ],
    )
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF")


@pytest.mark.skipif(ocr_disponivel(), reason="Só vale quando o Tesseract não está instalado")
def test_extrair_ocr_sem_tesseract_responde_503(pagina_plana_png):
    resposta = cliente.post(
        "/extrair-ocr", files={"imagem": arquivo(pagina_plana_png, "p.png", "image/png")}
    )
    assert resposta.status_code == 503


@pytest.mark.skipif(not ocr_disponivel(), reason="Tesseract com idioma 'por' não instalado")
def test_extrair_ocr(pagina_plana_png):
    resposta = cliente.post(
        "/extrair-ocr", files={"imagem": arquivo(pagina_plana_png, "p.png", "image/png")}
    )
    assert resposta.status_code == 200
    assert "MINISCAN" in resposta.json()["texto"].upper()
