"use client";

import { CalendarClock, CloudUpload, Download, FileText, LoaderCircle, RotateCw, Share2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAviso } from "@/componentes/aviso";
import { CabecalhoEtapa } from "@/componentes/cabecalho-etapa";
import { gerarPdf, mensagemDeErro, salvarDocumento } from "@/lib/api";
import { baixarArquivo, compartilharPdf, nomeDoArquivo } from "@/lib/arquivo";
import { useDigitalizacao } from "@/lib/estado-digitalizacao";
import { formatarTamanho } from "@/lib/imagem";
import { useProcessamento } from "@/lib/processamento";
import { ROTULO_FILTRO } from "@/lib/tipos";
import { useGuardaDigitalizacao } from "@/lib/usar-guarda";

type EstadoPdf = { tipo: "gerando" } | { tipo: "pronto"; blob: Blob } | { tipo: "erro"; mensagem: string };

function tituloPadrao(): string {
  const hoje = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date());
  return `Documento ${hoje}`;
}

/** Data e hora locais no formato aceito pela API: 16/11/2026 14:32. */
function carimboAgora(): string {
  const agora = new Date();
  const dois = (n: number) => String(n).padStart(2, "0");
  return `${dois(agora.getDate())}/${dois(agora.getMonth() + 1)}/${agora.getFullYear()} ${dois(agora.getHours())}:${dois(agora.getMinutes())}`;
}

export default function TelaExportar() {
  // Documento novo, tela nova: título, carimbo e PDF não passam de um documento a outro.
  const { sessao } = useDigitalizacao();
  return <ConteudoExportar key={sessao} />;
}

