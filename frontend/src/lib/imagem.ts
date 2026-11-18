const LADO_MAXIMO = 2400; // suficiente para OCR e bem mais leve que a foto de 12 MP da câmera
const QUALIDADE_JPEG = 0.9;

export interface FotoPreparada {
  blob: Blob;
  largura: number;
  altura: number;
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
  return { blob, largura, altura };
}

export function formatarTamanho(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}
