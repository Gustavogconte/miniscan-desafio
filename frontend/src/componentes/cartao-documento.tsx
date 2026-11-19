"use client";

import { FileText } from "lucide-react";
import Link from "next/link";

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

/**
 * Um documento do histórico. Não tem botão de compartilhar: o link do PDF vale só
 * uma hora (o bucket é privado). O cartão abre a tela do documento, que compartilha
 * o próprio arquivo.
 */
export function CartaoDocumento({ documento }: { documento: DocumentoHistorico }) {
  const trecho = documento.texto_capa.replace(/\s+/g, " ").trim();
  const paginas = `${documento.total_paginas} ${documento.total_paginas === 1 ? "pág." : "págs."}`;

  return (
    <article className="relative flex items-start gap-3.5 rounded-2xl border border-borda bg-cartao p-3.5 shadow-cartao transition hover:border-primaria/50 has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-primaria-texto has-[a:focus-visible]:ring-offset-2 has-[a:focus-visible]:ring-offset-fundo">
      <div className="flex h-[72px] w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-borda bg-secundario">
        {documento.url_miniatura ? (
          // eslint-disable-next-line @next/next/no-img-element -- miniatura com link assinado do Storage do Supabase
          <img src={documento.url_miniatura} alt="" loading="lazy" className="size-full object-cover" />
        ) : (
          <FileText className="size-6 text-texto-suave" aria-hidden />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <h2 className="truncate font-display text-sm font-bold text-texto">
          {/* O cartão inteiro abre a tela do documento, com as páginas e o texto. */}
          <Link
            href={`/documento?id=${documento.id}`}
            className="after:absolute after:inset-0 after:rounded-2xl focus-visible:outline-none"
          >
            {documento.titulo}
          </Link>
        </h2>
        {trecho ? (
          <p className="mt-1 line-clamp-2 text-xs leading-snug text-texto-secundario">“{trecho}”</p>
        ) : (
          <p className="mt-1 text-xs italic text-texto-suave">Sem texto reconhecido</p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-texto-secundario">
          {documento.filtro_capa && (
            <span className="rounded-md bg-primaria-suave px-2 py-0.5 font-mono font-semibold text-primaria-texto">
              {ROTULO_FILTRO[documento.filtro_capa]}
            </span>
          )}
          <span className="font-mono">{paginas}</span>
          <span aria-hidden>•</span>
          <time dateTime={documento.criado_em}>{formatarData(documento.criado_em)}</time>
        </div>
      </div>
    </article>
  );
}
