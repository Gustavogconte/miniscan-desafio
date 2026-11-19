# MiniScan API

API em FastAPI que faz o processamento de imagem do MiniScan: detecta os cantos da folha, corrige a perspectiva, aplica os filtros, extrai o texto em português com o PaddleOCR e junta as páginas em um PDF. O OCR (modelos PP-OCRv5 latinos) roda no `onnxruntime`, sem binários externos e sem PyTorch. Os endpoints de visão não guardam estado.

Os cantos da folha vêm primeiro do modelo [DocAligner](https://github.com/DocsaidLab/DocAligner), do DocsaidLab (FastViT-SA24 em ONNX, licença Apache-2.0 para o código e os pesos), que também roda no `onnxruntime` (`app/visao/docaligner.py`). Quando o modelo não acha a folha, fica com confiança abaixo de 0,7 ou devolve um quadrilátero que o recorte recusaria, a API usa o pipeline clássico com OpenCV (`app/visao/bordas.py`). Os testes que levaram a essa combinação estão na seção 3 da `docs/documentacao_miniscan.md`. A documentação interativa fica em `/docs` quando o servidor está rodando.

| Rota | Entrada | Saída |
|---|---|---|
| `POST /detectar-cantos` | `imagem` (arquivo) | `{cantos: [{x, y}] × 4, detectado}`, coordenadas de 0 a 1 |
| `POST /processar-pagina` | `imagem`, `cantos` (JSON), `filtro` (`original`, `grayscale` ou `bw`) | página retificada em JPEG, ou PNG no filtro `bw` |
| `POST /extrair-ocr` | `imagem` (foto original), `cantos` (JSON; com eles a API retifica a foto e lê a página sem filtro). Sem `cantos`, a imagem é tratada como já retificada | `{texto, titulo, idioma}`, com o texto em ordem de leitura e, em `titulo`, um nome sugerido para o documento (a linha de letra maior na metade de cima da página ou, sem destaque, a primeira com palavras, e vazio se nada servir) |
| `POST /gerar-pdf` | `paginas` (vários arquivos, na ordem), `carimbo` opcional (data e hora escritas em cada página) | PDF A4 |
| `POST /compor-cartao` | `frente` e `verso` opcional (já retificados), `formato` (`id` ou `passaporte`) | folha A4 em JPEG com os lados ampliados até o dobro do tamanho real, um embaixo do outro e com os cantos arredondados |
| `POST /documentos` | `titulo`, `pdf`, `originais` e `processadas` (arquivos, na ordem), `paginas` (JSON com `filtro` e `texto_ocr` de cada página) | `201` com `{id, titulo, total_paginas}` |
| `GET /documentos?busca=` | termo opcional (título e texto do OCR, em português) | documentos da conta, do mais novo ao mais antigo, com links de 1 hora para o PDF e a miniatura |
| `GET /documentos/{id}` | — | o documento com todas as páginas, o texto e os links; `404` se não existe ou é de outra conta |
| `PATCH /documentos/{id}` | JSON `{titulo}` | `{id, titulo}` com o nome novo; `422` se ficar vazio ou passar de 200 caracteres, `404` se não existe ou é de outra conta |
| `DELETE /documentos/{id}` | — | `204`, com o documento, as páginas, o PDF e as imagens apagados; `404` se não existe ou é de outra conta |
| `POST /cadastrar` | JSON `{nome, email, senha}` | `201` com `{token, expira_em, usuario}`; `409` se o e-mail já tem conta |
| `POST /entrar` | JSON `{email, senha}` | `{token, expira_em, usuario}`; `401` se não confere, `429` depois de 5 erros seguidos |
| `POST /sair` | — | `204`, e o token deixa de valer |
| `GET /eu` | — | `{id, nome, email}` do dono da sessão |
| `GET /saude` | — | `{status, ocr_disponivel, docaligner_disponivel, persistencia_configurada}` |

Só `/saude`, `/cadastrar` e `/entrar` são abertas. Todas as outras rotas, inclusive as de visão, OCR e PDF, exigem o cabeçalho `Authorization: Bearer <token>` e respondem `401` sem ele. Isso separa o histórico de cada pessoa e impede que qualquer um use a CPU da VPS para rodar OCR.

Os cantos seguem sempre a ordem superior esquerdo, superior direito, inferior direito e inferior esquerdo. Cada arquivo pode ter até 15 MB, o mesmo limite do bucket no Supabase. A requisição inteira pode ter até 100 MB, e cada imagem até 50 megapixels: a API confere as dimensões pelo cabeçalho antes de decodificar, porque um PNG de 100 KB pode descrever 10000 x 10000 pixels e ocupar centenas de MB na memória. Acima desses limites, a resposta é 413. O PDF aceita até 50 páginas, e o título de um documento salvo, até 200 caracteres.

O `POST /documentos` é a única rota que cria documentos no Supabase. Ela envia os arquivos para `miniscan-files/documentos/<id>/`, insere as linhas em `documents` (com o dono em `usuario_id`) e `document_pages`, e guarda nas colunas `*_url` o caminho do arquivo no bucket, e não um link. Se alguma etapa falhar, ela apaga o que já tinha gravado e responde 502. O bucket é privado: a leitura do histórico gera na hora links assinados que valem 1 hora. O `PATCH` troca só o título. O `DELETE` apaga primeiro a linha em `documents` (as páginas caem em cascata) e depois os arquivos do bucket. Se o Storage falhar nessa hora, os arquivos sobram no bucket privado e o caso vai para o log, sem o documento voltar ao histórico. Sem `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` configuradas, as contas e o histórico respondem 503, e por isso as rotas que exigem sessão também.

## Contas e sessão

O login é feito pela própria API (`app/contas.py` e `app/rotas_contas.py`), sem o Supabase Auth. A senha nunca é gravada: a tabela `usuarios` guarda só o hash Argon2id, feito com o `argon2-cffi` nos parâmetros mínimos da OWASP (19 MiB de memória, 2 passadas, 1 thread), cerca de 50 ms por senha. Cada hash leva um sal aleatório e os próprios parâmetros, no formato `$argon2id$v=19$m=19456,t=2,p=1$...`. A senha precisa ter de 8 a 128 caracteres, e o e-mail é gravado em minúsculas.

Ao entrar ou se cadastrar, a API sorteia um token de 256 bits, devolve esse token uma única vez e grava na tabela `sessoes` só o SHA-256 dele, com validade de 30 dias. O front-end o envia em toda chamada. Cookie não serviria: o app e a API ficam em domínios diferentes, e o Safari do iPhone bloqueia cookie de outro site. Para não ir ao banco em cada chamada, a sessão conferida fica um minuto num cache na memória, e sair da conta apaga a entrada na hora.

E-mail inexistente e senha errada dão a mesma resposta e levam o mesmo tempo (a senha é conferida contra um hash fictício), para a tela de entrada não revelar quem tem conta. Depois de 5 senhas erradas seguidas, o e-mail fica bloqueado por 15 minutos (`429`, com `Retry-After`). A tentativa é contada antes de conferir a senha, então uma rajada simultânea não passa do limite. Essa contagem fica na memória do processo e zera se a API reiniciar.

Algumas proteções existem porque a API divide uma VPS de 1 núcleo e 1 GB com outros projetos. A sessão é conferida num middleware (`ExigeSessao`) antes de a API ler o corpo: sem ela, quem não tem conta conseguiria mandar 100 MB de upload e só depois receberia o 401. Só uploads (`multipart/form-data`) podem ter até 100 MB; qualquer outro corpo, como o JSON do `/entrar`, fica em 64 KB, porque o FastAPI interpreta o JSON inteiro antes de validar os campos. No máximo 2 hashes de senha rodam ao mesmo tempo (cada um usa 19 MiB), e quem passa de 5 segundos na fila recebe `503`. O uvicorn aceita até 64 conexões simultâneas. O log de acesso não guarda a query string, porque a busca do histórico pode ter um CPF.

## Rodando localmente

É preciso ter o [uv](https://docs.astral.sh/uv/) instalado. Ele baixa o Python se for necessário (3.11 ou mais novo).

```bash
cd backend
uv sync
uv run python -m app.visao.docaligner   # baixa o modelo de cantos (83 MB) para backend/modelos/
cp .env.example .env   # preencha a URL e a chave secreta do Supabase
uv run uvicorn app.main:app --reload --env-file .env
```

Na primeira execução, o RapidOCR baixa os modelos do PaddleOCR (cerca de 15 MB) e guarda no ambiente virtual. O modelo de cantos vem da versão 1.1.1 publicada no GitHub do DocAligner, com o hash SHA-256 conferido, e fica em `backend/modelos/`, fora do Git. Sem ele, a API funciona e detecta os cantos só com o OpenCV, e o `/saude` mostra `docaligner_disponivel: false`. Os modelos são carregados uma única vez, na subida do servidor.

## Testes e lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Os testes geram fotos sintéticas de uma folha inclinada, sem depender de arquivos externos, e incluem a leitura de palavras acentuadas pelo OCR. As cenas de detecção rodam com o detector combinado e com o OpenCV sozinho. Sem o modelo de cantos baixado, os testes que precisam dele são pulados; no CI ele é obrigatório, e o `conftest.py` recusa rodar sem ele.

## Docker

```bash
docker build -t miniscan-api .
docker run --rm -p 8000:8000 -e MINISCAN_ORIGENS_CORS=http://localhost:3000 miniscan-api
```

A imagem usa `python:3.11-slim`, instala as dependências do `requirements.txt` (gerado do `uv.lock`, com versões e hashes fixos) e baixa durante o build os modelos do PaddleOCR e o modelo de cantos, que fica em `/srv/modelos`. A imagem respeita a variável `PORT` das plataformas de hospedagem. Depois de mudar dependências, regenere o `requirements.txt` com `uv export --no-dev --format requirements-txt --no-emit-project -o requirements.txt`.

## Deploy numa VPS com Docker Compose

O `deploy/vps/docker-compose.yml`, na raiz do repositório, sobe a API num projeto Compose próprio (`miniscan`), com reinício automático e travas de 1 GB de RAM, 1 núcleo e 30 MB de log. Ele também define `MINISCAN_THREADS_ONNX=1`, para o onnxruntime (OCR e detector de cantos) usar uma thread só: sem isso, ele abre uma thread por núcleo da VPS inteira, elas disputam a única CPU do contêiner, e o OCR de uma página passou de cerca de 3 para mais de 60 segundos com 5 pessoas ao mesmo tempo. A API escuta na porta 8020 do host, e um reverse proxy da VPS (Caddy, Nginx) serve o HTTPS e encaminha para ela. O `.env` com `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` e `MINISCAN_BUCKET` fica ao lado do compose, só na VPS. O CORS já vem no compose e aceita o projeto `miniscan-desafio` da Vercel, tanto a produção quanto as prévias. Antes de subir esta versão, rode no Supabase a migração `20261118000004_adiciona_login.sql`: sem as tabelas `usuarios` e `sessoes`, ninguém consegue entrar.

```bash
git clone https://github.com/Gustavogconte/miniscan-desafio.git /opt/miniscan
cd /opt/miniscan/deploy/vps
# copie o .env para esta pasta e rode chmod 600 .env
docker compose config --quiet && docker compose up -d --build
curl -s http://127.0.0.1:8020/saude
```

Para atualizar depois de um push: `git pull` na raiz e `docker compose up -d --build` em `deploy/vps`. Em produção, a API está em https://miniscan-api.duckdns.org; o guia de atualização, com as conferências e como voltar atrás, está em [`deploy/README.md`](../deploy/README.md).

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

A cada push na `main` que mexe no backend, e em cada pull request, o GitHub Actions (`.github/workflows/backend.yml`) roda o lint e os testes.
