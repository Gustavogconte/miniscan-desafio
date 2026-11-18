# MiniScan PWA

Front-end do MiniScan em Next.js 16 (App Router, TypeScript e Tailwind CSS v4), instalável como PWA no Android e no iPhone.

A câmera mostra o vídeo ao vivo na maior resolução 4:3 que o aparelho oferece (`maximizarResolucao`, em `src/lib/camera.ts`) e fotografa quando a pessoa toca no botão. Logo na captura, uma cópia de até 1280 px vai para a API em `../backend`, que acha os cantos da folha com o modelo DocAligner e, quando ele não acha, com o pipeline OpenCV. A tela de recorte abre com esses cantos para a pessoa conferir. O recorte final, os filtros, o OCR e o PDF também ficam com a API, que recebe a foto inteira. A foto da galeria sobe com até 3200 px no lado maior.

O app já teve um recorte ao vivo, com o OpenCV.js num Web Worker e captura automática quando a folha parava. Ele saiu porque errava muito nas fotos reais e baixava 11 MB de OpenCV.js no celular. A detecção depois da captura, no servidor, acerta bem mais.

Modos da câmera:

- **Digitalizar:** fluxo padrão, uma foto por vez (Único) ou várias seguidas (Lote). No editor, o botão "+ Página" volta para a câmera e acrescenta páginas ao mesmo documento.
- **RG ou CNH:** frente e verso do documento, montados numa folha A4 em tamanho real.

O texto reconhecido (OCR) de cada página fica no botão "Texto OCR" do editor.

As páginas abrem em tela cheia no visualizador (`src/componentes/visualizador-paginas.tsx`, com a biblioteca `yet-another-react-lightbox`): pinça e dois toques ampliam, deslizar troca de página e um botão alterna entre a página tratada e a foto original. Ele aparece no editor, na revisão das fotos do lote (tocando na miniatura da câmera) e na tela do documento salvo (`/documento?id=...`), que o histórico abre com as páginas, o texto do OCR e os botões do PDF. O gesto de voltar do celular fecha o visualizador sem sair da tela (`src/lib/usar-visualizador.ts`).

## Rodando localmente

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

No `.env.local`, preencha `NEXT_PUBLIC_API_URL` com o endereço da API e use a chave **publishable** do Supabase em `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. Nunca use a chave secreta: o RLS deixa a chave pública só com leitura.

A câmera ao vivo usa a `getUserMedia`, que exige contexto seguro. Ela funciona em `localhost` e em sites HTTPS. No celular, pela rede local em http, a tela oferece a câmera nativa do sistema e a galeria como alternativa.

## Testes e verificações

```bash
npm test          # regras do visualizador e dos cantos do cartão (node:test, Node 22.18+)
npx tsc --noEmit
npm run lint
npm run build
```

## Deploy na Vercel

1. Em [vercel.com/new](https://vercel.com/new), importe o repositório do GitHub, mantenha o nome de projeto `miniscan-desafio` (é o que o CORS da API aceita) e defina **Root Directory** como `frontend`. O framework (Next.js) é detectado sozinho.
2. Em *Environment Variables*, cadastre:
   - `NEXT_PUBLIC_API_URL`: o endereço HTTPS público da API (veja "Deploy numa VPS" em `backend/README.md`).
   - `NEXT_PUBLIC_SUPABASE_URL`: a URL do projeto no Supabase.
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: a chave **publishable** (`sb_publishable_...`).
3. Faça o deploy. As variáveis `NEXT_PUBLIC_*` entram no build, então qualquer mudança nelas pede um novo deploy.
4. Se o projeto tiver outro nome na Vercel, libere o domínio dele no CORS da API (`MINISCAN_ORIGENS_CORS` e `MINISCAN_ORIGENS_CORS_REGEX`; veja `backend/README.md`).

O `next.config.ts` envia cabeçalhos de segurança (câmera liberada só para o próprio app, bloqueio de iframe). A cada push na `main` que mexe no front-end, e em cada pull request, o GitHub Actions (`.github/workflows/frontend.yml`) roda lint, tipos, testes e build.

## Testar no celular com um túnel HTTPS (sem deploy)

Para testar a câmera ao vivo no celular sem publicar nada, a API e o app rodam no computador e um túnel gratuito da Cloudflare (`cloudflared`) dá uma URL HTTPS pública. O app é compilado no modo de mesma origem: `/api/*` é encaminhado pelo próprio Next para a API local, então basta um túnel e não há CORS.

```bash
# 1. API (em backend/)
uv run uvicorn app.main:app --port 8000 --env-file .env

# 2. App (em frontend/). No Git Bash, MSYS_NO_PATHCONV=1 impede que "/api" vire um caminho do Windows.
MSYS_NO_PATHCONV=1 MINISCAN_API_INTERNA=http://127.0.0.1:8000 NEXT_PUBLIC_API_URL=/api npm run build
npx next start -p 3000

# 3. Túnel: imprime uma URL https://....trycloudflare.com para abrir no celular
cloudflared tunnel --url http://localhost:3000
```

A URL muda a cada vez que o túnel é aberto e só funciona com o computador ligado e os três processos rodando.
