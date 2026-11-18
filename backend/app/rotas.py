"""Rotas HTTP da API do MiniScan.

As rotas são síncronas de propósito: o processamento com OpenCV e onnxruntime usa CPU,
e o FastAPI executa rotas síncronas em uma thread separada, sem travar o servidor.
"""

from functools import lru_cache
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import ValidationError

from app.config import MAXIMO_PAGINAS_PDF, TAMANHO_MAXIMO_ARQUIVO, configuracoes
from app.esquemas import (
    MetadadosPagina,
    Ponto,
    RespostaCantos,
    RespostaDocumento,
    RespostaErro,
    RespostaOcr,
    RespostaSaude,
    validador_cantos,
    validador_metadados,
)
from app.ocr import IDIOMA_OCR, extrair_texto_ocr, ocr_disponivel
from app.pdf import gerar_pdf
from app.persistencia import (
    PaginaParaSalvar,
    RepositorioDocumentos,
    RepositorioSupabase,
    salvar_documento,
)
from app.visao.bordas import detectar_cantos
from app.visao.cartao import FormatoCartao, compor_cartao
from app.visao.docaligner import docaligner_disponivel
from app.visao.filtros import Filtro, aplicar_filtro, formato_saida
from app.visao.imagem import codificar_imagem, decodificar_imagem
from app.visao.perspectiva import corrigir_perspectiva

roteador = APIRouter()


ERROS_ENTRADA = {
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": RespostaErro},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": RespostaErro},
}


def ler_arquivo(arquivo: UploadFile) -> bytes:
    dados = arquivo.file.read(TAMANHO_MAXIMO_ARQUIVO + 1)
    if len(dados) > TAMANHO_MAXIMO_ARQUIVO:
        limite_mb = TAMANHO_MAXIMO_ARQUIVO // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Cada arquivo pode ter no máximo {limite_mb} MB.",
        )
    return dados


def ler_cantos(cantos_json: str) -> np.ndarray:
    try:
        pontos: list[Ponto] = validador_cantos.validate_json(cantos_json)
    except ValidationError as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            'Envie "cantos" como JSON com 4 pontos {"x": 0..1, "y": 0..1}.',
        ) from erro
    return np.array([[ponto.x, ponto.y] for ponto in pontos], dtype=np.float32)


@roteador.get("/saude", response_model=RespostaSaude, tags=["infra"])
def rota_saude() -> RespostaSaude:
    return RespostaSaude(
        status="ok",
        ocr_disponivel=ocr_disponivel(),
        docaligner_disponivel=docaligner_disponivel(),
        persistencia_configurada=configuracoes.persistencia_configurada,
    )


@roteador.post(
    "/detectar-cantos",
    response_model=RespostaCantos,
    responses=ERROS_ENTRADA,
    tags=["visao"],
    summary="Detecta os 4 cantos da folha na foto",
)
def rota_detectar_cantos(imagem: Annotated[UploadFile, File()]) -> RespostaCantos:
    matriz = decodificar_imagem(ler_arquivo(imagem))
    cantos, detectado = detectar_cantos(matriz)
    return RespostaCantos(
        cantos=[Ponto(x=float(x), y=float(y)) for x, y in cantos],
        detectado=detectado,
    )


@roteador.post(
    "/processar-pagina",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}}},
        **ERROS_ENTRADA,
    },
    tags=["visao"],
    summary="Corrige a perspectiva e aplica o filtro escolhido",
)
def rota_processar_pagina(
    imagem: Annotated[UploadFile, File()],
    cantos: Annotated[str, Form(description='JSON com 4 pontos, ex.: [{"x":0.1,"y":0.1}, ...]')],
    filtro: Annotated[Filtro, Form()] = "original",
) -> Response:
    matriz = decodificar_imagem(ler_arquivo(imagem))
    retificada = corrigir_perspectiva(matriz, ler_cantos(cantos))
    filtrada = aplicar_filtro(retificada, filtro)
    extensao, tipo_mime = formato_saida(filtro)
    return Response(content=codificar_imagem(filtrada, extensao), media_type=tipo_mime)


@roteador.post(
    "/extrair-ocr",
    response_model=RespostaOcr,
    responses={**ERROS_ENTRADA, status.HTTP_503_SERVICE_UNAVAILABLE: {"model": RespostaErro}},
    tags=["ocr"],
    summary="Extrai o texto da página (foto original + cantos), em pt-BR",
)
def rota_extrair_ocr(
    imagem: Annotated[UploadFile, File(description="Foto original da página (ou já retificada)")],
    cantos: Annotated[
        str | None,
        Form(description="Cantos da página na foto; com eles a API retifica a foto original"),
    ] = None,
) -> RespostaOcr:
    matriz = decodificar_imagem(ler_arquivo(imagem))
    # O OCR lê sempre a página retificada sem filtro: com os cantos, a própria API
    # retifica a foto original (mesma função do /processar-pagina), sem depender do
    # filtro escolhido para exibição.
    if cantos is not None:
        matriz = corrigir_perspectiva(matriz, ler_cantos(cantos))
    texto = extrair_texto_ocr(matriz)
    return RespostaOcr(texto=texto, idioma=IDIOMA_OCR)


