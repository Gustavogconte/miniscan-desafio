/** Os três filtros do enunciado, com os mesmos valores da API e do banco. */
export type Filtro = "original" | "grayscale" | "bw";

export const FILTROS: { valor: Filtro; rotulo: string }[] = [
  { valor: "original", rotulo: "Original" },
  { valor: "grayscale", rotulo: "Cinza" },
  { valor: "bw", rotulo: "P&B" },
];

export const ROTULO_FILTRO: Record<Filtro, string> = {
  original: "Original",
  grayscale: "Cinza",
  bw: "P&B",
};

/** Modos da câmera: documento comum (uma ou várias páginas) ou documento de identidade. */
export type Modo = "digitalizar" | "cartao";

export const MODOS: { valor: Modo; rotulo: string; dica: string }[] = [
  { valor: "digitalizar", rotulo: "Digitalizar", dica: "Enquadre o documento" },
  { valor: "cartao", rotulo: "RG ou CNH", dica: "Frente e verso numa folha A4, em tamanho real" },
];

/** "id": RG e CNH (tamanho ISO ID-1, frente e verso). */
export type FormatoCartao = "id";

/** Coordenada normalizada (0..1) sobre a foto original. */
export interface Ponto {
  x: number;
  y: number;
}

/** Ordem: superior esquerdo, superior direito, inferior direito, inferior esquerdo. */
export type Cantos = [Ponto, Ponto, Ponto, Ponto];

/** Resposta do /detectar-cantos: sem a folha, `detectado` é falso e os cantos cobrem a foto toda. */
export interface Deteccao {
  cantos: Cantos;
  detectado: boolean;
}

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

type EstadoOcr = "pendente" | "carregando" | "pronto" | "erro";

/** Um lado do documento do modo RG ou CNH: a foto e os cantos do último recorte. */
export interface LadoDoDocumento {
  original: ImagemLocal;
  largura: number;
  altura: number;
  cantos: Cantos;
}

export interface Pagina {
  id: string;
  original: ImagemLocal;
  largura: number;
  altura: number;
  cantos: Cantos | null;
  cantosDetectados: Cantos | null;
  /** Cantos do último recorte confirmado: voltar sem confirmar restaura estes. */
  cantosConfirmados: Cantos | null;
  detectado: boolean;
  filtro: Filtro;
  processadas: Partial<Record<Filtro, ImagemLocal>>;
  textoOcr: string;
  estadoOcr: EstadoOcr;
  /** Página montada pelo modo RG ou CNH: guarda a foto de cada lado para dar para recortar de novo. */
  cartao?: { formato: FormatoCartao; lados: LadoDoDocumento[] };
}

/** Documento salvo com todas as páginas, para a tela do documento. */
export interface DocumentoCompleto {
  id: string;
  title: string;
  pdf_url: string | null;
  page_count: number;
  created_at: string;
  document_pages: {
    id: string;
    page_order: number;
    original_image_url: string;
    processed_image_url: string;
    filter_applied: Filtro;
    ocr_text: string;
  }[];
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
