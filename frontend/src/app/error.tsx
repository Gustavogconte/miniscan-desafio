"use client";

import { RotateCw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

/**
 * Erro inesperado numa tela. Este limite fica abaixo do layout raiz: as páginas da
 * digitalização, que vivem só na memória (ProvedorDigitalizacao), não se perdem, e
 * "Tentar de novo" redesenha a tela com elas.
 */
export default function ErroDaTela({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="font-display text-lg font-bold text-texto">Algo deu errado nesta tela</h1>
      <p className="max-w-xs text-sm text-texto-secundario">
        As páginas digitalizadas continuam guardadas. Tente de novo; voltar ao início descarta a digitalização em
        andamento.
      </p>
      <button
        type="button"
        onClick={() => retry()}
        className="flex min-h-12 items-center gap-2 rounded-xl bg-primaria px-5 text-sm font-semibold text-white"
      >
        <RotateCw className="size-4" aria-hidden />
        Tentar de novo
      </button>
      <Link href="/" className="text-sm font-semibold text-primaria-texto underline underline-offset-2">
        Voltar ao início
      </Link>
    </main>
  );
}
