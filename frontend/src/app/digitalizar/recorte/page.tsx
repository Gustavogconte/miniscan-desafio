"use client";

import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Check, LoaderCircle, Maximize, RefreshCw, ScanLine } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAviso } from "@/componentes/aviso";
import { CabecalhoEtapa } from "@/componentes/cabecalho-etapa";
import { EditorCantos, limitar, NOMES_CANTOS, PASSO_TECLADO } from "@/componentes/editor-cantos";
import { detectarCantos, mensagemDeErro } from "@/lib/api";
import { useProcessamento } from "@/lib/processamento";
import { CANTOS_TELA_INTEIRA, type Cantos } from "@/lib/tipos";
import { useGuardaDigitalizacao } from "@/lib/usar-guarda";

const PASSO_SETA = PASSO_TECLADO * 2;

export default function TelaRecorte() {
  const router = useRouter();
  const avisar = useAviso();
  const { paginaAtual: pagina, paginas, indiceAtual, atualizarPagina, removerPagina } = useGuardaDigitalizacao();
  const { confirmarPagina } = useProcessamento();
  const [detectando, setDetectando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [cantoAtivo, setCantoAtivo] = useState(0);
  const detectadoPara = useRef<string | null>(null);

  const id = pagina?.id;
  const precisaDetectar = pagina !== null && pagina.cantos === null;

  useEffect(() => {
    if (!id || !precisaDetectar || detectadoPara.current === id) return;
    detectadoPara.current = id;
    const original = pagina!.original.blob;
    setDetectando(true);
    detectarCantos(original)
      .then(({ cantos, detectado }) => {
        atualizarPagina(id, { cantos, cantosDetectados: cantos, detectado });
        if (!detectado) avisar("Não encontrei as bordas da folha. Arraste os cantos até ela.", "erro");
      })
      .catch((erro) => {
        atualizarPagina(id, { cantos: CANTOS_TELA_INTEIRA, detectado: false });
        avisar(mensagemDeErro(erro), "erro");
      })
      .finally(() => setDetectando(false));
  }, [id, precisaDetectar, pagina, atualizarPagina, avisar]);

  if (!pagina) return null;

  const cantos = pagina.cantos;
  // Página que nunca foi recortada: voltar significa desistir dela.
  const nuncaConfirmada = Object.keys(pagina.processadas).length === 0;
  const voltarPara = nuncaConfirmada && paginas.length === 1 ? "/" : "/digitalizar/editor";
  const rotuloVoltar = !nuncaConfirmada
    ? "Voltar ao editor sem mudar o recorte"
    : paginas.length > 1
      ? "Descartar esta página e voltar ao editor"
      : "Cancelar e voltar ao início";

  function aoVoltar() {
    const alvo = pagina!;
    if (nuncaConfirmada && paginas.length > 1) removerPagina(alvo.id);
    // Ajustes não confirmados não podem vazar para outros filtros: restaura o último recorte.
    else if (!nuncaConfirmada) atualizarPagina(alvo.id, { cantos: alvo.cantosConfirmados });
  }

  function usarCantos(novos: Cantos) {
    atualizarPagina(pagina!.id, { cantos: novos });
  }

  function moverCantoAtivo(dx: number, dy: number) {
    if (!cantos) return;
    const novos = cantos.map((c, i) => (i === cantoAtivo ? { x: limitar(c.x + dx), y: limitar(c.y + dy) } : c));
    usarCantos(novos as Cantos);
  }

  async function confirmar() {
    if (!cantos) return;
    setConfirmando(true);
    try {
      await confirmarPagina(pagina!.id, cantos);
      router.push("/digitalizar/editor");
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
    } finally {
      // O Next mantém esta tela montada (escondida) ao navegar: sem isto, ao voltar
      // pelo botão "Recortar" do editor o botão continuaria em "Corrigindo perspectiva…".
      setConfirmando(false);
    }
  }

  const nomeAtivo = NOMES_CANTOS[cantoAtivo];
  const botaoSeta =
    "flex size-11 items-center justify-center rounded-xl border border-borda bg-secundario text-texto transition hover:text-primaria-texto disabled:opacity-50";

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <CabecalhoEtapa
        titulo="Ajustar recorte"
        subtitulo={
          paginas.length > 1
            ? `Página ${indiceAtual + 1} de ${paginas.length} • arraste os 4 cantos`
            : "Arraste os 4 cantos até as bordas da folha"
        }
        voltarPara={voltarPara}
        aoVoltar={aoVoltar}
        rotuloVoltar={rotuloVoltar}
        acao={
          <span
            className={`rounded-lg px-2.5 py-1 font-mono text-[11px] font-semibold ${
              pagina.detectado ? "bg-primaria-suave text-primaria-texto" : "bg-secundario text-texto"
            }`}
          >
            {detectando ? "DETECTANDO" : pagina.detectado ? "AUTO" : "MANUAL"}
          </span>
        }
      />

      <div className="relative min-h-0 flex-1 bg-palco-recorte p-5">
        {cantos ? (
          <EditorCantos
            imagemUrl={pagina.original.url}
            largura={pagina.largura}
            altura={pagina.altura}
            cantos={cantos}
            aoMudar={usarCantos}
            cantoAtivo={cantoAtivo}
            aoSelecionarCanto={setCantoAtivo}
          />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-3 text-slate-300">
            <LoaderCircle className="size-8 animate-spin" aria-hidden />
            <p className="text-sm">Procurando as bordas da folha…</p>
          </div>
        )}
      </div>

      <div className="shrink-0 space-y-2.5 border-t border-borda bg-cartao p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        {/* Ajuste fino: alternativa ao arraste para leitores de tela e para precisão. */}
        <div className="flex items-center gap-1.5" role="group" aria-label={`Ajuste fino do canto ${nomeAtivo}`}>
          <button
            type="button"
            onClick={() => setCantoAtivo((atual) => (atual + 1) % 4)}
            disabled={!cantos}
            aria-label={`Canto selecionado: ${nomeAtivo}. Trocar de canto`}
            className="flex min-h-11 min-w-0 flex-1 items-center gap-1.5 rounded-xl border border-borda bg-secundario px-2.5 text-left text-[11px] font-semibold text-texto disabled:opacity-50"
          >
            <RefreshCw className="size-3.5 shrink-0 text-primaria-texto" aria-hidden />
            <span className="truncate">Canto {nomeAtivo}</span>
          </button>
          <button type="button" className={botaoSeta} disabled={!cantos} onClick={() => moverCantoAtivo(-PASSO_SETA, 0)} aria-label={`Mover canto ${nomeAtivo} para a esquerda`}>
            <ArrowLeft className="size-4" aria-hidden />
          </button>
          <button type="button" className={botaoSeta} disabled={!cantos} onClick={() => moverCantoAtivo(0, -PASSO_SETA)} aria-label={`Mover canto ${nomeAtivo} para cima`}>
            <ArrowUp className="size-4" aria-hidden />
          </button>
          <button type="button" className={botaoSeta} disabled={!cantos} onClick={() => moverCantoAtivo(0, PASSO_SETA)} aria-label={`Mover canto ${nomeAtivo} para baixo`}>
            <ArrowDown className="size-4" aria-hidden />
          </button>
          <button type="button" className={botaoSeta} disabled={!cantos} onClick={() => moverCantoAtivo(PASSO_SETA, 0)} aria-label={`Mover canto ${nomeAtivo} para a direita`}>
            <ArrowRight className="size-4" aria-hidden />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={() => pagina.cantosDetectados && usarCantos(pagina.cantosDetectados)}
            disabled={!pagina.cantosDetectados || !pagina.detectado || confirmando}
            className="flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-borda bg-secundario text-xs font-semibold text-texto transition hover:opacity-90 disabled:opacity-50"
          >
            <ScanLine className="size-4 text-primaria-texto" aria-hidden />
            Detecção automática
          </button>
          <button
            type="button"
            onClick={() => usarCantos(CANTOS_TELA_INTEIRA)}
            disabled={!cantos || confirmando}
            className="flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-borda bg-secundario text-xs font-semibold text-texto transition hover:opacity-90 disabled:opacity-50"
          >
            <Maximize className="size-4 text-texto-secundario" aria-hidden />
            Foto inteira
          </button>
        </div>
        <button
          type="button"
          onClick={confirmar}
          disabled={!cantos || confirmando}
          className="flex min-h-[52px] w-full items-center justify-center gap-2 rounded-xl bg-primaria font-display text-sm font-bold text-white shadow-sm transition hover:bg-primaria-hover active:scale-[0.98] disabled:opacity-60"
        >
          {confirmando ? (
            <LoaderCircle className="size-5 animate-spin" aria-hidden />
          ) : (
            <Check className="size-5" aria-hidden />
          )}
          {confirmando ? "Corrigindo perspectiva…" : "Confirmar recorte"}
        </button>
      </div>
    </main>
  );
}
