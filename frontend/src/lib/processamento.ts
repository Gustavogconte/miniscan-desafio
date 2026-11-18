"use client";

import { useCallback } from "react";

import {
  comporCartao,
  detectarCantos,
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
  largura: number;
  altura: number;
  cantos: Cantos | null;
}

/**
 * Cantos da folha A4 inteira, numa referência nova a cada montagem: assim uma resposta
 * de filtro ou de OCR da folha anterior é reconhecida como antiga e descartada.
 */
function folhaInteira(): Cantos {
  return CANTOS_TELA_INTEIRA.map((ponto) => ({ ...ponto })) as Cantos;
}

/** Retifica cada lado com os seus cantos e monta a folha A4 com o documento em tamanho real. */
async function comporFolha(lados: { blob: Blob; cantos: Cantos }[], formato: FormatoCartao): Promise<Blob> {
  const retificados = await Promise.all(lados.map((lado) => processarPagina(lado.blob, lado.cantos, "original")));
  return comporCartao(retificados[0], retificados[1] ?? null, formato);
}

export function useProcessamento() {
  const { lerPagina, atualizarPagina, adicionarPagina } = useDigitalizacao();

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

  /** Confirma o recorte de uma página: retifica, guarda e lê o texto em segundo plano. */
  const confirmarPagina = processarComCantos;

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

  /**
   * Retifica cada lado do cartão e monta tudo numa folha A4 em tamanho real. As fotos
   * de cada lado ficam guardadas na página, para o recorte poder ser refeito depois.
   */
  const montarCartao = useCallback(
    async (lados: LadoDoCartao[], formato: FormatoCartao): Promise<void> => {
      const comCantos = await Promise.all(
        lados.map(async (lado) => ({
          ...lado,
          cantos: lado.cantos ?? (await detectarCantos(lado.blob)).cantos,
        })),
      );
      const folha = await comporFolha(comCantos, formato);
      const cantos = folhaInteira();
      const pagina: Pagina = {
        ...novaPagina(folha, A4_300DPI.largura, A4_300DPI.altura, { cantos, filtro: "original" }),
        cartao: {
          formato,
          lados: comCantos.map((lado) => ({
            original: criarImagemLocal(lado.blob),
            largura: lado.largura,
            altura: lado.altura,
            cantos: lado.cantos,
          })),
        },
      };
      adicionarPagina(pagina);
      await processarComCantos(pagina.id, cantos);
    },
    [adicionarPagina, processarComCantos],
  );

  /** Refaz o recorte de cada lado de uma página do Cartão ID e monta a folha A4 de novo. */
  const recortarCartao = useCallback(
    async (id: string, cantosDosLados: Cantos[]): Promise<void> => {
      const pagina = lerPagina(id);
      if (!pagina?.cartao) return;
      const { formato, lados } = pagina.cartao;
      const folha = await comporFolha(
        lados.map((lado, indice) => ({ blob: lado.original.blob, cantos: cantosDosLados[indice] })),
        formato,
      );
      const atual = lerPagina(id);
      if (!atual?.cartao) return; // descartada enquanto montava
      liberarImagens([atual.original]);
      atualizarPagina(id, {
        original: criarImagemLocal(folha),
        cartao: {
          formato,
          lados: atual.cartao.lados.map((lado, indice) => ({ ...lado, cantos: cantosDosLados[indice] })),
        },
      });
      await processarComCantos(id, folhaInteira());
    },
    [atualizarPagina, lerPagina, processarComCantos],
  );

  return { garantirProcessada, executarOcr, confirmarPagina, concluirLote, montarCartao, recortarCartao };
}
