"use client";

import { Camera, ImageIcon, LoaderCircle, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { useCapturaFoto } from "@/componentes/captura-foto";
import { CartaoDocumento } from "@/componentes/cartao-documento";
import { Logo } from "@/componentes/logo";
import { BotaoTema } from "@/componentes/tema";
import { useDigitalizacao } from "@/lib/estado-digitalizacao";
import { buscarDocumentos } from "@/lib/supabase";
import type { DocumentoHistorico } from "@/lib/tipos";

type EstadoLista =
  | { tipo: "carregando" }
  | { tipo: "pronto"; documentos: DocumentoHistorico[] }
  | { tipo: "erro"; mensagem: string };

const ATRASO_BUSCA_MS = 300;

export default function TelaInicio() {
  const { paginas, reiniciar } = useDigitalizacao();
  const captura = useCapturaFoto();
  const [termo, setTermo] = useState("");
  const [lista, setLista] = useState<EstadoLista>({ tipo: "carregando" });

  // Voltar ao início descarta uma digitalização que não foi salva.
  useEffect(() => {
    if (paginas.length > 0) reiniciar();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- só ao abrir a tela
  }, []);

  useEffect(() => {
    let cancelado = false;
    const temporizador = setTimeout(
      async () => {
        try {
          const documentos = await buscarDocumentos(termo);
          if (!cancelado) setLista({ tipo: "pronto", documentos });
        } catch (erro) {
          if (!cancelado) {
            setLista({ tipo: "erro", mensagem: erro instanceof Error ? erro.message : "Erro ao carregar." });
          }
        }
      },
      termo ? ATRASO_BUSCA_MS : 0,
    );
    return () => {
      cancelado = true;
      clearTimeout(temporizador);
    };
  }, [termo]);

  const quantidade = lista.tipo === "pronto" ? lista.documentos.length : null;

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      {captura.entradas}

      <div className="shrink-0 px-5 pb-3 pt-[max(1rem,env(safe-area-inset-top))]">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="sr-only">MiniScan</h1>
            <Logo className="h-9 w-auto" />
            <p className="mt-1 text-xs text-texto-secundario">Digitalizador de documentos com OCR</p>
          </div>
          <BotaoTema />
        </div>

        <div className="relative mt-4">
          <label htmlFor="busca" className="sr-only">
            Buscar documento por título ou texto extraído
          </label>
          <Search
            className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-texto-suave"
            aria-hidden
          />
          <input
            id="busca"
            type="search"
            value={termo}
            onChange={(evento) => setTermo(evento.target.value)}
            placeholder="Buscar por título ou texto (OCR)"
            autoComplete="off"
            className="h-11 w-full rounded-xl border border-borda bg-cartao pl-10 pr-4 text-base text-texto placeholder:text-texto-suave focus:border-primaria focus:outline-none focus:ring-2 focus:ring-primaria-suave sm:text-sm"
          />
        </div>

        <p className="mt-3 text-xs font-medium text-texto-secundario" aria-live="polite">
          {quantidade === null
            ? " "
            : termo
              ? `${quantidade} ${quantidade === 1 ? "resultado" : "resultados"}`
              : `${quantidade} ${quantidade === 1 ? "documento salvo" : "documentos salvos"}`}
        </p>
      </div>

      <section aria-label="Histórico de documentos" className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-5 pb-4">
        {lista.tipo === "carregando" &&
          [0, 1, 2].map((i) => <div key={i} className="h-[100px] animate-pulse rounded-2xl bg-secundario" />)}

        {lista.tipo === "erro" && (
          <div className="rounded-2xl border border-borda bg-cartao p-5 text-center">
            <p className="font-display text-sm font-bold text-texto">Histórico indisponível</p>
            <p className="mt-1 text-xs text-texto-secundario">{lista.mensagem}</p>
          </div>
        )}

        {lista.tipo === "pronto" && lista.documentos.length === 0 && (
          <div className="rounded-2xl border border-dashed border-borda p-6 text-center">
            <p className="font-display text-sm font-bold text-texto">
              {termo ? `Nada encontrado para “${termo}”` : "Nenhum documento ainda"}
            </p>
            <p className="mt-1 text-xs text-texto-secundario">
              {termo
                ? "A busca procura no título e no texto reconhecido das páginas."
                : "Toque em Digitalizar para fotografar sua primeira folha."}
            </p>
          </div>
        )}

        {lista.tipo === "pronto" &&
          lista.documentos.map((documento) => <CartaoDocumento key={documento.id} documento={documento} />)}
      </section>

      <div className="grid shrink-0 grid-cols-5 gap-2.5 border-t border-borda bg-cartao p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <button
          type="button"
          onClick={captura.abrirGaleria}
          disabled={captura.preparando}
          className="col-span-2 flex min-h-[52px] items-center justify-center gap-2 rounded-xl border border-borda bg-secundario text-sm font-semibold text-texto transition hover:opacity-90 active:scale-[0.98] disabled:opacity-60"
        >
          <ImageIcon className="size-4 text-texto-secundario" aria-hidden />
          Galeria
        </button>
        <button
          type="button"
          onClick={captura.abrirCamera}
          disabled={captura.preparando}
          className="col-span-3 flex min-h-[52px] items-center justify-center gap-2 rounded-xl bg-primaria font-display text-sm font-bold text-white shadow-sm transition hover:bg-primaria-hover active:scale-[0.98] disabled:opacity-60"
        >
          {captura.preparando ? (
            <LoaderCircle className="size-5 animate-spin" aria-hidden />
          ) : (
            <Camera className="size-5" aria-hidden />
          )}
          {captura.preparando ? "Preparando foto…" : "Digitalizar"}
        </button>
      </div>
    </main>
  );
}
