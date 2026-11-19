"""Cadastro, entrada com senha, sessões e a exigência de sessão nas rotas."""

import logging
import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import contas, rotas_contas
from app.config import Configuracoes
from app.contas import (
    CacheDeSessoes,
    CredenciaisInvalidasError,
    DadosDeContaInvalidosError,
    EmailJaCadastradoError,
    LimitadorDeTentativas,
    MuitasTentativasError,
    cadastrar,
    conferir_senha,
    entrar,
    gerar_hash_senha,
    hash_do_token,
    sair,
    usuario_da_sessao,
)
from app.main import app


class ContasFalsas:
    """Tabelas usuarios e sessoes em memória, com a mesma regra de e-mail único."""

    def __init__(self) -> None:
        self.usuarios: dict[str, dict] = {}
        self.sessoes: dict[str, dict] = {}
        self.consultas_de_sessao = 0

    def buscar_usuario_por_email(self, email):
        return next((u for u in self.usuarios.values() if u["email"] == email), None)

    def inserir_usuario(self, registro):
        if self.buscar_usuario_por_email(registro["email"]):
            raise EmailJaCadastradoError("Já existe uma conta com este e-mail.")
        self.usuarios[registro["id"]] = registro

    def inserir_sessao(self, registro):
        self.sessoes[registro["token_hash"]] = registro

    def buscar_sessao(self, token_hash):
        self.consultas_de_sessao += 1
        sessao = self.sessoes.get(token_hash)
        if sessao is None:
            return None
        dono = self.usuarios[sessao["usuario_id"]]
        return {
            "expira_em": sessao["expira_em"],
            "usuarios": {k: dono[k] for k in ("id", "nome", "email")},
        }

    def remover_sessao(self, token_hash):
        self.sessoes.pop(token_hash, None)

    def remover_sessoes_vencidas(self, usuario_id):
        agora = datetime.now(UTC)
        self.sessoes = {
            h: s
            for h, s in self.sessoes.items()
            if s["usuario_id"] != usuario_id or datetime.fromisoformat(s["expira_em"]) > agora
        }


SENHA = "senha-boa-123"


class TestSenha:
    def test_hash_argon2id_com_sal_e_parametros(self):
        primeiro = gerar_hash_senha(SENHA)
        segundo = gerar_hash_senha(SENHA)
        assert primeiro.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
        assert primeiro != segundo  # sal aleatório: a mesma senha nunca dá o mesmo hash
        assert SENHA not in primeiro
        assert conferir_senha(primeiro, SENHA)
        assert not conferir_senha(primeiro, SENHA + "x")
        assert not conferir_senha("lixo", SENHA)


class TestCadastro:
    def test_cadastra_normaliza_e_abre_sessao(self):
        repositorio = ContasFalsas()
        sessao = cadastrar(repositorio, "  Ana   Lima ", " Ana@Exemplo.COM ", SENHA)

        (usuario,) = repositorio.usuarios.values()
        assert (usuario["nome"], usuario["email"]) == ("Ana Lima", "ana@exemplo.com")
        assert conferir_senha(usuario["senha_hash"], SENHA)
        assert sessao.usuario.email == "ana@exemplo.com"
        # No banco fica só o SHA-256 do token, nunca o token.
        (guardada,) = repositorio.sessoes.values()
        assert guardada["token_hash"] == hash_do_token(sessao.token)
        assert sessao.token not in str(repositorio.sessoes)
        assert sessao.expira_em - datetime.now(UTC) > timedelta(days=29)

    @pytest.mark.parametrize(
        ("nome", "email", "senha"),
        [
            ("", "a@b.com", SENHA),
            ("x" * 81, "a@b.com", SENHA),
            ("Ana", "sem-arroba", SENHA),
            ("Ana", "a@b", SENHA),
            ("Ana", "a@b.com", "curta"),
            ("Ana", "a@b.com", " " * 10),
            ("Ana", "a@b.com", "x" * 129),
        ],
        ids=[
            "nome-vazio",
            "nome-longo",
            "email-sem-arroba",
            "email-sem-dominio",
            "senha-curta",
            "senha-espacos",
            "senha-longa",
        ],
    )
    def test_recusa_dados_invalidos(self, nome, email, senha):
        repositorio = ContasFalsas()
        with pytest.raises(DadosDeContaInvalidosError):
            cadastrar(repositorio, nome, email, senha)
        assert repositorio.usuarios == {}

    def test_email_repetido(self):
        repositorio = ContasFalsas()
        cadastrar(repositorio, "Ana", "ana@exemplo.com", SENHA)
        with pytest.raises(EmailJaCadastradoError):
            cadastrar(repositorio, "Outra Ana", "ANA@exemplo.com", "outra-senha-1")


