"""Modos da Fase 1: quadro branco, livro, cartão de identidade, QR code e carimbo de data."""

import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pdf import CarimboInvalidoError, carimbar, gerar_pdf, validar_carimbo
from app.visao.cartao import CartaoInvalidoError, compor_cartao
from app.visao.filtros import aplicar_filtro
from app.visao.livro import dividir_livro, encontrar_lombada
from app.visao.qrcode import ler_qrcodes

cliente = TestClient(app)
CANTOS_INTEIROS = json.dumps(
    [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}]
)


def png(imagem: np.ndarray) -> bytes:
    return cv2.imencode(".png", imagem)[1].tobytes()


def livro_aberto(lombada: float = 0.47) -> np.ndarray:
    """Duas páginas claras com uma faixa escura (sombra da dobra) em `lombada`."""
    largura, altura = 1200, 800
    livro = np.full((altura, largura, 3), 235, np.uint8)
    x = int(lombada * largura)
    for deslocamento in range(-30, 31):
        intensidade = 235 - int(120 * (1 - abs(deslocamento) / 30))
        livro[:, x + deslocamento] = intensidade
    for linha in range(80, 720, 40):
        cv2.line(livro, (60, linha), (x - 60, linha), (40, 40, 40), 3)
        cv2.line(livro, (x + 60, linha), (largura - 60, linha), (40, 40, 40), 3)
    return livro


class TestQuadroBranco:
    def test_tira_reflexo_e_mantem_os_tracos(self):
        quadro = np.full((600, 800, 3), 200, np.uint8)
        # Reflexo forte da lâmpada no canto superior direito.
        yy, xx = np.mgrid[0:600, 0:800]
        reflexo = 55 * np.exp(-((xx - 650) ** 2 + (yy - 120) ** 2) / (2 * 150**2))
        quadro = np.clip(quadro + reflexo[..., None], 0, 255).astype(np.uint8)
        cv2.putText(quadro, "x + y = 7", (60, 330), cv2.FONT_HERSHEY_SIMPLEX, 3, (180, 60, 30), 8)

        resultado = aplicar_filtro(quadro, "whiteboard")
        fundo_perto_do_reflexo = resultado[100:140, 630:670].mean()
        fundo_longe = resultado[520:560, 60:100].mean()
        assert abs(fundo_perto_do_reflexo - fundo_longe) < 8  # fundo uniforme
        assert fundo_longe > 240  # e branco
        # O traço azul continua azul e escuro.
        b, g, r = resultado[300:320, 100:400].reshape(-1, 3).min(axis=0)
        assert b > r and r < 120


class TestLivro:
    def test_encontra_lombada_fora_do_centro(self):
        assert encontrar_lombada(livro_aberto(0.47)) == pytest.approx(0.47, abs=0.02)

    def test_sem_sombra_divide_ao_meio(self):
        assert encontrar_lombada(np.full((400, 600, 3), 230, np.uint8)) == 0.5

    def test_cantos_das_duas_paginas_na_foto_original(self):
        livro = livro_aberto(0.47)
        # Fotografa o livro em ângulo sobre uma mesa.
        h, w = livro.shape[:2]
        destino = np.float32([[200, 150], [1500, 220], [1450, 1100], [150, 1000]])
        matriz = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), destino)
        foto = cv2.warpPerspective(livro, matriz, (1700, 1250))
        cantos = destino / np.float32([1699, 1249])

        esquerda, direita, lombada = dividir_livro(foto, cantos)
        assert lombada == pytest.approx(0.47, abs=0.02)
        # O topo da linha de corte é a projeção do ponto (0,47 * largura, 0) do livro.
        esperado = cv2.perspectiveTransform(np.float32([[[0.47 * w, 0]]]), matriz)[0, 0]
        np.testing.assert_allclose(esquerda[1] * [1699, 1249], esperado, atol=15)
        np.testing.assert_allclose(direita[0], esquerda[1])  # as páginas se encontram na lombada
        np.testing.assert_allclose(esquerda[0], cantos[0], atol=1e-5)
        np.testing.assert_allclose(direita[2], cantos[2], atol=1e-5)


