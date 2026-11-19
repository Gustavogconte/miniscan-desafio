"""Contas de usuário: cadastro, entrada com e-mail e senha, e sessões.

A senha nunca é gravada. No banco fica só o hash Argon2id (argon2-cffi), com um sal
aleatório por senha e os parâmetros escritos no próprio texto do hash
(``$argon2id$v=19$m=19456,t=2,p=1$<sal>$<hash>``).

A sessão é um token aleatório de 256 bits, entregue ao navegador uma única vez. No
banco fica só o SHA-256 dele: quem ler a tabela de sessões não consegue se passar
por ninguém.
"""

import hashlib
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Parâmetros mínimos recomendados pela OWASP para o Argon2id: 19 MiB de memória,
# 2 passadas e 1 thread. Cerca de 50 ms por senha, o que cabe na VPS de 1 núcleo.
_hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)
# No máximo 2 hashes ao mesmo tempo. Sem esse teto, 40 entradas simultâneas (o pool
# de threads do servidor) somariam 760 MiB e derrubariam o contêiner de 1 GB.
_vagas_hash = threading.BoundedSemaphore(2)
ESPERA_MAXIMA_HASH_S = 5

DURACAO_SESSAO = timedelta(days=30)
TAMANHO_MINIMO_SENHA = 8
TAMANHO_MAXIMO_SENHA = 128
TAMANHO_MAXIMO_NOME = 80
TAMANHO_MAXIMO_EMAIL = 254
_FORMATO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DadosDeContaInvalidosError(ValueError):
    """Nome, e-mail ou senha fora do formato aceito."""


class EmailJaCadastradoError(ValueError):
    """Já existe uma conta com este e-mail."""


class CredenciaisInvalidasError(ValueError):
    """E-mail ou senha não conferem."""


class ServicoOcupadoError(RuntimeError):
    """Gente demais entrando ao mesmo tempo: a fila do hash de senha não andou a tempo."""


class MuitasTentativasError(RuntimeError):
    """Entradas erradas demais seguidas para o mesmo e-mail."""

    def __init__(self, segundos: int) -> None:
        minutos = max(1, round(segundos / 60))
        super().__init__(
            f"Muitas tentativas com senha errada. Tente de novo em {minutos} "
            f"{'minuto' if minutos == 1 else 'minutos'}."
        )
        self.segundos = segundos


@dataclass(frozen=True)
class Usuario:
    id: str
    nome: str
    email: str


@dataclass(frozen=True)
class SessaoCriada:
    token: str
    usuario: Usuario
    expira_em: datetime


class RepositorioContas(Protocol):
    def buscar_usuario_por_email(self, email: str) -> dict | None:
        """Linha de ``usuarios`` com id, nome, email e senha_hash, ou None."""
        ...

    def inserir_usuario(self, registro: dict) -> None:
        """Levanta EmailJaCadastradoError se o e-mail já existir."""
        ...

    def inserir_sessao(self, registro: dict) -> None: ...

    def buscar_sessao(self, token_hash: str) -> dict | None:
        """``{"expira_em": "...", "usuarios": {"id", "nome", "email"}}`` ou None."""
        ...

    def remover_sessao(self, token_hash: str) -> None: ...

    def remover_sessoes_vencidas(self, usuario_id: str) -> None: ...


# --- Validação ------------------------------------------------------------------


def normalizar_email(email: str) -> str:
    limpo = email.strip().lower()
    if len(limpo) > TAMANHO_MAXIMO_EMAIL or not _FORMATO_EMAIL.match(limpo):
        raise DadosDeContaInvalidosError("Informe um e-mail válido.")
    return limpo


def validar_nome(nome: str) -> str:
    limpo = " ".join(nome.split())
    if not limpo:
        raise DadosDeContaInvalidosError("Informe o seu nome.")
    if len(limpo) > TAMANHO_MAXIMO_NOME:
        raise DadosDeContaInvalidosError(
            f"O nome pode ter no máximo {TAMANHO_MAXIMO_NOME} caracteres."
        )
    return limpo


def validar_senha(senha: str) -> str:
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise DadosDeContaInvalidosError(
            f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres."
        )
    if len(senha) > TAMANHO_MAXIMO_SENHA:
        raise DadosDeContaInvalidosError(
            f"A senha pode ter no máximo {TAMANHO_MAXIMO_SENHA} caracteres."
        )
    if not senha.strip():
        raise DadosDeContaInvalidosError("A senha não pode ser só espaços.")
    return senha


# --- Senha e token --------------------------------------------------------------


