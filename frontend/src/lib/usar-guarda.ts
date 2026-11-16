"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useDigitalizacao } from "@/lib/estado-digitalizacao";

/**
 * As telas de digitalização dependem das fotos em memória. Se a página for recarregada
 * ou aberta direto pelo link, não há o que mostrar: volta para o início.
 */
export function useGuardaDigitalizacao() {
  const router = useRouter();
  const contexto = useDigitalizacao();
  const vazio = contexto.paginas.length === 0;

  useEffect(() => {
    if (vazio) router.replace("/");
  }, [vazio, router]);

  return contexto;
}
