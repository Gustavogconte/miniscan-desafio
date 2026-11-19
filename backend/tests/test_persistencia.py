import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.persistencia import (
    DocumentoInvalidoError,
    FalhaPersistenciaError,
    PaginaParaSalvar,
    abrir_documento,
    caminho_no_bucket,
    excluir_documento,
    listar_historico,
    renomear_documento,
    salvar_documento,
)
from app.rotas import obter_repositorio
from tests.conftest import USUARIO_TESTE_ID

OUTRA_CONTA = "00000000-0000-4000-8000-0000000000ff"
BUCKET = "miniscan-files"

JPEG = cv2.imencode(".jpg", np.full((60, 40, 3), 200, np.uint8))[1].tobytes()
PNG = cv2.imencode(".png", np.full((60, 40), 255, np.uint8))[1].tobytes()
PDF = b"%PDF-1.4\n%%EOF"


class RepositorioFalso:
    """Guarda tudo em memória e pode falhar em uma etapa escolhida."""

    def __init__(self, falhar_em: str | None = None) -> None:
        self.falhar_em = falhar_em
        self.arquivos: dict[str, tuple[bytes, str]] = {}
        self.documentos: dict[str, dict] = {}
        self.paginas: list[dict] = []

    def _talvez_falhar(self, etapa: str) -> None:
        if self.falhar_em == etapa:
            raise RuntimeError(f"falha simulada em {etapa}")

    def enviar_arquivo(self, caminho, dados, tipo_mime):
        self._talvez_falhar("enviar_arquivo")
        self.arquivos[caminho] = (dados, tipo_mime)

    def remover_arquivos(self, caminhos):
        self._talvez_falhar("remover_arquivos")
        for caminho in caminhos:
            self.arquivos.pop(caminho, None)

    def inserir_documento(self, registro):
        self._talvez_falhar("inserir_documento")
        self.documentos[registro["id"]] = registro

    def inserir_paginas(self, registros):
        self._talvez_falhar("inserir_paginas")
        self.paginas.extend(registros)

    def remover_documento(self, documento_id, usuario_id=None):
        documento = self.documentos.get(documento_id)
        if documento is None or usuario_id not in (None, documento["usuario_id"]):
            return
        del self.documentos[documento_id]
        self.paginas = [p for p in self.paginas if p["document_id"] != documento_id]

    def atualizar_titulo(self, usuario_id, documento_id, titulo):
        documento = self.documentos.get(documento_id)
        if documento is None or documento["usuario_id"] != usuario_id:
            return False
        documento["title"] = titulo
        return True

    def _linha(self, documento: dict, paginas: list[dict]) -> dict:
        return {
            "id": documento["id"],
            "title": documento["title"],
            "pdf_url": documento["pdf_url"],
            "page_count": len([p for p in self.paginas if p["document_id"] == documento["id"]]),
            "created_at": "2026-11-18T12:00:00+00:00",
            "document_pages": [{"id": f"p{p['page_order']}", **p} for p in paginas],
        }

    def listar_documentos(self, usuario_id, termo, limite):
        self.busca = (usuario_id, termo, limite)
        linhas = []
        for documento in self.documentos.values():
            if documento["usuario_id"] != usuario_id:
                continue
            paginas = sorted(
                (p for p in self.paginas if p["document_id"] == documento["id"]),
                key=lambda p: p["page_order"],
            )
            linhas.append(self._linha(documento, paginas[:1]))
        return linhas

    def obter_documento(self, usuario_id, documento_id):
        documento = self.documentos.get(documento_id)
        if documento is None or documento["usuario_id"] != usuario_id:
            return None
        # Fora de ordem de propósito: quem abre o documento ordena as páginas.
        paginas = sorted(
            (p for p in self.paginas if p["document_id"] == documento_id),
            key=lambda p: -p["page_order"],
        )
        return self._linha(documento, paginas)

    def assinar_urls(self, caminhos, validade_s):
        self.assinados = (list(caminhos), validade_s)
        return {c: f"https://exemplo.supabase.co/assinado/{c}?token=t" for c in caminhos}


