"""Contratos de entrada e saída da API."""

from typing import Annotated

from pydantic import BaseModel, Field, TypeAdapter

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
    idioma: str


class RespostaSaude(BaseModel):
    status: str
    ocr_disponivel: bool


class RespostaErro(BaseModel):
    detail: str
