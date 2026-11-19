import { encerrarSessao, guardarSessao, obterSessao, type Sessao, type UsuarioSessao } from "@/lib/sessao";
import type { Cantos, Deteccao, DocumentoCompleto, DocumentoHistorico, Filtro, FormatoCartao } from "@/lib/tipos";

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

/**
 * Chama a API com o token da sessão. Se a API recusar a sessão (401), ela é apagada
 * do aparelho, e a guarda do layout leva a pessoa para a tela de entrada.
 */
async function chamar(caminho: string, init: RequestInit = {}): Promise<Response> {
  const token = obterSessao()?.token;
  const cabecalhos = new Headers(init.headers);
  if (token) cabecalhos.set("Authorization", `Bearer ${token}`);

  let resposta: Response;
  try {
    resposta = await fetch(`${URL_API}${caminho}`, { ...init, headers: cabecalhos });
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
    // Só derruba a sessão que foi enviada: um 401 de senha errada em /entrar não conta.
    if (resposta.status === 401 && token && obterSessao()?.token === token) encerrarSessao();
    throw new ErroApi(detalhe, resposta.status);
  }
  return resposta;
}

function enviar(caminho: string, corpo: FormData): Promise<Response> {
  return chamar(caminho, { method: "POST", body: corpo });
}

function enviarJson(caminho: string, corpo: unknown): Promise<Response> {
  return chamar(caminho, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
}

interface RespostaSessao {
  token: string;
  expira_em: string;
  usuario: UsuarioSessao;
}

async function abrirSessao(resposta: Response): Promise<Sessao> {
  const dados: RespostaSessao = await resposta.json();
  const sessao: Sessao = { token: dados.token, expiraEm: dados.expira_em, usuario: dados.usuario };
  guardarSessao(sessao);
  return sessao;
}

export async function entrar(email: string, senha: string): Promise<Sessao> {
  return abrirSessao(await enviarJson("/entrar", { email, senha }));
}

export async function cadastrar(nome: string, email: string, senha: string): Promise<Sessao> {
  return abrirSessao(await enviarJson("/cadastrar", { nome, email, senha }));
}

/** Encerra a sessão no servidor e no aparelho. Sem internet, sai do aparelho mesmo assim. */
export async function sair(): Promise<void> {
  try {
    await chamar("/sair", { method: "POST" });
  } catch {
    // o token some do aparelho de qualquer jeito, e vence sozinho no servidor
  } finally {
    encerrarSessao();
  }
}

/** Histórico da conta; com texto, procura no título e no OCR (português). */
export async function listarDocumentos(busca: string): Promise<DocumentoHistorico[]> {
  const parametros = new URLSearchParams({ busca: busca.trim() });
  return (await chamar(`/documentos?${parametros}`)).json();
}

/** Um documento salvo com todas as páginas (null se não existe ou é de outra conta). */
export async function obterDocumento(id: string): Promise<DocumentoCompleto | null> {
  try {
    return await (await chamar(`/documentos/${encodeURIComponent(id)}`)).json();
  } catch (erro) {
    if (erro instanceof ErroApi && erro.status === 404) return null;
    throw erro;
  }
}

function nomeArquivo(blob: Blob, base: string): string {
  const extensao = blob.type === "image/png" ? "png" : blob.type === "application/pdf" ? "pdf" : "jpg";
  return `${base}.${extensao}`;
}

export async function detectarCantos(imagem: Blob): Promise<Deteccao> {
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

/** Monta frente (e verso) já retificados numa folha A4, ampliados até o dobro do tamanho real. */
export async function comporCartao(frente: Blob, verso: Blob | null, formato: FormatoCartao): Promise<Blob> {
  const corpo = new FormData();
  corpo.append("frente", frente, nomeArquivo(frente, "frente"));
  if (verso) corpo.append("verso", verso, nomeArquivo(verso, "verso"));
  corpo.append("formato", formato);
  return (await enviar("/compor-cartao", corpo)).blob();
}