class _VagaDeHash:
    def __enter__(self) -> None:
        if not _vagas_hash.acquire(timeout=ESPERA_MAXIMA_HASH_S):
            raise ServicoOcupadoError(
                "Muita gente entrando ao mesmo tempo. Tente de novo em alguns segundos."
            )

    def __exit__(self, *_) -> None:
        _vagas_hash.release()


def gerar_hash_senha(senha: str) -> str:
    with _VagaDeHash():
        return _hasher.hash(senha)


def conferir_senha(senha_hash: str, senha: str) -> bool:
    with _VagaDeHash():
        try:
            return _hasher.verify(senha_hash, senha)
        except (VerificationError, InvalidHashError):
            return False


@lru_cache(maxsize=1)
def _hash_ficticio() -> str:
    """Hash de uma senha qualquer: e-mail inexistente custa o mesmo tempo que senha errada.

    Sem isso, a resposta mais rápida para e-mails sem conta denunciaria quem tem conta.
    """
    return gerar_hash_senha(secrets.token_urlsafe(16))


def gerar_token() -> str:
    return secrets.token_urlsafe(32)


def hash_do_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Proteções em memória -------------------------------------------------------


class LimitadorDeTentativas:
    """Bloqueia um e-mail por um tempo depois de várias senhas erradas seguidas.

    A tentativa é contada antes de conferir a senha (``reservar``) e apagada se a
    senha estiver certa (``limpar``). Assim, uma rajada de tentativas simultâneas não
    passa junta do limite enquanto as senhas ainda estão sendo conferidas.

    Fica na memória do processo (a API roda num processo só). Reiniciar a API zera
    a contagem, o que é aceitável: o objetivo é frear quem tenta adivinhar a senha.
    """

    def __init__(self, maximo: int = 5, janela_s: float = 15 * 60, relogio=time.monotonic):
        self._maximo = maximo
        self._janela = janela_s
        self._relogio = relogio
        self._falhas: dict[str, list[float]] = {}
        self._trava = threading.Lock()

    def _recentes(self, chave: str, agora: float) -> list[float]:
        recentes = [t for t in self._falhas.get(chave, []) if agora - t < self._janela]
        if recentes:
            self._falhas[chave] = recentes
        else:
            self._falhas.pop(chave, None)
        return recentes

    def reservar(self, chave: str) -> None:
        """Conta mais uma tentativa, ou recusa se o limite já foi atingido."""
        with self._trava:
            agora = self._relogio()
            if len(self._falhas) > 10_000:
                # Limpa as chaves antigas para a memória não crescer sem limite.
                for antiga in list(self._falhas):
                    self._recentes(antiga, agora)
            recentes = self._recentes(chave, agora)
            if len(recentes) >= self._maximo:
                raise MuitasTentativasError(int(self._janela - (agora - recentes[0])) + 1)
            self._falhas[chave] = [*recentes, agora]

    def limpar(self, chave: str) -> None:
        with self._trava:
            self._falhas.pop(chave, None)


class CacheDeSessoes:
    """Guarda por um minuto as sessões já conferidas.

    Cada chamada da API (cantos, filtro, OCR, PDF) confere a sessão. Sem o cache,
    cada uma esperaria uma ida ao Supabase. Sair da conta apaga a entrada na hora.
    """

    def __init__(self, validade_s: float = 60, maximo: int = 1_000, relogio=time.monotonic):
        self._validade = validade_s
        self._maximo = maximo
        self._relogio = relogio
        self._itens: dict[str, tuple[Usuario, float, datetime]] = {}
        self._trava = threading.Lock()

    def obter(self, token_hash: str) -> Usuario | None:
        with self._trava:
            item = self._itens.get(token_hash)
            if item is None:
                return None
            usuario, guardado_em, expira_em = item
            if self._relogio() - guardado_em > self._validade or expira_em <= _agora():
                del self._itens[token_hash]
                return None
            return usuario

    def guardar(self, token_hash: str, usuario: Usuario, expira_em: datetime) -> None:
        with self._trava:
            if len(self._itens) >= self._maximo:
                self._itens.clear()
            self._itens[token_hash] = (usuario, self._relogio(), expira_em)

    def remover(self, token_hash: str) -> None:
        with self._trava:
            self._itens.pop(token_hash, None)


limitador_entrada = LimitadorDeTentativas()
cache_sessoes = CacheDeSessoes()


# --- Casos de uso ---------------------------------------------------------------


def _agora() -> datetime:
    return datetime.now(UTC)


def _abrir_sessao(repositorio: RepositorioContas, usuario: Usuario) -> SessaoCriada:
    token = gerar_token()
    expira_em = _agora() + DURACAO_SESSAO
    repositorio.inserir_sessao(
        {
            "token_hash": hash_do_token(token),
            "usuario_id": usuario.id,
            "expira_em": expira_em.isoformat(),
        }
    )
    return SessaoCriada(token=token, usuario=usuario, expira_em=expira_em)


