# CLAUDE.md — Contexto do Projeto MiniScan (IC)

## 1. Visão Geral e Escopo do Projeto

O **MiniScan** é um aplicativo de digitalização de documentos inspirado no CamScanner, desenvolvido como projeto de seleção para **Iniciação Científica (IC)** com prazo total de 15 dias.

- **Escopo Obrigatório (MVP):** os 5 itens do enunciado do professor, na ordem: capturar ou importar imagens (câmera ou galeria), **visualizar as imagens capturadas** (tela cheia com zoom), aplicar filtros (`original`, `grayscale`, `bw`), compilar páginas em PDF único e salvar/compartilhar. Também obrigatórios por decisão nossa: extrair texto via OCR (pt-BR; no enunciado é adicional) e detectar bordas da folha com correção de perspectiva (homografia 4 pontos). Os RF01–RF07 da documentação seguem essa ordem.
- **Estratégia de Execução:** Implementar 100% do MVP primeiro. Somente se sobrar tempo após o MVP estar testado e implantado, adicionar a extensão de **Segmentação Híbrida (ROI)** para preservar regiões gráficas/fotos coloridas sem degradá-las com a binarização do texto.

## 2. Arquitetura e Stack Definida

- **Front-end (`/frontend`):** Next.js (App Router, TypeScript), Tailwind CSS, configurado como **PWA** instalável no iOS (Safari) e Android (Chrome), utilizando `navigator.share` (Web Share API) para compartilhamento nativo de PDF.
- **Back-end (`/backend`):** Python + FastAPI + OpenCV (`opencv-python-headless`) + `img2pdf`, com OCR por **PaddleOCR** (modelos PP-OCRv5 latinos em ONNX, via `rapidocr` + `onnxruntime`). O OCR roda no `onnxruntime`: sem Tesseract, sem binários externos e sem PyTorch no servidor. Os cantos da folha vêm do modelo **DocAligner** (FastViT-SA24 em ONNX, DocsaidLab, Apache-2.0, também no `onnxruntime`), com o pipeline OpenCV de reserva. Empacotado com `Dockerfile` (`python:3.11-slim`).
- **Banco de Dados e Storage (`/supabase`):** Supabase PostgreSQL + Supabase Storage (bucket `miniscan-files`).

## 3. O Que Já Foi Concluído (Sprint 1)

1. **Documentação Técnica (`docs/documentacao_miniscan.md`):** Requisitos Funcionais (RF01–RF07), Não Funcionais (RNF01–RNF03), Casos de Uso (UC01–UC07) e diagramas Mermaid.
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
4. **Câmera e modos (`/camera`):** vídeo em tela cheia, que abre em 4:3 e sobe para a maior resolução 4:3 do aparelho (`maximizarResolucao` em `frontend/src/lib/camera.ts`, que volta atrás se a câmera recusar ou trocar para 16:9). A foto sai só pelo botão: o recorte ao vivo com OpenCV.js e a captura automática saíram em 2026-11-18, a pedido do autor, porque erravam nas fotos reais (não reintroduzir sem ele pedir). Logo na captura, uma cópia de até 1280 px vai ao `/detectar-cantos` (`detectarNaCaptura`), e o recorte e o Lote reaproveitam a resposta (`usarDeteccaoDaCaptura`). Modos Único/Lote e RG ou CNH (`/compor-cartao`, A4 em tamanho real; a moldura-guia só vale se o servidor não achar o documento; o passaporte e o nome "Cartão ID" saíram em 2026-11-18 a pedido do autor). Os modos Extrair texto, Livro, Quadro branco e QR code foram retirados em 2026-11-18, a pedido do autor: fogem do enunciado, e o OCR já fica no editor de toda página. O banco ainda aceita o filtro `whiteboard` (migração `20261116000003`), mas a API não. O PDF aceita carimbo de data e hora. A `getUserMedia` exige HTTPS no celular; sem ela, a tela cai para a câmera nativa e a galeria (que sobe com até 3200 px).
5. **Visualização das imagens capturadas (RF02):** visualizador em tela cheia (`frontend/src/componentes/visualizador-paginas.tsx`, `yet-another-react-lightbox` com o plugin de zoom, carregado sob demanda): pinça, dois toques, deslizar entre páginas e alternar entre página tratada e foto original. Abre no editor (que também tem a grade de todas as páginas), na revisão das fotos do lote antes de processar e na tela do documento salvo (`/documento?id=`, aberta pelo histórico, com páginas, texto OCR e PDF). O voltar do celular fecha o visualizador (`frontend/src/lib/usar-visualizador.ts`, entrada própria no histórico).

## 4. Pipeline de Visão Computacional (Especificação para `/backend`)

