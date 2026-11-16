import type { Cantos, Filtro } from "@/lib/tipos";

const URL_API = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ErroApi extends Error {
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

export interface PaginaProcessada {
  blob: Blob;
  /** JSON das figuras detectadas (cabeçalho X-Regioes-Graficas); null se não houve detecção. */
  regioesGraficas: string | null;
}

export async function processarPagina(imagem: Blob, cantos: Cantos, filtro: Filtro): Promise<PaginaProcessada> {
  const corpo = new FormData();
  corpo.append("imagem", imagem, nomeArquivo(imagem, "foto"));
  corpo.append("cantos", JSON.stringify(cantos));
  corpo.append("filtro", filtro);
  const resposta = await enviar("/processar-pagina", corpo);
  return { blob: await resposta.blob(), regioesGraficas: resposta.headers.get("X-Regioes-Graficas") };
}

/** Com `regioesGraficas`, a API reaproveita as figuras já detectadas e responde ~2 s mais rápido. */
export async function extrairOcr(pagina: Blob, regioesGraficas?: string | null): Promise<string> {
  const corpo = new FormData();
  corpo.append("imagem", pagina, nomeArquivo(pagina, "pagina"));
  if (regioesGraficas) corpo.append("regioes", regioesGraficas);
  const resposta: { texto: string } = await (await enviar("/extrair-ocr", corpo)).json();
  return resposta.texto;
}

export async function gerarPdf(paginas: Blob[]): Promise<Blob> {
  const corpo = new FormData();
  paginas.forEach((pagina, indice) => corpo.append("paginas", pagina, nomeArquivo(pagina, `pagina-${indice + 1}`)));
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
  if (erro instanceof ErroApi) return erro.message;
  if (erro instanceof Error) return erro.message;
  return "Algo deu errado. Tente novamente.";
}
