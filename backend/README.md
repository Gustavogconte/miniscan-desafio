# MiniScan API

API em FastAPI que faz o processamento de imagem do MiniScan: detecta os cantos da folha, corrige a perspectiva, aplica os filtros, extrai o texto em português com o PaddleOCR e junta as páginas em um PDF. O OCR (modelos PP-OCRv5 latinos) roda no `onnxruntime`, sem binários externos e sem PyTorch. Os endpoints de visão não guardam estado. A documentação interativa fica em `/docs` quando o servidor está rodando.

| Rota | Entrada | Saída |
|---|---|---|
| `POST /detectar-cantos` | `imagem` (arquivo) | `{cantos: [{x, y}] × 4, detectado}`, coordenadas de 0 a 1 |
| `POST /processar-pagina` | `imagem`, `cantos` (JSON), `filtro` (`original`, `grayscale`, `bw` ou `whiteboard`) | página retificada em JPEG, ou PNG no filtro `bw` |
| `POST /extrair-ocr` | `imagem` (foto original), `cantos` (JSON; com eles a API retifica a foto e lê a página sem filtro). Sem `cantos`, a imagem é tratada como já retificada | `{texto, idioma}`, com o texto em ordem de leitura |
| `POST /gerar-pdf` | `paginas` (vários arquivos, na ordem) | PDF A4 |
| `POST /documentos` | `titulo`, `pdf`, `originais` e `processadas` (arquivos, na ordem), `paginas` (JSON com `filtro` e `texto_ocr` de cada página) | `201` com `{id, titulo, pdf_url, total_paginas}` |
| `GET /saude` | — | `{status, ocr_disponivel, persistencia_configurada}` |

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


## Testes e lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Os testes geram fotos sintéticas de uma folha inclinada, sem depender de arquivos externos, e incluem a leitura de palavras acentuadas pelo OCR.

## Docker

```bash
docker build -t miniscan-api .
docker run --rm -p 8000:8000 -e MINISCAN_ORIGENS_CORS=http://localhost:3000 miniscan-api
```

A imagem usa `python:3.11-slim`, instala as dependências do `requirements.txt` (gerado do `uv.lock`, com versões e hashes fixos) e baixa os modelos do PaddleOCR durante o build. A imagem respeita a variável `PORT` das plataformas de hospedagem. Depois de mudar dependências, regenere o `requirements.txt` com `uv export --no-dev --format requirements-txt --no-emit-project -o requirements.txt`.

## Deploy no Hugging Face Spaces

A API roda no Hugging Face Spaces com o próprio Dockerfile: o plano gratuito tem 2 vCPU, 16 GB de RAM e HTTPS. Depois de 48 horas sem uso o Space hiberna, e a primeira requisição seguinte leva cerca de um minuto para acordá-lo.

1. Crie uma conta em [huggingface.co](https://huggingface.co) e entre pelo terminal: `uvx hf auth login`. Use um token com permissão de escrita.
2. Confira se `backend/.env` tem `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`.
3. Rode, dentro de `backend/`:

   ```bash
   uv run --no-project --with huggingface_hub python scripts/publicar_space.py \
       --space SEU_USUARIO/miniscan-api \
       --origens https://SEU-APP.vercel.app \
       --origens-regex '^https://miniscan-[a-z0-9-]+\.vercel\.app$' \
       --enviar-segredos
   ```

O script cria o Space (Docker, público) e cadastra o CORS como variáveis. Com `--enviar-segredos`, as credenciais do Supabase viram *Secrets* do Space, lidas do `.env` e nunca impressas. Depois ele envia o código e o Dockerfile. O `.env`, a `.venv` e os testes não são enviados. O build no Space leva alguns minutos, e o endereço final é `https://SEU_USUARIO-miniscan-api.hf.space`, que vai no `NEXT_PUBLIC_API_URL` da Vercel. Para atualizar a API depois, basta rodar o mesmo comando; o `--enviar-segredos` só é necessário quando as credenciais mudarem.

A cada push, o GitHub Actions (`.github/workflows/backend.yml`) roda o lint e os testes do backend.