class TestEntrada:
    def test_entra_com_email_em_outro_formato(self):
        repositorio = ContasFalsas()
        cadastrar(repositorio, "Ana", "ana@exemplo.com", SENHA)
        sessao = entrar(repositorio, " ANA@exemplo.com ", SENHA)
        assert sessao.usuario.nome == "Ana"
        assert len(repositorio.sessoes) == 2

    def test_mesma_mensagem_para_senha_errada_e_email_inexistente(self):
        repositorio = ContasFalsas()
        cadastrar(repositorio, "Ana", "ana@exemplo.com", SENHA)
        with pytest.raises(CredenciaisInvalidasError) as senha_errada:
            entrar(repositorio, "ana@exemplo.com", "senha-errada")
        with pytest.raises(CredenciaisInvalidasError) as sem_conta:
            entrar(repositorio, "ninguem@exemplo.com", SENHA)
        assert str(senha_errada.value) == str(sem_conta.value)

    def test_bloqueia_depois_de_cinco_senhas_erradas(self):
        repositorio = ContasFalsas()
        cadastrar(repositorio, "Ana", "ana@exemplo.com", SENHA)
        agora = [0.0]
        limitador = LimitadorDeTentativas(maximo=5, janela_s=900, relogio=lambda: agora[0])

        for _ in range(5):
            with pytest.raises(CredenciaisInvalidasError):
                entrar(repositorio, "ana@exemplo.com", "errada!!", limitador)
        # Nem a senha certa entra enquanto o bloqueio durar.
        with pytest.raises(MuitasTentativasError) as bloqueio:
            entrar(repositorio, "ana@exemplo.com", SENHA, limitador)
        assert "15 minutos" in str(bloqueio.value)

        agora[0] = 901.0
        assert entrar(repositorio, "ana@exemplo.com", SENHA, limitador).usuario.nome == "Ana"

    def test_acerto_zera_a_contagem(self):
        repositorio = ContasFalsas()
        cadastrar(repositorio, "Ana", "ana@exemplo.com", SENHA)
        limitador = LimitadorDeTentativas(maximo=2)
        with pytest.raises(CredenciaisInvalidasError):
            entrar(repositorio, "ana@exemplo.com", "errada!!", limitador)
        entrar(repositorio, "ana@exemplo.com", SENHA, limitador)
        with pytest.raises(CredenciaisInvalidasError):
            entrar(repositorio, "ana@exemplo.com", "errada!!", limitador)
        entrar(repositorio, "ana@exemplo.com", SENHA, limitador)


class TestSessao:
    def test_token_valido_vencido_e_encerrado(self):
        repositorio = ContasFalsas()
        sessao = cadastrar(repositorio, "Ana", "ana@exemplo.com", SENHA)
        cache = CacheDeSessoes()

        assert usuario_da_sessao(repositorio, sessao.token, cache).nome == "Ana"
        assert usuario_da_sessao(repositorio, "token-inventado", cache) is None
        assert usuario_da_sessao(repositorio, "", cache) is None

        sair(repositorio, sessao.token, cache)
        assert repositorio.sessoes == {}
        assert usuario_da_sessao(repositorio, sessao.token, cache) is None

    def test_sessao_vencida_e_apagada(self):
        repositorio = ContasFalsas()
        sessao = cadastrar(repositorio, "Ana", "ana@exemplo.com", SENHA)
        ontem = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        repositorio.sessoes[hash_do_token(sessao.token)]["expira_em"] = ontem

        assert usuario_da_sessao(repositorio, sessao.token, CacheDeSessoes()) is None
        assert repositorio.sessoes == {}

    def test_cache_evita_ida_ao_banco_por_um_minuto(self):
        repositorio = ContasFalsas()
        sessao = cadastrar(repositorio, "Ana", "ana@exemplo.com", SENHA)
        agora = [0.0]
        cache = CacheDeSessoes(validade_s=60, relogio=lambda: agora[0])

        for _ in range(3):
            usuario_da_sessao(repositorio, sessao.token, cache)
        assert repositorio.consultas_de_sessao == 1

        agora[0] = 61.0
        usuario_da_sessao(repositorio, sessao.token, cache)
        assert repositorio.consultas_de_sessao == 2