- **Detecção de Cantos (`POST /detectar-cantos`, `app/visao/bordas.py`):** híbrida. Primeiro o **DocAligner** (`app/visao/docaligner.py`, singleton carregado na subida como o `MotorOcr`, 1 thread): foto esticada a 256x256 (BGR, 0..1), 4 mapas de calor de 128x128, canto = centróide da maior mancha >= 0,3; aceito se o menor pico >= 0,7 e o quadrilátero passa em `validar_cantos_normalizados`. O `.onnx` (83 MB, release 1.1.1 do DocsaidLab/DocAligner, SHA-256 conferido) fica em `backend/modelos/`, fora do git: `uv run python -m app.visao.docaligner` baixa (o Dockerfile e o CI rodam o mesmo). Avaliação com 13 fotos reais na `docs/documentacao_miniscan.md`: OpenCV 7, DocAligner 8, híbrido 13 (o modelo não vê a folha que ocupa quase a foto toda; o OpenCV erra os cartões). Se o modelo recusa, vale `detectar_cantos_opencv`, o pipeline clássico: candidatos pelo brilho (`cv2.Canny` 50/150 e 20/60 + `cv2.morphologyEx`, Otsu) e pela cor (Canny e Otsu invertido na saturação HSV, para mesa ocre/bege/madeira clara) -> `cv2.convexHull` -> `cv2.approxPolyDP` com tolerância crescente; com mais de 4 lados (dedo no canto, canto dobrado, papel ondulado), os 4 lados mais longos são prolongados até se cruzarem. Vence o maior quadrilátero com **apoio de borda** >= 0,8 (gradiente perpendicular a cada lado, brilho + saturação somados, limiar `max(8, 2 x mediana do gradiente)`). Cenários de teste em `backend/tests/fotos_realistas.py`, rodados com o híbrido e com o OpenCV sozinho. Retorna coordenadas normalizadas `(0..1)` para o ajuste manual.
- **Processamento e Filtros (`POST /processar-pagina`):**
  - Homografia: `cv2.getPerspectiveTransform` + `cv2.warpPerspective` com `INTER_CUBIC`. Páginas `original` e `grayscale` em JPEG 95, `bw` em PNG.
  - `original`: Imagem retificada em RGB.
  - `grayscale`: Luminância + `cv2.createCLAHE` para uniformizar iluminação.
  - `bw`: P&B "suave" de scanner: amplia páginas com lado < 2000 px (`INTER_CUBIC`), nivela a iluminação dividindo pelo papel estimado (`cv2.dilate` + `cv2.medianBlur`) e aplica uma curva íngreme (abaixo de 150 preto, acima de 215 branco). Sem corte seco, as letras não serrilham em fotos de baixa resolução. É uma camada **só visual** (tela e PDF): o OCR nunca lê esta versão.
- **OCR e PDF (`POST /extrair-ocr` e `POST /gerar-pdf`):**
  - OCR com `RapidOCR` (singleton `MotorOcr` em `app/ocr.py`) sempre sobre a **página retificada original**, sem filtro: a rede do PaddleOCR depende dos gradientes suaves (anti-aliasing) das bordas das letras, que a binarização destrói. O front-end envia ao `/extrair-ocr` a foto original + os cantos confirmados, e a API retifica com a mesma `corrigir_perspectiva` do `/processar-pagina`. Medido: com texto pequeno, a leitura cai de ~99% (original) para ~35% (P&B) e ~55% (CLAHE). As caixas são ordenadas em linhas, de cima para baixo e da esquerda para a direita (`ordenar_em_linhas`).
  - Compilar páginas ordenadas em PDF único usando `img2pdf`.
- **Persistência (`POST /documentos`):** a API recebe PDF, imagens, filtros e textos OCR, faz o upload no bucket `miniscan-files` com a chave de serviço e insere em `documents` e `document_pages`. Os endpoints de visão continuam sem estado.
- **Saúde (`GET /saude`):** informa se a API está no ar, se o OCR e o modelo de cantos carregaram (`docaligner_disponivel`) e se a persistência está configurada.

## 5. Convenções de Código e Git

- **Idioma:** Projeto em **português (pt-BR)**: rotas da API, nomes de módulos, funções, variáveis e campos dos contratos, mensagens de commit, textos de interface e documentação. Identificadores sem acento e em `snake_case` no Python (`corrigir_perspectiva`) e `camelCase` no TypeScript (`corrigirPerspectiva`). Ficam como estão: APIs de bibliotecas (`cv2`, FastAPI, Supabase), nomes de tabelas e colunas já migrados (`documents`, `document_pages`) e os valores de filtro gravados no banco (`original`, `grayscale`, `bw`), que também são usados nos contratos da API.
- **Commits:** Seguir *Conventional Commits* atômicos, com descrição em português (`feat(visao): adiciona detecção de cantos`, `feat(ocr): ...`, `feat(pwa): ...`, `fix(...): ...`).
- **Estilo de Documentação do Usuário:** Parágrafos diretos e objetivos, sem listas com marcadores excessivos e sem vocabulário genérico de IA.

## 6. Pendências e Próximos Passos

- **Preservação de figuras removida (2026-11-17):** a extensão de Segmentação Híbrida (DocLayout-YOLO) foi retirada. Num teste real ela classificou um RG inteiro como figura por causa da foto 3x4, e sem ela a API caiu de ~1 GB para ~400 MB de pico de memória, o P&B de 2,4 s para 0,08 s e o OCR de 4,9 s para 2,7 s por página. Não reintroduzir sem resolver o falso positivo em documentos com foto.
- **Hospedagem da API:** o Hugging Face passou a cobrar por Spaces com Docker, e a API usa ~1 GB de RAM no pico (planos gratuitos de 512 MB não comportam). Hoje o teste no celular é feito com a API no computador e um túnel HTTPS (`frontend/README.md`). Para a entrega, falta escolher entre Google Cloud Run, Railway ou Hugging Face PRO (`backend/scripts/publicar_space.py` já está pronto).
- **Validação com fotos reais:** o detector de cantos foi medido em 2026-11-18 com 13 fotos do iPhone (resultado na documentação, seção 3), uma amostra pequena. A folha que ocupa quase a foto toda depende só do OpenCV, porque o modelo não a vê. O P&B ainda foi calibrado só com cenários sintéticos.
