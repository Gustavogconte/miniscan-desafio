# MiniScan

O MiniScan é um aplicativo de digitalização de documentos inspirado no CamScanner, desenvolvido como projeto de seleção para Iniciação Científica. Ele roda no Android e no iPhone como aplicação web instalável (PWA) e permite capturar ou importar uma foto, corrigir a perspectiva da folha, aplicar filtros, extrair o texto via OCR em português e gerar um PDF único para baixar ou compartilhar.

A interface é feita em Next.js com Tailwind CSS. O processamento de imagem fica em uma API Python (FastAPI, OpenCV, Tesseract e img2pdf), e o histórico e os arquivos ficam no Supabase (PostgreSQL e Storage).

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
├── backend/                   # Sprint 2: FastAPI + OpenCV + Tesseract
└── frontend/                  # Sprint 3: Next.js PWA + Supabase
```

## Banco de dados

As migrações em `supabase/migrations/` podem ser executadas no SQL Editor do Supabase. O script `*_init_miniscan_schema.sql` cria as tabelas, índices, gatilhos, políticas de RLS e o bucket `miniscan-files`, e o `*_down_miniscan_schema.sql` desfaz essas alterações.

## Documentação

A especificação completa, com requisitos, casos de uso, pipeline de visão computacional e diagramas, está em [docs/documentacao_miniscan.md](docs/documentacao_miniscan.md).
