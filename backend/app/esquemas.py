"""Contratos de entrada e saída da API."""

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


class RespostaLivro(BaseModel):
    esquerda: ListaDeCantos = Field(description="Cantos da página esquerda na foto original")
    direita: ListaDeCantos = Field(description="Cantos da página direita na foto original")
    lombada: float = Field(description="Posição da lombada (0..1) na largura do livro aberto")


class RespostaQrcode(BaseModel):
    textos: list[str]


class RespostaOcr(BaseModel):
    texto: str
    idioma: str


class RespostaSaude(BaseModel):
    status: str
    ocr_disponivel: bool
    persistencia_configurada: bool


class MetadadosPagina(BaseModel):
    filtro: Filtro
    texto_ocr: Annotated[str, Field(max_length=100_000)] = ""


ListaDeMetadados = Annotated[list[MetadadosPagina], Field(min_length=1)]
validador_metadados = TypeAdapter(ListaDeMetadados)


class RespostaDocumento(BaseModel):
    id: str
    titulo: str
    pdf_url: str
    total_paginas: int


class RespostaErro(BaseModel):
    detail: str
