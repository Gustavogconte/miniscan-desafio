"use client";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

interface Props {
  titulo: string;
  subtitulo?: string;
  voltarPara: string;
  rotuloVoltar: string;
  acao?: ReactNode;
  aoVoltar?: () => void;
}

export function CabecalhoEtapa({ titulo, subtitulo, voltarPara, rotuloVoltar, acao, aoVoltar }: Props) {
  return (
    <header className="flex shrink-0 items-center gap-2 border-b border-borda bg-cartao px-3 py-2.5 pt-[max(0.625rem,env(safe-area-inset-top))]">
      <Link
        href={voltarPara}
        onClick={aoVoltar}
        aria-label={rotuloVoltar}
        className="flex size-11 items-center justify-center rounded-xl text-texto-secundario transition hover:bg-secundario hover:text-texto"
      >
        <ChevronLeft className="size-6" aria-hidden />
      </Link>
      <div className="min-w-0 flex-1">
        <h1 className="truncate font-display text-base font-bold text-texto">{titulo}</h1>
        {subtitulo && <p className="truncate text-xs text-texto-secundario">{subtitulo}</p>}
      </div>
      {acao}
    </header>
  );
}
