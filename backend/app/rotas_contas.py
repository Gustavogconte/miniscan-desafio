"""Rotas de conta (cadastro, entrada e saída) e a dependência que exige sessão.

O navegador guarda o token devolvido por /entrar ou /cadastrar e o envia em toda
chamada, no cabeçalho ``Authorization: Bearer <token>``. Cookie não serviria: o app
(Vercel) e a API (VPS) ficam em domínios diferentes, e o Safari do iPhone bloqueia
cookie de outro site.
"""

import logging
from functools import lru_cache
from typing import Annotated

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import configuracoes
from app.contas import (
    RepositorioContas,
    RepositorioContasSupabase,
    SessaoCriada,
    Usuario,
    cadastrar,
    entrar,
    sair,
    usuario_da_sessao,
)
from app.esquemas import (
    PedidoCadastro,
    PedidoEntrada,
    RespostaErro,
    RespostaSessao,
    RespostaUsuario,
)

logger = logging.getLogger(__name__)

roteador_contas = APIRouter(tags=["contas"])

_bearer = HTTPBearer(auto_error=False, description="Token devolvido por /entrar ou /cadastrar.")
_NAO_AUTENTICADO = {"WWW-Authenticate": "Bearer"}


@lru_cache(maxsize=1)
def cliente_supabase():
    """Um cliente só (chave de serviço) para as contas e para o histórico."""
    from supabase import create_client

    return create_client(configuracoes.supabase_url, configuracoes.supabase_chave_servico)


@lru_cache(maxsize=1)
def _contas_supabase() -> RepositorioContasSupabase:
    return RepositorioContasSupabase(cliente_supabase())


def obter_contas() -> RepositorioContas:
    if not configuracoes.persistencia_configurada:
        logger.error("Contas indisponíveis: SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY ausente")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "As contas estão indisponíveis no momento."
        )
    return _contas_supabase()


def autenticar(token: str | None) -> Usuario | None:
    """Dono do token, ou None. Os testes trocam esta função por uma conta de teste."""
    if not token:
        return None
    return usuario_da_sessao(obter_contas(), token)


# Rotas que não pedem sessão. /sair aceita token vencido sem reclamar.
ROTAS_PUBLICAS = frozenset(
    {
        "/saude",
        "/entrar",
        "/cadastrar",
        "/sair",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
    }
)


def rota_publica(caminho: str) -> bool:
    return caminho in ROTAS_PUBLICAS


def _token_do_cabecalho(scope) -> str | None:
    for nome, valor in scope["headers"]:
        if nome == b"authorization":
            tipo, _, token = valor.decode("latin-1").partition(" ")
            if tipo.lower() != "bearer":
                return None
            return token.strip() or None
    return None


class ExigeSessao:
    """Confere a sessão antes de a API ler o corpo da requisição.

    O FastAPI lê e interpreta o corpo (uploads de até 100 MB) antes de rodar as
    dependências. Conferindo aqui, quem não tem sessão recebe 401 na hora, sem
    ocupar memória, disco ou CPU com o envio. O dono fica em ``scope["state"]``,
    de onde a dependência ``usuario_logado`` o lê.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or rota_publica(scope["path"]):
            await self.app(scope, receive, send)
            return
        try:
            # A consulta ao Supabase é síncrona: roda numa thread, fora do loop de eventos.
            usuario = await anyio.to_thread.run_sync(autenticar, _token_do_cabecalho(scope))
        except HTTPException as erro:
            await JSONResponse({"detail": erro.detail}, erro.status_code)(scope, receive, send)
            return
        except Exception:
            logger.exception("Falha ao conferir a sessão")
            resposta = JSONResponse(
                {"detail": "Não foi possível conferir a sua sessão. Tente de novo."},
                status.HTTP_502_BAD_GATEWAY,
            )
            await resposta(scope, receive, send)
            return
        if usuario is None:
            resposta = JSONResponse(
                {"detail": "Entre na sua conta para continuar."},
                status.HTTP_401_UNAUTHORIZED,
                headers=_NAO_AUTENTICADO,
            )
            await resposta(scope, receive, send)
            return
        scope.setdefault("state", {})["usuario"] = usuario
        await self.app(scope, receive, send)


def usuario_logado(
    request: Request,
    # Só para a documentação (/docs) mostrar o botão "Authorize".
    _credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario:
    """Dono da sessão, já conferido pelo middleware ExigeSessao."""
    usuario = getattr(request.state, "usuario", None)
    if usuario is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Entre na sua conta para continuar.",
            headers=_NAO_AUTENTICADO,
        )
    return usuario


def _resposta_sessao(sessao: SessaoCriada) -> RespostaSessao:
    return RespostaSessao(
        token=sessao.token,
        expira_em=sessao.expira_em,
        usuario=RespostaUsuario(
            id=sessao.usuario.id, nome=sessao.usuario.nome, email=sessao.usuario.email
        ),
    )


_ERRO_CONTAS = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": RespostaErro},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": RespostaErro},
}


@roteador_contas.post(
    "/cadastrar",
    status_code=status.HTTP_201_CREATED,
    response_model=RespostaSessao,
    responses={**_ERRO_CONTAS, status.HTTP_409_CONFLICT: {"model": RespostaErro}},
    summary="Cria a conta (nome, e-mail e senha) e já abre a sessão",
)
def rota_cadastrar(
    pedido: PedidoCadastro, contas: Annotated[RepositorioContas, Depends(obter_contas)]
) -> RespostaSessao:
    return _resposta_sessao(cadastrar(contas, pedido.nome, pedido.email, pedido.senha))


@roteador_contas.post(
    "/entrar",
    response_model=RespostaSessao,
    responses={
        **_ERRO_CONTAS,
        status.HTTP_401_UNAUTHORIZED: {"model": RespostaErro},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": RespostaErro},
    },
    summary="Confere e-mail e senha e abre uma sessão de 30 dias",
)
def rota_entrar(
    pedido: PedidoEntrada, contas: Annotated[RepositorioContas, Depends(obter_contas)]
) -> RespostaSessao:
    return _resposta_sessao(entrar(contas, pedido.email, pedido.senha))


@roteador_contas.post(
    "/sair",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Encerra a sessão do token enviado",
)
def rota_sair(
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    contas: Annotated[RepositorioContas, Depends(obter_contas)],
) -> Response:
    if credenciais is not None:
        sair(contas, credenciais.credentials)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roteador_contas.get(
    "/eu",
    response_model=RespostaUsuario,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": RespostaErro}},
    summary="Dono da sessão atual",
)
def rota_eu(usuario: Annotated[Usuario, Depends(usuario_logado)]) -> RespostaUsuario:
    return RespostaUsuario(id=usuario.id, nome=usuario.nome, email=usuario.email)
