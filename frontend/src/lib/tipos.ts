/** Os mesmos valores aceitos pela API e pela coluna document_pages.filter_applied. */
export type Filtro = "original" | "grayscale" | "bw";

export const FILTROS: { valor: Filtro; rotulo: string }[] = [
  { valor: "original", rotulo: "Original" },
  { valor: "grayscale", rotulo: "Cinza" },
  { valor: "bw", rotulo: "Preto e branco" },
];

export const ROTULO_FILTRO: Record<Filtro, string> = {
  original: "Original",
  grayscale: "Cinza",
  bw: "P&B",
};

/** Coordenada normalizada (0..1) sobre a foto original. */
export interface Ponto {
  x: number;
  y: number;
}

/** Ordem: superior esquerdo, superior direito, inferior direito, inferior esquerdo. */
export type Cantos = [Ponto, Ponto, Ponto, Ponto];

export const CANTOS_TELA_INTEIRA: Cantos = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
];

export interface ImagemLocal {
  blob: Blob;
  url: string;
}

export type EstadoOcr = "pendente" | "carregando" | "pronto" | "erro";

export interface Pagina {
  id: string;
  original: ImagemLocal;
  largura: number;
  altura: number;
  cantos: Cantos | null;
  cantosDetectados: Cantos | null;
  detectado: boolean;
  filtro: Filtro;
  processadas: Partial<Record<Filtro, ImagemLocal>>;
  textoOcr: string;
  estadoOcr: EstadoOcr;
}

export interface DocumentoHistorico {
  id: string;
  title: string;
  pdf_url: string | null;
  page_count: number;
  created_at: string;
  document_pages: {
    processed_image_url: string;
    ocr_text: string;
    filter_applied: Filtro;
    page_order: number;
  }[];
}
