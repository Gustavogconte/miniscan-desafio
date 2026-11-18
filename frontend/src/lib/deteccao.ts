import type { Cantos, Deteccao } from "@/lib/tipos";

/**
 * Cantos de um lado do cartão: os do servidor (modelo DocAligner e, se ele não achar,
 * OpenCV) quando ele achou o documento; senão, os da moldura-guia da câmera. Sem moldura
 * (foto da galeria), vale a resposta do servidor mesmo sem documento; sem resposta, null.
 */
export function cantosDoLado(cantosDaGuia: Cantos | null, servidor: Deteccao | null): Cantos | null {
  if (servidor?.detectado) return servidor.cantos;
  return cantosDaGuia ?? servidor?.cantos ?? null;
}
