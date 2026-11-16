"""Exporta o DocLayout-YOLO (pesos oficiais DocStructBench) para models/doclayout_yolo.onnx.

Roda uma única vez, num ambiente temporário com PyTorch, sem afetar as
dependências da API:

    uv run --no-project --python 3.11 \
        --with doclayout-yolo --with huggingface_hub --with onnx --with onnxslim --with onnxscript \
        python scripts/exportar_modelo_layout.py
"""

import shutil
from pathlib import Path

from doclayout_yolo import YOLOv10
from huggingface_hub import hf_hub_download

DESTINO = Path(__file__).resolve().parents[1] / "models" / "doclayout_yolo.onnx"

pesos = hf_hub_download(
    repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
    filename="doclayout_yolo_docstructbench_imgsz1024.pt",
)
modelo = YOLOv10(pesos)
print("Classes do modelo:", modelo.names)
exportado = modelo.export(format="onnx", imgsz=1024, simplify=True, opset=17, dynamic=False)
DESTINO.parent.mkdir(parents=True, exist_ok=True)
shutil.copy(exportado, DESTINO)
print(f"Modelo salvo em {DESTINO} ({DESTINO.stat().st_size / 1e6:.1f} MB)")