def duas_paginas() -> list[PaginaParaSalvar]:
    return [
        PaginaParaSalvar(original=JPEG, processada=PNG, filtro="bw", texto_ocr="primeira"),
        PaginaParaSalvar(original=JPEG, processada=JPEG, filtro="grayscale", texto_ocr=""),
    ]


class TestSalvarDocumento:
    def test_salva_arquivos_documento_e_paginas(self):
        repositorio = RepositorioFalso()
        salvo = salvar_documento(
            repositorio, USUARIO_TESTE_ID, "  Contrato   de estágio ", PDF, duas_paginas()
        )

        assert salvo.titulo == "Contrato de estágio"
        assert salvo.total_paginas == 2
        # O banco guarda o caminho no bucket (que é privado), e não um link.
        registro = repositorio.documentos[salvo.id]
        assert registro["pdf_url"] == f"documentos/{salvo.id}/documento.pdf"
        assert registro["usuario_id"] == USUARIO_TESTE_ID
        assert repositorio.paginas[0]["original_image_url"] == (
            f"documentos/{salvo.id}/pagina-01-original.jpg"
        )
        assert sorted(repositorio.arquivos) == sorted(
            [
                f"documentos/{salvo.id}/documento.pdf",
                f"documentos/{salvo.id}/pagina-01-original.jpg",
                f"documentos/{salvo.id}/pagina-01-processada.png",
                f"documentos/{salvo.id}/pagina-02-original.jpg",
                f"documentos/{salvo.id}/pagina-02-processada.jpg",
            ]
        )
        assert repositorio.arquivos[f"documentos/{salvo.id}/pagina-01-processada.png"][1] == (
            "image/png"
        )
        assert repositorio.documentos[salvo.id]["title"] == "Contrato de estágio"
        assert [p["page_order"] for p in repositorio.paginas] == [1, 2]
        assert [p["filter_applied"] for p in repositorio.paginas] == ["bw", "grayscale"]

    @pytest.mark.parametrize("etapa", ["enviar_arquivo", "inserir_documento", "inserir_paginas"])
    def test_desfaz_tudo_quando_uma_etapa_falha(self, etapa):
        repositorio = RepositorioFalso(falhar_em=etapa)
        with pytest.raises(FalhaPersistenciaError):
            salvar_documento(repositorio, USUARIO_TESTE_ID, "Documento", PDF, duas_paginas())
        assert repositorio.arquivos == {}
        assert repositorio.documentos == {}
        assert repositorio.paginas == []

    @pytest.mark.parametrize(
        ("titulo", "pdf", "paginas"),
        [
            ("   ", PDF, duas_paginas()),
            ("x" * 201, PDF, duas_paginas()),
            ("Documento", JPEG, duas_paginas()),
            ("Documento", PDF, []),
            (
                "Documento",
                PDF,
                [PaginaParaSalvar(original=b"texto", processada=PNG, filtro="bw", texto_ocr="")],
            ),
        ],
        ids=["titulo-vazio", "titulo-longo", "pdf-invalido", "sem-paginas", "imagem-invalida"],
    )
    def test_rejeita_entrada_invalida_sem_gravar_nada(self, titulo, pdf, paginas):
        repositorio = RepositorioFalso()
        with pytest.raises(DocumentoInvalidoError):
            salvar_documento(repositorio, USUARIO_TESTE_ID, titulo, pdf, paginas)
        assert repositorio.arquivos == {}


@pytest.fixture
def cliente_com_repositorio():
    repositorio = RepositorioFalso()
    app.dependency_overrides[obter_repositorio] = lambda: repositorio
    yield TestClient(app), repositorio
    app.dependency_overrides.clear()


