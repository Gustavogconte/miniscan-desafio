/** Uma página no visualizador em tela cheia. */
export interface ImagemVisualizada {
  id: string;
  /** Versão mostrada por padrão: a página tratada (recorte e filtro) ou a própria foto. */
  src: string;
  /** Foto como foi capturada, antes do recorte e do filtro, quando existir. */
  srcOriginal?: string;
  /** Complemento do rótulo, ex.: "P&B" ou "sem recorte". */
  detalhe?: string;
}

export function fonteDaImagem(imagem: ImagemVisualizada, verOriginal: boolean): string {
  return verOriginal && imagem.srcOriginal ? imagem.srcOriginal : imagem.src;
}

export function rotuloDaPagina(indice: number, total: number, detalhe?: string, nome = "Página"): string {
  const base = `${nome} ${indice + 1} de ${total}`;
  return detalhe ? `${base} · ${detalhe}` : base;
}

/** Página que fica à mostra depois de excluir a do índice dado (null: não sobrou nenhuma). */
export function indiceDepoisDeExcluir(indice: number, totalAntes: number): number | null {
  const restantes = totalAntes - 1;
  if (restantes <= 0) return null;
  return Math.min(indice, restantes - 1);
}
