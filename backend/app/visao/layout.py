"""Detecção de regiões gráficas (figuras, fotos, assinaturas) com DocLayout-YOLO em ONNX.

As regiões encontradas são usadas para dois fins:
- manter a imagem original dessas áreas sobre o fundo filtrado (cinza ou P&B),
  para que fotos e carimbos não sejam destruídos pela binarização;
- apagar essas áreas antes do OCR, para que não virem caracteres soltos no texto.

O modelo é opcional: sem o arquivo .onnx, o detector fica desligado e o restante
do pipeline funciona normalmente.
"""

import ast
import hashlib
import logging
import os
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

CAMINHO_PADRAO = Path(__file__).resolve().parents[2] / "models" / "doclayout_yolo.onnx"
TAMANHO_ENTRADA = 1024
CONFIANCA_MINIMA = 0.35
LIMIAR_NMS = 0.45
TAMANHO_CACHE = 16  # páginas recentes cujas regiões ficam guardadas
COR_PREENCHIMENTO = 114  # cinza usado no letterbox do YOLO
# Nomes de classe tratados como gráficos. O DocLayout-YOLO (DocStructBench) usa "figure";
# modelos treinados no DocLayNet usam "Picture"; alguns modelos têm "signature" ou "stamp".
CLASSES_GRAFICAS = frozenset({"figure", "picture", "image", "signature", "stamp"})


@dataclass(frozen=True)
class Regiao:
    x0: int
    y0: int
    x1: int
    y1: int
    classe: str
    confianca: float

    @property
    def area(self) -> int:
        return max(0, self.x1 - self.x0) * max(0, self.y1 - self.y0)

    def para_dict(self) -> dict:
        return asdict(self)


def letterbox(
    imagem: np.ndarray, tamanho: int = TAMANHO_ENTRADA
) -> tuple[np.ndarray, float, int, int]:
    """Redimensiona mantendo a proporção e completa com bordas até `tamanho` x `tamanho`."""
    altura, largura = imagem.shape[:2]
    escala = min(tamanho / altura, tamanho / largura)
    nova_largura, nova_altura = round(largura * escala), round(altura * escala)
    reduzida = cv2.resize(imagem, (nova_largura, nova_altura), interpolation=cv2.INTER_LINEAR)
    borda_x = (tamanho - nova_largura) // 2
    borda_y = (tamanho - nova_altura) // 2
    quadrada = cv2.copyMakeBorder(
        reduzida,
        borda_y,
        tamanho - nova_altura - borda_y,
        borda_x,
        tamanho - nova_largura - borda_x,
        cv2.BORDER_CONSTANT,
        value=(COR_PREENCHIMENTO,) * 3,
    )
    return quadrada, escala, borda_x, borda_y


def _ler_nomes(sessao) -> dict[int, str]:
    """O export do Ultralytics grava os nomes das classes nos metadados do ONNX."""
    metadados = sessao.get_modelmeta().custom_metadata_map
    try:
        return {int(k): str(v) for k, v in ast.literal_eval(metadados.get("names", "{}")).items()}
    except (ValueError, SyntaxError):
        return {}


