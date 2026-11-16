# MiniScan PWA

Front-end do MiniScan em Next.js 16 (App Router, TypeScript e Tailwind CSS v4), instalável como PWA no Android e no iPhone.

A câmera ao vivo detecta a folha a cada quadro com o OpenCV.js, rodando num Web Worker (`public/workers/`). Ela usa o mesmo pipeline do backend: Canny, fechamento morfológico e quadrilátero convexo. O contorno fica verde quando a folha para, e a foto é tirada sozinha depois de cerca de 0,7 s parada. O recorte final, os filtros, o OCR e o PDF ficam com a API em `../backend`.

Modos da câmera:

- **Digitalizar:** fluxo padrão, uma foto por vez (Único) ou várias seguidas (Lote).
- **Extrair texto:** abre o texto reconhecido logo depois do recorte.
- **Cartão ID:** frente e verso de RG, CNH ou cartão, ou a página do passaporte, montados numa folha A4 em tamanho real.
- **Livro:** uma foto do livro aberto vira duas páginas; a lombada é encontrada sozinha.
- **Quadro branco:** filtro que tira o reflexo e realça a cor das canetas.
- **QR code:** leitura ao vivo, com o `BarcodeDetector` do navegador ou, no Safari, pela API.

## Rodando localmente

```bash
cd frontend
npm install            # também copia o OpenCV.js para public/vendor/
cp .env.example .env.local
npm run dev
```

No `.env.local`, preencha `NEXT_PUBLIC_API_URL` com o endereço da API e use a chave **publishable** do Supabase em `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. Nunca use a chave secreta: o RLS deixa a chave pública só com leitura.

A câmera ao vivo usa a `getUserMedia`, que exige contexto seguro. Ela funciona em `localhost` e em sites HTTPS. No celular, pela rede local em http, a tela oferece a câmera nativa do sistema e a galeria como alternativa.

## Testes e verificações

```bash
npm test          # detecção de cantos do OpenCV.js (node:test)
npx tsc --noEmit
npm run lint
npm run build
```

O OpenCV.js (cerca de 11 MB) não vai para o Git. O script `scripts/copiar-opencv.mjs` o copia de `node_modules` antes do `dev` e do `build`.

## Deploy na Vercel

1. Em [vercel.com/new](https://vercel.com/new), importe o repositório do GitHub e defina **Root Directory** como `frontend`. O framework (Next.js) é detectado sozinho.
2. Em *Environment Variables*, cadastre:
   - `NEXT_PUBLIC_API_URL`: o endereço da API no Hugging Face Spaces, por exemplo `https://usuario-miniscan-api.hf.space`.
   - `NEXT_PUBLIC_SUPABASE_URL`: a URL do projeto no Supabase.
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: a chave **publishable** (`sb_publishable_...`).
3. Faça o deploy. As variáveis `NEXT_PUBLIC_*` entram no build, então qualquer mudança nelas pede um novo deploy.
4. Libere o domínio da Vercel no CORS da API (variável `MINISCAN_ORIGENS_CORS` do Space; veja `backend/README.md`).

O `next.config.ts` envia cabeçalhos de segurança (câmera liberada só para o próprio app, bloqueio de iframe) e deixa o OpenCV.js em cache permanente, porque o nome do arquivo já tem a versão. A cada push, o GitHub Actions (`.github/workflows/frontend.yml`) roda lint, tipos, testes e build.

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
