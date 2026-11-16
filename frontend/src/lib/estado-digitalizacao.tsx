"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import type { ImagemLocal, Pagina } from "@/lib/tipos";

interface Estado {
  paginas: Pagina[];
  indiceAtual: number;
}

type Acao =
  | { tipo: "adicionar"; pagina: Pagina }
  | { tipo: "atualizar"; id: string; mudancas: Partial<Pagina> }
  | { tipo: "remover"; id: string }
  | { tipo: "selecionar"; indice: number }
  | { tipo: "reiniciar" };

function redutor(estado: Estado, acao: Acao): Estado {
  switch (acao.tipo) {
    case "adicionar":
      return { paginas: [...estado.paginas, acao.pagina], indiceAtual: estado.paginas.length };
    case "atualizar":
      return {
        ...estado,
        paginas: estado.paginas.map((p) => (p.id === acao.id ? { ...p, ...acao.mudancas } : p)),
      };
    case "remover": {
      const paginas = estado.paginas.filter((p) => p.id !== acao.id);
      return { paginas, indiceAtual: Math.min(estado.indiceAtual, Math.max(paginas.length - 1, 0)) };
    }
    case "selecionar":
      return { ...estado, indiceAtual: acao.indice };
    case "reiniciar":
      return { paginas: [], indiceAtual: 0 };
  }
}

function urlsDaPagina(pagina: Pagina): string[] {
  return [pagina.original.url, ...Object.values(pagina.processadas).map((imagem) => imagem!.url)];
}

interface ContextoDigitalizacao extends Estado {
  paginaAtual: Pagina | null;
  adicionarPagina: (pagina: Pagina) => void;
  atualizarPagina: (id: string, mudancas: Partial<Pagina>) => void;
  removerPagina: (id: string) => void;
  selecionarPagina: (indice: number) => void;
  reiniciar: () => void;
  /** Lê a versão mais recente de uma página (útil depois de chamadas assíncronas). */
  lerPagina: (id: string) => Pagina | undefined;
}

const Contexto = createContext<ContextoDigitalizacao | null>(null);

const ESTADO_INICIAL: Estado = { paginas: [], indiceAtual: 0 };

export function ProvedorDigitalizacao({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<Estado>(ESTADO_INICIAL);
  // Cópia sempre atualizada no próprio despacho: quem lê depois de um `await`
  // enxerga as mudanças mais recentes, mesmo antes da próxima renderização.
  const estadoRef = useRef<Estado>(ESTADO_INICIAL);

  const despachar = useCallback((acao: Acao) => {
    const proximo = redutor(estadoRef.current, acao);
    estadoRef.current = proximo;
    setEstado(proximo);
  }, []);

  const removerPagina = useCallback(
    (id: string) => {
      const pagina = estadoRef.current.paginas.find((p) => p.id === id);
      if (pagina) urlsDaPagina(pagina).forEach((url) => URL.revokeObjectURL(url));
      despachar({ tipo: "remover", id });
    },
    [despachar],
  );

  const reiniciar = useCallback(() => {
    estadoRef.current.paginas.flatMap(urlsDaPagina).forEach((url) => URL.revokeObjectURL(url));
    despachar({ tipo: "reiniciar" });
  }, [despachar]);

  const atualizarPagina = useCallback(
    (id: string, mudancas: Partial<Pagina>) => despachar({ tipo: "atualizar", id, mudancas }),
    [despachar],
  );

  const adicionarPagina = useCallback((pagina: Pagina) => despachar({ tipo: "adicionar", pagina }), [despachar]);

  const selecionarPagina = useCallback((indice: number) => despachar({ tipo: "selecionar", indice }), [despachar]);

  const lerPagina = useCallback((id: string) => estadoRef.current.paginas.find((p) => p.id === id), []);

  const valor = useMemo<ContextoDigitalizacao>(
    () => ({
      ...estado,
      paginaAtual: estado.paginas[estado.indiceAtual] ?? null,
      adicionarPagina,
      atualizarPagina,
      removerPagina,
      selecionarPagina,
      reiniciar,
      lerPagina,
    }),
    [estado, adicionarPagina, atualizarPagina, removerPagina, selecionarPagina, reiniciar, lerPagina],
  );

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useDigitalizacao(): ContextoDigitalizacao {
  const contexto = useContext(Contexto);
  if (!contexto) throw new Error("useDigitalizacao precisa estar dentro de <ProvedorDigitalizacao>.");
  return contexto;
}

export function criarImagemLocal(blob: Blob): ImagemLocal {
  return { blob, url: URL.createObjectURL(blob) };
}

export function liberarImagens(imagens: (ImagemLocal | undefined)[]): void {
  imagens.forEach((imagem) => imagem && URL.revokeObjectURL(imagem.url));
}
