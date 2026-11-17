import type { Cantos, Filtro, FormatoCartao } from "@/lib/tipos";

const URL_API = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

class ErroApi extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ErroApi";
  }
}

async function enviar(caminho: string, corpo: FormData): Promise<Response> {
  let resposta: Response;
  try {
    resposta = await fetch(`${URL_API}${caminho}`, { method: "POST", body: corpo });
  } catch {
    throw new ErroApi("Não foi possível conectar ao servidor. Verifique sua internet.", 0);
  }
  if (!resposta.ok) {
    let detalhe = `O servidor respondeu com erro ${resposta.status}.`;
    try {
      const corpoErro = await resposta.json();
      if (typeof corpoErro?.detail === "string") detalhe = corpoErro.detail;
    } catch {
      // resposta sem JSON: mantém a mensagem genérica
    }
    throw new ErroApi(detalhe, resposta.status);
  }
  return resposta;
}

function nomeArquivo(blob: Blob, base: string): string {
  const extensao = blob.type === "image/png" ? "png" : blob.type === "application/pdf" ? "pdf" : "jpg";
  return `${base}.${extensao}`;
}

export async function detectarCantos(imagem: Blob): Promise<{ cantos: Cantos; detectado: boolean }> {
  const corpo = new FormData();
  corpo.append("imagem", imagem, nomeArquivo(imagem, "foto"));
  return (await enviar("/detectar-cantos", corpo)).json();
}

export async function processarPagina(imagem: Blob, cantos: Cantos, filtro: Filtro): Promise<Blob> {
  const corpo = new FormData();
  corpo.append("imagem", imagem, nomeArquivo(imagem, "foto"));
  corpo.append("cantos", JSON.stringify(cantos));
  corpo.append("filtro", filtro);
  return (await enviar("/processar-pagina", corpo)).blob();
}

/**
 * Lê o texto da página. Envia a FOTO ORIGINAL e os cantos: a API retifica e lê a
 * versão sem filtro, porque o OCR erra muito na versão binarizada (P&B), que serve
 * só para a tela e o PDF.
 */
export async function extrairOcr(fotoOriginal: Blob, cantos: Cantos): Promise<string> {
  const corpo = new FormData();
  corpo.append("imagem", fotoOriginal, nomeArquivo(fotoOriginal, "foto"));
  corpo.append("cantos", JSON.stringify(cantos));
  const resposta: { texto: string } = await (await enviar("/extrair-ocr", corpo)).json();
  return resposta.texto;
}

/** `carimbo`: data e hora escritas em cada página (ex.: "16/11/2026 14:32"). */
export async function gerarPdf(paginas: Blob[], carimbo?: string): Promise<Blob> {
  const corpo = new FormData();
  paginas.forEach((pagina, indice) => corpo.append("paginas", pagina, nomeArquivo(pagina, `pagina-${indice + 1}`)));
  if (carimbo) corpo.append("carimbo", carimbo);
  return (await enviar("/gerar-pdf", corpo)).blob();
}

export interface DadosDocumento {
  titulo: string;
  pdf: Blob;
  paginas: { original: Blob; processada: Blob; filtro: Filtro; textoOcr: string }[];
}

export interface DocumentoSalvo {
  id: string;
  titulo: string;
  pdf_url: string;
  total_paginas: number;
}

export async function salvarDocumento(dados: DadosDocumento): Promise<DocumentoSalvo> {
  const corpo = new FormData();
  corpo.append("titulo", dados.titulo);
  corpo.append("pdf", dados.pdf, "documento.pdf");
  dados.paginas.forEach((pagina, indice) => {
    corpo.append("originais", pagina.original, nomeArquivo(pagina.original, `original-${indice + 1}`));
    corpo.append("processadas", pagina.processada, nomeArquivo(pagina.processada, `processada-${indice + 1}`));
  });
  corpo.append(
    "paginas",
    JSON.stringify(dados.paginas.map((p) => ({ filtro: p.filtro, texto_ocr: p.textoOcr }))),
  );
  return (await enviar("/documentos", corpo)).json();
}

export function mensagemDeErro(erro: unknown): string {
  if (erro instanceof Error) return erro.message;
  return "Algo deu errado. Tente novamente.";
}

export interface LivroDividido {
  esquerda: Cantos;
  direita: Cantos;
  lombada: number;
}

/** Recebe os cantos do livro aberto inteiro e devolve os cantos de cada página na mesma foto. */
export async function dividirLivro(imagem: Blob, cantos: Cantos): Promise<LivroDividido> {
  const corpo = new FormData();
  corpo.append("imagem", imagem, nomeArquivo(imagem, "livro"));
  corpo.append("cantos", JSON.stringify(cantos));
  return (await enviar("/dividir-livro", corpo)).json();
}

/** Monta frente (e verso) já retificados numa folha A4, em tamanho real. */
export async function comporCartao(frente: Blob, verso: Blob | null, formato: FormatoCartao): Promise<Blob> {
  const corpo = new FormData();
  corpo.append("frente", frente, nomeArquivo(frente, "frente"));
  if (verso) corpo.append("verso", verso, nomeArquivo(verso, "verso"));
  corpo.append("formato", formato);
  return (await enviar("/compor-cartao", corpo)).blob();
}

export async function lerQrcode(imagem: Blob): Promise<string[]> {
  const corpo = new FormData();
  corpo.append("imagem", imagem, nomeArquivo(imagem, "qrcode"));
  const resposta: { textos: string[] } = await (await enviar("/ler-qrcode", corpo)).json();
  return resposta.textos;
}
