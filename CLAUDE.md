# CLAUDE.md — Contexto do Projeto MiniScan (IC)

## 1. Visão Geral e Escopo do Projeto

O **MiniScan** é um aplicativo de digitalização de documentos inspirado no CamScanner, desenvolvido como projeto de seleção para **Iniciação Científica (IC)** com prazo total de 15 dias.

- **Escopo Obrigatório (MVP):** Capturar ou importar imagens (câmera ou galeria), detectar bordas da folha e corrigir perspectiva (homografia 4 pontos), aplicar filtros (`original`, `grayscale`, `bw`), extrair texto via OCR (pt-BR), compilar páginas em PDF único, e salvar/compartilhar o histórico na nuvem.
- **Estratégia de Execução:** Implementar 100% do MVP primeiro. Somente se sobrar tempo após o MVP estar testado e implantado, adicionar a extensão de **Segmentação Híbrida (ROI)** para preservar regiões gráficas/fotos coloridas sem degradá-las com a binarização do texto.

## 2. Arquitetura e Stack Definida

- **Front-end (`/frontend`):** Next.js (App Router, TypeScript), Tailwind CSS, configurado como **PWA** instalável no iOS (Safari) e Android (Chrome), utilizando `navigator.share` (Web Share API) para compartilhamento nativo de PDF.
- **Back-end (`/backend`):** Python + FastAPI + OpenCV (`opencv-python-headless`) + `img2pdf`, com OCR por **PaddleOCR** (modelos PP-OCRv5 latinos em ONNX, via `rapidocr` + `onnxruntime`) e detecção de regiões gráficas por **DocLayout-YOLO** em ONNX (`models/doclayout_yolo.onnx`, opcional). Tudo roda no `onnxruntime`: sem Tesseract, sem binários externos e sem PyTorch no servidor. Empacotado com `Dockerfile` (`python:3.11-slim`).
- **Banco de Dados e Storage (`/supabase`):** Supabase PostgreSQL + Supabase Storage (bucket `miniscan-files`).

## 3. O Que Já Foi Concluído (Sprint 1)

1. **Documentação Técnica (`docs/documentacao_miniscan.md`):** Requisitos Funcionais (RF01–RF06), Não Funcionais (RNF01–RNF03), Casos de Uso e diagramas Mermaid.
2. **Banco de Dados (`supabase/migrations/20261116000001_init_miniscan_schema.sql`):**
   - Tabelas `public.documents` (`id`, `title`, `pdf_url`, `page_count`, `created_at`, `updated_at`) e `public.document_pages` (`id`, `document_id`, `page_order`, `original_image_url`, `processed_image_url`, `filter_applied`, `ocr_text`, `created_at`, `updated_at`).
   - Triggers automáticos para `updated_at` e sincronização de `documents.page_count`.
   - Busca Full-Text em português via RPC `search_miniscan_documents(search_query TEXT)`.
   - RLS ativado e bucket `miniscan-files` (limite 15MB, MIME types restritos). A migração `20261116000002_restringe_escrita_anonima.sql` deixa `anon`/`authenticated` só com leitura: toda gravação passa pela API com a chave secreta.
3. **Design System e Protótipo (`prototype/miniscan_prototype.html` e `docs/figma/`):**
   - Identidade visual **Clean Professional** com temas Claro (padrão) e Escuro (`data-theme="light"` e `data-theme="dark"`).
   - Paleta Light: fundo `#F8FAFC`, cards `#FFFFFF`, secundário `#F1F5F9`, bordas `#E2E8F0`, destaque `#2563EB`, texto `#172033` / `#64748B`.
   - Paleta Dark: fundo `#0F172A`, cards `#1E293B`, elevado `#334155`, destaque `#3B82F6`, texto `#F8FAFC` / `#CBD5E1`.
   - Tipografia: `Space Grotesk` (títulos), `IBM Plex Sans` (corpo) e `JetBrains Mono` (metadados/OCR).
   - Fluxo validado de 4 telas: (1) Início & Busca OCR, (2) Ajuste de Perspectiva 4 pontos, (3) Editor de Filtros & Gaveta OCR, (4) Exportação & Compartilhamento PDF.
4. **Câmera ao vivo e modos (`/camera`, Fase 1):** detecção da folha a cada quadro com OpenCV.js num Web Worker (`frontend/public/workers/detectar-cantos.js`, mesmo pipeline de `bordas.py`), captura automática quando a folha fica parada (~0,7 s), Único/Lote e os modos Digitalizar, Extrair texto, Cartão ID (`/compor-cartao`, A4 em tamanho real), Livro (`/dividir-livro`, lombada pela sombra + homografia inversa), Quadro branco (filtro `whiteboard`, migração `20261116000003`) e QR code (`BarcodeDetector` ou `/ler-qrcode`). O PDF aceita carimbo de data e hora. A `getUserMedia` exige HTTPS no celular; sem ela, a tela cai para a câmera nativa e a galeria.

