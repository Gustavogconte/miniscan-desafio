"""Aplicação FastAPI do MiniScan."""

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError
from storage3.utils import StorageException

from app.config import (
    TAMANHO_MAXIMO_REQUISICAO,
    TAMANHO_MAXIMO_REQUISICAO_SEM_ARQUIVO,
    configuracoes,
)
from app.contas import (
    CredenciaisInvalidasError,
    DadosDeContaInvalidosError,
    EmailJaCadastradoError,
    MuitasTentativasError,
    ServicoOcupadoError,
)
from app.ocr import MotorOcr, OcrIndisponivelError
from app.pdf import CarimboInvalidoError
from app.persistencia import DocumentoInvalidoError, FalhaPersistenciaError
from app.rotas import roteador, roteador_publico
from app.rotas_contas import ExigeSessao, roteador_contas, usuario_logado
from app.visao.cartao import CartaoInvalidoError
from app.visao.docaligner import docaligner_disponivel
from app.visao.imagem import ImagemGrandeDemaisError, ImagemInvalidaError
from app.visao.perspectiva import CantosInvalidosError

logger = logging.getLogger(__name__)


class _SemBuscaNoLog(logging.Filter):
    """Tira a query string do log de acesso do uvicorn.

    A busca do histórico vai na URL (GET /documentos?busca=...) e pode ter um CPF.
    """

    def filter(self, registro: logging.LogRecord) -> bool:
        argumentos = registro.args
        if isinstance(argumentos, tuple) and len(argumentos) >= 3:
            caminho = argumentos[2]
            if isinstance(caminho, str) and "?" in caminho:
                registro.args = (*argumentos[:2], caminho.split("?", 1)[0], *argumentos[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(_SemBuscaNoLog())


def _erro(codigo: int):
    async def tratar(_: Request, erro: Exception) -> JSONResponse:
        return JSONResponse(status_code=codigo, content={"detail": str(erro)})

    return tratar


async def _falha_persistencia(_: Request, erro: Exception) -> JSONResponse:
    logger.error("Falha ao salvar documento", exc_info=erro)
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": str(erro)})


async def _falha_supabase(_: Request, erro: Exception) -> JSONResponse:
    """Banco ou Storage fora do ar: 502 com mensagem genérica, e o detalhe só no log.

    Sem este tratador, o erro viraria um 500 sem cabeçalhos de CORS, e o navegador
    mostraria só "não foi possível conectar".
    """
    logger.error("Falha ao falar com o Supabase", exc_info=erro)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "O banco de dados não respondeu. Tente de novo em instantes."},
    )


async def _credenciais_invalidas(_: Request, erro: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(erro)},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _servico_ocupado(_: Request, erro: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(erro)},
        headers={"Retry-After": "5"},
    )


async def _muitas_tentativas(_: Request, erro: Exception) -> JSONResponse:
    assert isinstance(erro, MuitasTentativasError)
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": str(erro)},
        headers={"Retry-After": str(erro.segundos)},
    )


class LimiteDeCorpo:
    """Recusa com 413 a requisição cujo corpo passa do teto.

    O teto grande vale só para uploads (multipart/form-data). Qualquer outro corpo,
    como o JSON do /entrar, fica limitado a poucos KB: o FastAPI interpreta o JSON
    inteiro antes de validar os campos, e 100 MB de "[{},{},...]" virariam gigabytes
    de memória, numa rota que nem pede sessão.

    Confere o Content-Length antes de ler qualquer byte e, quando ele não vem
    (envio em partes), conta os bytes conforme chegam.
    """

    def __init__(self, app, maximo: int, maximo_sem_arquivo: int) -> None:
        self.app = app
        self.maximo = maximo
        self.maximo_sem_arquivo = maximo_sem_arquivo

    @staticmethod
    def _mensagem(teto: int) -> str:
        if teto >= 1024 * 1024:
            return f"A requisição pode ter no máximo {teto // (1024 * 1024)} MB no total."
        return f"A requisição pode ter no máximo {teto // 1024} KB no total."

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cabecalhos = dict(scope["headers"])
        envia_arquivos = cabecalhos.get(b"content-type", b"").startswith(b"multipart/form-data")
        teto = self.maximo if envia_arquivos else self.maximo_sem_arquivo
        declarado = cabecalhos.get(b"content-length", b"")
        if declarado.isdigit() and int(declarado) > teto:
            resposta = JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": self._mensagem(teto)},
            )
            await resposta(scope, receive, send)
            return

        recebidos = 0

        async def receber():
            nonlocal recebidos
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                recebidos += len(mensagem.get("body", b""))
                if recebidos > teto:
                    # O FastAPI repassa HTTPException levantada durante a leitura do corpo.
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, self._mensagem(teto))
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
    # Middlewares, de dentro para fora: sessão, tamanho do corpo e CORS. O CORS fica
    # por fora para os 401 e 413 também levarem os cabeçalhos dele, e o navegador
    # conseguir ler a mensagem (e o app saber que a sessão acabou).
    app.add_middleware(ExigeSessao)
    app.add_middleware(
        LimiteDeCorpo,
        maximo=TAMANHO_MAXIMO_REQUISICAO,
        maximo_sem_arquivo=TAMANHO_MAXIMO_REQUISICAO_SEM_ARQUIVO,
    )
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
    for erro_supabase in (APIError, StorageException, httpx.HTTPError):
        app.add_exception_handler(erro_supabase, _falha_supabase)
    app.add_exception_handler(
        DadosDeContaInvalidosError, _erro(status.HTTP_422_UNPROCESSABLE_CONTENT)
    )
    app.add_exception_handler(EmailJaCadastradoError, _erro(status.HTTP_409_CONFLICT))
    app.add_exception_handler(CredenciaisInvalidasError, _credenciais_invalidas)
    app.add_exception_handler(MuitasTentativasError, _muitas_tentativas)
    app.add_exception_handler(ServicoOcupadoError, _servico_ocupado)

    app.include_router(roteador_publico)
    app.include_router(roteador_contas)
    # Cantos, filtros, OCR, PDF e histórico: só com sessão aberta (conferida antes no
    # ExigeSessao; a dependência só lê o dono). Separa o histórico de cada pessoa e
    # deixa de fora da CPU da VPS quem não tem conta.
    app.include_router(roteador, dependencies=[Depends(usuario_logado)])
    return app


app = criar_app()
