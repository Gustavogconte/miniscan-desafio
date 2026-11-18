"use client";

import { LoaderCircle } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect } from "react";

import { useAviso } from "@/componentes/aviso";
import type { PropsVisualizador } from "@/componentes/visualizador-paginas";

/** Baixa o visualizador (e a biblioteca de zoom) antes do primeiro toque. */
export function carregarVisualizador() {
  return import("@/componentes/visualizador-paginas");
}

/** Pré-carga silenciosa: uma falha aqui reaparece, tratada, quando o visualizador abrir. */
export function adiantarVisualizador(): void {
  carregarVisualizador().catch(() => {});
}

/**
 * Sem rede para baixar o visualizador, a tela não pode cair: as páginas da
 * digitalização ficam só na memória. Avisa, fecha e deixa o resto funcionando.
 */
function FalhaAoCarregar({ aoFechar }: PropsVisualizador) {
  const avisar = useAviso();
  useEffect(() => {
    avisar("Não foi possível abrir as páginas em tela cheia. Confira a conexão.", "erro");
    aoFechar();
  }, [avisar, aoFechar]);
  return null;
}

export const VisualizadorPaginas = dynamic<PropsVisualizador>(
  () => carregarVisualizador().catch(() => ({ default: FalhaAoCarregar })),
  {
    ssr: false,
    // Enquanto baixa, a tela já escurece e não aceita outro toque por baixo.
    loading: () => (
      <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-950" role="status">
        <LoaderCircle className="size-8 animate-spin text-white" aria-label="Abrindo as páginas" />
      </div>
    ),
  },
);