## 4. Pipeline de Visão Computacional (Especificação para `/backend`)

- **Detecção de Cantos (`POST /detectar-cantos`):** Redimensionamento proporcional -> `cv2.cvtColor` (cinza) -> `cv2.GaussianBlur` -> `cv2.Canny` -> `cv2.morphologyEx` (fechamento) -> `cv2.findContours` -> `cv2.approxPolyDP` (4 vértices). Retornar coordenadas normalizadas `(0..1)` para o front-end permitir ajuste manual.
- **Processamento e Filtros (`POST /processar-pagina`):**
  - Homografia: `cv2.getPerspectiveTransform` + `cv2.warpPerspective`.
  - `original`: Imagem retificada em RGB.
  - `grayscale`: Luminância + `cv2.createCLAHE` para uniformizar iluminação.
  - `bw`: `cv2.GaussianBlur(3x3)` + `cv2.adaptiveThreshold` (`ADAPTIVE_THRESH_GAUSSIAN_C`, bloco ímpar de no mínimo 35 px crescendo com a página, `C=15`) para remover sombras sem serrilhar as letras. É uma camada **só visual** (tela e PDF): o OCR nunca lê a versão binarizada.
- **OCR e PDF (`POST /extrair-ocr` e `POST /gerar-pdf`):**
  - OCR com `RapidOCR` (singleton `MotorOcr` em `app/ocr.py`) sempre sobre a **página retificada original**, sem filtro: a rede do PaddleOCR depende dos gradientes suaves (anti-aliasing) das bordas das letras, que a binarização destrói. O front-end envia ao `/extrair-ocr` a foto original + os cantos confirmados, e a API retifica com a mesma `corrigir_perspectiva` do `/processar-pagina`. Medido: com texto pequeno, a leitura cai de ~99% (original) para ~35% (P&B) e ~55% (CLAHE). As caixas são ordenadas em linhas, de cima para baixo e da esquerda para a direita (`ordenar_em_linhas`).
  - Regiões gráficas (`figure`, `picture`, `signature`, `image`, `stamp`) vêm do `DetectorLayout` (singleton em `app/visao/layout.py`, letterbox 1024x1024 + `cv2.dnn.NMSBoxes`). Elas são mantidas com a imagem original sobre o fundo filtrado (`preservar_graficos=True` em `/processar-pagina`) e mascaradas antes do OCR. O `/processar-pagina` devolve as regiões no cabeçalho `X-Regioes-Graficas` e o front-end as reenvia ao `/extrair-ocr` (campo `regioes`), porque a detecção custa ~2 s em CPU; o detector também guarda cache por página. Sem o arquivo `.onnx`, o detector fica desligado e o restante funciona igual.
  - Compilar páginas ordenadas em PDF único usando `img2pdf`.
- **Persistência (`POST /documentos`):** a API recebe PDF, imagens, filtros e textos OCR, faz o upload no bucket `miniscan-files` com a chave de serviço e insere em `documents` e `document_pages`. Os endpoints de visão continuam sem estado.
- **Saúde (`GET /saude`):** informa se a API está no ar, se o OCR carregou, se o modelo de layout está instalado e se a persistência está configurada.

## 5. Convenções de Código e Git

- **Idioma:** Projeto em **português (pt-BR)**: rotas da API, nomes de módulos, funções, variáveis e campos dos contratos, mensagens de commit, textos de interface e documentação. Identificadores sem acento e em `snake_case` no Python (`corrigir_perspectiva`) e `camelCase` no TypeScript (`corrigirPerspectiva`). Ficam como estão: APIs de bibliotecas (`cv2`, FastAPI, Supabase), nomes de tabelas e colunas já migrados (`documents`, `document_pages`) e os valores de filtro gravados no banco (`original`, `grayscale`, `bw`), que também são usados nos contratos da API.
- **Commits:** Seguir *Conventional Commits* atômicos, com descrição em português (`feat(visao): adiciona detecção de cantos`, `feat(ocr): ...`, `feat(pwa): ...`, `fix(...): ...`).
- **Estilo de Documentação do Usuário:** Parágrafos diretos e objetivos, sem listas com marcadores excessivos e sem vocabulário genérico de IA.
