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


def pixels_da_cor(folha: np.ndarray, cor: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Linhas e colunas da folha que têm a cor exata (o contorno cinza fica de fora)."""
    mascara = (folha == np.array(cor, np.uint8)).all(axis=2)
    return np.flatnonzero(mascara.any(axis=1)), np.flatnonzero(mascara.any(axis=0))


def area_ocupada(folha: np.ndarray) -> tuple[int, int, int, int]:
    """Topo, base, esquerda e direita de tudo o que não é branco (documento e contorno)."""
    mascara = (folha != 255).any(axis=2)
    linhas, colunas = np.flatnonzero(mascara.any(axis=1)), np.flatnonzero(mascara.any(axis=0))
    return int(linhas.min()), int(linhas.max()), int(colunas.min()), int(colunas.max())


class TestCartao:
    FRENTE = (200, 80, 40)
    VERSO = (40, 160, 40)

    def test_frente_e_verso_ampliados_na_a4(self):
        frente = np.full((540, 856, 3), self.FRENTE, np.uint8)
        verso = np.full((856, 540, 3), self.VERSO, np.uint8)  # em pé: deve ser girado
        folha = compor_cartao([frente, verso], "id")
        assert folha.shape == (3508, 2480, 3)  # A4 a 300 dpi
        # O dobro do tamanho real: cada lado com 171,2 x 108 mm (2022 x 1276 px a 300
        # dpi), e 12 mm (142 px) entre eles.
        topo, base, esquerda, direita = area_ocupada(folha)
        assert direita - esquerda + 1 == pytest.approx(2022, abs=3)
        assert base - topo + 1 == pytest.approx(2 * 1276 + 142, abs=3)
        # Centrado na largura, com margem branca embaixo.
        assert esquerda == pytest.approx(2480 - 1 - direita, abs=2)
        assert base < 3508 - 150
        # O verso, girado, fica embaixo da frente.
        linhas_frente, _ = pixels_da_cor(folha, self.FRENTE)
        linhas_verso, _ = pixels_da_cor(folha, self.VERSO)
        assert len(linhas_frente) > 1200 and len(linhas_verso) > 1200
        assert linhas_verso.min() > linhas_frente.max()

    def test_cantos_arredondados_como_no_documento(self):
        folha = compor_cartao([np.full((540, 856, 3), self.FRENTE, np.uint8)], "id")
        topo, _, esquerda, _ = area_ocupada(folha)
        # A ponta do retângulo fica branca; um pouco para dentro já é o documento.
        assert tuple(int(v) for v in folha[topo + 3, esquerda + 3]) == (255, 255, 255)
        assert tuple(int(v) for v in folha[topo + 100, esquerda + 100]) == self.FRENTE

    def test_passaporte_cabe_na_largura_da_folha(self):
        folha = compor_cartao([np.full((880, 1250, 3), (30, 30, 200), np.uint8)], "passaporte")
        _, _, esquerda, direita = area_ocupada(folha)
        # 125 mm não cabem dobrados: a ampliação para nas margens de 15 mm (180 mm).
        assert direita - esquerda + 1 == pytest.approx(2126, abs=3)

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
