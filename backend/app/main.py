"""Aplicação FastAPI do MiniScan."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import configuracoes
from app.ocr import MotorOcr, OcrIndisponivelError
from app.persistencia import DocumentoInvalidoError, FalhaPersistenciaError
from app.rotas import roteador
from app.visao.imagem import ImagemInvalidaError
from app.visao.layout import DetectorLayout
from app.visao.perspectiva import CantosInvalidosError

logger = logging.getLogger(__name__)


def _erro(codigo: int):
    async def tratar(_: Request, erro: Exception) -> JSONResponse:
        return JSONResponse(status_code=codigo, content={"detail": str(erro)})

    return tratar


async def _falha_persistencia(_: Request, erro: Exception) -> JSONResponse:
    logger.error("Falha ao salvar documento", exc_info=erro)
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": str(erro)})


@asynccontextmanager
async def _ciclo_de_vida(_: FastAPI):
    """Carrega os modelos ONNX na subida do servidor, e não na primeira requisição."""
    try:
        MotorOcr.obter()
    except OcrIndisponivelError:
        logger.exception("OCR indisponível; /extrair-ocr responderá 503")
    DetectorLayout.obter()
    yield


def criar_app() -> FastAPI:
    app = FastAPI(
        title="MiniScan API",
        version="0.2.0",
        description="Detecção de cantos, correção de perspectiva, filtros com preservação de "
        "figuras (DocLayout-YOLO), OCR em português (PaddleOCR) e geração de PDF.",
        lifespan=_ciclo_de_vida,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuracoes.origens_cors,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        # O front-end precisa ler as regiões gráficas devolvidas pelo /processar-pagina.
        expose_headers=["X-Regioes-Graficas"],
    )
    app.add_exception_handler(ImagemInvalidaError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    app.add_exception_handler(CantosInvalidosError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    app.add_exception_handler(OcrIndisponivelError, _erro(status.HTTP_503_SERVICE_UNAVAILABLE))
    app.add_exception_handler(DocumentoInvalidoError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    # A mensagem é genérica de propósito; o detalhe do Supabase fica só no log.
    app.add_exception_handler(FalhaPersistenciaError, _falha_persistencia)
    app.include_router(roteador)
    return app


app = criar_app()
