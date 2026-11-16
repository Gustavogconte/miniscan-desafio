"""Aplicação FastAPI do MiniScan."""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import configuracoes
from app.ocr import OcrIndisponivelError
from app.rotas import roteador
from app.visao.imagem import ImagemInvalidaError
from app.visao.perspectiva import CantosInvalidosError


def _erro(codigo: int):
    async def tratar(_: Request, erro: Exception) -> JSONResponse:
        return JSONResponse(status_code=codigo, content={"detail": str(erro)})

    return tratar


def criar_app() -> FastAPI:
    app = FastAPI(
        title="MiniScan API",
        version="0.1.0",
        description="Detecção de cantos, correção de perspectiva, filtros, OCR em "
        "português e geração de PDF para o MiniScan.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuracoes.origens_cors,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ImagemInvalidaError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    app.add_exception_handler(CantosInvalidosError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT))
    app.add_exception_handler(OcrIndisponivelError, _erro(status.HTTP_503_SERVICE_UNAVAILABLE))
    app.include_router(roteador)
    return app


app = criar_app()
