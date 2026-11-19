"""Rotas HTTP da API do MiniScan.

As rotas são síncronas de propósito: o processamento com OpenCV e onnxruntime usa CPU,
e o FastAPI executa rotas síncronas em uma thread separada, sem travar o servidor.

Só o /saude é público (``roteador_publico``). Tudo do ``roteador`` exige sessão: o
app/main.py o inclui com a dependência ``usuario_logado``.
"""

import logging
import uuid
from functools import lru_cache
from typing import Annotated

import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError

from app.config import MAXIMO_PAGINAS_PDF, TAMANHO_MAXIMO_ARQUIVO, configuracoes
from app.contas import Usuario
from app.esquemas import (
    DocumentoCompleto,
    DocumentoRenomeado,
    MetadadosPagina,
    PedidoRenomear,
    Ponto,
    RespostaCantos,
    RespostaDocumento,
    RespostaErro,
    RespostaOcr,
    RespostaSaude,
    ResumoDocumento,
    validador_cantos,
    validador_metadados,
)
from app.ocr import IDIOMA_OCR, ler_pagina, ocr_disponivel
from app.pdf import gerar_pdf
from app.persistencia import (
    PaginaParaSalvar,
    RepositorioDocumentos,
    RepositorioSupabase,
    abrir_documento,
    excluir_documento,
    listar_historico,
    renomear_documento,
    salvar_documento,
)
from app.rotas_contas import cliente_supabase, usuario_logado
from app.visao.bordas import detectar_cantos
from app.visao.cartao import FormatoCartao, compor_cartao
from app.visao.docaligner import docaligner_disponivel
from app.visao.filtros import Filtro, aplicar_filtro, formato_saida
from app.visao.imagem import codificar_imagem, decodificar_imagem
from app.visao.perspectiva import corrigir_perspectiva

logger = logging.getLogger(__name__)

roteador_publico = APIRouter()
roteador = APIRouter(responses={status.HTTP_401_UNAUTHORIZED: {"model": RespostaErro}})


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


@roteador_publico.get("/saude", response_model=RespostaSaude, tags=["infra"])
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
    summary="Extrai o texto da página (foto original + cantos) e sugere um nome",
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
    leitura = ler_pagina(matriz)
    return RespostaOcr(texto=leitura.texto, titulo=leitura.titulo, idioma=IDIOMA_OCR)


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
    summary="Monta frente e verso do documento numa folha A4, ampliados",
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
    return RepositorioSupabase(cliente_supabase(), configuracoes.bucket)


def obter_repositorio() -> RepositorioDocumentos:
    if not configuracoes.persistencia_configurada:
        logger.error("Histórico indisponível: SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY ausente")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "O histórico está indisponível no momento."
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
    usuario: Annotated[Usuario, Depends(usuario_logado)],
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
        usuario.id,
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
    return RespostaDocumento(id=salvo.id, titulo=salvo.titulo, total_paginas=salvo.total_paginas)


ERROS_HISTORICO = {
    status.HTTP_502_BAD_GATEWAY: {"model": RespostaErro},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": RespostaErro},
}


@roteador.get(
    "/documentos",
    response_model=list[ResumoDocumento],
    responses=ERROS_HISTORICO,
    tags=["historico"],
    summary="Documentos da conta, do mais novo ao mais antigo (busca no título e no OCR)",
)
def rota_listar_documentos(
    usuario: Annotated[Usuario, Depends(usuario_logado)],
    repositorio: Annotated[RepositorioDocumentos, Depends(obter_repositorio)],
    busca: Annotated[str, Query(max_length=200)] = "",
) -> list[ResumoDocumento]:
    resumos = listar_historico(repositorio, usuario.id, busca, configuracoes.bucket)
    return [ResumoDocumento.model_validate(r, from_attributes=True) for r in resumos]


@roteador.get(
    "/documentos/{documento_id}",
    response_model=DocumentoCompleto,
    responses={**ERROS_HISTORICO, status.HTTP_404_NOT_FOUND: {"model": RespostaErro}},
    tags=["historico"],
    summary="Um documento da conta com todas as páginas, o texto e o PDF",
)
def rota_abrir_documento(
    documento_id: uuid.UUID,
    usuario: Annotated[Usuario, Depends(usuario_logado)],
    repositorio: Annotated[RepositorioDocumentos, Depends(obter_repositorio)],
) -> DocumentoCompleto:
    documento = abrir_documento(repositorio, usuario.id, str(documento_id), configuracoes.bucket)
    # Documento de outra conta responde igual a documento inexistente.
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    return DocumentoCompleto.model_validate(documento, from_attributes=True)


@roteador.patch(
    "/documentos/{documento_id}",
    response_model=DocumentoRenomeado,
    responses={
        **ERROS_HISTORICO,
        status.HTTP_404_NOT_FOUND: {"model": RespostaErro},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": RespostaErro},
    },
    tags=["historico"],
    summary="Muda o nome (título) de um documento da conta",
)
def rota_renomear_documento(
    documento_id: uuid.UUID,
    pedido: PedidoRenomear,
    usuario: Annotated[Usuario, Depends(usuario_logado)],
    repositorio: Annotated[RepositorioDocumentos, Depends(obter_repositorio)],
) -> DocumentoRenomeado:
    titulo = renomear_documento(repositorio, usuario.id, str(documento_id), pedido.titulo)
    if titulo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    return DocumentoRenomeado(id=str(documento_id), titulo=titulo)


@roteador.delete(
    "/documentos/{documento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**ERROS_HISTORICO, status.HTTP_404_NOT_FOUND: {"model": RespostaErro}},
    tags=["historico"],
    summary="Apaga um documento da conta, com as páginas, o PDF e as imagens",
)
def rota_excluir_documento(
    documento_id: uuid.UUID,
    usuario: Annotated[Usuario, Depends(usuario_logado)],
    repositorio: Annotated[RepositorioDocumentos, Depends(obter_repositorio)],
) -> Response:
    if not excluir_documento(repositorio, usuario.id, str(documento_id), configuracoes.bucket):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
