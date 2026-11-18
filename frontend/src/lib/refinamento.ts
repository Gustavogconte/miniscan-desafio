import type { Cantos, Deteccao, Pagina } from "@/lib/tipos";

/*
 * A detecção ao vivo da câmera (OpenCV.js no worker) serve só de prévia. Logo depois da
 * captura, o servidor detecta de novo com o modelo DocAligner, bem mais certeiro com o
 * cartão na mão ou o fundo confuso, e cai no OpenCV quando o modelo não acha a folha.
 */

/**
 * O que muda numa página da câmera quando o servidor responde (`servidor` é null se o
 * pedido falhou). Se a pessoa já arrastou algum canto, o recorte dela fica e o do
 * servidor vira a "Detecção automática", a um toque.
 */
export function mudancasDoRefinamento(
  pagina: Pick<Pagina, "cantos" | "processadas">,
  cantosDaPrevia: Cantos | null,
  servidor: Deteccao | null,
): Partial<Pagina> {
  const jaRecortada = Object.keys(pagina.processadas).length > 0;
  // Sem resposta, ou o servidor não achou a folha que a prévia achou: fica a prévia.
  if (jaRecortada || !servidor || (!servidor.detectado && cantosDaPrevia)) return { refinando: false };
  const deteccao = { cantosDetectados: servidor.cantos, detectado: servidor.detectado, refinando: false };
  const mexeu = pagina.cantos !== cantosDaPrevia;
  return mexeu ? deteccao : { ...deteccao, cantos: servidor.cantos };
}

/** Cantos de um lado do cartão: os do servidor quando ele achou o documento, senão os da prévia. */
export function cantosDoLado(cantosDaPrevia: Cantos | null, servidor: Deteccao | null): Cantos | null {
  if (servidor?.detectado) return servidor.cantos;
  return cantosDaPrevia ?? servidor?.cantos ?? null;
}
