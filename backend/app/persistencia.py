"""Gravação do documento digitalizado no Supabase (Storage + Postgres).

A API é a única que grava: usa a chave de serviço, que ignora as políticas RLS.
O papel anônimo do front-end só tem leitura (migração 20261116000002).
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.visao.filtros import Filtro

logger = logging.getLogger(__name__)

TIPOS_IMAGEM = {
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
}
TAMANHO_MAXIMO_TITULO = 200


class DocumentoInvalidoError(ValueError):
    """Os dados enviados para salvar o documento estão incompletos ou inconsistentes."""


class FalhaPersistenciaError(RuntimeError):
    """O Supabase recusou ou não respondeu a uma das etapas de gravação."""


class RepositorioDocumentos(Protocol):
    def enviar_arquivo(self, caminho: str, dados: bytes, tipo_mime: str) -> str:
        """Faz o upload e devolve a URL pública do arquivo."""
        ...

    def remover_arquivos(self, caminhos: list[str]) -> None: ...

    def inserir_documento(self, registro: dict) -> None: ...

    def inserir_paginas(self, registros: list[dict]) -> None: ...

    def remover_documento(self, documento_id: str) -> None: ...


@dataclass(frozen=True)
class PaginaParaSalvar:
    original: bytes
    processada: bytes
    filtro: Filtro
    texto_ocr: str


@dataclass(frozen=True)
class DocumentoSalvo:
    id: str
    titulo: str
    pdf_url: str
    total_paginas: int


def identificar_tipo(dados: bytes) -> tuple[str, str] | None:
    """Tipo MIME e extensão pelos bytes iniciais (WebP: RIFF....WEBP)."""
    for assinatura, tipo in TIPOS_IMAGEM.items():
        if dados.startswith(assinatura):
            return tipo
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp", "webp"
    if dados.startswith(b"%PDF"):
        return "application/pdf", "pdf"
    return None


def _tipo_imagem(dados: bytes, descricao: str) -> tuple[str, str]:
    tipo = identificar_tipo(dados)
    if tipo is None or tipo[0] == "application/pdf":
        raise DocumentoInvalidoError(f"{descricao} precisa ser JPEG, PNG ou WebP.")
    return tipo


def validar_titulo(titulo: str) -> str:
    limpo = " ".join(titulo.split())
    if not limpo:
        raise DocumentoInvalidoError("Informe um título para o documento.")
    if len(limpo) > TAMANHO_MAXIMO_TITULO:
        raise DocumentoInvalidoError(
            f"O título pode ter no máximo {TAMANHO_MAXIMO_TITULO} caracteres."
        )
    return limpo


def salvar_documento(
    repositorio: RepositorioDocumentos,
    titulo: str,
    pdf: bytes,
    paginas: list[PaginaParaSalvar],
) -> DocumentoSalvo:
    """Envia PDF e imagens ao Storage e registra documento e páginas no banco.

    Se qualquer etapa falhar, desfaz o que já foi gravado (arquivos e linhas),
    para não deixar documento pela metade no histórico.
    """
    titulo = validar_titulo(titulo)
    if not paginas:
        raise DocumentoInvalidoError("Envie ao menos uma página.")
    if identificar_tipo(pdf) != ("application/pdf", "pdf"):
        raise DocumentoInvalidoError("O arquivo do documento precisa ser um PDF.")

    documento_id = str(uuid.uuid4())
    pasta = f"documentos/{documento_id}"
    enviados: list[str] = []
    documento_inserido = False

    def enviar(caminho: str, dados: bytes, tipo_mime: str) -> str:
        url = repositorio.enviar_arquivo(caminho, dados, tipo_mime)
        enviados.append(caminho)
        return url

    # Valida todos os tipos antes de começar a enviar qualquer arquivo.
    tipos = [
        (
            _tipo_imagem(pagina.original, f"A imagem original da página {numero}"),
            _tipo_imagem(pagina.processada, f"A imagem processada da página {numero}"),
        )
        for numero, pagina in enumerate(paginas, 1)
    ]

    try:
        pdf_url = enviar(f"{pasta}/documento.pdf", pdf, "application/pdf")
        registros_paginas = []
        for numero, (pagina, (tipo_original, tipo_processada)) in enumerate(
            zip(paginas, tipos, strict=True), 1
        ):
            prefixo = f"{pasta}/pagina-{numero:02d}"
            registros_paginas.append(
                {
                    "document_id": documento_id,
                    "page_order": numero,
                    "original_image_url": enviar(
                        f"{prefixo}-original.{tipo_original[1]}", pagina.original, tipo_original[0]
                    ),
                    "processed_image_url": enviar(
                        f"{prefixo}-processada.{tipo_processada[1]}",
                        pagina.processada,
                        tipo_processada[0],
                    ),
                    "filter_applied": pagina.filtro,
                    "ocr_text": pagina.texto_ocr,
                }
            )

        repositorio.inserir_documento({"id": documento_id, "title": titulo, "pdf_url": pdf_url})
        documento_inserido = True
        # O gatilho trg_sync_page_count atualiza documents.page_count sozinho.
        repositorio.inserir_paginas(registros_paginas)
    except Exception as erro:
        _desfazer(repositorio, documento_id if documento_inserido else None, enviados)
        raise FalhaPersistenciaError("Não foi possível salvar o documento no Supabase.") from erro

    return DocumentoSalvo(
        id=documento_id, titulo=titulo, pdf_url=pdf_url, total_paginas=len(paginas)
    )


def _desfazer(
    repositorio: RepositorioDocumentos, documento_id: str | None, caminhos: list[str]
) -> None:
    """Melhor esforço: registra no log o que não deu para apagar, sem esconder o erro original."""
    if documento_id:
        try:
            repositorio.remover_documento(documento_id)  # as páginas caem em cascata
        except Exception:
            logger.exception("Falha ao remover o documento %s após erro", documento_id)
    if caminhos:
        try:
            repositorio.remover_arquivos(caminhos)
        except Exception:
            logger.exception("Falha ao remover arquivos órfãos: %s", caminhos)


class RepositorioSupabase:
    """Implementação real usando o cliente oficial supabase-py."""

    def __init__(self, url: str, chave_servico: str, bucket: str) -> None:
        from supabase import create_client

        self._cliente = create_client(url, chave_servico)
        self._bucket = bucket

    def enviar_arquivo(self, caminho: str, dados: bytes, tipo_mime: str) -> str:
        armazenamento = self._cliente.storage.from_(self._bucket)
        armazenamento.upload(caminho, dados, {"content-type": tipo_mime, "upsert": "false"})
        return armazenamento.get_public_url(caminho)

    def remover_arquivos(self, caminhos: list[str]) -> None:
        self._cliente.storage.from_(self._bucket).remove(caminhos)

    def inserir_documento(self, registro: dict) -> None:
        self._cliente.table("documents").insert(registro).execute()

    def inserir_paginas(self, registros: list[dict]) -> None:
        self._cliente.table("document_pages").insert(registros).execute()

    def remover_documento(self, documento_id: str) -> None:
        self._cliente.table("documents").delete().eq("id", documento_id).execute()
