"""Histórico de documentos no Supabase (Storage + Postgres), separado por dono.

A API é a única que lê e grava: usa a chave de serviço, que ignora as políticas RLS.
Desde a migração 20261118000004, os papéis públicos não leem nada, o bucket é
privado e cada documento tem dono (``documents.usuario_id``). Os arquivos chegam ao
navegador por links assinados, que valem por pouco tempo.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import unquote

from app.visao.filtros import Filtro

logger = logging.getLogger(__name__)

TIPOS_IMAGEM = {
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
}
TAMANHO_MAXIMO_TITULO = 200
MAXIMO_DOCUMENTOS_LISTA = 50
# Validade dos links assinados dos arquivos (miniaturas, páginas e PDF).
VALIDADE_LINK_S = 60 * 60


class DocumentoInvalidoError(ValueError):
    """Os dados enviados para salvar o documento estão incompletos ou inconsistentes."""


class FalhaPersistenciaError(RuntimeError):
    """O Supabase recusou ou não respondeu a uma das etapas de gravação."""


class RepositorioDocumentos(Protocol):
    def enviar_arquivo(self, caminho: str, dados: bytes, tipo_mime: str) -> None: ...

    def remover_arquivos(self, caminhos: list[str]) -> None: ...

    def inserir_documento(self, registro: dict) -> None: ...

    def inserir_paginas(self, registros: list[dict]) -> None: ...

    def remover_documento(self, documento_id: str, usuario_id: str | None = None) -> None:
        """Apaga a linha do documento (as páginas caem em cascata); com dono, só se for dele."""
        ...

    def atualizar_titulo(self, usuario_id: str, documento_id: str, titulo: str) -> bool:
        """Troca o título do documento do dono. False se não existe ou é de outra conta."""
        ...

    def listar_documentos(self, usuario_id: str, termo: str, limite: int) -> list[dict]:
        """Documentos do dono, do mais novo para o mais antigo, só com a 1ª página."""
        ...

    def obter_documento(self, usuario_id: str, documento_id: str) -> dict | None:
        """O documento com todas as páginas, só se for do dono."""
        ...

    def assinar_urls(self, caminhos: list[str], validade_s: int) -> dict[str, str]:
        """Link temporário de cada caminho do bucket (os que falharem ficam de fora)."""
        ...


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
    total_paginas: int


@dataclass(frozen=True)
class PaginaGuardada:
    id: str
    ordem: int
    url_original: str | None
    url_processada: str | None
    filtro: Filtro
    texto_ocr: str


@dataclass(frozen=True)
class ResumoDocumento:
    id: str
    titulo: str
    total_paginas: int
    criado_em: str
    url_pdf: str | None
    url_miniatura: str | None
    filtro_capa: Filtro | None
    texto_capa: str


@dataclass(frozen=True)
class DocumentoGuardado:
    id: str
    titulo: str
    total_paginas: int
    criado_em: str
    url_pdf: str | None
    paginas: list[PaginaGuardada]


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
    usuario_id: str,
    titulo: str,
    pdf: bytes,
    paginas: list[PaginaParaSalvar],
) -> DocumentoSalvo:
    """Envia PDF e imagens ao Storage e registra documento e páginas no banco.

    As colunas ``*_url`` guardam o caminho do arquivo no bucket, e não um link: o
    bucket é privado, e o link de leitura é assinado na hora de abrir o histórico.

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
        repositorio.enviar_arquivo(caminho, dados, tipo_mime)
        enviados.append(caminho)
        return caminho

    # Valida todos os tipos antes de começar a enviar qualquer arquivo.
    tipos = [
        (
            _tipo_imagem(pagina.original, f"A imagem original da página {numero}"),
            _tipo_imagem(pagina.processada, f"A imagem processada da página {numero}"),
        )
        for numero, pagina in enumerate(paginas, 1)
    ]

    try:
        caminho_pdf = enviar(f"{pasta}/documento.pdf", pdf, "application/pdf")
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

        repositorio.inserir_documento(
            {"id": documento_id, "usuario_id": usuario_id, "title": titulo, "pdf_url": caminho_pdf}
        )
        documento_inserido = True
        # O gatilho trg_sync_page_count atualiza documents.page_count sozinho.
        repositorio.inserir_paginas(registros_paginas)
    except Exception as erro:
        _desfazer(repositorio, documento_id if documento_inserido else None, enviados)
        raise FalhaPersistenciaError("Não foi possível salvar o documento.") from erro

    return DocumentoSalvo(id=documento_id, titulo=titulo, total_paginas=len(paginas))


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


