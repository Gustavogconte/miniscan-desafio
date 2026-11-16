"""Rotas HTTP da API do MiniScan.

As rotas são síncronas de propósito: o processamento com OpenCV e Tesseract usa CPU,
e o FastAPI executa rotas síncronas em uma thread separada, sem travar o servidor.
"""

from typing import Annotated

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import ValidationError

from app.config import MAXIMO_PAGINAS_PDF, TAMANHO_MAXIMO_ARQUIVO
from app.esquemas import (
    Ponto,
    RespostaCantos,
    RespostaErro,
    RespostaOcr,
    RespostaSaude,
    validador_cantos,
)
from app.ocr import IDIOMA_OCR, extrair_texto_ocr, ocr_disponivel
from app.pdf import gerar_pdf
from app.visao.bordas import detectar_cantos
from app.visao.filtros import Filtro, aplicar_filtro, formato_saida
from app.visao.imagem import codificar_imagem, decodificar_imagem
from app.visao.perspectiva import corrigir_perspectiva

roteador = APIRouter()

ERROS_ENTRADA = {
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": RespostaErro},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": RespostaErro},
}


def ler_arquivo(arquivo: UploadFile) -> bytes:
    dados = arquivo.file.read(TAMANHO_MAXIMO_ARQUIVO + 1)
    if len(dados) > TAMANHO_MAXIMO_ARQUIVO:
        limite_mb = TAMANHO_MAXIMO_ARQUIVO // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Cada arquivo pode ter no máximo {limite_mb} MB.",
        )
    return dados


def ler_cantos(cantos_json: str) -> np.ndarray:
    try:
        pontos: list[Ponto] = validador_cantos.validate_json(cantos_json)
    except ValidationError as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            'Envie "cantos" como JSON com 4 pontos {"x": 0..1, "y": 0..1}.',
        ) from erro
    return np.array([[ponto.x, ponto.y] for ponto in pontos], dtype=np.float32)


@roteador.get("/saude", response_model=RespostaSaude, tags=["infra"])
def rota_saude() -> RespostaSaude:
    return RespostaSaude(status="ok", ocr_disponivel=ocr_disponivel())


@roteador.post(
    "/detectar-cantos",
    response_model=RespostaCantos,
    responses=ERROS_ENTRADA,
    tags=["visao"],
    summary="Detecta os 4 cantos da folha na foto",
)
def rota_detectar_cantos(imagem: Annotated[UploadFile, File()]) -> RespostaCantos:
    matriz = decodificar_imagem(ler_arquivo(imagem))
    cantos, detectado = detectar_cantos(matriz)
    return RespostaCantos(
        cantos=[Ponto(x=float(x), y=float(y)) for x, y in cantos],
        detectado=detectado,
    )


@roteador.post(
    "/processar-pagina",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}}},
        **ERROS_ENTRADA,
    },
    tags=["visao"],
    summary="Corrige a perspectiva e aplica o filtro escolhido",
)
def rota_processar_pagina(
    imagem: Annotated[UploadFile, File()],
    cantos: Annotated[str, Form(description='JSON com 4 pontos, ex.: [{"x":0.1,"y":0.1}, ...]')],
    filtro: Annotated[Filtro, Form()] = "original",
) -> Response:
    matriz = decodificar_imagem(ler_arquivo(imagem))
    retificada = corrigir_perspectiva(matriz, ler_cantos(cantos))
    filtrada = aplicar_filtro(retificada, filtro)
    extensao, tipo_mime = formato_saida(filtro)
    return Response(content=codificar_imagem(filtrada, extensao), media_type=tipo_mime)


@roteador.post(
    "/extrair-ocr",
    response_model=RespostaOcr,
    responses={**ERROS_ENTRADA, status.HTTP_503_SERVICE_UNAVAILABLE: {"model": RespostaErro}},
    tags=["ocr"],
    summary="Extrai o texto da página retificada (pt-BR)",
)
def rota_extrair_ocr(imagem: Annotated[UploadFile, File()]) -> RespostaOcr:
    matriz = decodificar_imagem(ler_arquivo(imagem))
    return RespostaOcr(texto=extrair_texto_ocr(matriz), idioma=IDIOMA_OCR)


@roteador.post(
    "/gerar-pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}, **ERROS_ENTRADA},
    tags=["pdf"],
    summary="Junta as páginas, na ordem enviada, em um PDF único",
)
def rota_gerar_pdf(paginas: Annotated[list[UploadFile], File()]) -> Response:
    if len(paginas) > MAXIMO_PAGINAS_PDF:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"O PDF aceita no máximo {MAXIMO_PAGINAS_PDF} páginas.",
        )
    pdf = gerar_pdf([ler_arquivo(pagina) for pagina in paginas])
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="miniscan.pdf"'},
    )
