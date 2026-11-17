"""API do MiniScan."""

import os

# Segunda camada do teto de pixels (a primeira é `conferir_dimensoes`, em
# app/visao/imagem.py): o OpenCV só lê esta variável no primeiro import do cv2, e
# este pacote é importado antes dele quando o servidor sobe.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", "50000000")