class TestCartao:
    def test_frente_e_verso_em_tamanho_real_na_a4(self):
        frente = np.full((540, 856, 3), (200, 80, 40), np.uint8)
        verso = np.full((856, 540, 3), (40, 160, 40), np.uint8)  # em pé: deve ser girado
        folha = compor_cartao([frente, verso], "id")
        assert folha.shape == (3508, 2480, 3)  # A4 a 300 dpi
        # 85,6 mm a 300 dpi = 1011 px: a linha central da folha cruza os dois cartões.
        cores = {tuple(int(v) for v in folha[y, 1240]) for y in range(0, 3508, 4)}
        assert (200, 80, 40) in cores and (40, 160, 40) in cores
        largura_frente = (folha[:, :, 0] == 200).any(axis=0).sum()
        assert largura_frente == pytest.approx(1011, abs=3)

    def test_passaporte_aceita_um_lado_so(self):
        with pytest.raises(CartaoInvalidoError):
            compor_cartao([np.zeros((10, 10, 3), np.uint8)] * 2, "passaporte")


class TestQrcode:
    def test_le_qrcode_gerado(self):
        codigo = cv2.QRCodeEncoder.create().encode("https://miniscan.app/teste")
        codigo = cv2.resize(codigo, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
        foto = np.full((800, 800, 3), 255, np.uint8)
        foto[100 : 100 + codigo.shape[0], 100 : 100 + codigo.shape[1]] = codigo[..., None]
        assert ler_qrcodes(foto) == ["https://miniscan.app/teste"]

    def test_sem_qrcode_devolve_lista_vazia(self):
        assert ler_qrcodes(np.full((300, 300, 3), 255, np.uint8)) == []


class TestCarimbo:
    def test_aceita_so_data_e_hora(self):
        assert validar_carimbo(" 16/11/2026 14:32 ") == "16/11/2026 14:32"
        assert validar_carimbo("") is None
        with pytest.raises(CarimboInvalidoError):
            validar_carimbo("<script>")

    def test_escreve_no_canto_inferior_direito(self):
        pagina = np.full((1400, 1000), 255, np.uint8)
        carimbada = carimbar(pagina, "16/11/2026 14:32")
        assert carimbada[1200:, 500:].min() < 100  # há texto escuro embaixo à direita
        assert carimbada[:700, :].min() == 255  # o resto da página não mudou

    def test_pdf_com_carimbo(self, pagina_plana_png):
        pdf = gerar_pdf([pagina_plana_png], carimbo="16/11/2026 14:32")
        assert pdf.startswith(b"%PDF")


class TestRotasDosModos:
    def test_processar_pagina_com_filtro_quadro_branco(self, pagina_plana_png):
        resposta = cliente.post(
            "/processar-pagina",
            files={"imagem": ("p.png", pagina_plana_png, "image/png")},
            data={"cantos": CANTOS_INTEIROS, "filtro": "whiteboard"},
        )
        assert resposta.status_code == 200
        assert resposta.headers["content-type"] == "image/jpeg"

    def test_dividir_livro(self):
        resposta = cliente.post(
            "/dividir-livro",
            files={"imagem": ("livro.png", png(livro_aberto(0.47)), "image/png")},
            data={"cantos": CANTOS_INTEIROS},
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["lombada"] == pytest.approx(0.47, abs=0.02)
        assert len(corpo["esquerda"]) == 4 and len(corpo["direita"]) == 4

    def test_compor_cartao(self):
        lado = png(np.full((540, 856, 3), 128, np.uint8))
        resposta = cliente.post(
            "/compor-cartao",
            files={"frente": ("f.png", lado, "image/png"), "verso": ("v.png", lado, "image/png")},
            data={"formato": "id"},
        )
        assert resposta.status_code == 200
        folha = cv2.imdecode(np.frombuffer(resposta.content, np.uint8), cv2.IMREAD_COLOR)
        assert folha.shape == (3508, 2480, 3)

    def test_compor_cartao_rejeita_dois_lados_no_passaporte(self):
        lado = png(np.full((100, 140, 3), 128, np.uint8))
        resposta = cliente.post(
            "/compor-cartao",
            files={"frente": ("f.png", lado, "image/png"), "verso": ("v.png", lado, "image/png")},
            data={"formato": "passaporte"},
        )
        assert resposta.status_code == 422

    def test_ler_qrcode(self):
        codigo = cv2.QRCodeEncoder.create().encode("MiniScan")
        codigo = cv2.resize(codigo, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)
        foto = cv2.copyMakeBorder(codigo, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=255)
        resposta = cliente.post("/ler-qrcode", files={"imagem": ("q.png", png(foto), "image/png")})
        assert resposta.status_code == 200
        assert resposta.json() == {"textos": ["MiniScan"]}

    def test_gerar_pdf_rejeita_carimbo_invalido(self, pagina_plana_png):
        resposta = cliente.post(
            "/gerar-pdf",
            files=[("paginas", ("p.png", pagina_plana_png, "image/png"))],
            data={"carimbo": "texto livre <b>"},
        )
        assert resposta.status_code == 422
