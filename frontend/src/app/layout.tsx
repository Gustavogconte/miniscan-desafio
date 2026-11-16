import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans, JetBrains_Mono, Space_Grotesk } from "next/font/google";

import { ProvedorAvisos } from "@/componentes/aviso";
import { SCRIPT_TEMA_INICIAL } from "@/componentes/tema";
import { ProvedorDigitalizacao } from "@/lib/estado-digitalizacao";

import "./globals.css";

const fonteDisplay = Space_Grotesk({
  variable: "--fonte-display",
  subsets: ["latin"],
  weight: ["600", "700"],
});

const fonteCorpo = IBM_Plex_Sans({
  variable: "--fonte-corpo",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const fonteMono = JetBrains_Mono({
  variable: "--fonte-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "MiniScan",
  description: "Digitalize documentos com o celular: recorte automático, filtros, OCR em português e PDF.",
  applicationName: "MiniScan",
  appleWebApp: {
    capable: true,
    title: "MiniScan",
    statusBarStyle: "default",
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8fafc" },
    { media: "(prefers-color-scheme: dark)", color: "#0f172a" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pt-BR"
      data-theme="light"
      suppressHydrationWarning
      className={`${fonteDisplay.variable} ${fonteCorpo.variable} ${fonteMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: SCRIPT_TEMA_INICIAL }} />
      </head>
      <body className="h-full">
        <ProvedorAvisos>
          <ProvedorDigitalizacao>
            <div className="mx-auto flex h-dvh w-full max-w-md flex-col overflow-hidden bg-fundo sm:border-x sm:border-borda">
              {children}
            </div>
          </ProvedorDigitalizacao>
        </ProvedorAvisos>
      </body>
    </html>
  );
}
