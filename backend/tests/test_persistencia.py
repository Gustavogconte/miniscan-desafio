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
    salvar_documento,
)
from app.rotas import obter_repositorio

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
        return f"https://exemplo.supabase.co/storage/v1/object/public/miniscan-files/{caminho}"

    def remover_arquivos(self, caminhos):
        for caminho in caminhos:
            self.arquivos.pop(caminho, None)

    def inserir_documento(self, registro):
        self._talvez_falhar("inserir_documento")
        self.documentos[registro["id"]] = registro

    def inserir_paginas(self, registros):
        self._talvez_falhar("inserir_paginas")
        self.paginas.extend(registros)

    def remover_documento(self, documento_id):
        self.documentos.pop(documento_id, None)
        self.paginas = [p for p in self.paginas if p["document_id"] != documento_id]


def duas_paginas() -> list[PaginaParaSalvar]:
    return [
        PaginaParaSalvar(original=JPEG, processada=PNG, filtro="bw", texto_ocr="primeira"),
        PaginaParaSalvar(original=JPEG, processada=JPEG, filtro="grayscale", texto_ocr=""),
    ]


class TestSalvarDocumento:
    def test_salva_arquivos_documento_e_paginas(self):
        repositorio = RepositorioFalso()
        salvo = salvar_documento(repositorio, "  Contrato   de estágio ", PDF, duas_paginas())

        assert salvo.titulo == "Contrato de estágio"
        assert salvo.total_paginas == 2
        assert salvo.pdf_url.endswith(f"documentos/{salvo.id}/documento.pdf")
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
            salvar_documento(repositorio, "Documento", PDF, duas_paginas())
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
            salvar_documento(repositorio, titulo, pdf, paginas)
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
