"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import type { FormatoCartao, ImagemLocal, Modo, Pagina } from "@/lib/tipos";

interface Estado {
  paginas: Pagina[];
  indiceAtual: number;
  /** Modo escolhido na câmera; decide o que acontece depois da foto. */
  modo: Modo;
  formatoCartao: FormatoCartao;
  /**
   * Sobe a cada documento novo (reiniciar). O Next guarda as telas escondidas entre
   * uma visita e outra; com esta chave, editor e exportação recomeçam do zero.
   */
  sessao: number;
}

type Acao =
  | { tipo: "adicionar"; pagina: Pagina }
  | { tipo: "atualizar"; id: string; mudancas: Partial<Pagina> }
  | { tipo: "remover"; id: string }
  | { tipo: "selecionar"; indice: number }
  | { tipo: "configurar"; modo?: Modo; formatoCartao?: FormatoCartao }
  | { tipo: "reiniciar" };

const ESTADO_INICIAL: Estado = {
  paginas: [],
  indiceAtual: 0,
  modo: "digitalizar",
  formatoCartao: "id",
  sessao: 0,
};

function redutor(estado: Estado, acao: Acao): Estado {
  switch (acao.tipo) {
    case "adicionar":
      return { ...estado, paginas: [...estado.paginas, acao.pagina], indiceAtual: estado.paginas.length };
    case "atualizar":
      return {
        ...estado,
        paginas: estado.paginas.map((p) => (p.id === acao.id ? { ...p, ...acao.mudancas } : p)),
      };
    case "remover": {
      const paginas = estado.paginas.filter((p) => p.id !== acao.id);
      return { ...estado, paginas, indiceAtual: Math.min(estado.indiceAtual, Math.max(paginas.length - 1, 0)) };
    }
    case "configurar":
      return {
        ...estado,
        modo: acao.modo ?? estado.modo,
        formatoCartao: acao.formatoCartao ?? estado.formatoCartao,
      };
    case "selecionar":
      return { ...estado, indiceAtual: acao.indice };
    case "reiniciar":
      return {
        ...ESTADO_INICIAL,
        modo: estado.modo,
        formatoCartao: estado.formatoCartao,
        sessao: estado.sessao + 1,
      };
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
  configurar: (opcoes: { modo?: Modo; formatoCartao?: FormatoCartao }) => void;
  selecionarPagina: (indice: number) => void;
  reiniciar: () => void;
  /** Lê a versão mais recente de uma página (útil depois de chamadas assíncronas). */
  lerPagina: (id: string) => Pagina | undefined;
}

const Contexto = createContext<ContextoDigitalizacao | null>(null);

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

  const configurar = useCallback(
    (opcoes: { modo?: Modo; formatoCartao?: FormatoCartao }) => despachar({ tipo: "configurar", ...opcoes }),
    [despachar],
  );

  const selecionarPagina = useCallback((indice: number) => despachar({ tipo: "selecionar", indice }), [despachar]);

  const lerPagina = useCallback((id: string) => estadoRef.current.paginas.find((p) => p.id === id), []);

  const valor = useMemo<ContextoDigitalizacao>(
    () => ({
      ...estado,
      paginaAtual: estado.paginas[estado.indiceAtual] ?? null,
      adicionarPagina,
      atualizarPagina,
      removerPagina,
      configurar,
      selecionarPagina,
      reiniciar,
      lerPagina,
    }),
    [
      estado,
      adicionarPagina,
      atualizarPagina,
      removerPagina,
      configurar,
      selecionarPagina,
      reiniciar,
      lerPagina,
    ],
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
