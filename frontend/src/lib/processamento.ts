"use client";

import { useCallback } from "react";

import {
  comporCartao,
  detectarCantos,
  dividirLivro,
  extrairOcr,
  mensagemDeErro,
  processarPagina,
} from "@/lib/api";
import { criarImagemLocal, liberarImagens, useDigitalizacao } from "@/lib/estado-digitalizacao";
import { novaPagina } from "@/lib/paginas";
import {
  CANTOS_TELA_INTEIRA,
  type Cantos,
  type Filtro,
  type FormatoCartao,
  type ImagemLocal,
  type Pagina,
} from "@/lib/tipos";

/** Tamanho, em pixels, da folha A4 a 300 dpi devolvida pelo /compor-cartao. */
const A4_300DPI = { largura: 2480, altura: 3508 };

/**
 * Cantos do último recorte confirmado, usados pelos filtros e pelo OCR. São a mesma
 * referência enquanto o recorte não muda: comparar com `!==` diz se a página foi
 * recortada de novo durante uma requisição.
 */
function cantosDoRecorte(pagina: Pagina): Cantos {
  return pagina.cantosConfirmados ?? pagina.cantos ?? CANTOS_TELA_INTEIRA;
}

export interface LadoDoCartao {
  blob: Blob;
  cantos: Cantos | null;
}

export function useProcessamento() {
  const { lerPagina, atualizarPagina, adicionarPagina, substituirPagina, modo } = useDigitalizacao();

  /** Devolve a página retificada no filtro pedido, chamando a API só se ainda não estiver em cache. */
  const garantirProcessada = useCallback(
    async (id: string, filtro: Filtro): Promise<ImagemLocal> => {
      // Repete quando a página é recortada de novo durante a requisição: a resposta
      // traria o recorte antigo para este filtro, ao lado dos outros já no recorte novo.
      for (;;) {
        const pagina = lerPagina(id);
        if (!pagina) throw new Error("Página não encontrada.");
        const emCache = pagina.processadas[filtro];
        if (emCache) return emCache;

        const cantos = cantosDoRecorte(pagina);
        const blob = await processarPagina(pagina.original.blob, cantos, filtro);
        const imagem = criarImagemLocal(blob);
        const atual = lerPagina(id);
        if (!atual) {
          URL.revokeObjectURL(imagem.url); // a página foi descartada enquanto processava
          throw new Error("Página descartada.");
        }
        if (cantosDoRecorte(atual) !== cantos) {
          URL.revokeObjectURL(imagem.url);
          continue;
        }
        const chegouAntes = atual.processadas[filtro];
        if (chegouAntes) {
          URL.revokeObjectURL(imagem.url); // outra requisição do mesmo filtro terminou primeiro
          return chegouAntes;
        }
        atualizarPagina(id, { processadas: { ...atual.processadas, [filtro]: imagem } });
        return imagem;
      }
    },
    [lerPagina, atualizarPagina],
  );

  /**
   * Extrai o texto da página a partir da foto original e dos cantos confirmados,
   * independentemente do filtro escolhido para a tela e o PDF.
   */
  const executarOcr = useCallback(
    async (id: string): Promise<void> => {
      const pagina = lerPagina(id);
      if (!pagina) return;
      const cantos = cantosDoRecorte(pagina);
      // Só grava se a página ainda existe e não foi recortada de novo enquanto lia.
      const aindaValida = () => {
        const atual = lerPagina(id);
        return atual ? cantosDoRecorte(atual) === cantos : false;
      };
      atualizarPagina(id, { estadoOcr: "carregando" });
      try {
        const texto = await extrairOcr(pagina.original.blob, cantos);
        if (aindaValida()) atualizarPagina(id, { textoOcr: texto, estadoOcr: "pronto" });
      } catch (erro) {
        if (aindaValida()) atualizarPagina(id, { estadoOcr: "erro" });
        console.warn("OCR falhou:", mensagemDeErro(erro));
      }
    },
    [atualizarPagina, lerPagina],
  );

  /** Retifica a página com os cantos escolhidos, guarda o resultado e lê o texto em segundo plano. */
  const processarComCantos = useCallback(
    async (id: string, cantos: Cantos): Promise<void> => {
      const pagina = lerPagina(id);
      if (!pagina) return;
      const blob = await processarPagina(pagina.original.blob, cantos, pagina.filtro);
      const atual = lerPagina(id);
      if (!atual) return; // descartada enquanto processava
      // Cantos novos invalidam as versões já processadas e o texto lido antes.
      liberarImagens(Object.values(atual.processadas));
      atualizarPagina(id, {
        cantos,
        cantosConfirmados: cantos,
        processadas: { [pagina.filtro]: criarImagemLocal(blob) },
        textoOcr: "",
        estadoOcr: "pendente",
      });
      void executarOcr(id);
    },
    [atualizarPagina, executarOcr, lerPagina],
  );

  /**
   * Confirma o recorte de uma página. No modo livro, uma foto do livro aberto vira
   * duas páginas: a API acha a lombada e devolve os cantos de cada metade.
   */
  const confirmarPagina = useCallback(
    async (id: string, cantos: Cantos): Promise<void> => {
      const pagina = lerPagina(id);
      if (!pagina) return;
      if (modo === "livro" && !pagina.metadeDeLivro) {
        const { esquerda, direita } = await dividirLivro(pagina.original.blob, cantos);
        const metades = [esquerda, direita].map((c) =>
          novaPagina(pagina.original.blob, pagina.largura, pagina.altura, {
            cantos: c,
            filtro: pagina.filtro,
            metadeDeLivro: true,
          }),
        );
        substituirPagina(id, metades);
        await Promise.all(metades.map((m) => processarComCantos(m.id, m.cantos!)));
        return;
      }
      await processarComCantos(id, cantos);
    },
    [lerPagina, modo, processarComCantos, substituirPagina],
  );

  /** Processa, em sequência, as fotos tiradas em lote que ainda não foram recortadas. */
  const concluirLote = useCallback(
    async (ids: string[], aoAvancar?: (feitas: number) => void): Promise<void> => {
      for (const [indice, id] of ids.entries()) {
        const pagina = lerPagina(id);
        if (pagina && Object.keys(pagina.processadas).length === 0) {
          let cantos = pagina.cantos;
          if (!cantos) {
            const deteccao = await detectarCantos(pagina.original.blob);
            cantos = deteccao.cantos;
          }
          await confirmarPagina(id, cantos);
        }
        aoAvancar?.(indice + 1);
      }
    },
    [confirmarPagina, lerPagina],
  );

  /** Retifica cada lado do cartão e monta tudo numa folha A4 em tamanho real. */
  const montarCartao = useCallback(
    async (lados: LadoDoCartao[], formato: FormatoCartao): Promise<void> => {
      const retificados = await Promise.all(
        lados.map(async (lado) => {
          const cantos = lado.cantos ?? (await detectarCantos(lado.blob)).cantos;
          return processarPagina(lado.blob, cantos, "original");
        }),
      );
      const folha = await comporCartao(retificados[0], retificados[1] ?? null, formato);
      const pagina = novaPagina(folha, A4_300DPI.largura, A4_300DPI.altura, {
        cantos: CANTOS_TELA_INTEIRA,
        filtro: "original",
      });
      adicionarPagina(pagina);
      await processarComCantos(pagina.id, CANTOS_TELA_INTEIRA);
    },
    [adicionarPagina, processarComCantos],
  );

  return { garantirProcessada, executarOcr, confirmarPagina, concluirLote, montarCartao };
}