def caminho_no_bucket(valor: str | None, bucket: str) -> str | None:
    """Caminho do arquivo dentro do bucket.

    Documentos novos já guardam o caminho. Os salvos antes do login guardavam a URL
    pública inteira (``.../object/public/<bucket>/<caminho>``), convertida aqui.
    """
    if not valor:
        return None
    if not valor.startswith(("http://", "https://")):
        return valor
    marcador = f"/object/public/{bucket}/"
    posicao = valor.find(marcador)
    return unquote(valor[posicao + len(marcador) :]) if posicao >= 0 else None


def _assinador(repositorio: RepositorioDocumentos, valores: list[str | None], bucket: str):
    """Assina todos os arquivos de uma vez e devolve a função que acha o link de cada um."""
    caminhos = {caminho for valor in valores if (caminho := caminho_no_bucket(valor, bucket))}
    links = repositorio.assinar_urls(sorted(caminhos), VALIDADE_LINK_S) if caminhos else {}

    def link(valor: str | None) -> str | None:
        caminho = caminho_no_bucket(valor, bucket)
        return links.get(caminho) if caminho else None

    return link


def listar_historico(
    repositorio: RepositorioDocumentos, usuario_id: str, termo: str, bucket: str
) -> list[ResumoDocumento]:
    linhas = repositorio.listar_documentos(usuario_id, termo.strip(), MAXIMO_DOCUMENTOS_LISTA)
    capas = [(linha.get("document_pages") or [None])[0] for linha in linhas]
    link = _assinador(
        repositorio,
        [linha.get("pdf_url") for linha in linhas]
        + [capa["processed_image_url"] for capa in capas if capa],
        bucket,
    )
    return [
        ResumoDocumento(
            id=linha["id"],
            titulo=linha["title"],
            total_paginas=linha["page_count"],
            criado_em=linha["created_at"],
            url_pdf=link(linha.get("pdf_url")),
            url_miniatura=link(capa["processed_image_url"]) if capa else None,
            filtro_capa=capa["filter_applied"] if capa else None,
            texto_capa=capa["ocr_text"] if capa else "",
        )
        for linha, capa in zip(linhas, capas, strict=True)
    ]


def abrir_documento(
    repositorio: RepositorioDocumentos, usuario_id: str, documento_id: str, bucket: str
) -> DocumentoGuardado | None:
    """O documento com links para todas as páginas, ou None se não existe ou é de outra conta."""
    linha = repositorio.obter_documento(usuario_id, documento_id)
    if linha is None:
        return None
    paginas = sorted(linha.get("document_pages") or [], key=lambda p: p["page_order"])
    link = _assinador(
        repositorio,
        [linha.get("pdf_url")]
        + [p["original_image_url"] for p in paginas]
        + [p["processed_image_url"] for p in paginas],
        bucket,
    )
    return DocumentoGuardado(
        id=linha["id"],
        titulo=linha["title"],
        total_paginas=linha["page_count"],
        criado_em=linha["created_at"],
        url_pdf=link(linha.get("pdf_url")),
        paginas=[
            PaginaGuardada(
                id=p["id"],
                ordem=p["page_order"],
                url_original=link(p["original_image_url"]),
                url_processada=link(p["processed_image_url"]),
                filtro=p["filter_applied"],
                texto_ocr=p["ocr_text"],
            )
            for p in paginas
        ],
    )


def renomear_documento(
    repositorio: RepositorioDocumentos, usuario_id: str, documento_id: str, titulo: str
) -> str | None:
    """Novo título já limpo, ou None se o documento não existe ou é de outra conta."""
    titulo = validar_titulo(titulo)
    if not repositorio.atualizar_titulo(usuario_id, documento_id, titulo):
        return None
    return titulo


