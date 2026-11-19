import type { Pagina } from "@/lib/tipos";

const formatoDia = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });

/**
 * Nome do documento antes de a pessoa mudar, tirado do texto da primeira página: no RG
 * ou CNH, o tipo do documento; nas outras, o título que a API achou (a linha de letra
 * maior no alto da página). Sem texto, fica "Documento" com a data.
 */
export function sugerirTitulo(paginas: Pagina[], hoje: Date): string {
  const primeira = paginas[0];
  if (primeira?.cartao) return tipoDoCartao(primeira.textoOcr);
  if (primeira?.tituloOcr) return primeira.tituloOcr;
  return `Documento ${formatoDia.format(hoje)}`;
}

/** "CNH" ou "RG" pelas palavras impressas no documento. */
export function tipoDoCartao(texto: string): string {
  // Sem acento e em maiúsculas: "Habilitação" e "HABILITACAO" contam igual.
  const simples = texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
  // A CNH também tem a palavra "IDENTIDADE" (no campo do RG), por isso vem primeiro.
  if (simples.includes("HABILITACAO")) return "CNH";
  if (simples.includes("IDENTIDADE") || simples.includes("REGISTRO GERAL")) return "RG";
  return "RG ou CNH";
}
