// Folha com resolução de sobra para o PDF (a API limita a página a 3000 px), sem subir
// os 12 MP inteiros de uma foto da galeria.
const LADO_MAXIMO = 3200;
const QUALIDADE_JPEG = 0.9;
// Cópia que vai ao /detectar-cantos. O detector trabalha com 256 a 500 px e os cantos
// voltam normalizados (0..1): a cópia pequena sobe rápido e dá o mesmo resultado.
const LADO_DETECCAO = 1280;

export interface FotoPreparada {
  blob: Blob;
  largura: number;
  altura: number;
  /** Cópia reduzida da mesma foto, só para detectar os cantos. */
  copiaDeteccao: Blob;
}

/** Desenha a foto reduzida a no máximo 1280 px e devolve um JPEG para a detecção. */
export async function copiaParaDeteccao(origem: CanvasImageSource, largura: number, altura: number): Promise<Blob> {
  const escala = Math.min(1, LADO_DETECCAO / Math.max(largura, altura));
  const tela = document.createElement("canvas");
  tela.width = Math.round(largura * escala);
  tela.height = Math.round(altura * escala);
  tela.getContext("2d")?.drawImage(origem, 0, 0, tela.width, tela.height);
  const blob = await new Promise<Blob | null>((resolver) => tela.toBlob(resolver, "image/jpeg", 0.85));
  if (!blob) throw new Error("Seu navegador não conseguiu processar a imagem.");
  return blob;
}

function carregarImagem(arquivo: Blob): Promise<HTMLImageElement> {
  return new Promise((resolver, rejeitar) => {
    const url = URL.createObjectURL(arquivo);
    const imagem = new Image();
    imagem.onload = () => {
      URL.revokeObjectURL(url);
      resolver(imagem);
    };
    imagem.onerror = () => {
      URL.revokeObjectURL(url);
      rejeitar(new Error("Não foi possível abrir essa imagem. Tente outra foto."));
    };
    imagem.src = url;
  });
}

/**
 * Reduz a foto e regrava em JPEG antes de enviar.
 *
 * O navegador já desenha a imagem com a orientação EXIF aplicada, então o JPEG
 * gerado sai "em pé" e sem metadados (inclusive a localização GPS da foto).
 */
export async function prepararFoto(arquivo: File): Promise<FotoPreparada> {
  const imagem = await carregarImagem(arquivo);
  const escala = Math.min(1, LADO_MAXIMO / Math.max(imagem.naturalWidth, imagem.naturalHeight));
  const largura = Math.round(imagem.naturalWidth * escala);
  const altura = Math.round(imagem.naturalHeight * escala);

  const tela = document.createElement("canvas");
  tela.width = largura;
  tela.height = altura;
  const contexto = tela.getContext("2d");
  if (!contexto) throw new Error("Seu navegador não conseguiu processar a imagem.");
  // O JPEG não tem transparência: sem um fundo branco, a parte transparente de um PNG
  // (assinatura, print recortado) viraria preto e confundiria o recorte e o OCR.
  contexto.fillStyle = "#ffffff";
  contexto.fillRect(0, 0, largura, altura);
  contexto.drawImage(imagem, 0, 0, largura, altura);

  const blob = await new Promise<Blob | null>((resolver) => tela.toBlob(resolver, "image/jpeg", QUALIDADE_JPEG));
  if (!blob) throw new Error("Seu navegador não conseguiu processar a imagem.");
  return { blob, largura, altura, copiaDeteccao: await copiaParaDeteccao(tela, largura, altura) };
}

// Montagem com as fotos de cada lado do RG ou CNH, para o "Ver foto original": basta
// para conferir o que foi fotografado, sem guardar duas fotos inteiras.
const LADO_MONTAGEM = 2400;
const ESPACO_MONTAGEM = 32;

/**
 * Junta as fotos dos lados do documento numa imagem só: lado a lado quando as fotos
 * estão em pé (como o celular costuma fotografar), uma embaixo da outra quando estão
 * deitadas. Cada foto fica com a mesma altura (ou largura) das outras.
 */
export async function juntarFotos(fotos: Blob[]): Promise<Blob> {
  const imagens = await Promise.all(fotos.map(carregarImagem));
  const emPe = imagens.every((imagem) => imagem.naturalHeight >= imagem.naturalWidth);
  const medida = (imagem: HTMLImageElement) => (emPe ? imagem.naturalHeight : imagem.naturalWidth);
  const base = Math.min(...imagens.map(medida));
  const partes = imagens.map((imagem) => {
    const fator = base / medida(imagem);
    return { imagem, largura: imagem.naturalWidth * fator, altura: imagem.naturalHeight * fator };
  });
  const comprimento =
    partes.reduce((soma, parte) => soma + (emPe ? parte.largura : parte.altura), 0) +
    ESPACO_MONTAGEM * (partes.length - 1);
  const [largura, altura] = emPe ? [comprimento, base] : [base, comprimento];
  const escala = Math.min(1, LADO_MONTAGEM / Math.max(largura, altura));

  const tela = document.createElement("canvas");
  tela.width = Math.round(largura * escala);
  tela.height = Math.round(altura * escala);
  const contexto = tela.getContext("2d");
  if (!contexto) throw new Error("Seu navegador não conseguiu processar a imagem.");
  contexto.fillStyle = "#0f172a";
  contexto.fillRect(0, 0, tela.width, tela.height);
  let posicao = 0;
  for (const parte of partes) {
    const [x, y] = emPe ? [posicao, 0] : [0, posicao];
    contexto.drawImage(parte.imagem, x * escala, y * escala, parte.largura * escala, parte.altura * escala);
    posicao += (emPe ? parte.largura : parte.altura) + ESPACO_MONTAGEM;
  }
  const blob = await new Promise<Blob | null>((resolver) => tela.toBlob(resolver, "image/jpeg", 0.85));
  if (!blob) throw new Error("Seu navegador não conseguiu processar a imagem.");
  return blob;
}

export function formatarTamanho(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}