def enviar_documento(cliente, paginas_json=None, quantidade_processadas=2):
    metadados = paginas_json or json.dumps(
        [{"filtro": "bw", "texto_ocr": "abc"}, {"filtro": "original"}]
    )
    arquivos = [("pdf", ("doc.pdf", PDF, "application/pdf"))]
    arquivos += [("originais", (f"o{i}.jpg", JPEG, "image/jpeg")) for i in range(2)]
    arquivos += [
        ("processadas", (f"p{i}.png", PNG, "image/png")) for i in range(quantidade_processadas)
    ]
    return cliente.post(
        "/documentos", data={"titulo": "Meu documento", "paginas": metadados}, files=arquivos
    )


class TestRotaDocumentos:
    def test_cria_documento(self, cliente_com_repositorio):
        cliente, repositorio = cliente_com_repositorio
        resposta = enviar_documento(cliente)
        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["titulo"] == "Meu documento"
        assert corpo["total_paginas"] == 2
        assert [p["ocr_text"] for p in repositorio.paginas] == ["abc", ""]

    def test_quantidades_diferentes(self, cliente_com_repositorio):
        cliente, _ = cliente_com_repositorio
        assert enviar_documento(cliente, quantidade_processadas=1).status_code == 422

    def test_filtro_invalido_nos_metadados(self, cliente_com_repositorio):
        cliente, _ = cliente_com_repositorio
        metadados = json.dumps([{"filtro": "sepia"}, {"filtro": "bw"}])
        assert enviar_documento(cliente, paginas_json=metadados).status_code == 422

    def test_falha_no_supabase_responde_502_sem_vazar_detalhes(self):
        app.dependency_overrides[obter_repositorio] = lambda: RepositorioFalso("inserir_paginas")
        try:
            resposta = enviar_documento(TestClient(app))
        finally:
            app.dependency_overrides.clear()
        assert resposta.status_code == 502
        assert "simulada" not in resposta.json()["detail"]

    def test_sem_configuracao_responde_503(self):
        resposta = enviar_documento(TestClient(app))
        assert resposta.status_code == 503


class TestHistorico:
    def test_caminho_no_bucket_aceita_caminho_e_url_publica_antiga(self):
        caminho = "documentos/a/documento.pdf"
        assert caminho_no_bucket(caminho, BUCKET) == caminho
        antiga = (
            "https://abc.supabase.co/storage/v1/object/public/miniscan-files/"
            "documentos/a/p%C3%A1gina.png"
        )
        assert caminho_no_bucket(antiga, BUCKET) == "documentos/a/página.png"
        assert caminho_no_bucket("https://outro.site/arquivo.pdf", BUCKET) is None
        assert caminho_no_bucket(None, BUCKET) is None

    def test_lista_so_os_documentos_da_conta_com_links_assinados(self):
        repositorio = RepositorioFalso()
        meu = salvar_documento(repositorio, USUARIO_TESTE_ID, "Meu", PDF, duas_paginas())
        salvar_documento(repositorio, OUTRA_CONTA, "De outra pessoa", PDF, duas_paginas())

        resumos = listar_historico(repositorio, USUARIO_TESTE_ID, "  contrato ", BUCKET)

        assert [r.titulo for r in resumos] == ["Meu"]
        assert repositorio.busca == (USUARIO_TESTE_ID, "contrato", 50)
        resumo = resumos[0]
        assert resumo.total_paginas == 2
        assert resumo.url_pdf.endswith(f"documentos/{meu.id}/documento.pdf?token=t")
        assert resumo.url_miniatura.endswith(
            f"documentos/{meu.id}/pagina-01-processada.png?token=t"
        )
        assert (resumo.filtro_capa, resumo.texto_capa) == ("bw", "primeira")
        # Todos os links saem numa chamada só, com validade de uma hora.
        assert repositorio.assinados[1] == 3600

    def test_abre_documento_com_paginas_em_ordem(self):
        repositorio = RepositorioFalso()
        salvo = salvar_documento(repositorio, USUARIO_TESTE_ID, "Meu", PDF, duas_paginas())

        documento = abrir_documento(repositorio, USUARIO_TESTE_ID, salvo.id, BUCKET)

        assert [p.ordem for p in documento.paginas] == [1, 2]
        assert documento.paginas[0].url_original.endswith("pagina-01-original.jpg?token=t")
        assert documento.paginas[1].url_processada.endswith("pagina-02-processada.jpg?token=t")
        assert len(repositorio.assinados[0]) == 5

    def test_documento_de_outra_conta_nao_abre(self):
        repositorio = RepositorioFalso()
        alheio = salvar_documento(repositorio, OUTRA_CONTA, "Alheio", PDF, duas_paginas())
        assert abrir_documento(repositorio, USUARIO_TESTE_ID, alheio.id, BUCKET) is None


