# MiniScan

O MiniScan é um aplicativo de digitalização de documentos inspirado no CamScanner, desenvolvido como projeto de seleção para Iniciação Científica. Ele roda no Android e no iPhone como aplicação web instalável (PWA) e permite capturar ou importar uma foto, corrigir a perspectiva da folha, aplicar filtros, extrair o texto via OCR em português e gerar um PDF único para baixar ou compartilhar.

A câmera faz o recorte ao vivo: a folha é detectada a cada quadro, direto no navegador, e a foto é tirada sozinha quando o documento fica parado. Há também modos para extrair texto, digitalizar cartões de identidade em tamanho real, separar as duas páginas de um livro aberto, realçar quadros brancos e ler QR codes.

A interface é feita em Next.js com Tailwind CSS. O processamento de imagem fica em uma API Python (FastAPI, OpenCV, PaddleOCR e DocLayout-YOLO em ONNX Runtime, e img2pdf), e o histórico e os arquivos ficam no Supabase (PostgreSQL e Storage).

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
├── backend/                   # FastAPI + OpenCV + PaddleOCR/DocLayout-YOLO (ONNX)
└── frontend/                  # Next.js PWA: câmera ao vivo (OpenCV.js), modos e histórico
```

## Banco de dados

As migrações em `supabase/migrations/` podem ser executadas no SQL Editor do Supabase. O script `*_init_miniscan_schema.sql` cria as tabelas, índices, gatilhos, políticas de RLS e o bucket `miniscan-files`, e o `*_down_miniscan_schema.sql` desfaz essas alterações. As migrações seguintes, na ordem do nome, deixam o papel anônimo só com leitura (`000002`) e aceitam o filtro de quadro branco (`000003`); cada uma tem o seu script `down` de reversão.

## Documentação

A especificação completa, com requisitos, casos de uso, pipeline de visão computacional e diagramas, está em [docs/documentacao_miniscan.md](docs/documentacao_miniscan.md).
