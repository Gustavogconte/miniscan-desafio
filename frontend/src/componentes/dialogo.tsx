"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

interface Props {
  aberto: boolean;
  titulo: string;
  aoFechar: () => void;
  children: ReactNode;
}

/** Janela no meio da tela, para confirmar ou pedir um dado. Fecha com Esc e ao tocar fora. */
export function Dialogo({ aberto, titulo, aoFechar, children }: Props) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const idTitulo = useId();

  useEffect(() => {
    const elemento = dialogo.current;
    if (!elemento) return;
    if (aberto && !elemento.open) elemento.showModal();
    if (!aberto && elemento.open) elemento.close();
  }, [aberto]);

  // Ao sair da tela (ou quando o Next a guarda escondida), a janela fecha: aberta, ela
  // deixaria o resto do app sem responder ao toque.
  useEffect(() => {
    const elemento = dialogo.current;
    return () => elemento?.close();
  }, []);

  return (
    <dialog
      ref={dialogo}
      onClose={aoFechar}
      onClick={(evento) => evento.target === dialogo.current && aoFechar()}
      aria-labelledby={idTitulo}
      className="m-auto w-[calc(100%-2rem)] max-w-sm rounded-2xl border border-borda bg-cartao p-0 text-texto shadow-xl backdrop:bg-slate-950/50"
    >
      <div className="space-y-4 p-5">
        <h2 id={idTitulo} className="font-display text-base font-bold">
          {titulo}
        </h2>
        {children}
      </div>
    </dialog>
  );
}