class TestRotasHistorico:
    def test_lista_pela_api(self, cliente_com_repositorio):
        cliente, repositorio = cliente_com_repositorio
        assert enviar_documento(cliente).status_code == 201

        resposta = cliente.get("/documentos", params={"busca": "meu"})

        assert resposta.status_code == 200
        (item,) = resposta.json()
        assert item["titulo"] == "Meu documento"
        assert item["url_miniatura"].endswith("pagina-01-processada.png?token=t")
        assert repositorio.busca[:2] == (USUARIO_TESTE_ID, "meu")

    def test_abre_pela_api_e_esconde_documento_alheio(self, cliente_com_repositorio):
        cliente, repositorio = cliente_com_repositorio
        meu = enviar_documento(cliente).json()["id"]
        alheio = salvar_documento(repositorio, OUTRA_CONTA, "Alheio", PDF, duas_paginas()).id

        resposta = cliente.get(f"/documentos/{meu}")
        assert resposta.status_code == 200
        assert [p["ordem"] for p in resposta.json()["paginas"]] == [1, 2]
        assert cliente.get(f"/documentos/{alheio}").status_code == 404
        assert cliente.get("/documentos/nao-e-uuid").status_code == 422


def arquivos_do(documento_id: str, repositorio: RepositorioFalso) -> list[str]:
    return [c for c in repositorio.arquivos if c.startswith(f"documentos/{documento_id}/")]


class TestExcluirDocumento:
    def test_apaga_documento_paginas_e_arquivos_so_da_conta(self):
        repositorio = RepositorioFalso()
        meu = salvar_documento(repositorio, USUARIO_TESTE_ID, "Meu", PDF, duas_paginas())
        alheio = salvar_documento(repositorio, OUTRA_CONTA, "Alheio", PDF, duas_paginas())

        assert excluir_documento(repositorio, USUARIO_TESTE_ID, meu.id, BUCKET) is True

        assert list(repositorio.documentos) == [alheio.id]
        assert {p["document_id"] for p in repositorio.paginas} == {alheio.id}
        assert arquivos_do(meu.id, repositorio) == []
        assert len(arquivos_do(alheio.id, repositorio)) == 5

    def test_documento_de_outra_conta_fica_intacto(self):
        repositorio = RepositorioFalso()
        alheio = salvar_documento(repositorio, OUTRA_CONTA, "Alheio", PDF, duas_paginas())

        assert excluir_documento(repositorio, USUARIO_TESTE_ID, alheio.id, BUCKET) is False
        assert alheio.id in repositorio.documentos
        assert len(arquivos_do(alheio.id, repositorio)) == 5

    def test_falha_no_storage_nao_devolve_o_documento_ao_historico(self, caplog):
        repositorio = RepositorioFalso()
        meu = salvar_documento(repositorio, USUARIO_TESTE_ID, "Meu", PDF, duas_paginas())
        repositorio.falhar_em = "remover_arquivos"

        assert excluir_documento(repositorio, USUARIO_TESTE_ID, meu.id, BUCKET) is True
        assert meu.id not in repositorio.documentos
        # Os arquivos sobram no bucket privado, e o caso fica registrado no log.
        assert len(arquivos_do(meu.id, repositorio)) == 5
        assert "ficaram no bucket" in caplog.text

    def test_apaga_arquivos_de_documento_antigo_com_url_publica(self):
        repositorio = RepositorioFalso()
        meu = salvar_documento(repositorio, USUARIO_TESTE_ID, "Antigo", PDF, duas_paginas())
        publica = "https://abc.supabase.co/storage/v1/object/public/miniscan-files/"
        registro = repositorio.documentos[meu.id]
        registro["pdf_url"] = publica + registro["pdf_url"]

        assert excluir_documento(repositorio, USUARIO_TESTE_ID, meu.id, BUCKET) is True
        assert arquivos_do(meu.id, repositorio) == []