function ConteudoExportar() {
  const router = useRouter();
  const avisar = useAviso();
  const { paginas, reiniciar } = useGuardaDigitalizacao();
  const { garantirProcessada } = useProcessamento();
  // null = o usuário ainda não editou; o padrão com a data só é calculado no navegador.
  const [tituloEditado, setTitulo] = useState<string | null>(null);
  const [pdf, setPdf] = useState<EstadoPdf>({ tipo: "gerando" });
  const [salvando, setSalvando] = useState(false);
  const [comCarimbo, setComCarimbo] = useState(false);
  // Só a geração mais recente pode mostrar o resultado (uma antiga pode terminar depois).
  const geracao = useRef(0);

  const gerar = useCallback(async (carimbar: boolean) => {
    if (paginas.length === 0) return;
    const minha = ++geracao.current;
    setPdf({ tipo: "gerando" });
    try {
      const imagens = await Promise.all(paginas.map((p) => garantirProcessada(p.id, p.filtro)));
      const carimbo = carimbar ? carimboAgora() : undefined;
      const blob = await gerarPdf(imagens.map((i) => i.blob), carimbo);
      if (minha === geracao.current) setPdf({ tipo: "pronto", blob });
    } catch (erro) {
      if (minha === geracao.current) setPdf({ tipo: "erro", mensagem: mensagemDeErro(erro) });
    }
  }, [paginas, garantirProcessada]);

  // O Next guarda esta tela escondida ao navegar. O PDF é gerado de novo cada vez que
  // ela aparece: o guardado podia ser de antes de o usuário mudar um filtro ou uma página.
  const gerarAoAparecer = useRef(gerar);
  const carimboAtual = useRef(comCarimbo);
  useEffect(() => {
    gerarAoAparecer.current = gerar;
    carimboAtual.current = comCarimbo;
  });
  useEffect(() => {
    void gerarAoAparecer.current(carimboAtual.current);
    return () => {
      geracao.current += 1;
      setPdf({ tipo: "gerando" });
      setSalvando(false);
    };
  }, []);

  if (paginas.length === 0) return null;

  const titulo = tituloEditado ?? tituloPadrao();
  const nomeArquivo = nomeDoArquivo(titulo);
  const ocrPendente = paginas.some((p) => p.estadoOcr === "carregando" || p.estadoOcr === "pendente");
  const pronto = pdf.tipo === "pronto";

  function baixar() {
    if (pdf.tipo === "pronto") baixarArquivo(pdf.blob, nomeArquivo);
  }

  async function compartilhar() {
    if (pdf.tipo !== "pronto") return;
    try {
      const resultado = await compartilharPdf(pdf.blob, nomeArquivo, titulo);
      if (resultado === "baixado") avisar("Este navegador não compartilha arquivos; o PDF foi baixado.");
    } catch {
      avisar("Não foi possível compartilhar. Use o botão Baixar.", "erro");
    }
  }

  async function salvar() {
    if (pdf.tipo !== "pronto") return;
    if (!titulo.trim()) {
      avisar("Dê um título ao documento antes de salvar.", "erro");
      return;
    }
    setSalvando(true);
    try {
      const imagens = await Promise.all(paginas.map((p) => garantirProcessada(p.id, p.filtro)));
      await salvarDocumento({
        titulo: titulo.trim(),
        pdf: pdf.blob,
        paginas: paginas.map((p, i) => ({
          original: p.original.blob,
          processada: imagens[i].blob,
          filtro: p.filtro,
          textoOcr: p.textoOcr,
        })),
      });
      avisar("Documento salvo no histórico");
      reiniciar();
      router.push("/");
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
      setSalvando(false);
    }
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <CabecalhoEtapa
        titulo="Exportar PDF"
        subtitulo="Compartilhe, baixe ou salve no histórico"
        voltarPara="/digitalizar/editor"
        rotuloVoltar="Voltar ao editor"
      />

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
        <div className="flex items-center gap-4 rounded-2xl border border-borda bg-cartao p-4 shadow-cartao">
          <div className="flex h-16 w-14 shrink-0 flex-col items-center justify-center rounded-xl border border-perigo/25 bg-perigo/10">
            <FileText className="size-6 text-perigo" aria-hidden />
            <span className="mt-0.5 font-mono text-[11px] font-bold text-texto">
              {paginas.length} {paginas.length === 1 ? "PÁG" : "PÁGS"}
            </span>
          </div>
          <div className="min-w-0 flex-1" aria-live="polite">
            {pdf.tipo === "gerando" && (
              <span className="flex items-center gap-1.5 text-xs font-semibold text-texto-secundario">
                <LoaderCircle className="size-3.5 animate-spin" aria-hidden /> Montando o PDF…
              </span>
            )}
            {pdf.tipo === "pronto" && (
              <span className="flex items-center gap-1.5 font-mono text-[11px] font-semibold text-sucesso">
                <span className="size-1.5 rounded-full bg-sucesso" /> PDF pronto
              </span>
            )}
            {pdf.tipo === "erro" && <span className="text-xs font-semibold text-perigo">{pdf.mensagem}</span>}
            <p className="mt-0.5 truncate font-display text-sm font-bold text-texto">{nomeArquivo}</p>
            <p className="mt-0.5 font-mono text-[11px] text-texto-secundario">
              {pronto ? formatarTamanho(pdf.blob.size) : "—"} • A4
            </p>
          </div>
          {pdf.tipo === "erro" && (
            <button
              type="button"
              onClick={() => gerar(comCarimbo)}
              aria-label="Tentar gerar o PDF de novo"
              className="flex size-11 items-center justify-center rounded-xl border border-borda text-primaria-texto"
            >
              <RotateCw className="size-4" aria-hidden />
            </button>
          )}
        </div>

        <label className="flex min-h-14 cursor-pointer items-center gap-3 rounded-2xl border border-borda bg-cartao p-4 shadow-cartao">
          <input
            type="checkbox"
            checked={comCarimbo}
            disabled={pdf.tipo === "gerando"}
            onChange={(evento) => {
              setComCarimbo(evento.target.checked);
              void gerar(evento.target.checked);
            }}
            className="size-5 shrink-0 accent-[var(--primaria)]"
          />
          <CalendarClock className="size-5 shrink-0 text-primaria-texto" aria-hidden />
          <span className="text-sm">
            <span className="block font-semibold text-texto">Carimbo de data e hora</span>
            <span className="block text-xs text-texto-secundario">Escreve a data e a hora atuais no rodapé de cada página</span>
          </span>
        </label>

        <div className="space-y-2 rounded-2xl border border-borda bg-cartao p-4 shadow-cartao">
          <label htmlFor="titulo" className="block text-xs font-semibold text-texto">
            Título do documento
          </label>
          <input
            id="titulo"
            value={titulo}
            onChange={(evento) => setTitulo(evento.target.value)}
            maxLength={200}
            className="h-11 w-full rounded-xl border border-borda-campo bg-fundo px-3.5 text-base text-texto focus:border-primaria-texto focus:outline-none focus:ring-2 focus:ring-primaria-suave sm:text-sm"
          />
          <p className="text-[11px] text-texto-secundario">O título também é usado na busca do histórico.</p>
        </div>

        <div className="rounded-2xl border border-borda bg-cartao p-4 shadow-cartao">
          <h2 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-texto-secundario">
            Páginas
          </h2>
          <ul className="mt-2 space-y-1.5">
            {paginas.map((p, i) => (
              <li key={p.id} className="flex items-center justify-between gap-2 text-xs">
                <span className="text-texto">Página {i + 1}</span>
                <span className="flex items-center gap-2 text-texto-secundario">
                  <span className="rounded-md bg-primaria-suave px-2 py-0.5 font-mono font-semibold text-primaria-texto">
                    {ROTULO_FILTRO[p.filtro]}
                  </span>
                  {p.estadoOcr === "pronto"
                    ? `${p.textoOcr.split(/\s+/).filter(Boolean).length} palavras`
                    : p.estadoOcr === "erro"
                      ? "sem OCR"
                      : "lendo texto…"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="shrink-0 space-y-2.5 border-t border-borda bg-cartao p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <button
          type="button"
          onClick={compartilhar}
          disabled={!pronto}
          className="flex min-h-[52px] w-full items-center justify-center gap-2 rounded-xl bg-primaria font-display text-sm font-bold text-white shadow-sm transition hover:bg-primaria-hover active:scale-[0.98] disabled:opacity-60"
        >
          <Share2 className="size-4" aria-hidden />
          Compartilhar PDF
        </button>
        <div className="grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={baixar}
            disabled={!pronto}
            className="flex min-h-12 items-center justify-center gap-1.5 rounded-xl border border-borda bg-cartao text-xs font-semibold text-texto transition hover:bg-secundario disabled:opacity-60"
          >
            <Download className="size-4 text-primaria-texto" aria-hidden />
            Baixar
          </button>
          <button
            type="button"
            onClick={salvar}
            disabled={!pronto || salvando || ocrPendente}
            className="flex min-h-12 items-center justify-center gap-1.5 rounded-xl border border-borda bg-secundario text-xs font-semibold text-texto transition hover:opacity-90 disabled:opacity-60"
          >
            {salvando ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            ) : (
              <CloudUpload className="size-4 text-primaria-texto" aria-hidden />
            )}
            {salvando ? "Salvando…" : ocrPendente ? "Aguardando OCR…" : "Salvar no histórico"}
          </button>
        </div>
      </div>
    </main>
  );
}
