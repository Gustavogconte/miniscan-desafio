# MiniScan API

API em FastAPI que faz o processamento de imagem do MiniScan: detecta os cantos da folha, corrige a perspectiva, aplica os filtros, extrai o texto com Tesseract em português e junta as páginas em um PDF. Os endpoints de visão não guardam estado. A documentação interativa fica em `/docs` quando o servidor está rodando.

| Rota | Entrada | Saída |
|---|---|---|
| `POST /detectar-cantos` | `imagem` (arquivo) | `{cantos: [{x, y}] × 4, detectado}`, coordenadas de 0 a 1 |
| `POST /processar-pagina` | `imagem`, `cantos` (JSON), `filtro` (`original`, `grayscale` ou `bw`) | página retificada em JPEG, ou PNG no filtro `bw` |
| `POST /extrair-ocr` | `imagem` (página retificada) | `{texto, idioma}` |
| `POST /gerar-pdf` | `paginas` (vários arquivos, na ordem) | PDF A4 |
| `POST /documentos` | `titulo`, `pdf`, `originais` e `processadas` (arquivos, na ordem), `paginas` (JSON com `filtro` e `texto_ocr` de cada página) | `201` com `{id, titulo, pdf_url, total_paginas}` |
| `GET /saude` | — | `{status, ocr_disponivel, persistencia_configurada}` |

Os cantos seguem sempre a ordem superior esquerdo, superior direito, inferior direito e inferior esquerdo. Cada arquivo pode ter até 15 MB, o mesmo limite do bucket no Supabase.

A rota `/documentos` é a única que grava no Supabase. Ela envia os arquivos para `miniscan-files/documentos/<id>/` e insere as linhas em `documents` e `document_pages`. Se alguma etapa falhar, ela apaga o que já tinha gravado e responde 502. Sem `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` configuradas, a rota responde 503.

## Rodando localmente

É preciso ter o [uv](https://docs.astral.sh/uv/) instalado. Ele baixa o Python 3.12 se for necessário.

```bash
cd backend
uv sync
cp .env.example .env   # preencha a URL e a chave service_role do Supabase
uv run uvicorn app.main:app --reload --env-file .env
```

Para o OCR funcionar fora do Docker, instale o Tesseract com o idioma português. No Windows, use o instalador da UB Mannheim marcando o pacote "Portuguese" e coloque a pasta do Tesseract no `PATH`. No Linux, instale `tesseract-ocr` e `tesseract-ocr-por`. Sem o Tesseract, a rota `/extrair-ocr` responde 503 e as demais funcionam normalmente.

## Testes e lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Os testes geram fotos sintéticas de uma folha inclinada, sem depender de arquivos externos. Os testes de OCR são pulados quando o Tesseract não está instalado.

## Docker

```bash
docker build -t miniscan-api .
docker run --rm -p 8000:8000 -e MINISCAN_ORIGENS_CORS=http://localhost:3000 miniscan-api
```

A imagem já inclui o Tesseract com o idioma português e respeita a variável `PORT` das plataformas de hospedagem.