class TestRenomearDocumento:
    def test_renomeia_com_o_titulo_limpo(self):
        repositorio = RepositorioFalso()
        meu = salvar_documento(repositorio, USUARIO_TESTE_ID, "Velho", PDF, duas_paginas())

        novo = renomear_documento(repositorio, USUARIO_TESTE_ID, meu.id, "  Contrato   novo ")

        assert novo == "Contrato novo"
        assert repositorio.documentos[meu.id]["title"] == "Contrato novo"

    @pytest.mark.parametrize("titulo", ["   ", "x" * 201])
    def test_rejeita_titulo_invalido(self, titulo):
        repositorio = RepositorioFalso()
        meu = salvar_documento(repositorio, USUARIO_TESTE_ID, "Velho", PDF, duas_paginas())
        with pytest.raises(DocumentoInvalidoError):
            renomear_documento(repositorio, USUARIO_TESTE_ID, meu.id, titulo)
        assert repositorio.documentos[meu.id]["title"] == "Velho"

    def test_nao_renomeia_documento_de_outra_conta(self):
        repositorio = RepositorioFalso()
        alheio = salvar_documento(repositorio, OUTRA_CONTA, "Alheio", PDF, duas_paginas())
        assert renomear_documento(repositorio, USUARIO_TESTE_ID, alheio.id, "Meu agora") is None
        assert repositorio.documentos[alheio.id]["title"] == "Alheio"


class TestRotasExcluirERenomear:
    def test_exclui_pela_api(self, cliente_com_repositorio):
        cliente, repositorio = cliente_com_repositorio
        meu = enviar_documento(cliente).json()["id"]
        alheio = salvar_documento(repositorio, OUTRA_CONTA, "Alheio", PDF, duas_paginas()).id

        resposta = cliente.delete(f"/documentos/{meu}")

        assert resposta.status_code == 204
        assert resposta.content == b""
        assert cliente.get(f"/documentos/{meu}").status_code == 404
        assert cliente.delete(f"/documentos/{meu}").status_code == 404
        # Documento de outra conta responde como inexistente e não sai do banco.
        assert cliente.delete(f"/documentos/{alheio}").status_code == 404
        assert alheio in repositorio.documentos
        assert cliente.delete("/documentos/nao-e-uuid").status_code == 422

    def test_renomeia_pela_api(self, cliente_com_repositorio):
        cliente, repositorio = cliente_com_repositorio
        meu = enviar_documento(cliente).json()["id"]
        alheio = salvar_documento(repositorio, OUTRA_CONTA, "Alheio", PDF, duas_paginas()).id

        resposta = cliente.patch(f"/documentos/{meu}", json={"titulo": "  RG da Ana "})

        assert resposta.status_code == 200
        assert resposta.json() == {"id": meu, "titulo": "RG da Ana"}
        assert cliente.get(f"/documentos/{meu}").json()["titulo"] == "RG da Ana"
        assert cliente.patch(f"/documentos/{meu}", json={"titulo": "  "}).status_code == 422
        assert cliente.patch(f"/documentos/{meu}", json={}).status_code == 422
        assert cliente.patch(f"/documentos/{alheio}", json={"titulo": "Meu"}).status_code == 404
        assert repositorio.documentos[alheio]["title"] == "Alheio"
