"use client";

import { Check, Copy, Download, ExternalLink, LoaderCircle, Share2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAviso } from "@/componentes/aviso";
import { CabecalhoEtapa } from "@/componentes/cabecalho-etapa";
import { GradePaginas } from "@/componentes/grade-paginas";
import { adiantarVisualizador, VisualizadorPaginas } from "@/componentes/visualizador-sob-demanda";
import { obterDocumento } from "@/lib/api";
import { baixarArquivo, compartilharPdf, nomeDoArquivo } from "@/lib/arquivo";
import { ROTULO_FILTRO, type DocumentoCompleto } from "@/lib/tipos";
import { useVisualizador } from "@/lib/usar-visualizador";
import type { ImagemVisualizada } from "@/lib/visualizador";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const formatoData = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

type Estado =
  | { tipo: "carregando" }
  | { tipo: "erro"; mensagem: string }
  | { tipo: "pronto"; documento: DocumentoCompleto };

function contarPalavras(texto: string): number {
  return texto.split(/\s+/).filter(Boolean).length;
}

export function TelaDocumento() {
  const id = useSearchParams().get("id") ?? "";
  // Trocar de documento remonta a tela: nada do anterior fica na memória.
  return <ConteudoDocumento key={id} id={id} />;
}

function ConteudoDocumento({ id }: { id: string }) {
  const avisar = useAviso();
  const visualizador = useVisualizador();
  const idValido = UUID.test(id);
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });
  // O PDF é baixado logo ao abrir: no iPhone, o menu de compartilhar só abre se for
  // chamado logo depois do toque, sem esperar um download no meio. `blob` null = falhou.
  const [arquivoPdf, setArquivoPdf] = useState<{ url: string; blob: Blob | null } | null>(null);
  const [copiado, setCopiado] = useState<string | null>(null);

  useEffect(() => {
    if (!idValido) return;
    let cancelado = false;
    obterDocumento(id)
      .then((documento) => {
        if (cancelado) return;
        setEstado(
          documento
            ? { tipo: "pronto", documento }
            : { tipo: "erro", mensagem: "Documento não encontrado. Ele pode ter sido apagado." },
        );
      })
      .catch((erro: unknown) => {
        if (!cancelado) setEstado({ tipo: "erro", mensagem: erro instanceof Error ? erro.message : "Erro ao abrir." });
      });
    return () => {
      cancelado = true;
    };
  }, [id, idValido]);

  const urlPdf = estado.tipo === "pronto" ? estado.documento.url_pdf : null;
  // Já baixado (ou já falhou) para este endereço: voltar à tela não baixa de novo.
  const pdfResolvido = arquivoPdf !== null && arquivoPdf.url === urlPdf;

  useEffect(() => {
    if (!urlPdf || pdfResolvido) return;
    const controle = new AbortController();
    fetch(urlPdf, { signal: controle.signal })
      .then((resposta) => (resposta.ok ? resposta.blob() : Promise.reject(new Error(`HTTP ${resposta.status}`))))
      .then((blob) => setArquivoPdf({ url: urlPdf, blob }))
      .catch(() => {
        if (!controle.signal.aborted) setArquivoPdf({ url: urlPdf, blob: null });
      });
    return () => controle.abort();
  }, [urlPdf, pdfResolvido]);

  useEffect(() => {
    adiantarVisualizador();
  }, []);

  const imagensDoVisualizador = useMemo<ImagemVisualizada[]>(
    () =>
      estado.tipo === "pronto"
        ? estado.documento.paginas.map((p) => ({
            id: p.id,
            src: p.url_processada ?? "",
            srcOriginal: p.url_original ?? undefined,
            detalhe: ROTULO_FILTRO[p.filtro],
          }))
        : [],
    [estado],
  );

  const situacao: Estado = idValido ? estado : { tipo: "erro", mensagem: "Documento não encontrado." };

  if (situacao.tipo !== "pronto") {
    return (
      <main className="flex min-h-0 flex-1 flex-col">
        <CabecalhoEtapa titulo="Documento" voltarPara="/" rotuloVoltar="Voltar ao histórico" />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
          {situacao.tipo === "carregando" ? (
            <>
              <LoaderCircle className="size-8 animate-spin text-texto-suave" aria-hidden />
              <p className="text-sm text-texto-secundario">Abrindo o documento…</p>
            </>
          ) : (
            <>
              <p className="font-display text-sm font-bold text-texto">{situacao.mensagem}</p>
              <Link href="/" className="text-sm font-semibold text-primaria-texto underline underline-offset-2">
                Voltar ao histórico
              </Link>
            </>
          )}
        </div>
      </main>
    );
  }

  const { documento } = situacao;
  const paginas = documento.paginas;
  const nomeArquivo = nomeDoArquivo(documento.titulo);
  const textoCompleto = paginas
    .map((p) => p.texto_ocr.trim())
    .filter(Boolean)
    .join("\n\n");
  const pdf = pdfResolvido ? arquivoPdf.blob : null;
  const preparandoPdf = Boolean(urlPdf) && !pdfResolvido;

  async function copiar(texto: string, chave: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(chave);
      setTimeout(() => setCopiado((atual) => (atual === chave ? null : atual)), 2000);
    } catch {
      avisar("Não foi possível copiar. Selecione o texto e copie manualmente.", "erro");
    }
  }

  async function compartilhar() {
    if (preparandoPdf) return;
    // Sem o arquivo, não há o que compartilhar: o link do PDF vence em uma hora, e
    // mandar o link entregaria um endereço que para de funcionar.
    if (!pdf) {
      avisar("Não foi possível baixar o PDF. Toque em Abrir PDF ou volte e abra o documento de novo.", "erro");
      return;
    }
    try {
      const resultado = await compartilharPdf(pdf, nomeArquivo, documento.titulo);
      if (resultado === "baixado") avisar("Este navegador não compartilha arquivos; o PDF foi baixado.");
    } catch (erro) {
      if (erro instanceof DOMException && erro.name === "AbortError") return;
      avisar("Não foi possível compartilhar. Use o botão Baixar.", "erro");
    }
  }

  function baixar() {
    if (preparandoPdf) return;
    if (pdf) baixarArquivo(pdf, nomeArquivo);
    else if (documento.url_pdf) window.open(documento.url_pdf, "_blank", "noopener");
  }

  const botaoSecundario =
    "flex min-h-12 items-center justify-center gap-1.5 rounded-xl border border-borda bg-cartao text-xs font-semibold text-texto transition hover:bg-secundario disabled:opacity-60";

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <CabecalhoEtapa
        titulo={documento.titulo}
        subtitulo={`${paginas.length} ${paginas.length === 1 ? "página" : "páginas"} • ${formatoData.format(new Date(documento.criado_em))}`}
        voltarPara="/"
        rotuloVoltar="Voltar ao histórico"
      />

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-5">
        <section aria-labelledby="titulo-paginas">
          <h2
            id="titulo-paginas"
            className="mb-2.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-texto-secundario"
          >
            Páginas
          </h2>
          <GradePaginas
            itens={paginas.map((p) => ({ id: p.id, src: p.url_processada ?? "", detalhe: ROTULO_FILTRO[p.filtro] }))}
            aoEscolher={visualizador.abrir}
            acao="Ampliar"
          />
        </section>

        <section aria-labelledby="titulo-texto">
          <div className="mb-2.5 flex items-center justify-between gap-2">
            <h2
              id="titulo-texto"
              className="font-mono text-[11px] font-semibold uppercase tracking-wider text-texto-secundario"
            >
              Texto reconhecido
            </h2>
            {textoCompleto && (
              <button
                type="button"
                onClick={() => copiar(textoCompleto, "tudo")}
                className="flex min-h-9 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-primaria-texto hover:bg-secundario"
              >
                {copiado === "tudo" ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
                <span aria-live="polite">{copiado === "tudo" ? "Copiado" : "Copiar tudo"}</span>
              </button>
            )}
          </div>
          <div className="space-y-2">
            {paginas.map((p, indice) => {
              const palavras = contarPalavras(p.texto_ocr);
              return (
                <details key={p.id} className="group rounded-xl border border-borda bg-cartao shadow-cartao">
                  <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-2 px-3.5 text-sm font-semibold text-texto">
                    Página {indice + 1}
                    <span className="font-mono text-[11px] font-normal text-texto-secundario">
                      {palavras ? `${palavras} ${palavras === 1 ? "palavra" : "palavras"}` : "sem texto"}
                    </span>
                  </summary>
                  <div className="space-y-2 border-t border-borda p-3.5">
                    {p.texto_ocr.trim() ? (
                      <>
                        <p className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-texto">
                          {p.texto_ocr}
                        </p>
                        <button
                          type="button"
                          onClick={() => copiar(p.texto_ocr, p.id)}
                          className="flex min-h-9 items-center gap-1.5 rounded-lg text-xs font-semibold text-primaria-texto"
                        >
                          {copiado === p.id ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
                          <span aria-live="polite">{copiado === p.id ? "Copiado" : "Copiar texto da página"}</span>
                        </button>
                      </>
                    ) : (
                      <p className="text-xs italic text-texto-suave">Nenhum texto reconhecido nesta página.</p>
                    )}
                  </div>
                </details>
              );
            })}
          </div>
        </section>
      </div>

      {documento.url_pdf && (
        <div className="shrink-0 space-y-2.5 border-t border-borda bg-cartao p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <button
            type="button"
            onClick={compartilhar}
            disabled={preparandoPdf}
            className="flex min-h-[52px] w-full items-center justify-center gap-2 rounded-xl bg-primaria font-display text-sm font-bold text-white shadow-sm transition hover:bg-primaria-hover active:scale-[0.98] disabled:opacity-60"
          >
            {preparandoPdf ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            ) : (
              <Share2 className="size-4" aria-hidden />
            )}
            <span aria-live="polite">{preparandoPdf ? "Preparando o PDF…" : "Compartilhar PDF"}</span>
          </button>
          <div className="grid grid-cols-2 gap-2.5">
            <button type="button" onClick={baixar} disabled={preparandoPdf} className={botaoSecundario}>
              <Download className="size-4 text-primaria-texto" aria-hidden />
              Baixar PDF
            </button>
            <a href={documento.url_pdf} target="_blank" rel="noopener noreferrer" className={botaoSecundario}>
              <ExternalLink className="size-4 text-primaria-texto" aria-hidden />
              Abrir PDF
            </a>
          </div>
        </div>
      )}

      {visualizador.indice !== null && (
        <VisualizadorPaginas
          imagens={imagensDoVisualizador}
          indice={Math.min(visualizador.indice, paginas.length - 1)}
          aoMudarIndice={visualizador.mostrar}
          aoFechar={visualizador.fechar}
        />
      )}
    </main>
  );
}
