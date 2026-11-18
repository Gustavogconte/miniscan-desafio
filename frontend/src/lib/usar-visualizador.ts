"use client";

import { useCallback, useEffect, useState } from "react";

/** Marca a entrada do histórico criada ao abrir o visualizador. */
const MARCA = "miniscanVisualizador";

function entradaDoVisualizador(): boolean {
  return Boolean((window.history.state as Record<string, unknown> | null)?.[MARCA]);
}

/**
 * Estado do visualizador em tela cheia (índice da página aberta, ou null).
 *
 * Abrir empilha uma entrada no histórico: assim o botão ou o gesto de voltar do
 * celular fecha o visualizador em vez de sair da tela. Fechar pelo X desfaz essa
 * entrada, e é o `popstate` que fecha de fato, nos dois caminhos.
 */
export function useVisualizador() {
  const [indice, setIndice] = useState<number | null>(null);
  const aberto = indice !== null;

  useEffect(() => {
    if (!aberto) return;
    const aoVoltar = () => setIndice(null);
    window.addEventListener("popstate", aoVoltar);
    return () => window.removeEventListener("popstate", aoVoltar);
  }, [aberto]);

  const abrir = useCallback((novo: number) => {
    // O Next copia o próprio estado para esta entrada: voltar dela não recarrega a tela.
    if (!entradaDoVisualizador()) window.history.pushState({ [MARCA]: true }, "");
    setIndice(novo);
  }, []);

  const fechar = useCallback(() => {
    if (entradaDoVisualizador()) window.history.back();
    else setIndice(null);
  }, []);

  return { indice, aberto, abrir, fechar, mostrar: setIndice };
}
