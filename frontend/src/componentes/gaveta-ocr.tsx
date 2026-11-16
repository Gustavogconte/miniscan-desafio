"use client";

import { Copy, LoaderCircle, RotateCw, X } from "lucide-react";
import { useEffect, useRef } from "react";

import { useAviso } from "@/componentes/aviso";
import type { Pagina } from "@/lib/tipos";

interface Props {
  aberta: boolean;
  pagina: Pagina;
  aoFechar: () => void;
  aoEditar: (texto: string) => void;
  aoTentarDeNovo: () => void;
}

export function GavetaOcr({ aberta, pagina, aoFechar, aoEditar, aoTentarDeNovo }: Props) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const avisar = useAviso();

  useEffect(() => {
    const elemento = dialogo.current;
    if (!elemento) return;
    if (aberta && !elemento.open) elemento.showModal();
    if (!aberta && elemento.open) elemento.close();
  }, [aberta]);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(pagina.textoOcr);
      avisar("Texto copiado");
    } catch {
      avisar("Não foi possível copiar. Selecione o texto e copie manualmente.", "erro");
    }
  }

  return (
    <dialog
      ref={dialogo}
      onClose={aoFechar}
      onClick={(evento) => evento.target === dialogo.current && aoFechar()}
      aria-labelledby="titulo-ocr"
      className="mx-auto mb-0 mt-auto w-full max-w-md rounded-t-2xl border-t border-borda bg-cartao p-0 text-texto backdrop:bg-slate-950/50 backdrop:backdrop-blur-[2px]"
    >
      <div className="space-y-3 p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="titulo-ocr" className="font-display text-base font-bold">
              Texto reconhecido (OCR)
            </h2>
            <p className="mt-0.5 text-xs text-texto-secundario">Confira e corrija antes de salvar. Português (pt-BR).</p>
          </div>
          <button
            type="button"
            onClick={aoFechar}
            aria-label="Fechar"
            className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-secundario text-texto-secundario hover:text-texto"
          >
            <X className="size-5" aria-hidden />
          </button>
        </div>

        {pagina.estadoOcr === "carregando" || pagina.estadoOcr === "pendente" ? (
          <div className="flex h-44 items-center justify-center gap-2 rounded-xl border border-borda bg-fundo text-sm text-texto-secundario">
            <LoaderCircle className="size-4 animate-spin" aria-hidden />
            Lendo o texto da página…
          </div>
        ) : pagina.estadoOcr === "erro" ? (
          <div className="flex h-44 flex-col items-center justify-center gap-3 rounded-xl border border-borda bg-fundo p-4 text-center">
            <p className="text-sm text-texto-secundario">Não foi possível ler o texto desta página.</p>
            <button
              type="button"
              onClick={aoTentarDeNovo}
              className="flex min-h-11 items-center gap-1.5 rounded-xl border border-borda bg-cartao px-4 text-xs font-semibold"
            >
              <RotateCw className="size-4 text-primaria" aria-hidden />
              Tentar de novo
            </button>
          </div>
        ) : (
          <>
            <label htmlFor="texto-ocr" className="sr-only">
              Texto reconhecido
            </label>
            <textarea
              id="texto-ocr"
              value={pagina.textoOcr}
              onChange={(evento) => aoEditar(evento.target.value)}
              rows={9}
              placeholder="Nenhum texto foi reconhecido nesta página."
              className="w-full resize-none rounded-xl border border-borda bg-fundo p-3.5 font-mono text-base leading-relaxed text-texto focus:border-primaria focus:outline-none focus:ring-2 focus:ring-primaria-suave sm:text-xs"
            />
          </>
        )}

        <button
          type="button"
          onClick={copiar}
          disabled={pagina.estadoOcr !== "pronto" || !pagina.textoOcr}
          className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-primaria font-display text-sm font-bold text-white transition hover:bg-primaria-hover disabled:opacity-50"
        >
          <Copy className="size-4" aria-hidden />
          Copiar texto
        </button>
      </div>
    </dialog>
  );
}
