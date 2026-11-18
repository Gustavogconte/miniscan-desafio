"""Aplicação FastAPI do MiniScan."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import TAMANHO_MAXIMO_REQUISICAO, configuracoes
from app.ocr import MotorOcr, OcrIndisponivelError
from app.pdf import CarimboInvalidoError
from app.persistencia import DocumentoInvalidoError, FalhaPersistenciaError
from app.rotas import roteador
from app.visao.cartao import CartaoInvalidoError
from app.visao.docaligner import docaligner_disponivel
from app.visao.imagem import ImagemGrandeDemaisError, ImagemInvalidaError
from app.visao.perspectiva import CantosInvalidosError

logger = logging.getLogger(__name__)


def _erro(codigo: int):
    async def tratar(_: Request, erro: Exception) -> JSONResponse:
        return JSONResponse(status_code=codigo, content={"detail": str(erro)})

    return tratar


async def _falha_persistencia(_: Request, erro: Exception) -> JSONResponse:
    logger.error("Falha ao salvar documento", exc_info=erro)
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": str(erro)})


class LimiteDeCorpo:
    """Recusa com 413 a requisição cujo corpo passa do teto.

    Confere o Content-Length antes de ler qualquer byte e, quando ele não vem
    (envio em partes), conta os bytes conforme chegam.
    """

    def __init__(self, app, maximo: int) -> None:
        self.app = app
        self.maximo = maximo

    def _mensagem(self) -> str:
        return f"A requisição pode ter no máximo {self.maximo // (1024 * 1024)} MB no total."

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declarado = dict(scope["headers"]).get(b"content-length", b"")
        if declarado.isdigit() and int(declarado) > self.maximo:
            resposta = JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE, content={"detail": self._mensagem()}
            )
            await resposta(scope, receive, send)
            return

        recebidos = 0

        async def receber():
            nonlocal recebidos
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                recebidos += len(mensagem.get("body", b""))
                if recebidos > self.maximo:
                    # O FastAPI repassa HTTPException levantada durante a leitura do corpo.
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, self._mensagem())
            return mensagem

        await self.app(scope, receber, send)


@asynccontextmanager
async def _ciclo_de_vida(_: FastAPI):
    """Carrega o OCR e o modelo de cantos na subida do servidor, e não na primeira requisição."""
    try:
        MotorOcr.obter()
    except OcrIndisponivelError:
        logger.exception("OCR indisponível; /extrair-ocr responderá 503")
    if not docaligner_disponivel():
        logger.warning("Modelo de cantos indisponível; /detectar-cantos usará só o OpenCV")
    yield


def criar_app() -> FastAPI:
    app = FastAPI(
        title="MiniScan API",
        version="0.2.0",
        description="Detecção de cantos, correção de perspectiva, filtros, OCR em português "
        "(PaddleOCR) e geração de PDF.",
        lifespan=_ciclo_de_vida,
    )
    # Adicionado antes do CORS para ficar por dentro dele: a resposta 413 também
    # leva os cabeçalhos de CORS, e o navegador consegue ler a mensagem.
    app.add_middleware(LimiteDeCorpo, maximo=TAMANHO_MAXIMO_REQUISICAO)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuracoes.origens_cors,
        allow_origin_regex=configuracoes.origens_cors_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ImagemGrandeDemaisError, _erro(status.HTTP_413_CONTENT_TOO_LARGE))
    app.add_exception_handler(ImagemInvalidaError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    app.add_exception_handler(CantosInvalidosError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    app.add_exception_handler(CartaoInvalidoError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    app.add_exception_handler(CarimboInvalidoError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    app.add_exception_handler(OcrIndisponivelError, _erro(status.HTTP_503_SERVICE_UNAVAILABLE))
    app.add_exception_handler(DocumentoInvalidoError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    # A mensagem é genérica de propósito; o detalhe do Supabase fica só no log.
    app.add_exception_handler(FalhaPersistenciaError, _falha_persistencia)
    app.include_router(roteador)
    return app


app = criar_app()
