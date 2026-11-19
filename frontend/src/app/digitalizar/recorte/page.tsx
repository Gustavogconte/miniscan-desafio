"use client";

import { Check, LoaderCircle, Maximize, ScanLine } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAviso } from "@/componentes/aviso";
import { CabecalhoEtapa } from "@/componentes/cabecalho-etapa";
import { EditorCantos } from "@/componentes/editor-cantos";
import { detectarCantos, mensagemDeErro } from "@/lib/api";
import { useDigitalizacao } from "@/lib/estado-digitalizacao";
import { usarDeteccaoDaCaptura, useProcessamento } from "@/lib/processamento";
import { CANTOS_TELA_INTEIRA, type Cantos } from "@/lib/tipos";
import { useGuardaDigitalizacao } from "@/lib/usar-guarda";

const BOTAO_SECUNDARIO =
  "flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-borda bg-secundario text-xs font-semibold text-texto transition hover:opacity-90 disabled:opacity-50";
const BOTAO_CONFIRMAR =
  "flex min-h-[52px] w-full items-center justify-center gap-2 rounded-xl bg-primaria font-display text-sm font-bold text-white shadow-sm transition hover:bg-primaria-hover active:scale-[0.98] disabled:opacity-60";
const RODAPE = "shrink-0 space-y-2.5 border-t border-borda bg-cartao p-4 pb-[max(1rem,env(safe-area-inset-bottom))]";

export default function TelaRecorte() {
  const { paginaAtual } = useDigitalizacao();
  // Página do modo RG ou CNH: recorta a foto de cada lado, e não a folha A4 já montada.
  return paginaAtual?.cartao ? <RecorteCartao key={paginaAtual.id} /> : <RecortePagina />;
}

