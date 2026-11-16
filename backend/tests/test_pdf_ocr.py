import re
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.ocr import extrair_texto_ocr, ocr_disponivel, ordenar_em_linhas
from app.pdf import gerar_pdf
from app.visao.imagem import ImagemInvalidaError


def contar_paginas(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf))


class TestGerarPdf:
    def test_junta_paginas_na_ordem(self, pagina_plana_png):
        jpeg = cv2.imencode(".jpg", np.full((300, 200, 3), 200, np.uint8))[1].tobytes()
        pdf = gerar_pdf([pagina_plana_png, jpeg, pagina_plana_png])
        assert pdf.startswith(b"%PDF")
        assert contar_paginas(pdf) == 3

    def test_aceita_png_com_transparencia_e_webp(self):
        com_alfa = cv2.imencode(".png", np.full((100, 80, 4), 255, np.uint8))[1].tobytes()
        webp = cv2.imencode(".webp", np.full((100, 80, 3), 200, np.uint8))[1].tobytes()
        assert contar_paginas(gerar_pdf([com_alfa, webp])) == 2

    def test_rejeita_pagina_invalida(self, pagina_plana_png):
        with pytest.raises(ImagemInvalidaError, match="página 2"):
            gerar_pdf([pagina_plana_png, b"corrompido"])

    def test_rejeita_lista_vazia(self):
        with pytest.raises(ValueError):
            gerar_pdf([])


requer_ocr = pytest.mark.skipif(not ocr_disponivel(), reason="Modelos de OCR indisponíveis")
FONTES = [
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
]


class TestOrdenarEmLinhas:
    @staticmethod
    def caixa(x: float, y: float, largura: float = 80, altura: float = 20) -> np.ndarray:
        return np.array([[x, y], [x + largura, y], [x + largura, y + altura], [x, y + altura]])

    def test_ordem_natural_de_leitura(self):
        # Caixas fora de ordem; "mundo" está 4 px abaixo de "Olá", mas na mesma linha.
        caixas = [self.caixa(200, 104), self.caixa(10, 160), self.caixa(10, 100)]
        textos = ["mundo", "segunda linha", "Olá"]
        assert ordenar_em_linhas(caixas, textos) == "Olá mundo\nsegunda linha"

    def test_ignora_textos_vazios(self):
        assert ordenar_em_linhas([self.caixa(0, 0)], ["   "]) == ""
        assert ordenar_em_linhas([], []) == ""


@requer_ocr
def test_ocr_le_o_texto_da_pagina(pagina_plana):
    texto = extrair_texto_ocr(pagina_plana).upper()
    assert "MINISCAN" in texto
    assert "DOCUMENTO" in texto


@requer_ocr
def test_ocr_le_acentos_do_portugues():
    fonte = next((f for f in FONTES if f.exists()), None)
    if fonte is None:
        pytest.skip("Nenhuma fonte TrueType conhecida neste sistema")
    from PIL import Image, ImageDraw, ImageFont

    pagina = Image.new("RGB", (1100, 260), "white")
    desenho = ImageDraw.Draw(pagina)
    desenho.text(
        (40, 40), "Declaração de Matrícula", fill="black", font=ImageFont.truetype(str(fonte), 40)
    )
    desenho.text(
        (40, 140), "Ação, função, não, você", fill="black", font=ImageFont.truetype(str(fonte), 40)
    )
    texto = extrair_texto_ocr(cv2.cvtColor(np.array(pagina), cv2.COLOR_RGB2BGR))
    for palavra in ["Declaração", "Matrícula", "Ação", "função", "não", "você"]:
        assert palavra in texto, f"{palavra!r} não encontrada em {texto!r}"
