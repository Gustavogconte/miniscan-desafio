import type { NextConfig } from "next";

/** Origem da API (NEXT_PUBLIC_API_URL entra no build), para o connect-src do CSP. */
function origemDaApi(): string {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").origin;
  } catch {
    return "";
  }
}

/**
 * Política de conteúdo, só em produção (o modo dev precisa de eval e WebSocket).
 * O ponto principal é o connect-src: o token da sessão fica no localStorage, e,
 * se um dia entrar um XSS ou uma dependência maliciosa, ela não consegue mandá-lo
 * para fora. Só a API, o próprio app e o Storage do Supabase (links assinados do
 * PDF) são alcançáveis. Os scripts embutidos do Next e o do tema pedem 'unsafe-inline'.
 */
function politicaDeConteudo(): string {
  return [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data: https://*.supabase.co",
    "font-src 'self'",
    `connect-src 'self' ${origemDaApi()} https://*.supabase.co`,
    "media-src 'self' blob:",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // Toda tela passa pela guarda de sessão (src/componentes/guarda-sessao.tsx), que só
    // existe no navegador: no servidor, a página vira um "carregando". A validação de
    // navegação instantânea do modo dev não tem o que medir e avisaria em toda rota;
    // fica só para quem exportar `instant` explicitamente.
    instantInsights: { validationLevel: "manual-warning" },
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  /**
   * Com MINISCAN_API_INTERNA definida no build, /api/* é encaminhado para a API
   * (ex.: http://127.0.0.1:8000). Assim o app e a API ficam na mesma origem: basta
   * um túnel HTTPS para o celular e não há CORS. Sem a variável, nada é reescrito
   * e o front-end chama a API pelo NEXT_PUBLIC_API_URL.
   */
  async rewrites() {
    const apiInterna = process.env.MINISCAN_API_INTERNA?.replace(/\/$/, "");
    return apiInterna ? [{ source: "/api/:caminho*", destination: `${apiInterna}/:caminho*` }] : [];
  },
  async headers() {
    return [
      {
        source: "/:caminho*",
        headers: [
          // Só o próprio app pode usar a câmera; microfone e localização ficam bloqueados.
          { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=()" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Impede que o app seja embutido em outro site (clickjacking).
          { key: "X-Frame-Options", value: "DENY" },
          ...(process.env.NODE_ENV === "production"
            ? [{ key: "Content-Security-Policy", value: politicaDeConteudo() }]
            : []),
        ],
      },
    ];
  },
};

export default nextConfig;
