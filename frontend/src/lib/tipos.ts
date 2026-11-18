/** Os mesmos valores aceitos pela API e pela coluna document_pages.filter_applied. */
export type Filtro = "original" | "grayscale" | "bw" | "whiteboard";

export const FILTROS: { valor: Filtro; rotulo: string }[] = [
  { valor: "original", rotulo: "Original" },
  { valor: "grayscale", rotulo: "Cinza" },
  { valor: "bw", rotulo: "P&B" },
  { valor: "whiteboard", rotulo: "Quadro" },
];

export const ROTULO_FILTRO: Record<Filtro, string> = {
  original: "Original",
  grayscale: "Cinza",
  bw: "P&B",
  whiteboard: "Quadro",
};

/** Modos da câmera: cada um muda o que acontece depois da foto. */
export type Modo = "digitalizar" | "texto" | "cartao" | "livro" | "quadro" | "qrcode";

export const MODOS: { valor: Modo; rotulo: string; dica: string }[] = [
  { valor: "texto", rotulo: "Extrair texto", dica: "Fotografe a página para copiar o texto" },
  { valor: "cartao", rotulo: "Cartão ID", dica: "Frente e verso numa folha A4, em tamanho real" },
  { valor: "digitalizar", rotulo: "Digitalizar", dica: "Enquadre o documento" },
  { valor: "livro", rotulo: "Livro", dica: "Livro aberto: as duas páginas viram páginas separadas" },
  { valor: "quadro", rotulo: "Quadro branco", dica: "Remove reflexo e realça as canetas" },
  { valor: "qrcode", rotulo: "QR code", dica: "Aponte para o QR code" },
];

/** "id": RG, CNH e cartões (ISO ID-1, frente e verso). "passaporte": página de dados. */
export type FormatoCartao = "id" | "passaporte";

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

type EstadoOcr = "pendente" | "carregando" | "pronto" | "erro";

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
  /** Metade de um livro aberto já separado: não deve ser dividida de novo. */
  metadeDeLivro: boolean;
  textoOcr: string;
  estadoOcr: EstadoOcr;
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
