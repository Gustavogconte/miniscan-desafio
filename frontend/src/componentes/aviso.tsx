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

export function ProvedorAvisos({ children }: { children: ReactNode }) {
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const temporizador = useRef<ReturnType<typeof setTimeout>>(undefined);

  const avisar = useCallback((mensagem: string, tipo: TipoAviso = "sucesso") => {
    clearTimeout(temporizador.current);
    setAviso({ id: Date.now(), mensagem, tipo });
    temporizador.current = setTimeout(() => setAviso(null), tipo === "erro" ? 5000 : 2600);
  }, []);

  return (
    <Contexto.Provider value={avisar}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-28 z-50 flex justify-center"
      >
        {aviso && (
          <div
            key={aviso.id}
            className="flex max-w-sm items-start gap-2 rounded-xl border border-borda bg-cartao px-4 py-3 text-sm font-medium text-texto shadow-lg"
          >
            {aviso.tipo === "erro" ? (
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-perigo" aria-hidden />
            ) : (
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-sucesso" aria-hidden />
            )}
            <span>{aviso.mensagem}</span>
          </div>
        )}
      </div>
    </Contexto.Provider>
  );
}

export function useAviso() {
  return useContext(Contexto);
}