@roteador.post(
    "/gerar-pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}, **ERROS_ENTRADA},
    tags=["pdf"],
    summary="Junta as páginas, na ordem enviada, em um PDF único",
)
def rota_gerar_pdf(
    paginas: Annotated[list[UploadFile], File()],
    carimbo: Annotated[
        str | None, Form(description="Data e hora escritas em cada página, ex.: 16/11/2026 14:32")
    ] = None,
) -> Response:
    if len(paginas) > MAXIMO_PAGINAS_PDF:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"O PDF aceita no máximo {MAXIMO_PAGINAS_PDF} páginas.",
        )
    pdf = gerar_pdf([ler_arquivo(pagina) for pagina in paginas], carimbo=carimbo)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="miniscan.pdf"'},
    )


@roteador.post(
    "/compor-cartao",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}, **ERROS_ENTRADA},
    tags=["visao"],
    summary="Monta frente e verso do documento numa folha A4, em tamanho real",
)
def rota_compor_cartao(
    frente: Annotated[UploadFile, File(description="Frente já retificada")],
    formato: Annotated[FormatoCartao, Form()] = "id",
    verso: Annotated[UploadFile | None, File(description="Verso já retificado")] = None,
) -> Response:
    lados = [decodificar_imagem(ler_arquivo(frente))]
    if verso is not None:
        lados.append(decodificar_imagem(ler_arquivo(verso)))
    folha = compor_cartao(lados, formato)
    return Response(content=codificar_imagem(folha, ".jpg"), media_type="image/jpeg")


@lru_cache(maxsize=1)
def _repositorio_supabase() -> RepositorioSupabase:
    return RepositorioSupabase(
        configuracoes.supabase_url, configuracoes.supabase_chave_servico, configuracoes.bucket
    )


def obter_repositorio() -> RepositorioDocumentos:
    if not configuracoes.persistencia_configurada:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Persistência não configurada: defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.",
        )
    return _repositorio_supabase()


def ler_metadados(paginas_json: str) -> list[MetadadosPagina]:
    try:
        return validador_metadados.validate_json(paginas_json)
    except ValidationError as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            'Envie "paginas" como JSON: [{"filtro": "original|grayscale|bw", "texto_ocr": "..."}].',
        ) from erro


@roteador.post(
    "/documentos",
    status_code=status.HTTP_201_CREATED,
    response_model=RespostaDocumento,
    responses={
        **ERROS_ENTRADA,
        status.HTTP_502_BAD_GATEWAY: {"model": RespostaErro},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": RespostaErro},
    },
    tags=["historico"],
    summary="Salva PDF, imagens e textos OCR no histórico (Supabase)",
)
def rota_salvar_documento(
    repositorio: Annotated[RepositorioDocumentos, Depends(obter_repositorio)],
    titulo: Annotated[str, Form()],
    pdf: Annotated[UploadFile, File()],
    originais: Annotated[list[UploadFile], File(description="Fotos originais, na ordem")],
    processadas: Annotated[list[UploadFile], File(description="Páginas filtradas, na ordem")],
    paginas: Annotated[
        str, Form(description='JSON na ordem: [{"filtro": "bw", "texto_ocr": "..."}]')
    ],
) -> RespostaDocumento:
    metadados = ler_metadados(paginas)
    if not len(originais) == len(processadas) == len(metadados):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Envie a mesma quantidade de originais, processadas e itens em 'paginas'.",
        )
    if len(metadados) > MAXIMO_PAGINAS_PDF:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"O documento aceita no máximo {MAXIMO_PAGINAS_PDF} páginas.",
        )

    salvo = salvar_documento(
        repositorio,
        titulo,
        ler_arquivo(pdf),
        [
            PaginaParaSalvar(
                original=ler_arquivo(original),
                processada=ler_arquivo(processada),
                filtro=meta.filtro,
                texto_ocr=meta.texto_ocr,
            )
            for original, processada, meta in zip(originais, processadas, metadados, strict=True)
        ],
    )
    return RespostaDocumento(
        id=salvo.id, titulo=salvo.titulo, pdf_url=salvo.pdf_url, total_paginas=salvo.total_paginas
    )