function RecortePagina() {
  const router = useRouter();
  const avisar = useAviso();
  const { paginaAtual: pagina, paginas, indiceAtual, atualizarPagina, removerPagina } = useGuardaDigitalizacao();
  const { confirmarPagina } = useProcessamento();
  const [confirmando, setConfirmando] = useState(false);
  const detectadoPara = useRef<string | null>(null);

  const id = pagina?.id;
  const precisaDetectar = pagina !== null && pagina.cantos === null;

  useEffect(() => {
    if (!id || !precisaDetectar || detectadoPara.current === id) return;
    detectadoPara.current = id;
    const original = pagina!.original.blob;
    // A câmera já pediu os cantos ao servidor na captura: aproveita a resposta e só pede
    // de novo se esse pedido falhou (ou se a foto veio de outro caminho).
    Promise.resolve(usarDeteccaoDaCaptura(id))
      .then((daCaptura) => daCaptura ?? detectarCantos(original))
      .then(({ cantos, detectado }) => {
        atualizarPagina(id, { cantos, cantosDetectados: cantos, detectado });
        if (!detectado) avisar("Não encontrei as bordas da folha. Arraste os cantos até ela.", "erro");
      })
      .catch((erro) => {
        atualizarPagina(id, { cantos: CANTOS_TELA_INTEIRA, detectado: false });
        avisar(mensagemDeErro(erro), "erro");
      });
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
      />

      <div className="relative min-h-0 flex-1 bg-palco-recorte">
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

      <div className={RODAPE}>
        <div className="grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={() => pagina.cantosDetectados && usarCantos(pagina.cantosDetectados)}
            disabled={!pagina.cantosDetectados || !pagina.detectado || confirmando}
            className={BOTAO_SECUNDARIO}
          >
            <ScanLine className="size-4 text-primaria-texto" aria-hidden />
            Recorte automático
          </button>
          <button
            type="button"
            onClick={() => usarCantos(CANTOS_TELA_INTEIRA)}
            disabled={!cantos || confirmando}
            className={BOTAO_SECUNDARIO}
          >
            <Maximize className="size-4 text-texto-secundario" aria-hidden />
            Foto inteira
          </button>
        </div>
        <button type="button" onClick={confirmar} disabled={!cantos || confirmando} className={BOTAO_CONFIRMAR}>
          {confirmando ? <LoaderCircle className="size-5 animate-spin" aria-hidden /> : <Check className="size-5" aria-hidden />}
          {confirmando ? "Endireitando a página…" : "Confirmar recorte"}
        </button>
      </div>
    </main>
  );
}

/** Recorte de uma página do modo RG ou CNH: os cantos da frente e do verso, cada um na sua foto. */
function RecorteCartao() {
  const router = useRouter();
  const avisar = useAviso();
  const { paginaAtual: pagina } = useGuardaDigitalizacao();
  const { recortarCartao } = useProcessamento();
  const [ladoAtivo, setLadoAtivo] = useState(0);
  // Cantos ajustados nesta visita; null = os do último recorte confirmado.
  const [editados, setEditados] = useState<Cantos[] | null>(null);
  const [detectando, setDetectando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  // O Next guarda esta tela escondida ao navegar: sair sem confirmar descarta os ajustes.
  useEffect(
    () => () => {
      setEditados(null);
      setLadoAtivo(0);
    },
    [],
  );

  if (!pagina?.cartao) return null;

  const { lados } = pagina.cartao;
  const indice = Math.min(ladoAtivo, lados.length - 1);
  const lado = lados[indice];
  const cantosDosLados = editados ?? lados.map((l) => l.cantos);
  const nomes = lados.length > 1 ? ["Frente", "Verso"] : ["Documento"];

  function usarCantos(novos: Cantos) {
    const copia = [...cantosDosLados];
    copia[indice] = novos;
    setEditados(copia);
  }

  async function detectarDeNovo() {
    setDetectando(true);
    try {
      const { cantos, detectado } = await detectarCantos(lado.original.blob);
      if (detectado) usarCantos(cantos);
      else avisar("Não encontrei as bordas do documento. Arraste os cantos até ele.", "erro");
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
    } finally {
      setDetectando(false);
    }
  }

  async function confirmar() {
    setConfirmando(true);
    try {
      await recortarCartao(pagina!.id, cantosDosLados);
      setEditados(null);
      router.push("/digitalizar/editor");
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
    } finally {
      setConfirmando(false);
    }
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <CabecalhoEtapa
        titulo="Recortar documento"
        subtitulo="Arraste os 4 cantos até as bordas do documento"
        voltarPara="/digitalizar/editor"
        rotuloVoltar="Voltar ao editor sem mudar o recorte"
      />

      {lados.length > 1 && (
        <div className="flex shrink-0 justify-center border-b border-borda bg-cartao px-4 py-2.5">
          <div className="flex rounded-full bg-secundario p-1" role="radiogroup" aria-label="Lado do documento">
            {nomes.map((nome, i) => (
              <button
                key={nome}
                type="button"
                role="radio"
                aria-checked={indice === i}
                onClick={() => setLadoAtivo(i)}
                className={`min-h-10 rounded-full px-5 text-sm font-semibold transition ${
                  indice === i ? "bg-primaria text-white" : "text-texto"
                }`}
              >
                {nome}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="relative min-h-0 flex-1 bg-palco-recorte">
        <EditorCantos
          key={indice}
          imagemUrl={lado.original.url}
          largura={lado.largura}
          altura={lado.altura}
          cantos={cantosDosLados[indice]}
          aoMudar={usarCantos}
        />
      </div>

      <div className={RODAPE}>
        <div className="grid grid-cols-2 gap-2.5">
          <button type="button" onClick={detectarDeNovo} disabled={detectando || confirmando} className={BOTAO_SECUNDARIO}>
            {detectando ? (
              <LoaderCircle className="size-4 animate-spin text-primaria-texto" aria-hidden />
            ) : (
              <ScanLine className="size-4 text-primaria-texto" aria-hidden />
            )}
            Recorte automático
          </button>
          <button
            type="button"
            onClick={() => usarCantos(CANTOS_TELA_INTEIRA)}
            disabled={confirmando}
            className={BOTAO_SECUNDARIO}
          >
            <Maximize className="size-4 text-texto-secundario" aria-hidden />
            Foto inteira
          </button>
        </div>
        <button type="button" onClick={confirmar} disabled={confirmando} className={BOTAO_CONFIRMAR}>
          {confirmando ? <LoaderCircle className="size-5 animate-spin" aria-hidden /> : <Check className="size-5" aria-hidden />}
          {confirmando ? "Montando o documento…" : "Confirmar recorte"}
        </button>
      </div>
    </main>
  );
}
