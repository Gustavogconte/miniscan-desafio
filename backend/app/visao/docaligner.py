"""Detecção dos 4 cantos da folha com o modelo DocAligner (DocsaidLab, licença Apache-2.0).

O modelo FastViT-SA24 recebe a foto reduzida a 256x256 e devolve, para cada canto, um
mapa de calor de 128x128 com a chance de o canto estar em cada ponto. O canto é o
centro da maior mancha acima de 0,3, como no pós-processamento original. Roda no
onnxruntime, o mesmo do OCR. O arquivo .onnx (83 MB) fica fora do git: o build do
Docker, a CI e quem roda a API localmente o baixam com `python -m app.visao.docaligner`.

Nas fotos reais testadas, o modelo acertou cartões na mão e sobre papelão, onde o
pipeline OpenCV errava, mas não achou a folha que ocupa quase a foto toda, que o OpenCV
acerta. Por isso o modelo vem primeiro e, quando não acha ou não tem certeza,
`detectar_cantos` (app/visao/bordas.py) cai no OpenCV.
"""

import hashlib
import logging
import shutil
import threading
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from app.visao.perspectiva import (
    CantosInvalidosError,
    ordenar_cantos,
    validar_cantos_normalizados,
)

logger = logging.getLogger(__name__)

ARQUIVO_MODELO = "fastvit_sa24_h_e_bifpn_256_fp32.onnx"
URL_MODELO = f"https://github.com/DocsaidLab/DocAligner/releases/download/1.1.1/{ARQUIVO_MODELO}"
SHA256_MODELO = "7f9f5a8935b2eb22b3ee0245d34996063f54562df390d34714af2d76928695bc"
CAMINHO_MODELO = Path(__file__).resolve().parents[2] / "modelos" / ARQUIVO_MODELO
LADO_ENTRADA = 256
# Valor mínimo do mapa para um ponto fazer parte da mancha do canto (o do DocAligner).
LIMIAR_MAPA = 0.3
# Menor pico entre os 4 mapas para aceitar a detecção. Nas 13 fotos reais medidas, os
# acertos ficaram acima de 0,88 e as falhas abaixo de 0,11. Nas cenas sintéticas dos
# testes, os erros acima de 3% da diagonal vieram com pico de 0,46 a 0,49 e os acertos
# acima de 0,78. O corte fica no meio desse vão: recusar só faz cair no OpenCV, mas um
# erro aceito não tem reserva.
CONFIANCA_MINIMA = 0.7
# A VPS limita o container a 1 CPU: mais threads só disputariam o mesmo núcleo.
THREADS = 1
# Depois de uma falha ao carregar, espera este tempo antes de tentar de novo.
ESPERA_APOS_FALHA_S = 60


class ModeloIndisponivelError(RuntimeError):
    """O modelo não pôde ser carregado (arquivo ausente ou falha no onnxruntime)."""


class DetectorDocAligner:
    """Singleton: a sessão do onnxruntime é criada uma única vez por processo.

    Como no OCR, a trava de carga garante uma carga só, e a de inferência serializa as
    detecções, para a memória não crescer com várias fotos ao mesmo tempo.
    """

    _sessao = None
    # Momento da última carga que falhou (time.monotonic), ou None se nunca falhou.
    _ultima_falha: float | None = None
    _trava_carga = threading.Lock()
    _trava_inferencia = threading.Lock()

    @classmethod
    def carregado(cls) -> bool:
        return cls._sessao is not None

    @classmethod
    def obter(cls):
        if cls._sessao is not None:
            return cls._sessao
        with cls._trava_carga:
            if cls._sessao is None:
                falhou_ha_pouco = (
                    cls._ultima_falha is not None
                    and time.monotonic() - cls._ultima_falha < ESPERA_APOS_FALHA_S
                )
                if falhou_ha_pouco:
                    raise ModeloIndisponivelError("O modelo de cantos está indisponível.")
                try:
                    cls._sessao = cls._carregar()
                except ModeloIndisponivelError:
                    cls._ultima_falha = time.monotonic()
                    raise
            return cls._sessao

    @staticmethod
    def _carregar():
        if not CAMINHO_MODELO.is_file():
            logger.warning("Modelo de cantos ausente em %s: só o OpenCV detecta", CAMINHO_MODELO)
            raise ModeloIndisponivelError("O modelo de cantos não foi baixado.")
        try:
            import onnxruntime as ort

            opcoes = ort.SessionOptions()
            opcoes.intra_op_num_threads = THREADS
            opcoes.inter_op_num_threads = THREADS
            sessao = ort.InferenceSession(
                str(CAMINHO_MODELO), opcoes, providers=["CPUExecutionProvider"]
            )
            # Uma inferência de aquecimento confere a saída e já reserva a memória.
            vazia = np.zeros((1, 3, LADO_ENTRADA, LADO_ENTRADA), np.float32)
            forma = sessao.run(None, {"img": vazia})[0].shape
            if forma[1] != 4:
                raise RuntimeError(f"saída inesperada do modelo de cantos: {forma}")
            return sessao
        except Exception as erro:
            logger.exception("Falha ao carregar o modelo de cantos")
            raise ModeloIndisponivelError("O modelo de cantos está indisponível.") from erro

    @classmethod
    def mapas(cls, entrada: np.ndarray) -> np.ndarray:
        """Os 4 mapas de calor (4 x 128 x 128) de uma entrada já preparada."""
        sessao = cls.obter()
        with cls._trava_inferencia:
            return sessao.run(None, {"img": entrada})[0][0]


