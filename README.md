# MiniScan

O MiniScan é um aplicativo de digitalização de documentos inspirado no CamScanner, desenvolvido como projeto de seleção para Iniciação Científica. Ele roda no Android e no iPhone como aplicação web instalável (PWA) e permite capturar ou importar uma foto, corrigir a perspectiva da folha, ver as páginas em tela cheia com zoom, aplicar filtros, extrair o texto via OCR em português e gerar um PDF único para baixar, compartilhar ou salvar no histórico, de onde o documento pode ser aberto de novo.

A câmera faz o recorte ao vivo: a folha é detectada a cada quadro, direto no navegador, e a foto é tirada sozinha quando o documento fica parado. Há também um modo para documentos de identidade (RG ou CNH), que monta frente e verso numa folha A4 em tamanho real.

A interface é feita em Next.js com Tailwind CSS. O processamento de imagem fica em uma API Python (FastAPI, OpenCV, PaddleOCR em ONNX Runtime e img2pdf), e o histórico e os arquivos ficam no Supabase (PostgreSQL e Storage). Cada pessoa entra com e-mail e senha e vê só os próprios documentos: o login é feito pela própria API, com a senha guardada em hash Argon2id, e o aplicativo só fala com a API, nunca direto com o banco.

## Estrutura do repositório

```text
.
├── CLAUDE.md                  # Contexto e diretrizes de engenharia do projeto
├── README.md
├── docs/
│   ├── documentacao_miniscan.md   # Requisitos, casos de uso e diagramas Mermaid
│   └── figma/                     # Tokens de design e wireframes
├── prototype/                 # Protótipo interativo de UI/UX
├── supabase/
│   └── migrations/            # Schema, índices FTS, triggers, RLS e rollback
├── backend/                   # FastAPI + OpenCV + PaddleOCR (ONNX)
├── frontend/                  # Next.js PWA: câmera ao vivo (OpenCV.js), modos e histórico
├── deploy/vps/                # docker-compose da API para uma VPS
└── .github/workflows/         # CI do backend e do frontend
```

## Como rodar

São três partes, nesta ordem. Primeiro o banco: crie um projeto no Supabase e rode as migrações de `supabase/migrations/`, como explicado abaixo. Depois a API, que precisa do Python 3.11 ou mais novo e do [uv](https://docs.astral.sh/uv/) (veja [backend/README.md](backend/README.md)). Por último o app, que precisa do Node 22.18 ou mais novo (veja [frontend/README.md](frontend/README.md)). A câmera ao vivo só abre no celular por HTTPS; para testar sem publicar nada, o `frontend/README.md` mostra como usar um túnel HTTPS.

## Banco de dados

As migrações em `supabase/migrations/` podem ser executadas no SQL Editor do Supabase. O script `*_init_miniscan_schema.sql` cria as tabelas, índices, gatilhos, políticas de RLS e o bucket `miniscan-files`, e o `*_down_miniscan_schema.sql` desfaz as tabelas, os gatilhos e as políticas (o bucket continua, para não apagar arquivos por engano). As migrações seguintes, na ordem do nome, deixam o papel anônimo só com leitura (`000002`), aceitam o filtro de quadro branco, de um modo que depois foi retirado (`000003`), e criam as contas e as sessões do login, dão dono a cada documento, tiram a leitura pública e deixam o bucket privado (`20261118000004`); cada uma tem o seu script `down` de reversão.

## Documentação

A especificação completa, com requisitos, casos de uso, pipeline de visão computacional e diagramas, está em [docs/documentacao_miniscan.md](docs/documentacao_miniscan.md).
