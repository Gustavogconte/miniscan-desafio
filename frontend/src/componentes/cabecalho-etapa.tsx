"use client";

import { ChevronLeft, CircleAlert } from "lucide-react";
import Link from "next/link";
import type { MouseEvent, ReactNode } from "react";

interface Props {
  titulo: string;
  subtitulo?: string;
  /** Mostra o subtítulo como aviso, na cor de alerta: fica à vista sem cobrir a tela. */
  alerta?: boolean;
  voltarPara: string;
  rotuloVoltar: string;
  acao?: ReactNode;
  /** Chamado antes de navegar; `evento.preventDefault()` cancela a volta. */
  aoVoltar?: (evento: MouseEvent<HTMLAnchorElement>) => void;
}

export function CabecalhoEtapa({ titulo, subtitulo, alerta, voltarPara, rotuloVoltar, acao, aoVoltar }: Props) {
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
        {subtitulo && (
          <p
            aria-live="polite"
            className={`flex items-center gap-1 text-xs ${alerta ? "font-semibold text-alerta" : "text-texto-secundario"}`}
          >
            {alerta && <CircleAlert className="size-3.5 shrink-0" aria-hidden />}
            <span className="truncate">{subtitulo}</span>
          </p>
        )}
      </div>
      {acao}
    </header>
  );
}
