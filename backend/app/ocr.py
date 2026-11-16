"""Extração de texto com PaddleOCR (modelos PP-OCRv5 latinos em ONNX, via RapidOCR).

O modelo latino cobre o português com acentos. Tudo roda no onnxruntime, sem
binários instalados no sistema operacional e sem PyTorch.
"""

import logging
import threading
from collections.abc import Sequence

import cv2
import numpy as np

from app.visao.layout import DetectorLayout, Regiao, mascarar_regioes

logger = logging.getLogger(__name__)

IDIOMA_OCR = "latin"  # modelo multilíngue latino: português, espanhol, inglês, francês...
# Duas caixas estão na mesma linha quando o centro vertical difere menos que
# esta fração da altura mediana das caixas.
TOLERANCIA_LINHA = 0.5


class OcrIndisponivelError(RuntimeError):
    """O motor de OCR não pôde ser carregado (modelos ausentes ou falha no onnxruntime)."""


def _aquecer(motor) -> None:
    imagem = np.full((80, 360, 3), 255, np.uint8)
    cv2.putText(imagem, "MiniScan 2026", (12, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    resultado = motor(imagem)
    if not resultado.txts:
        raise RuntimeError("o OCR não reconheceu o texto de aquecimento")


class MotorOcr:
    """Singleton: os modelos ONNX são carregados uma única vez por processo.

    A trava também serializa as chamadas, porque o FastAPI executa rotas síncronas
    em várias threads e o OCR já usa todos os núcleos da CPU sozinho.
    """

    _instancia = None
    _trava = threading.Lock()

    @classmethod
    def obter(cls):
        with cls._trava:
            if cls._instancia is None:
                cls._instancia = cls._carregar()
            return cls._instancia

    @staticmethod
    def _carregar():
        try:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

            motor = RapidOCR(
                params={
                    "Global.log_level": "error",
                    # Páginas já chegam retificadas e em pé: o classificador de
                    # orientação de linha só custaria tempo.
                    "Global.use_cls": False,
                    "Det.ocr_version": OCRVersion.PPOCRV5,
                    "Det.model_type": ModelType.MOBILE,
                    "Rec.ocr_version": OCRVersion.PPOCRV5,
                    "Rec.model_type": ModelType.MOBILE,
                    "Rec.lang_type": LangRec.LATIN,
                }
            )
            # O RapidOCR só baixa e carrega os modelos na primeira leitura. Ler uma
            # imagem com texto aqui força isso agora: no build do Docker os modelos
            # ficam na imagem, e /saude só diz "disponível" se o OCR funciona mesmo.
            _aquecer(motor)
            return motor
        except Exception as erro:
            raise OcrIndisponivelError(f"Não foi possível carregar o OCR: {erro}") from erro

    @classmethod
    def ler(cls, imagem: np.ndarray):
        motor = cls.obter()
        with cls._trava:
            return motor(imagem)


def ocr_disponivel() -> bool:
    try:
        MotorOcr.obter()
        return True
    except OcrIndisponivelError:
        logger.exception("Motor de OCR indisponível")
        return False


def ordenar_em_linhas(caixas: Sequence[np.ndarray], textos: Sequence[str]) -> str:
    """Monta o texto na ordem natural de leitura: de cima para baixo, da esquerda para a direita.

    O detector devolve caixas soltas. Caixas com centro vertical próximo formam uma
    linha; dentro da linha, a ordem é pela borda esquerda.
    """
    if not textos:
        return ""
    pontos = [np.asarray(caixa, dtype=np.float32).reshape(-1, 2) for caixa in caixas]
    itens = [
        {
            "texto": texto.strip(),
            "esquerda": float(p[:, 0].min()),
            "centro_y": float(p[:, 1].mean()),
            "altura": float(p[:, 1].max() - p[:, 1].min()),
        }
        for p, texto in zip(pontos, textos, strict=True)
        if texto.strip()
    ]
    if not itens:
        return ""
    tolerancia = TOLERANCIA_LINHA * float(np.median([item["altura"] for item in itens]))

    linhas: list[list[dict]] = []
    for item in sorted(itens, key=lambda i: i["centro_y"]):
        linha_atual = linhas[-1] if linhas else None
        if linha_atual is not None:
            centro_linha = float(np.mean([i["centro_y"] for i in linha_atual]))
            if abs(item["centro_y"] - centro_linha) <= tolerancia:
                linha_atual.append(item)
                continue
        linhas.append([item])

    return "\n".join(
        " ".join(i["texto"] for i in sorted(linha, key=lambda i: i["esquerda"])) for linha in linhas
    )


def extrair_texto_ocr(
    imagem: np.ndarray, ignorar_graficos: bool = True, regioes: list[Regiao] | None = None
) -> str:
    """Lê o texto da página retificada ORIGINAL (sem filtro).

    A rede do PaddleOCR usa os gradientes suaves (anti-aliasing) das bordas das letras;
    a binarização do filtro P&B destrói esses gradientes. Com texto pequeno, ler a
    versão P&B derruba a acurácia de ~99% para ~35%, então o P&B fica só para a
    tela e o PDF.
    Com `ignorar_graficos`, figuras e fotos são apagadas antes, para não virarem
    caracteres soltos no texto. Se `regioes` vier preenchido (devolvido antes pelo
    /processar-pagina), a detecção de layout não roda de novo.
    """
    if imagem.ndim == 2:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
    if ignorar_graficos:
        if regioes is None:
            regioes = DetectorLayout.obter().detectar(imagem)
        imagem = mascarar_regioes(imagem, regioes)
    try:
        resultado = MotorOcr.ler(imagem)
    except OcrIndisponivelError:
        raise
    except Exception as erro:
        raise OcrIndisponivelError(f"Falha ao executar o OCR: {erro}") from erro
    if resultado.boxes is None or resultado.txts is None:
        return ""
    return ordenar_em_linhas(list(resultado.boxes), list(resultado.txts))