def _decodificar(saida: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Converte a saída do YOLO em (caixas x1y1x2y2, confianças, classes).

    Aceita os dois formatos de export:
    - YOLOv10 / DocLayout-YOLO: (1, N, 6) com [x1, y1, x2, y2, confiança, classe];
    - YOLOv8: (1, 4 + classes, N) com [cx, cy, w, h, pontuação por classe...].
    """
    saida = np.squeeze(saida, axis=0)
    if saida.ndim == 2 and saida.shape[1] == 6:
        return saida[:, :4], saida[:, 4], saida[:, 5].astype(int)
    previsoes = saida.T  # (N, 4 + classes)
    pontuacoes = previsoes[:, 4:]
    classes = pontuacoes.argmax(axis=1)
    confiancas = pontuacoes.max(axis=1)
    cx, cy, w, h = previsoes[:, 0], previsoes[:, 1], previsoes[:, 2], previsoes[:, 3]
    caixas = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    return caixas, confiancas, classes


class DetectorLayout:
    """Singleton: a sessão do onnxruntime é criada uma única vez por processo."""

    _instancia: "DetectorLayout | None" = None
    _trava_criacao = threading.Lock()

    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho
        self._sessao = None
        self._nomes: dict[int, str] = {}
        self._trava = threading.Lock()  # protege o cache
        self._trava_inferencia = threading.Lock()
        self._cache: OrderedDict[str, list[Regiao]] = OrderedDict()
        if not caminho.exists():
            logger.warning(
                "Modelo de layout não encontrado em %s: figuras não serão preservadas.", caminho
            )
            return
        try:
            import onnxruntime as ort

            self._sessao = ort.InferenceSession(str(caminho), providers=["CPUExecutionProvider"])
            self._nomes = _ler_nomes(self._sessao)
            self._entrada = self._sessao.get_inputs()[0].name
        except Exception:
            logger.exception("Falha ao carregar o modelo de layout %s", caminho)
            self._sessao = None

    @classmethod
    def obter(cls) -> "DetectorLayout":
        with cls._trava_criacao:
            if cls._instancia is None:
                caminho = Path(os.getenv("MINISCAN_MODELO_LAYOUT", str(CAMINHO_PADRAO)))
                cls._instancia = cls(caminho)
            return cls._instancia

    @property
    def disponivel(self) -> bool:
        return self._sessao is not None

    def detectar(self, imagem: np.ndarray) -> list[Regiao]:
        """Devolve as regiões gráficas da página, em coordenadas da imagem recebida.

        A inferência custa cerca de 2 s em CPU. Trocar de filtro reprocessa a mesma
        página retificada, então o resultado fica em cache pelo conteúdo da imagem.
        """
        if self._sessao is None:
            return []
        if imagem.ndim == 2:
            imagem = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
        chave = hashlib.blake2b(np.ascontiguousarray(imagem).data, digest_size=16).hexdigest()
        chave += f":{imagem.shape}"
        with self._trava:
            if chave in self._cache:
                self._cache.move_to_end(chave)
                return list(self._cache[chave])
        regioes = self._inferir(imagem)
        with self._trava:
            self._cache[chave] = regioes
            while len(self._cache) > TAMANHO_CACHE:
                self._cache.popitem(last=False)
        return list(regioes)

    def _inferir(self, imagem: np.ndarray) -> list[Regiao]:
        altura, largura = imagem.shape[:2]
        quadrada, escala, borda_x, borda_y = letterbox(imagem)
        tensor = cv2.cvtColor(quadrada, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = np.ascontiguousarray(tensor.transpose(2, 0, 1)[None])

        with self._trava_inferencia:
            saida = self._sessao.run(None, {self._entrada: tensor})[0]

        caixas, confiancas, classes = _decodificar(saida)
        nomes = [self._nomes.get(int(c), str(int(c))) for c in classes]
        manter = [
            i
            for i, (conf, nome) in enumerate(zip(confiancas, nomes, strict=True))
            if conf >= CONFIANCA_MINIMA and nome.lower() in CLASSES_GRAFICAS
        ]
        if not manter:
            return []

        # Volta do espaço 1024x1024 (com bordas) para a imagem original.
        caixas = (caixas[manter] - [borda_x, borda_y, borda_x, borda_y]) / escala
        caixas = np.clip(caixas, 0, [largura, altura, largura, altura])
        retangulos = [
            [float(x0), float(y0), float(x1 - x0), float(y1 - y0)] for x0, y0, x1, y1 in caixas
        ]
        escolhidos = cv2.dnn.NMSBoxes(
            retangulos, [float(confiancas[i]) for i in manter], CONFIANCA_MINIMA, LIMIAR_NMS
        )
        regioes = []
        for j in np.array(escolhidos).flatten():
            x0, y0, x1, y1 = (int(round(v)) for v in caixas[j])
            regiao = Regiao(x0, y0, x1, y1, nomes[manter[j]], float(confiancas[manter[j]]))
            if regiao.area > 0:
                regioes.append(regiao)
        return regioes


def preservar_regioes(
    filtrada: np.ndarray, original: np.ndarray, regioes: list[Regiao]
) -> np.ndarray:
    """Cola as regiões gráficas da imagem original por cima da versão filtrada."""
    if not regioes:
        return filtrada
    resultado = (
        cv2.cvtColor(filtrada, cv2.COLOR_GRAY2BGR) if filtrada.ndim == 2 else filtrada.copy()
    )
    for r in regioes:
        resultado[r.y0 : r.y1, r.x0 : r.x1] = original[r.y0 : r.y1, r.x0 : r.x1]
    return resultado


def mascarar_regioes(imagem: np.ndarray, regioes: list[Regiao]) -> np.ndarray:
    """Pinta as regiões gráficas de branco para que o OCR não tente ler figuras."""
    if not regioes:
        return imagem
    mascarada = imagem.copy()
    for r in regioes:
        mascarada[r.y0 : r.y1, r.x0 : r.x1] = 255
    return mascarada