def docaligner_disponivel() -> bool:
    """Tenta carregar o modelo só se ainda não carregou."""
    if DetectorDocAligner.carregado():
        return True
    try:
        DetectorDocAligner.obter()
        return True
    except ModeloIndisponivelError:
        return False


def preparar_entrada(imagem: np.ndarray) -> np.ndarray:
    """Foto BGR -> tensor [1, 3, 256, 256] de 0 a 1.

    A foto é esticada até o quadrado, sem manter a proporção, como no treino do modelo.
    """
    if imagem.ndim == 2:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
    reduzida = cv2.resize(imagem, (LADO_ENTRADA, LADO_ENTRADA), interpolation=cv2.INTER_LINEAR)
    return (np.transpose(reduzida, (2, 0, 1)).astype(np.float32) / 255.0)[None]


def cantos_dos_mapas(mapas: np.ndarray) -> tuple[np.ndarray | None, float]:
    """Um canto por mapa: o centro da maior mancha acima do limiar, ponderado pelo mapa.

    Devolve os cantos normalizados (0..1), já ordenados, e a confiança: o menor pico
    entre os 4 mapas. Se algum mapa não tem mancha, os cantos vêm None.
    """
    altura, largura = mapas.shape[1:]
    confianca = float(min(mapa.max() for mapa in mapas[:4]))
    cantos = []
    for mapa in mapas[:4]:
        quantidade, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(
            (mapa >= LIMIAR_MAPA).astype(np.uint8), connectivity=8
        )
        if quantidade <= 1:
            return None, confianca
        maior = 1 + int(np.argmax(estatisticas[1:, cv2.CC_STAT_AREA]))
        ys, xs = np.nonzero(rotulos == maior)
        pesos = mapa[ys, xs]
        x = (float(np.average(xs, weights=pesos)) + 0.5) / largura
        y = (float(np.average(ys, weights=pesos)) + 0.5) / altura
        cantos.append((x, y))
    return ordenar_cantos(np.clip(np.array(cantos, dtype=np.float32), 0, 1)), confianca


def detectar_cantos_docaligner(imagem: np.ndarray) -> np.ndarray | None:
    """Cantos normalizados (sup. esq., sup. dir., inf. dir., inf. esq.), ou None.

    None quando o modelo não está disponível, não acha os 4 cantos, não tem certeza ou
    devolve um quadrilátero que o recorte recusaria. Nesses casos vale o OpenCV.
    """
    try:
        mapas = DetectorDocAligner.mapas(preparar_entrada(imagem))
    except ModeloIndisponivelError:
        return None
    except Exception:
        logger.exception("Falha ao detectar os cantos com o modelo")
        return None
    cantos, confianca = cantos_dos_mapas(mapas)
    if cantos is None or confianca < CONFIANCA_MINIMA:
        return None
    try:
        return validar_cantos_normalizados(cantos)
    except CantosInvalidosError:
        return None


def _sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def baixar_modelo() -> Path:
    """Baixa o modelo da release do GitHub, se ainda não estiver aqui, e confere o SHA-256."""
    if CAMINHO_MODELO.is_file() and _sha256(CAMINHO_MODELO) == SHA256_MODELO:
        return CAMINHO_MODELO
    CAMINHO_MODELO.parent.mkdir(parents=True, exist_ok=True)
    parcial = CAMINHO_MODELO.with_suffix(".parcial")
    with urllib.request.urlopen(URL_MODELO, timeout=60) as resposta, parcial.open("wb") as arquivo:
        shutil.copyfileobj(resposta, arquivo)
    if _sha256(parcial) != SHA256_MODELO:
        parcial.unlink()
        raise RuntimeError(f"O arquivo baixado de {URL_MODELO} não confere com o SHA-256.")
    parcial.replace(CAMINHO_MODELO)
    return CAMINHO_MODELO


if __name__ == "__main__":
    print(f"Modelo em {baixar_modelo()}")
    DetectorDocAligner.obter()
    print("Modelo carregado.")
