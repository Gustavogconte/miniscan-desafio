"use client";

import { CircleAlert, CircleCheck } from "lucide-react";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

type TipoAviso = "sucesso" | "erro";

interface Aviso {
  id: number;
  mensagem: string;
  tipo: TipoAviso;
}

const Contexto = createContext<(mensagem: string, tipo?: TipoAviso) => void>(() => {});

/**
 * Avisos no topo da tela: embaixo eles cobririam os botões de ação, que ficam na
 * zona do polegar. Erros vão para uma região role="alert", anunciada na hora pelo
 * leitor de tela; confirmações usam role="status".
 */
export function ProvedorAvisos({ children }: { children: ReactNode }) {
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const temporizador = useRef<ReturnType<typeof setTimeout>>(undefined);

  const avisar = useCallback((mensagem: string, tipo: TipoAviso = "sucesso") => {
    clearTimeout(temporizador.current);
    setAviso({ id: Date.now(), mensagem, tipo });
    temporizador.current = setTimeout(() => setAviso(null), tipo === "erro" ? 7000 : 2600);
  }, []);

  const conteudo = (tipo: TipoAviso) =>
    aviso?.tipo === tipo && (
      <div
        key={aviso.id}
        className="pointer-events-auto flex max-w-sm items-start gap-2 rounded-xl border border-borda bg-cartao px-4 py-3 text-sm font-medium text-texto shadow-lg"
      >
        {tipo === "erro" ? (
          <CircleAlert className="mt-0.5 size-4 shrink-0 text-perigo" aria-hidden />
        ) : (
          <CircleCheck className="mt-0.5 size-4 shrink-0 text-sucesso" aria-hidden />
        )}
        <span>{aviso.mensagem}</span>
      </div>
    );

  const posicao =
    "pointer-events-none fixed inset-x-4 top-[calc(env(safe-area-inset-top)+4.5rem)] z-50 flex justify-center";

  return (
    <Contexto.Provider value={avisar}>
      {children}
      <div role="status" aria-live="polite" className={posicao}>
        {conteudo("sucesso")}
      </div>
      <div role="alert" className={posicao}>
        {conteudo("erro")}
      </div>
    </Contexto.Provider>
  );
}

export function useAviso() {
  return useContext(Contexto);
}