AUTENTICAR_DE_VERDADE = rotas_contas.autenticar


@pytest.fixture
def login_de_verdade(monkeypatch):
    """Tira a conta de teste do conftest e liga a API a contas em memória.

    Troca o repositório na origem (``_contas_supabase``), e não pelo
    dependency_overrides, porque o middleware ExigeSessao também usa as contas.
    """
    repositorio = ContasFalsas()
    monkeypatch.setattr(rotas_contas, "autenticar", AUTENTICAR_DE_VERDADE)
    monkeypatch.setattr(
        rotas_contas,
        "configuracoes",
        Configuracoes(supabase_url="https://teste.supabase.co", supabase_chave_servico="chave"),
    )
    monkeypatch.setattr(rotas_contas, "_contas_supabase", lambda: repositorio)
    return TestClient(app), repositorio


class TestRotas:
    def test_rotas_exigem_sessao(self, login_de_verdade):
        cliente, _ = login_de_verdade
        for metodo, caminho in [
            ("post", "/detectar-cantos"),
            ("post", "/processar-pagina"),
            ("post", "/extrair-ocr"),
            ("post", "/gerar-pdf"),
            ("post", "/compor-cartao"),
            ("post", "/documentos"),
            ("get", "/documentos"),
            ("get", "/documentos/00000000-0000-4000-8000-000000000001"),
            ("patch", "/documentos/00000000-0000-4000-8000-000000000001"),
            ("delete", "/documentos/00000000-0000-4000-8000-000000000001"),
            ("get", "/eu"),
        ]:
            resposta = getattr(cliente, metodo)(caminho)
            assert resposta.status_code == 401, caminho
            assert resposta.headers["www-authenticate"] == "Bearer"
        assert cliente.get("/saude").status_code == 200

    def test_cadastro_entrada_e_saida(self, login_de_verdade):
        cliente, _ = login_de_verdade
        cadastro = cliente.post(
            "/cadastrar", json={"nome": "Ana", "email": "ana@exemplo.com", "senha": SENHA}
        )
        assert cadastro.status_code == 201
        assert cadastro.json()["usuario"]["email"] == "ana@exemplo.com"

        repetido = cliente.post(
            "/cadastrar", json={"nome": "Ana", "email": "ana@exemplo.com", "senha": SENHA}
        )
        assert repetido.status_code == 409

        entrada = cliente.post("/entrar", json={"email": "ana@exemplo.com", "senha": SENHA})
        assert entrada.status_code == 200
        cabecalho = {"Authorization": f"Bearer {entrada.json()['token']}"}
        assert cliente.get("/eu", headers=cabecalho).json()["nome"] == "Ana"

        assert cliente.post("/sair", headers=cabecalho).status_code == 204
        assert cliente.get("/eu", headers=cabecalho).status_code == 401

    def test_erros_de_entrada(self, login_de_verdade):
        cliente, _ = login_de_verdade
        cliente.post("/cadastrar", json={"nome": "Ana", "email": "ana@exemplo.com", "senha": SENHA})

        errada = cliente.post("/entrar", json={"email": "ana@exemplo.com", "senha": "nao-e-essa"})
        assert errada.status_code == 401
        assert errada.json()["detail"] == "E-mail ou senha incorretos."

        curta = cliente.post("/cadastrar", json={"nome": "Bia", "email": "b@b.com", "senha": "1"})
        assert curta.status_code == 422
        assert "8 caracteres" in curta.json()["detail"]

        for _ in range(4):
            cliente.post("/entrar", json={"email": "ana@exemplo.com", "senha": "nao-e-essa"})
        bloqueada = cliente.post("/entrar", json={"email": "ana@exemplo.com", "senha": SENHA})
        assert bloqueada.status_code == 429
        assert int(bloqueada.headers["retry-after"]) > 0

    def test_sem_supabase_as_contas_respondem_503(self, monkeypatch):
        monkeypatch.setattr(rotas_contas, "autenticar", AUTENTICAR_DE_VERDADE)
        cliente = TestClient(app)
        resposta = cliente.post("/entrar", json={"email": "a@b.com", "senha": SENHA})
        assert resposta.status_code == 503
        assert "SUPABASE" not in resposta.json()["detail"]
        # Com token mas sem banco, a sessão não tem como ser conferida.
        com_token = cliente.get("/documentos", headers={"Authorization": "Bearer abc"})
        assert com_token.status_code == 503

    def test_sem_sessao_recusa_antes_de_ler_o_upload(self, login_de_verdade):
        cliente, _ = login_de_verdade
        lidos = []

        def upload():
            for _ in range(50):
                lidos.append(1)
                yield b"x" * 1024 * 1024

        resposta = cliente.post(
            "/documentos",
            content=upload(),
            headers={"Content-Type": "multipart/form-data; boundary=limite"},
        )
        assert resposta.status_code == 401
        # Nenhum (ou quase nenhum) dos 50 MB foi lido antes da resposta.
        assert len(lidos) <= 1

    def test_token_invalido_e_cabecalho_sem_bearer(self, login_de_verdade):
        cliente, _ = login_de_verdade
        for cabecalho in ("Bearer inventado", "Basic dXNlcjpzZW5oYQ==", "Bearer ", "bearer"):
            resposta = cliente.get("/documentos", headers={"Authorization": cabecalho})
            assert resposta.status_code == 401, cabecalho

    def test_json_grande_e_recusado_sem_ser_interpretado(self, login_de_verdade):
        cliente, _ = login_de_verdade
        corpo = "[" + "{}," * 40_000 + "{}]"  # ~120 KB
        resposta = cliente.post(
            "/entrar", content=corpo, headers={"Content-Type": "application/json"}
        )
        assert resposta.status_code == 413
        assert "64 KB" in resposta.json()["detail"]


