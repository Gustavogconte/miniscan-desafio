"use client";

import { LoaderCircle } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useSessao } from "@/lib/sessao";

const TELA_DE_ENTRADA = "/entrar";

/**
 * Sem sessão, todas as telas levam para /entrar; com sessão, /entrar leva ao início.
 *
 * Fica por fora do estado da digitalização: sair da conta desmonta tudo o que está
 * dentro, e nenhuma foto da conta anterior fica na memória para a próxima pessoa.
 */
export function GuardaSessao({ children }: { children: ReactNode }) {
  const sessao = useSessao();
  const caminho = usePathname();
  const router = useRouter();
  const naEntrada = caminho === TELA_DE_ENTRADA;
  const conhecida = sessao !== undefined;
  const liberada = conhecida && (naEntrada ? !sessao : Boolean(sessao));

  useEffect(() => {
    if (!conhecida || liberada) return;
    router.replace(naEntrada ? "/" : TELA_DE_ENTRADA);
  }, [conhecida, liberada, naEntrada, router]);

  if (liberada) return children;
  return (
    <div className="flex h-dvh items-center justify-center bg-fundo" aria-busy="true">
      <LoaderCircle className="size-7 animate-spin text-texto-suave" aria-label="Carregando" />
    </div>
  );
}
