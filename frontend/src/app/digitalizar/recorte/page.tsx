"use client";

import { Check, LoaderCircle, Maximize, ScanLine } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAviso } from "@/componentes/aviso";
import { CabecalhoEtapa } from "@/componentes/cabecalho-etapa";
import { EditorCantos } from "@/componentes/editor-cantos";
import { detectarCantos, mensagemDeErro, processarPagina } from "@/lib/api";
import { criarImagemLocal, liberarImagens } from "@/lib/estado-digitalizacao";
import { useProcessamento } from "@/lib/processamento";
import { CANTOS_TELA_INTEIRA, type Cantos } from "@/lib/tipos";
import { useGuardaDigitalizacao } from "@/lib/usar-guarda";

export default function TelaRecorte() {
  const router = useRouter();
  const avisar = useAviso();
  const { paginaAtual: pagina, paginas, indiceAtual, atualizarPagina, removerPagina } = useGuardaDigitalizacao();
  const { executarOcr } = useProcessamento();
  const [detectando, setDetectando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
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
  const voltarPara = paginas.length > 1 ? "/digitalizar/editor" : "/";
  // Página recém-adicionada que nunca foi recortada: voltar significa desistir dela.
  const nuncaConfirmada = Object.keys(pagina.processadas).length === 0;
  const descartarSeNova = paginas.length > 1 && nuncaConfirmada ? () => removerPagina(pagina.id) : undefined;

  function usarCantos(novos: Cantos) {
    atualizarPagina(pagina!.id, { cantos: novos });
  }

  async function confirmar() {
    if (!cantos) return;
    setConfirmando(true);
    const alvo = pagina!;
    try {
      const blob = await processarPagina(alvo.original.blob, cantos, alvo.filtro);
      // Cantos novos invalidam as versões já processadas e o texto lido antes.
      liberarImagens(Object.values(alvo.processadas));
      const imagem = criarImagemLocal(blob);
      atualizarPagina(alvo.id, { processadas: { [alvo.filtro]: imagem }, textoOcr: "", estadoOcr: "pendente" });
      void executarOcr(alvo.id, alvo.filtro === "bw" ? blob : undefined);
      router.push("/digitalizar/editor");
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
      setConfirmando(false);
    }
  }

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
        aoVoltar={descartarSeNova}
        rotuloVoltar={
          descartarSeNova ? "Descartar esta página e voltar ao editor" : paginas.length > 1 ? "Voltar ao editor" : "Cancelar e voltar ao início"
        }
        acao={
          <span
            className={`rounded-lg px-2.5 py-1 font-mono text-[10px] font-semibold ${
              pagina.detectado ? "bg-primaria-suave text-primaria" : "bg-secundario text-texto-secundario"
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
          />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-3 text-slate-300">
            <LoaderCircle className="size-8 animate-spin" aria-hidden />
            <p className="text-sm">Procurando as bordas da folha…</p>
          </div>
        )}
      </div>

      <div className="shrink-0 space-y-3 border-t border-borda bg-cartao p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={() => pagina.cantosDetectados && usarCantos(pagina.cantosDetectados)}
            disabled={!pagina.cantosDetectados || !pagina.detectado || confirmando}
            className="flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-borda bg-secundario text-xs font-semibold text-texto transition hover:opacity-90 disabled:opacity-50"
          >
            <ScanLine className="size-4 text-primaria" aria-hidden />
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
