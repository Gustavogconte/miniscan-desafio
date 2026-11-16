import re

import cv2
import numpy as np
import pytest

from app.ocr import extrair_texto_ocr, ocr_disponivel
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


@pytest.mark.skipif(not ocr_disponivel(), reason="Tesseract com idioma 'por' não instalado")
def test_ocr_le_o_texto_da_pagina(pagina_plana):
    texto = extrair_texto_ocr(pagina_plana).upper()
    assert "MINISCAN" in texto
    assert "DOCUMENTO" in texto
