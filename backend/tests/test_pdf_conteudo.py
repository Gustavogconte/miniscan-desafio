"""O que o PDF entregue ao usuário realmente contém: ordem, tamanho e formato das páginas.

O PDF é aberto com o pikepdf (dependência do img2pdf) e cada página é conferida pela
imagem embutida, e não só pela contagem de páginas.
"""

import io

import cv2
import numpy as np
import pikepdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.pdf import gerar_pdf

A4_PT = (595.28, 841.89)
cliente = TestClient(app)


def _jpeg(cor_bgr, largura=400, altura=560) -> bytes:
    return cv2.imencode(".jpg", np.full((altura, largura, 3), cor_bgr, np.uint8))[1].tobytes()


def _png_cinza(valor=255, largura=400, altura=560) -> bytes:
    return cv2.imencode(".png", np.full((altura, largura), valor, np.uint8))[1].tobytes()


def _paginas(pdf: bytes):
    """(MediaBox, filtro do stream, imagem decodificada) de cada página, na ordem do PDF."""
    with pikepdf.open(io.BytesIO(pdf)) as documento:
        resultado = []
        for pagina in documento.pages:
            caixa = [float(v) for v in pagina.mediabox]
            (_, objeto), *_ = pagina.get_images().items()
            filtro = str(objeto.get("/Filter"))
            imagem = pikepdf.PdfImage(objeto).as_pil_image()
            resultado.append((caixa, filtro, np.asarray(imagem)))
        return resultado


def _canal_dominante(imagem: np.ndarray) -> int:
    """0, 1 ou 2: o canal RGB mais forte na média da página."""
    return int(np.argmax(imagem.reshape(-1, 3).mean(axis=0)))


def test_paginas_saem_na_ordem_enviada():
    vermelho, verde, azul = (0, 0, 220), (0, 200, 0), (220, 0, 0)  # BGR
    paginas = _paginas(gerar_pdf([_jpeg(vermelho), _jpeg(verde), _jpeg(azul)]))
    assert [_canal_dominante(imagem) for _, _, imagem in paginas] == [0, 1, 2]


def test_toda_pagina_e_a4_e_a_paisagem_vira_a4_deitada():
    retrato = _jpeg((200, 200, 200), 400, 560)
    paisagem = _jpeg((200, 200, 200), 560, 400)
    caixas = [caixa for caixa, _, _ in _paginas(gerar_pdf([retrato, paisagem]))]
    largura, altura = caixas[0][2] - caixas[0][0], caixas[0][3] - caixas[0][1]
    assert (largura, altura) == pytest.approx(A4_PT, abs=1)
    largura, altura = caixas[1][2] - caixas[1][0], caixas[1][3] - caixas[1][1]
    assert sorted((largura, altura)) == pytest.approx(sorted(A4_PT), abs=1)


def test_pagina_png_do_pb_entra_sem_virar_jpeg():
    ((_, filtro, _),) = _paginas(gerar_pdf([_png_cinza()]))
    assert "DCTDecode" not in filtro  # JPEG criaria artefatos em volta das letras


def test_carimbo_fica_no_rodape_e_o_png_continua_png():
    sem_carimbo = _paginas(gerar_pdf([_png_cinza()]))[0]
    com_carimbo = _paginas(gerar_pdf([_png_cinza()], carimbo="16/11/2026 14:32"))[0]
    assert "DCTDecode" not in com_carimbo[1]
    imagem = com_carimbo[2]
    altura, largura = imagem.shape[:2]
    rodape_direito = imagem[int(altura * 0.85) :, int(largura * 0.4) :]
    assert rodape_direito.min() < 100, "o carimbo não aparece no rodapé"
    assert imagem[: int(altura * 0.5)].min() == 255, "o carimbo vazou para o resto da página"
    assert sem_carimbo[2].min() == 255


def test_rota_gerar_pdf_preserva_a_ordem_de_ponta_a_ponta():
    """Mesma conferência pela rota HTTP, com o multipart que o front-end monta."""
    arquivos = [
        ("paginas", (f"pagina-{i}.jpg", _jpeg(cor), "image/jpeg"))
        for i, cor in enumerate([(220, 0, 0), (0, 0, 220)], 1)  # azul, vermelho (BGR)
    ]
    resposta = cliente.post("/gerar-pdf", files=arquivos)
    assert resposta.status_code == 200
    assert [_canal_dominante(imagem) for _, _, imagem in _paginas(resposta.content)] == [2, 0]


def test_png_com_transparencia_sem_canal_alfa_vira_pagina_valida():
    # PNG RGB com o bloco tRNS: o OpenCV lê 3 canais e a página vai direto para o img2pdf.
    imagem = Image.new("RGB", (120, 160), (255, 255, 255))
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG", transparency=(255, 255, 255))
    assert len(_paginas(gerar_pdf([buffer.getvalue()]))) == 1
