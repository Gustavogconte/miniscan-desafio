import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import TAMANHO_MAXIMO_ARQUIVO
from app.main import app
from app.ocr import MotorOcr, OcrIndisponivelError, ocr_disponivel
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


def test_extrair_ocr_responde_503_quando_o_motor_falha(pagina_plana_png, monkeypatch):
    def falhar(_imagem):
        raise OcrIndisponivelError("modelos ausentes")

    monkeypatch.setattr(MotorOcr, "ler", staticmethod(falhar))
    resposta = cliente.post(
        "/extrair-ocr", files={"imagem": arquivo(pagina_plana_png, "p.png", "image/png")}
    )
    assert resposta.status_code == 503


@pytest.mark.skipif(not ocr_disponivel(), reason="Modelos de OCR indisponíveis")
def test_extrair_ocr(pagina_plana_png):
    resposta = cliente.post(
        "/extrair-ocr", files={"imagem": arquivo(pagina_plana_png, "p.png", "image/png")}
    )
    assert resposta.status_code == 200
    assert "MINISCAN" in resposta.json()["texto"].upper()


def test_processar_pagina_devolve_regioes_no_cabecalho(foto_documento_jpeg):
    resposta = cliente.post(
        "/processar-pagina",
        files={"imagem": arquivo(foto_documento_jpeg)},
        data={"cantos": CANTOS_JSON, "filtro": "bw"},
    )
    assert resposta.status_code == 200
    assert isinstance(json.loads(resposta.headers["x-regioes-graficas"]), list)

    sem_preservar = cliente.post(
        "/processar-pagina",
        files={"imagem": arquivo(foto_documento_jpeg)},
        data={"cantos": CANTOS_JSON, "filtro": "bw", "preservar_graficos": "false"},
    )
    assert "x-regioes-graficas" not in sem_preservar.headers


def test_extrair_ocr_valida_regioes(pagina_plana_png, monkeypatch):
    recebidas = {}

    def ocr_falso(_imagem, ignorar_graficos=True, regioes=None):
        recebidas["regioes"] = regioes
        return "texto"

    monkeypatch.setattr("app.rotas.extrair_texto_ocr", ocr_falso)
    regioes = json.dumps([{"x0": 1, "y0": 2, "x1": 30, "y1": 40}])
    resposta = cliente.post(
        "/extrair-ocr",
        files={"imagem": arquivo(pagina_plana_png, "p.png", "image/png")},
        data={"regioes": regioes},
    )
    assert resposta.status_code == 200
    assert (recebidas["regioes"][0].x1, recebidas["regioes"][0].y1) == (30, 40)

    invalida = cliente.post(
        "/extrair-ocr",
        files={"imagem": arquivo(pagina_plana_png, "p.png", "image/png")},
        data={"regioes": '[{"x0": -5}]'},
    )
    assert invalida.status_code == 422


def test_cors_aceita_origens_de_previa_por_regex(monkeypatch):
    from app import main
    from app.config import Configuracoes

    monkeypatch.setenv("MINISCAN_ORIGENS_CORS", "https://miniscan.vercel.app")
    monkeypatch.setenv("MINISCAN_ORIGENS_CORS_REGEX", r"^https://miniscan-[a-z0-9-]+\.vercel\.app$")
    monkeypatch.setattr(main, "configuracoes", Configuracoes())
    cliente_cors = TestClient(main.criar_app())

    def origem_liberada(origem: str) -> bool:
        resposta = cliente_cors.get("/saude", headers={"Origin": origem})
        return resposta.headers.get("access-control-allow-origin") == origem

    assert origem_liberada("https://miniscan.vercel.app")
    assert origem_liberada("https://miniscan-git-main-gustavo.vercel.app")
    assert not origem_liberada("https://site-malicioso.com")
