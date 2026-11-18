"""Modo cartão de identidade e carimbo de data no PDF."""

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pdf import CarimboInvalidoError, carimbar, gerar_pdf, validar_carimbo
from app.visao.cartao import CartaoInvalidoError, compor_cartao

cliente = TestClient(app)


def png(imagem: np.ndarray) -> bytes:
    return cv2.imencode(".png", imagem)[1].tobytes()


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

    def test_gerar_pdf_rejeita_carimbo_invalido(self, pagina_plana_png):
        resposta = cliente.post(
            "/gerar-pdf",
            files=[("paginas", ("p.png", pagina_plana_png, "image/png"))],
            data={"carimbo": "texto livre <b>"},
        )
        assert resposta.status_code == 422

    def test_filtro_quadro_branco_nao_existe_mais(self, pagina_plana_png):
        resposta = cliente.post(
            "/processar-pagina",
            files={"imagem": ("p.png", pagina_plana_png, "image/png")},
            data={
                "cantos": '[{"x":0,"y":0},{"x":1,"y":0},{"x":1,"y":1},{"x":0,"y":1}]',
                "filtro": "whiteboard",
            },
        )
        assert resposta.status_code == 422
