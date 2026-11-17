FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Só bibliotecas de sistema do OpenCV/onnxruntime: o OCR roda em ONNX,
# sem Tesseract nem outros binários externos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Dependências primeiro, para aproveitar o cache de camadas do Docker.
# requirements.txt é gerado do uv.lock, com versões e hashes fixos.
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

COPY app ./app

# Baixa os modelos do PaddleOCR (PP-OCRv5 latino) durante o build, para o
# container nunca depender de download em produção.
RUN python -c "from app.ocr import MotorOcr; MotorOcr.obter()"

RUN useradd --create-home --uid 1000 miniscan
USER miniscan

EXPOSE 8000

# Plataformas como Render e Railway informam a porta pela variável PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
