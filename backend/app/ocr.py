"""Extração de texto com PaddleOCR (modelos PP-OCRv5 latinos em ONNX, via RapidOCR).

O modelo latino cobre o português com acentos. Tudo roda no onnxruntime, sem
binários instalados no sistema operacional e sem PyTorch.
"""

import logging
import threading
import time
from collections.abc import Sequence

import cv2
import numpy as np

from app.config import configuracoes

logger = logging.getLogger(__name__)

IDIOMA_OCR = "latin"  # modelo multilíngue latino: português, espanhol, inglês, francês...
# Duas caixas estão na mesma linha quando o centro vertical difere menos que
# esta fração da altura mediana das caixas.
TOLERANCIA_LINHA = 0.5
# Inclinação máxima (rad, ~10°) desfeita antes de agrupar as linhas. Acima disso não é
# página torta, é página de lado, e girar as caixas não ajudaria.
INCLINACAO_MAXIMA = 0.17
# Depois de uma falha ao carregar o OCR, espera este tempo antes de tentar de novo,
# em vez de recarregar o modelo a cada /saude ou /extrair-ocr.
ESPERA_APOS_FALHA_S = 60


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

    Há duas travas. A de carga garante que o modelo seja carregado uma vez só. A de
    leitura serializa o OCR, porque o FastAPI executa rotas síncronas em várias threads
    e o OCR já usa todos os núcleos da CPU sozinho. Separadas, o /saude não fica
    esperando atrás de um lote de páginas.
    """

    _instancia = None
    # Momento da última carga que falhou (time.monotonic), ou None se nunca falhou. Não
    # pode começar em 0: o relógio monotônico conta desde o boot da máquina, e uma API
    # que sobe logo depois de um reinício da VPS recusaria o OCR no primeiro minuto.
    _ultima_falha: float | None = None
    _trava_carga = threading.Lock()
    _trava_leitura = threading.Lock()

    @classmethod
    def carregado(cls) -> bool:
        return cls._instancia is not None

    @classmethod
    def obter(cls):
        if cls._instancia is not None:
            return cls._instancia
        with cls._trava_carga:
            if cls._instancia is None:
                falhou_ha_pouco = (
                    cls._ultima_falha is not None
                    and time.monotonic() - cls._ultima_falha < ESPERA_APOS_FALHA_S
                )
                if falhou_ha_pouco:
                    raise OcrIndisponivelError("O OCR está indisponível no momento.")
                try:
                    cls._instancia = cls._carregar()
                except OcrIndisponivelError:
                    cls._ultima_falha = time.monotonic()
                    raise
            return cls._instancia

    @staticmethod
    def _carregar():
        try:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

            parametros = {
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
            if configuracoes.threads_onnx:
                parametros["EngineConfig.onnxruntime.intra_op_num_threads"] = (
                    configuracoes.threads_onnx
                )
                parametros["EngineConfig.onnxruntime.inter_op_num_threads"] = 1
            motor = RapidOCR(params=parametros)
            # O RapidOCR só baixa e carrega os modelos na primeira leitura. Ler uma
            # imagem com texto aqui força isso agora: no build do Docker os modelos
            # ficam na imagem, e /saude só diz "disponível" se o OCR funciona mesmo.
            _aquecer(motor)
            return motor
        except Exception as erro:
            # O detalhe fica no log; o cliente recebe uma mensagem genérica.
            logger.exception("Falha ao carregar o OCR")
            raise OcrIndisponivelError("O OCR está indisponível no momento.") from erro

    @classmethod
    def ler(cls, imagem: np.ndarray):
        motor = cls.obter()
        with cls._trava_leitura:
            return motor(imagem)


def ocr_disponivel() -> bool:
    """Não espera nenhuma leitura em andamento; tenta carregar só se ainda não carregou."""
    if MotorOcr.carregado():
        return True
    try:
        MotorOcr.obter()
        return True
    except OcrIndisponivelError:
        return False


def _desfazer_inclinacao(pontos: list[np.ndarray]) -> list[np.ndarray]:
    """Gira as caixas pela inclinação mediana do texto, para as linhas ficarem horizontais.

    Numa página torta só 2°, duas colunas de uma tabela a ~1200 px uma da outra ficam
    com mais de meia linha de diferença de altura, e o valor ia para a linha de baixo.
    """
    angulos = [np.arctan2(p[1, 1] - p[0, 1], p[1, 0] - p[0, 0]) for p in pontos if len(p) >= 2]
    if not angulos:
        return pontos
    angulo = float(np.clip(np.median(angulos), -INCLINACAO_MAXIMA, INCLINACAO_MAXIMA))
    if abs(angulo) < 1e-3:
        return pontos
    cosseno, seno = np.cos(angulo), np.sin(angulo)
    giro = np.array([[cosseno, -seno], [seno, cosseno]], dtype=np.float32)
    return [p @ giro for p in pontos]


def ordenar_em_linhas(caixas: Sequence[np.ndarray], textos: Sequence[str]) -> str:
    """Monta o texto na ordem natural de leitura: de cima para baixo, da esquerda para a direita.

    O detector devolve caixas soltas. Depois de desfazer a inclinação da página, caixas
    com centro vertical próximo formam uma linha; dentro da linha, a ordem é pela
    borda esquerda.
    """
    if not textos:
        return ""
    pontos = _desfazer_inclinacao(
        [np.asarray(caixa, dtype=np.float32).reshape(-1, 2) for caixa in caixas]
    )
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


def extrair_texto_ocr(imagem: np.ndarray) -> str:
    """Lê o texto da página retificada ORIGINAL (sem filtro).

    A rede do PaddleOCR usa os gradientes suaves (anti-aliasing) das bordas das letras;
    a binarização do filtro P&B destrói esses gradientes. Com texto pequeno, ler a
    versão P&B derruba a acurácia de ~99% para ~35%, então o P&B fica só para a
    tela e o PDF.
    """
    if imagem.ndim == 2:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
    try:
        resultado = MotorOcr.ler(imagem)
    except OcrIndisponivelError:
        raise
    except Exception as erro:
        logger.exception("Falha ao executar o OCR")
        raise OcrIndisponivelError("Não foi possível ler o texto desta página.") from erro
    if resultado.boxes is None or resultado.txts is None:
        return ""
    return ordenar_em_linhas(list(resultado.boxes), list(resultado.txts))
