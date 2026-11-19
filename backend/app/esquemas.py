"""Contratos de entrada e saída da API."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, TypeAdapter

from app.visao.filtros import Filtro

Coordenada = Annotated[float, Field(ge=0, le=1)]


class Ponto(BaseModel):
    x: Coordenada
    y: Coordenada


ListaDeCantos = Annotated[list[Ponto], Field(min_length=4, max_length=4)]
validador_cantos = TypeAdapter(ListaDeCantos)


class RespostaCantos(BaseModel):
    cantos: ListaDeCantos = Field(
        description="Cantos normalizados (0..1) na ordem: superior esquerdo, "
        "superior direito, inferior direito, inferior esquerdo."
    )
    detectado: bool = Field(
        description="Falso quando a folha não foi encontrada e os cantos cobrem a imagem inteira."
    )


class RespostaOcr(BaseModel):
    texto: str
    titulo: str = Field(
        default="",
        description="Sugestão de nome para o documento: a linha de letra maior na metade de "
        "cima da página ou, sem destaque, a primeira com palavras. Vazio se nada servir.",
    )
    idioma: str


class RespostaSaude(BaseModel):
    status: str
    ocr_disponivel: bool
    docaligner_disponivel: bool = Field(
        description="Falso quando o modelo de cantos não carregou e só o OpenCV detecta a folha."
    )
    persistencia_configurada: bool


class MetadadosPagina(BaseModel):
    filtro: Filtro
    texto_ocr: Annotated[str, Field(max_length=100_000)] = ""


ListaDeMetadados = Annotated[list[MetadadosPagina], Field(min_length=1)]
validador_metadados = TypeAdapter(ListaDeMetadados)


class RespostaDocumento(BaseModel):
    id: str
    titulo: str
    total_paginas: int


class PedidoRenomear(BaseModel):
    # O limite real (200 caracteres, sem ficar vazio) fica em app/persistencia.py.
    titulo: Annotated[str, Field(max_length=1000)]


class DocumentoRenomeado(BaseModel):
    id: str
    titulo: str


class ResumoDocumento(BaseModel):
    """Um item do histórico, com a primeira página como capa."""

    id: str
    titulo: str
    total_paginas: int
    criado_em: datetime
    url_pdf: str | None = Field(description="Link temporário (1 hora) do PDF")
    url_miniatura: str | None = Field(description="Link temporário da 1ª página tratada")
    filtro_capa: Filtro | None
    texto_capa: str = Field(description="Texto do OCR da 1ª página")


class PaginaDocumento(BaseModel):
    id: str
    ordem: int
    url_original: str | None
    url_processada: str | None
    filtro: Filtro
    texto_ocr: str


class DocumentoCompleto(BaseModel):
    id: str
    titulo: str
    total_paginas: int
    criado_em: datetime
    url_pdf: str | None
    paginas: list[PaginaDocumento]


# Os limites aqui só protegem a memória; as regras (tamanho mínimo da senha, formato
# do e-mail) ficam em app/contas.py, com mensagens em português.
class PedidoCadastro(BaseModel):
    nome: Annotated[str, Field(max_length=500)]
    email: Annotated[str, Field(max_length=500)]
    senha: Annotated[str, Field(max_length=1024)]


class PedidoEntrada(BaseModel):
    email: Annotated[str, Field(max_length=500)]
    senha: Annotated[str, Field(max_length=1024)]


class RespostaUsuario(BaseModel):
    id: str
    nome: str
    email: str


class RespostaSessao(BaseModel):
    token: str = Field(description="Enviar em toda chamada: Authorization: Bearer <token>")
    expira_em: datetime
    usuario: RespostaUsuario


class RespostaErro(BaseModel):
    detail: str
