# MiniScan API

API em FastAPI que faz o processamento de imagem do MiniScan: detecta os cantos da folha, corrige a perspectiva, aplica os filtros preservando fotos e figuras, extrai o texto em português com o PaddleOCR e junta as páginas em um PDF. O OCR (modelos PP-OCRv5 latinos) e a detecção de layout (DocLayout-YOLO) rodam no `onnxruntime`, sem binários externos e sem PyTorch. Os endpoints de visão não guardam estado. A documentação interativa fica em `/docs` quando o servidor está rodando.

| Rota | Entrada | Saída |
|---|---|---|
| `POST /detectar-cantos` | `imagem` (arquivo) | `{cantos: [{x, y}] × 4, detectado}`, coordenadas de 0 a 1 |
| `POST /processar-pagina` | `imagem`, `cantos` (JSON), `filtro` (`original`, `grayscale` ou `bw`), `preservar_graficos` (padrão `true`) | página retificada em JPEG, ou PNG no filtro `bw`; o cabeçalho `X-Regioes-Graficas` traz as figuras detectadas |
| `POST /extrair-ocr` | `imagem` (página retificada, qualquer filtro) e, opcionalmente, `regioes` (o JSON do cabeçalho acima, para não detectar de novo) | `{texto, idioma}`, com o texto em ordem de leitura |
| `POST /gerar-pdf` | `paginas` (vários arquivos, na ordem) | PDF A4 |
| `POST /documentos` | `titulo`, `pdf`, `originais` e `processadas` (arquivos, na ordem), `paginas` (JSON com `filtro` e `texto_ocr` de cada página) | `201` com `{id, titulo, pdf_url, total_paginas}` |
| `GET /saude` | — | `{status, ocr_disponivel, layout_disponivel, persistencia_configurada}` |

Os cantos seguem sempre a ordem superior esquerdo, superior direito, inferior direito e inferior esquerdo. Cada arquivo pode ter até 15 MB, o mesmo limite do bucket no Supabase.

A rota `/documentos` é a única que grava no Supabase. Ela envia os arquivos para `miniscan-files/documentos/<id>/` e insere as linhas em `documents` e `document_pages`. Se alguma etapa falhar, ela apaga o que já tinha gravado e responde 502. Sem `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` configuradas, a rota responde 503.

## Rodando localmente

É preciso ter o [uv](https://docs.astral.sh/uv/) instalado. Ele baixa o Python se for necessário (3.11 ou mais novo).

```bash
cd backend
uv sync
cp .env.example .env   # preencha a URL e a chave secreta do Supabase
uv run uvicorn app.main:app --reload --env-file .env
```

Na primeira execução, o RapidOCR baixa os modelos do PaddleOCR (cerca de 15 MB) e guarda no ambiente virtual. Os modelos são carregados uma única vez, na subida do servidor.

## Modelo de layout (opcional)

A preservação de figuras usa o DocLayout-YOLO em `models/doclayout_yolo.onnx`. O arquivo tem dezenas de MB e não vai para o Git. Sem ele, a API funciona normalmente, só sem preservar figuras, e `/saude` mostra `layout_disponivel: false`. Para gerar o arquivo uma única vez a partir dos pesos oficiais, rode:

```bash
uv run --no-project --python 3.11 \
    --with doclayout-yolo --with huggingface_hub --with onnx --with onnxslim --with onnxscript \
    python scripts/exportar_modelo_layout.py
```

O comando cria um ambiente temporário com PyTorch só para a exportação; a API continua sem PyTorch. O caminho do modelo pode ser trocado pela variável `MINISCAN_MODELO_LAYOUT`. A detecção leva cerca de 2 s em CPU, então o resultado fica em cache por página: trocar de filtro não detecta de novo, e o front-end reenvia as regiões ao OCR. São tratadas como gráficas as classes `figure`, `picture`, `image`, `signature` e `stamp`, então modelos treinados no DocLayNet (que usam `Picture`) também funcionam.

## Testes e lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Os testes geram fotos sintéticas de uma folha inclinada, sem depender de arquivos externos, e incluem a leitura de palavras acentuadas pelo OCR. O detector de layout é testado com uma sessão ONNX simulada, então não precisa do modelo.

## Docker

```bash
docker build -t miniscan-api .
docker run --rm -p 8000:8000 -e MINISCAN_ORIGENS_CORS=http://localhost:3000 miniscan-api
```

A imagem usa `python:3.11-slim`, instala as dependências do `requirements.txt` (gerado do `uv.lock`, com versões e hashes fixos) e baixa os modelos do PaddleOCR durante o build. Se `models/doclayout_yolo.onnx` existir na hora do build, ele entra na imagem. A imagem respeita a variável `PORT` das plataformas de hospedagem. Depois de mudar dependências, regenere o `requirements.txt` com `uv export --no-dev --format requirements-txt --no-emit-project -o requirements.txt`.
