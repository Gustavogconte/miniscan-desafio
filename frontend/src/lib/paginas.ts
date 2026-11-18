import { criarImagemLocal } from "@/lib/estado-digitalizacao";
import type { Cantos, Filtro, Pagina } from "@/lib/tipos";

function novoId(): string {
  // crypto.randomUUID só existe em contexto seguro (HTTPS); no teste pela rede local não.
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

interface OpcoesPagina {
  cantos?: Cantos | null;
  filtro?: Filtro;
}

/** Cria uma página nova a partir de uma foto já preparada (JPEG em pé, sem EXIF). */
export function novaPagina(blob: Blob, largura: number, altura: number, opcoes: OpcoesPagina = {}): Pagina {
  const cantos = opcoes.cantos ?? null;
  return {
    id: novoId(),
    original: criarImagemLocal(blob),
    largura,
    altura,
    cantos,
    cantosDetectados: cantos,
    cantosConfirmados: null,
    detectado: cantos !== null,
    filtro: opcoes.filtro ?? "bw",
    processadas: {},
    textoOcr: "",
    estadoOcr: "pendente",
  };
}