def test_tentativas_simultaneas_nao_passam_do_limite():
    limitador = LimitadorDeTentativas(maximo=5)
    aceitas = []

    def tentar():
        try:
            limitador.reservar("ana@exemplo.com")
            aceitas.append(1)
        except MuitasTentativasError:
            pass

    threads = [threading.Thread(target=tentar) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(aceitas) == 5


def test_hash_ocupado_responde_503(monkeypatch, login_de_verdade):
    cliente, _ = login_de_verdade
    vagas = threading.BoundedSemaphore(1)
    vagas.acquire()  # a única vaga já está ocupada
    monkeypatch.setattr(contas, "_vagas_hash", vagas)
    monkeypatch.setattr(contas, "ESPERA_MAXIMA_HASH_S", 0.05)
    resposta = cliente.post("/entrar", json={"email": "a@b.com", "senha": SENHA})
    assert resposta.status_code == 503
    assert resposta.headers["retry-after"] == "5"


def test_log_de_acesso_sem_a_busca():
    from app.main import _SemBuscaNoLog

    registro = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/documentos?busca=123.456.789-00", "1.1", 200),
        None,
    )
    assert _SemBuscaNoLog().filter(registro)
    assert "123.456" not in registro.getMessage()
    assert "/documentos" in registro.getMessage()


def test_limitador_nao_cresce_sem_limite():
    agora = [0.0]
    limitador = LimitadorDeTentativas(janela_s=10, relogio=lambda: agora[0])
    for indice in range(10_001):
        limitador.reservar(f"pessoa{indice}@exemplo.com")
    agora[0] = 20.0
    limitador.reservar("nova@exemplo.com")
    assert len(limitador._falhas) == 1
    assert contas.limitador_entrada is not limitador
