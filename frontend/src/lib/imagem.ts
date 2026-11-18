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
      rejeitar(new Error("Não foi possível abrir essa imagem. Tente uma foto em JPEG ou PNG."));
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

export function formatarTamanho(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}
