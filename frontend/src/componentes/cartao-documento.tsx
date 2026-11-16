"use client";

import { FileText, Share2 } from "lucide-react";

import { useAviso } from "@/componentes/aviso";
import { ROTULO_FILTRO, type DocumentoHistorico } from "@/lib/tipos";

const formatoHora = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" });
const formatoData = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" });

function formatarData(iso: string): string {
  const data = new Date(iso);
  const hoje = new Date();
  const ontem = new Date(hoje);
  ontem.setDate(hoje.getDate() - 1);
  if (data.toDateString() === hoje.toDateString()) return `Hoje, ${formatoHora.format(data)}`;
  if (data.toDateString() === ontem.toDateString()) return `Ontem, ${formatoHora.format(data)}`;
  return formatoData.format(data).replace(".", "");
}

export function CartaoDocumento({ documento }: { documento: DocumentoHistorico }) {
  const avisar = useAviso();
  const primeira = documento.document_pages[0];
  const trecho = primeira?.ocr_text.replace(/\s+/g, " ").trim();
  const paginas = `${documento.page_count} ${documento.page_count === 1 ? "pág." : "págs."}`;

  async function compartilhar() {
    if (!documento.pdf_url) return;
    try {
      if (navigator.share) {
        await navigator.share({ title: documento.title, url: documento.pdf_url });
      } else {
        await navigator.clipboard.writeText(documento.pdf_url);
        avisar("Link do PDF copiado");
      }
    } catch (erro) {
      if (erro instanceof DOMException && erro.name === "AbortError") return;
      avisar("Não foi possível compartilhar o link.", "erro");
    }
  }

  return (
    <article className="relative flex items-start gap-3.5 rounded-2xl border border-borda bg-cartao p-3.5 shadow-cartao transition hover:border-primaria/50">
      <div className="flex h-[72px] w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-borda bg-secundario">
        {primeira ? (
          // eslint-disable-next-line @next/next/no-img-element -- miniatura vinda do Storage do Supabase
          <img src={primeira.processed_image_url} alt="" loading="lazy" className="size-full object-cover" />
        ) : (
          <FileText className="size-6 text-texto-suave" aria-hidden />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <h2 className="truncate pr-10 font-display text-sm font-bold text-texto">
          {documento.pdf_url ? (
            <a
              href={documento.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              className="after:absolute after:inset-0 after:rounded-2xl focus-visible:outline-none"
            >
              {documento.title}
            </a>
          ) : (
            documento.title
          )}
        </h2>
        {trecho ? (
          <p className="mt-1 line-clamp-2 text-xs leading-snug text-texto-secundario">“{trecho}”</p>
        ) : (
          <p className="mt-1 text-xs italic text-texto-suave">Sem texto reconhecido</p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-texto-secundario">
          {primeira && (
            <span className="rounded-md bg-primaria-suave px-2 py-0.5 font-mono font-semibold text-primaria">
              {ROTULO_FILTRO[primeira.filter_applied]}
            </span>
          )}
          <span className="font-mono">{paginas}</span>
          <span aria-hidden>•</span>
          <time dateTime={documento.created_at}>{formatarData(documento.created_at)}</time>
        </div>
      </div>

      {documento.pdf_url && (
        <button
          type="button"
          onClick={compartilhar}
          aria-label={`Compartilhar ${documento.title}`}
          className="absolute right-2 top-2 z-10 flex size-10 items-center justify-center rounded-xl text-texto-secundario transition hover:bg-secundario hover:text-primaria"
        >
          <Share2 className="size-4" aria-hidden />
        </button>
      )}
    </article>
  );
}
