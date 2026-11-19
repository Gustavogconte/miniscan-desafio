import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import type { ReactNode } from "react";

import { ProvedorAvisos } from "@/componentes/aviso";
import { GuardaSessao } from "@/componentes/guarda-sessao";
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
  description: "Digitalize documentos com o celular: recorte automático, filtros, leitura do texto e PDF.",
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
  // No Android, o teclado virtual encolhe a área útil (dvh) em vez de cobrir a tela.
  interactiveWidget: "resizes-content",
  // Barra do navegador na cor do fundo do app (o app tem só o tema claro).
  themeColor: "#f8fafc",
};

// Tipo escrito aqui, e não o LayoutProps gerado pelo Next em .next/: no CI o tsc roda
// antes do build, quando esses tipos ainda não existem.
export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html
      lang="pt-BR"
      className={`${fonteDisplay.variable} ${fonteCorpo.variable} ${fonteMono.variable} h-full antialiased`}
    >
      <body className="h-full">
        <ProvedorAvisos>
          <GuardaSessao>
            <ProvedorDigitalizacao>
              <div className="mx-auto flex h-dvh w-full max-w-md flex-col overflow-hidden bg-fundo sm:border-x sm:border-borda">
                {children}
              </div>
            </ProvedorDigitalizacao>
          </GuardaSessao>
        </ProvedorAvisos>
      </body>
    </html>
  );
}
