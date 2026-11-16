import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
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
        ],
      },
      {
        // OpenCV.js (~11 MB) com a versão no nome do arquivo: pode ficar em cache para sempre.
        source: "/vendor/:arquivo*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
      {
        // Workers sem versão no nome: o navegador revalida a cada carregamento.
        source: "/workers/:arquivo*",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }],
      },
    ];
  },
};

export default nextConfig;
