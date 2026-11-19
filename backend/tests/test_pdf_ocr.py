import re
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.ocr import (
    Linha,
    extrair_texto_ocr,
    ler_pagina,
    ocr_disponivel,
    ordenar_em_linhas,
    sugerir_titulo,
)
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


class TestSugerirTitulo:
    """Página de 1000 px de altura; ``linha(texto, y, altura da letra)``."""

    @staticmethod
    def linha(texto: str, centro_y: float, altura: float = 20) -> Linha:
        return Linha(texto=texto, centro_y=centro_y, altura=altura)

    def test_vence_a_letra_maior_da_metade_de_cima(self):
        linhas = [
            self.linha("Rua das Flores, 123 - Curitiba", 40),
            self.linha("CONTRATO DE LOCAÇÃO", 120, altura=42),
            self.linha("Pelo presente instrumento particular", 200),
            self.linha("as partes abaixo assinadas", 230),
        ]
        assert sugerir_titulo(linhas, 1000) == "CONTRATO DE LOCAÇÃO"

    def test_sem_destaque_fica_a_primeira_linha_com_palavras(self):
        linhas = [
            self.linha("19/11/2026 - 14:32", 30),
            self.linha("Prezado cliente,", 80),
            self.linha("Segue o boleto do mês.", 110),
        ]
        assert sugerir_titulo(linhas, 1000) == "Prezado cliente"

    def test_letra_grande_embaixo_nao_conta(self):
        linhas = [
            self.linha("Recibo de pagamento", 100),
            self.linha("valor recebido", 140),
            self.linha("ASSINATURA", 900, altura=60),
        ]
        assert sugerir_titulo(linhas, 1000) == "Recibo de pagamento"

    def test_titulo_em_duas_linhas_fica_com_a_de_cima(self):
        # A cedilha deixa a segunda linha um pouco mais alta que a primeira.
        linhas = [
            self.linha("CONTRATO DE PRESTACAO", 100, altura=60),
            self.linha("DE SERVIÇOS GERAIS", 170, altura=63),
            self.linha("Pelo presente instrumento", 260),
            self.linha("as partes abaixo", 290),
        ]
        assert sugerir_titulo(linhas, 1000) == "CONTRATO DE PRESTACAO"

    def test_numero_na_linha_do_titulo_sai_do_nome(self):
        linhas = [self.linha("RECIBO Nº 0001234", 80, altura=45), self.linha("Recebi de", 150)]
        assert sugerir_titulo(linhas, 1000) == "RECIBO Nº"
        linhas = [self.linha("NOTA FISCAL 000.123.456", 40), self.linha("Emitente", 80)]
        assert sugerir_titulo(linhas, 1000) == "NOTA FISCAL"

    def test_sem_palavras_devolve_vazio(self):
        assert (
            sugerir_titulo([self.linha("123.456.789-00", 50), self.linha("R$ 10", 90)], 1000) == ""
        )
        assert sugerir_titulo([], 1000) == ""

    def test_encurta_no_limite_de_palavra(self):
        longo = "Relatório anual de atividades do laboratório de visão computacional - 2026"
        titulo = sugerir_titulo([self.linha(longo, 50, altura=40), self.linha("corpo", 80)], 1000)
        assert titulo == "Relatório anual de atividades do laboratório de visão"
        assert len(titulo) <= 60


@requer_ocr
def test_ocr_le_o_texto_da_pagina(pagina_plana):
    texto = extrair_texto_ocr(pagina_plana).upper()
    assert "MINISCAN" in texto
    assert "DOCUMENTO" in texto


@requer_ocr
def test_ocr_sugere_o_titulo_de_letra_maior():
    pagina = np.full((1400, 1000, 3), 250, np.uint8)
    escrever = [
        ("Curitiba, 19 de novembro", 90, 0.9, 2),
        ("RECIBO DE PAGAMENTO", 260, 2.0, 5),
        ("Recebi de Ana Souza a quantia", 400, 0.9, 2),
        ("referente ao aluguel de novembro", 460, 0.9, 2),
    ]
    for texto, y, escala, espessura in escrever:
        cv2.putText(
            pagina, texto, (60, y), cv2.FONT_HERSHEY_SIMPLEX, escala, (20, 20, 20), espessura
        )
    leitura = ler_pagina(pagina)
    assert leitura.titulo.upper() == "RECIBO DE PAGAMENTO"
    assert leitura.texto.splitlines()[0].startswith("Curitiba")


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
