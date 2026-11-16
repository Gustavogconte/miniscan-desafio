"use client";

import { useCallback } from "react";

import { extrairOcr, mensagemDeErro, processarPagina } from "@/lib/api";
import { criarImagemLocal, useDigitalizacao } from "@/lib/estado-digitalizacao";
import { CANTOS_TELA_INTEIRA, type Filtro, type ImagemLocal } from "@/lib/tipos";

export function useProcessamento() {
  const { lerPagina, atualizarPagina } = useDigitalizacao();

  /** Devolve a página retificada no filtro pedido, chamando a API só se ainda não estiver em cache. */
  const garantirProcessada = useCallback(
    async (id: string, filtro: Filtro): Promise<ImagemLocal> => {
      const pagina = lerPagina(id);
      if (!pagina) throw new Error("Página não encontrada.");
      const emCache = pagina.processadas[filtro];
      if (emCache) return emCache;

      const blob = await processarPagina(pagina.original.blob, pagina.cantos ?? CANTOS_TELA_INTEIRA, filtro);
      const imagem = criarImagemLocal(blob);
      const atual = lerPagina(id);
      if (!atual) {
        URL.revokeObjectURL(imagem.url); // a página foi descartada enquanto processava
        throw new Error("Página descartada.");
      }
      atualizarPagina(id, { processadas: { ...atual.processadas, [filtro]: imagem } });
      return imagem;
    },
    [lerPagina, atualizarPagina],
  );

  /** Extrai o texto sempre da versão em preto e branco, que dá a melhor leitura. */
  const executarOcr = useCallback(
    async (id: string, pretoEBrancoPronto?: Blob): Promise<void> => {
      atualizarPagina(id, { estadoOcr: "carregando" });
      try {
        const pretoEBranco = pretoEBrancoPronto ?? (await garantirProcessada(id, "bw")).blob;
        const texto = await extrairOcr(pretoEBranco);
        if (lerPagina(id)) atualizarPagina(id, { textoOcr: texto, estadoOcr: "pronto" });
      } catch (erro) {
        if (lerPagina(id)) atualizarPagina(id, { estadoOcr: "erro" });
        console.warn("OCR falhou:", mensagemDeErro(erro));
      }
    },
    [atualizarPagina, garantirProcessada, lerPagina],
  );

  return { garantirProcessada, executarOcr };
}