def excluir_documento(
    repositorio: RepositorioDocumentos, usuario_id: str, documento_id: str, bucket: str
) -> bool:
    """Apaga o documento da conta, com as páginas e os arquivos. False se não existe ou é alheio.

    Primeiro sai a linha do banco (as páginas caem em cascata), e o documento some do
    histórico. Os arquivos saem depois: se o Storage falhar nessa hora, eles sobram no
    bucket privado, onde ninguém os alcança sem um link assinado, e o caso vai para o log.
    Na ordem inversa, uma falha no banco deixaria no histórico um documento sem arquivos.
    """
    linha = repositorio.obter_documento(usuario_id, documento_id)
    if linha is None:
        return False
    paginas = linha.get("document_pages") or []
    valores = [linha.get("pdf_url")]
    valores += [p.get("original_image_url") for p in paginas]
    valores += [p.get("processed_image_url") for p in paginas]
    caminhos = sorted({c for valor in valores if (c := caminho_no_bucket(valor, bucket))})

    repositorio.remover_documento(documento_id, usuario_id)
    if caminhos:
        try:
            repositorio.remover_arquivos(caminhos)
        except Exception:
            logger.exception(
                "Documento %s apagado, mas os arquivos ficaram no bucket", documento_id
            )
    return True


CAMPOS_LISTA = (
    "id, title, pdf_url, page_count, created_at, "
    "document_pages(processed_image_url, ocr_text, filter_applied, page_order)"
)
CAMPOS_DOCUMENTO = (
    "id, title, pdf_url, page_count, created_at, document_pages(id, page_order, "
    "original_image_url, processed_image_url, filter_applied, ocr_text)"
)


class RepositorioSupabase:
    """Implementação real usando o cliente oficial supabase-py."""

    def __init__(self, cliente, bucket: str) -> None:
        self._cliente = cliente
        self._bucket = bucket

    def enviar_arquivo(self, caminho: str, dados: bytes, tipo_mime: str) -> None:
        self._cliente.storage.from_(self._bucket).upload(
            caminho, dados, {"content-type": tipo_mime, "upsert": "false"}
        )

    def remover_arquivos(self, caminhos: list[str]) -> None:
        self._cliente.storage.from_(self._bucket).remove(caminhos)

    def inserir_documento(self, registro: dict) -> None:
        self._cliente.table("documents").insert(registro).execute()

    def inserir_paginas(self, registros: list[dict]) -> None:
        self._cliente.table("document_pages").insert(registros).execute()

    def remover_documento(self, documento_id: str, usuario_id: str | None = None) -> None:
        consulta = self._cliente.table("documents").delete().eq("id", documento_id)
        if usuario_id is not None:
            consulta = consulta.eq("usuario_id", usuario_id)
        consulta.execute()

    def atualizar_titulo(self, usuario_id: str, documento_id: str, titulo: str) -> bool:
        # O PostgREST devolve as linhas alteradas: nenhuma = não existe ou é de outra conta.
        resposta = (
            self._cliente.table("documents")
            .update({"title": titulo})
            .eq("id", documento_id)
            .eq("usuario_id", usuario_id)
            .execute()
        )
        return bool(resposta.data)

    def listar_documentos(self, usuario_id: str, termo: str, limite: int) -> list[dict]:
        # A função do banco filtra pelo dono e busca no título e no OCR (português).
        # O embutido traz só a primeira página de cada documento, para a miniatura.
        resposta = (
            self._cliente.rpc("buscar_documentos_usuario", {"termo": termo, "dono": usuario_id})
            .select(CAMPOS_LISTA)
            .order("created_at", desc=True)
            .order("page_order", foreign_table="document_pages")
            .limit(1, foreign_table="document_pages")
            .limit(limite)
            .execute()
        )
        return resposta.data or []

    def obter_documento(self, usuario_id: str, documento_id: str) -> dict | None:
        resposta = (
            self._cliente.table("documents")
            .select(CAMPOS_DOCUMENTO)
            .eq("id", documento_id)
            .eq("usuario_id", usuario_id)
            .limit(1)
            .execute()
        )
        return resposta.data[0] if resposta.data else None

    def assinar_urls(self, caminhos: list[str], validade_s: int) -> dict[str, str]:
        itens = self._cliente.storage.from_(self._bucket).create_signed_urls(caminhos, validade_s)
        return {
            item["path"]: item["signedURL"]
            for item in itens
            if item.get("path") and item.get("signedURL") and not item.get("error")
        }