def cadastrar(repositorio: RepositorioContas, nome: str, email: str, senha: str) -> SessaoCriada:
    """Cria a conta e já devolve uma sessão aberta."""
    nome = validar_nome(nome)
    email = normalizar_email(email)
    senha = validar_senha(senha)
    usuario = Usuario(id=str(uuid.uuid4()), nome=nome, email=email)
    repositorio.inserir_usuario(
        {
            "id": usuario.id,
            "nome": nome,
            "email": email,
            "senha_hash": gerar_hash_senha(senha),
        }
    )
    return _abrir_sessao(repositorio, usuario)


def entrar(
    repositorio: RepositorioContas,
    email: str,
    senha: str,
    limitador: LimitadorDeTentativas | None = None,
) -> SessaoCriada:
    limitador = limitador or limitador_entrada
    # Cortado no tamanho máximo: a chave do limitador nunca ocupa memória demais, e
    # nenhum e-mail cadastrado passa desse tamanho.
    email = email.strip().lower()[: TAMANHO_MAXIMO_EMAIL + 1]
    limitador.reservar(email)

    linha = repositorio.buscar_usuario_por_email(email) if email else None
    # Confere a senha mesmo sem conta, contra um hash fictício: o tempo de resposta
    # fica igual e não revela quais e-mails estão cadastrados.
    senha_confere = conferir_senha(linha["senha_hash"] if linha else _hash_ficticio(), senha)
    if linha is None or not senha_confere:
        raise CredenciaisInvalidasError("E-mail ou senha incorretos.")

    limitador.limpar(email)
    usuario = Usuario(id=linha["id"], nome=linha["nome"], email=linha["email"])
    repositorio.remover_sessoes_vencidas(usuario.id)
    return _abrir_sessao(repositorio, usuario)


def usuario_da_sessao(
    repositorio: RepositorioContas, token: str, cache: CacheDeSessoes | None = None
) -> Usuario | None:
    """O dono do token, ou None se o token não existe ou venceu."""
    cache = cache or cache_sessoes
    if not token or len(token) > 200:
        return None
    token_hash = hash_do_token(token)
    usuario = cache.obter(token_hash)
    if usuario is not None:
        return usuario

    linha = repositorio.buscar_sessao(token_hash)
    if linha is None or not linha.get("usuarios"):
        return None
    expira_em = datetime.fromisoformat(linha["expira_em"])
    if expira_em <= _agora():
        repositorio.remover_sessao(token_hash)
        return None
    dono = linha["usuarios"]
    usuario = Usuario(id=dono["id"], nome=dono["nome"], email=dono["email"])
    cache.guardar(token_hash, usuario, expira_em)
    return usuario


def sair(repositorio: RepositorioContas, token: str, cache: CacheDeSessoes | None = None) -> None:
    cache = cache or cache_sessoes
    token_hash = hash_do_token(token)
    cache.remover(token_hash)
    repositorio.remover_sessao(token_hash)


# --- Supabase -------------------------------------------------------------------


class RepositorioContasSupabase:
    """Tabelas ``usuarios`` e ``sessoes``, acessadas só com a chave de serviço."""

    def __init__(self, cliente) -> None:
        self._cliente = cliente

    def buscar_usuario_por_email(self, email: str) -> dict | None:
        resposta = (
            self._cliente.table("usuarios")
            .select("id, nome, email, senha_hash")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        return resposta.data[0] if resposta.data else None

    def inserir_usuario(self, registro: dict) -> None:
        from postgrest.exceptions import APIError

        try:
            self._cliente.table("usuarios").insert(registro).execute()
        except APIError as erro:
            if erro.code == "23505":  # unique_violation
                raise EmailJaCadastradoError("Já existe uma conta com este e-mail.") from erro
            raise

    def inserir_sessao(self, registro: dict) -> None:
        self._cliente.table("sessoes").insert(registro).execute()

    def buscar_sessao(self, token_hash: str) -> dict | None:
        resposta = (
            self._cliente.table("sessoes")
            .select("expira_em, usuarios(id, nome, email)")
            .eq("token_hash", token_hash)
            .limit(1)
            .execute()
        )
        return resposta.data[0] if resposta.data else None

    def remover_sessao(self, token_hash: str) -> None:
        self._cliente.table("sessoes").delete().eq("token_hash", token_hash).execute()

    def remover_sessoes_vencidas(self, usuario_id: str) -> None:
        (
            self._cliente.table("sessoes")
            .delete()
            .eq("usuario_id", usuario_id)
            .lt("expira_em", _agora().isoformat())
            .execute()
        )
