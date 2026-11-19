"use client";

import { Camera, Check, Flashlight, FlashlightOff, ImageIcon, LoaderCircle, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type MouseEvent } from "react";

import { useAviso } from "@/componentes/aviso";
import { adiantarVisualizador, VisualizadorPaginas } from "@/componentes/visualizador-sob-demanda";
import { detectarCantos, mensagemDeErro } from "@/lib/api";
import { useCameraAoVivo } from "@/lib/camera";
import { useDigitalizacao } from "@/lib/estado-digitalizacao";
import { prepararFoto, type FotoPreparada } from "@/lib/imagem";
import { novaPagina } from "@/lib/paginas";
import { detectarNaCaptura, useProcessamento, type LadoDoCartao } from "@/lib/processamento";
import { MODOS, type Cantos, type FormatoCartao, type Ponto } from "@/lib/tipos";
import { useVisualizador } from "@/lib/usar-visualizador";
import { indiceDepoisDeExcluir } from "@/lib/visualizador";

/** Proporção (largura/altura) dos formatos de cartão, para a moldura-guia. */
const PROPORCAO_CARTAO: Record<FormatoCartao, number> = { id: 85.6 / 54 };
const LADOS_DO_CARTAO: Record<FormatoCartao, number> = { id: 2 };

interface Tamanho {
  largura: number;
  altura: number;
}

/** As três formas de fotografar, num seletor só. */
const OPCOES_CAPTURA = [
  { valor: "unico", rotulo: "Único" },
  { valor: "lote", rotulo: "Lote" },
  { valor: "cartao", rotulo: "RG ou CNH" },
] as const;
type OpcaoCaptura = (typeof OPCOES_CAPTURA)[number]["valor"];

/**
 * Converte coordenadas da tela para o vídeo (0..1). O vídeo cobre a tela inteira
 * (object-cover): o que sobra nas bordas fica fora da tela, mas entra na foto, e o
 * recorte automático cuida disso.
 */
function geometria(tela: Tamanho, video: Tamanho) {
  const escala = Math.max(tela.largura / video.largura, tela.altura / video.altura);
  const largura = video.largura * escala;
  const altura = video.altura * escala;
  const dx = (tela.largura - largura) / 2;
  const dy = (tela.altura - altura) / 2;
  return {
    paraVideo: (x: number, y: number): Ponto => ({
      x: Math.min(1, Math.max(0, (x - dx) / largura)),
      y: Math.min(1, Math.max(0, (y - dy) / altura)),
    }),
  };
}

export default function TelaCamera() {
  const router = useRouter();
  const avisar = useAviso();
  const { modo, formatoCartao, configurar, paginas, adicionarPagina, removerPagina } = useDigitalizacao();
  const { concluirLote, montarCartao } = useProcessamento();
  // Revisão das fotos do lote antes de processar: ver em tela cheia e excluir as ruins.
  const revisao = useVisualizador();

  const area = useRef<HTMLDivElement>(null);
  const galeria = useRef<HTMLInputElement>(null);
  const cameraSistema = useRef<HTMLInputElement>(null);
  const botaoFotografar = useRef<HTMLButtonElement>(null);
  const ocupado = useRef(false);
  // A revisão excluiu a última foto: a miniatura sumiu, e o foco vai para o botão de fotografar.
  const focarNoDisparo = useRef(false);

  const {
    video,
    estado: estadoCamera,
    nomeCamera,
    lanternaSuportada,
    lanternaLigada,
    alternarLanterna,
    capturarQuadro,
  } = useCameraAoVivo();
  const ativa = estadoCamera === "ativa";
  const [tamanhoTela, setTamanhoTela] = useState<Tamanho>({ largura: 1, altura: 1 });
  const [tamanhoVideo, setTamanhoVideo] = useState<Tamanho>({ largura: 1, altura: 1 });
  const [lote, setLote] = useState(false);
  const [capturando, setCapturando] = useState(false);
  const [processando, setProcessando] = useState<string | null>(null);
  const [ladosCartao, setLadosCartao] = useState<LadoDoCartao[]>([]);

  const { paraVideo } = geometria(tamanhoTela, tamanhoVideo);
  const capturadas = useMemo(() => paginas.filter((p) => Object.keys(p.processadas).length === 0), [paginas]);
  const usaLote = lote && modo !== "cartao";
  const fotosDaRevisao = useMemo(() => capturadas.map((foto) => ({ id: foto.id, src: foto.original.url })), [capturadas]);
  const temFotoNoLote = usaLote && capturadas.length > 0;
  const opcaoAtual: OpcaoCaptura = modo === "cartao" ? "cartao" : lote ? "lote" : "unico";

  function escolherOpcao(opcao: OpcaoCaptura) {
    setLadosCartao([]);
    if (opcao === "cartao") {
      configurar({ modo: "cartao" });
      return;
    }
    configurar({ modo: "digitalizar" });
    setLote(opcao === "lote");
  }
  // Aberta pelo "+ Página" do editor: já há páginas recortadas, e fechar volta para o
  // documento (ir ao início descartaria tudo).
  const temDocumento = paginas.some((p) => Object.keys(p.processadas).length > 0);

  // O Next guarda esta tela escondida ao navegar. Sem limpar ao sair, o "Concluindo…"
  // do lote (ou do cartão) voltava junto e travava a câmera na visita seguinte.
  useEffect(
    () => () => {
      setProcessando(null);
      setLadosCartao([]);
    },
    [],
  );

  useEffect(() => {
    if (temFotoNoLote) adiantarVisualizador();
  }, [temFotoNoLote]);

  useEffect(() => {
    if (revisao.aberto || !focarNoDisparo.current) return;
    focarNoDisparo.current = false;
    botaoFotografar.current?.focus();
  }, [revisao.aberto]);

  // Moldura-guia do cartão: 86% da largura, na proporção real do documento.
  const guiaCartao = (() => {
    const largura = tamanhoTela.largura * 0.86;
    const altura = largura / PROPORCAO_CARTAO[formatoCartao];
    const x = (tamanhoTela.largura - largura) / 2;
    const y = (tamanhoTela.altura - altura) / 2 - tamanhoTela.altura * 0.04;
    return { x, y, largura, altura };
  })();

  function cantosDaGuia(): Cantos {
    const { x, y, largura, altura } = guiaCartao;
    return [paraVideo(x, y), paraVideo(x + largura, y), paraVideo(x + largura, y + altura), paraVideo(x, y + altura)];
  }

  useEffect(() => {
    const elemento = area.current;
    if (!elemento) return;
    const observador = new ResizeObserver(([entrada]) =>
      setTamanhoTela({ largura: entrada.contentRect.width, altura: entrada.contentRect.height }),
    );
    observador.observe(elemento);
    return () => observador.disconnect();
  }, []);

  // A foto vai ao servidor logo na captura: ele acha os cantos com o modelo DocAligner
  // enquanto a pessoa vira o documento, abre o recorte ou segue fotografando. No cartão,
  // `cantos` é a moldura-guia, que só vale se o servidor não achar o documento.
  async function registrarFoto(foto: FotoPreparada, cantos: Cantos | null) {
    const { blob, largura, altura, copiaDeteccao } = foto;
    if (modo === "cartao") {
      const deteccao = detectarCantos(copiaDeteccao).catch(() => null);
      const lados = [...ladosCartao, { blob, largura, altura, cantos, deteccao }];
      if (lados.length < LADOS_DO_CARTAO[formatoCartao]) {
        setLadosCartao(lados);
        avisar("Frente capturada. Agora vire o documento.");
        return;
      }
      await finalizarCartao(lados);
      return;
    }
    const pagina = novaPagina(blob, largura, altura);
    adicionarPagina(pagina);
    detectarNaCaptura(pagina.id, copiaDeteccao);
    if (usaLote) avisar(`Página ${capturadas.length + 1} capturada`);
    else router.push("/digitalizar/recorte");
  }

  async function capturar() {
    if (ocupado.current || processando) return;
    ocupado.current = true;
    setCapturando(true);
    try {
      const quadro = await capturarQuadro();
      await registrarFoto(quadro, modo === "cartao" ? cantosDaGuia() : null);
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
    } finally {
      ocupado.current = false;
      setCapturando(false);
    }
  }

  async function finalizarCartao(lados: LadoDoCartao[]) {
    setProcessando("Montando a folha com frente e verso…");
    try {
      await montarCartao(lados, formatoCartao);
      setLadosCartao([]);
      router.push("/digitalizar/editor");
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
      setLadosCartao([]);
      setProcessando(null);
    }
  }

  async function concluir() {
    const ids = capturadas.map((p) => p.id);
    if (ids.length === 0) return;
    setProcessando(`Recortando 1 de ${ids.length}…`);
    try {
      await concluirLote(ids, (feitas) =>
        setProcessando(feitas < ids.length ? `Recortando ${feitas + 1} de ${ids.length}…` : "Concluindo…"),
      );
      router.push("/digitalizar/editor");
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
      setProcessando(null);
    }
  }

  async function aoEscolherArquivo(evento: ChangeEvent<HTMLInputElement>) {
    const arquivo = evento.target.files?.[0];
    evento.target.value = "";
    if (!arquivo) return;
    try {
      await registrarFoto(await prepararFoto(arquivo), null);
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
    }
  }

  function confirmarSaida(evento: MouseEvent<HTMLAnchorElement>) {
    const total = capturadas.length + ladosCartao.length;
    if (total > 0 && !window.confirm(`Descartar ${total === 1 ? "a foto tirada" : `as ${total} fotos tiradas`}?`)) {
      evento.preventDefault();
      return;
    }
    // De volta ao documento: só as fotos ainda sem recorte saem; as páginas ficam.
    if (temDocumento) capturadas.forEach((foto) => removerPagina(foto.id));
  }

  function excluirDaRevisao(indice: number) {
    const foto = capturadas[indice];
    if (!foto || !window.confirm(`Excluir a foto ${indice + 1}?`)) return;
    removerPagina(foto.id);
    const proximo = indiceDepoisDeExcluir(indice, capturadas.length);
    if (proximo === null) {
      focarNoDisparo.current = true;
      revisao.fechar();
    } else revisao.mostrar(proximo);
  }

  // Com artigo: "a frente", "o verso".
  const ladoAtual = ladosCartao.length === 0 ? "a frente" : "o verso";
  const dica = (() => {
    if (processando) return processando;
    if (modo === "cartao") return `Encaixe ${ladoAtual} do documento na moldura`;
    if (capturando) return "Capturando…";
    return MODOS.find((m) => m.valor === modo)?.dica ?? "Enquadre o documento";
  })();

  return (
    <main className="relative min-h-0 flex-1 overflow-hidden bg-black text-white">
      <input ref={galeria} type="file" accept="image/*" className="hidden" onChange={aoEscolherArquivo} aria-hidden tabIndex={-1} />
      <input
        ref={cameraSistema}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={aoEscolherArquivo}
        aria-hidden
        tabIndex={-1}
      />

      {/* Barra superior */}
      <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-between gap-2 bg-gradient-to-b from-black/70 to-transparent px-3 pb-6 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <Link
          href={temDocumento ? "/digitalizar/editor" : "/"}
          onClick={confirmarSaida}
          aria-label={temDocumento ? "Fechar a câmera e voltar ao documento" : "Fechar a câmera"}
          className="flex size-11 items-center justify-center rounded-full bg-black/40"
        >
          <X className="size-6" aria-hidden />
        </Link>
        {estadoCamera === "ativa" && tamanhoVideo.largura > 1 && (
          // Resolução real entregue pela câmera: ajuda a entender fotos com pouca nitidez.
          <span
            title={nomeCamera || undefined}
            className="mr-auto truncate rounded-full bg-black/40 px-2.5 py-1 font-mono text-[11px] text-white/80"
          >
            {tamanhoVideo.largura}×{tamanhoVideo.altura}
          </span>
        )}
        <div className="flex items-center gap-2">
          {lanternaSuportada && (
            <button
              type="button"
              onClick={alternarLanterna}
              aria-pressed={lanternaLigada}
              aria-label={lanternaLigada ? "Desligar a lanterna" : "Ligar a lanterna"}
              className="flex size-11 items-center justify-center rounded-full bg-black/40"
            >
              {lanternaLigada ? <Flashlight className="size-5" aria-hidden /> : <FlashlightOff className="size-5" aria-hidden />}
            </button>
          )}
        </div>
      </div>

      {/* Vídeo na tela inteira; a barra de cima e os controles de baixo ficam por cima. */}
      <div ref={area} className="absolute inset-0 overflow-hidden">
        <video
          ref={video}
          playsInline
          muted
          autoPlay
          onLoadedMetadata={(e) =>
            setTamanhoVideo({ largura: e.currentTarget.videoWidth, altura: e.currentTarget.videoHeight })
          }
          // A resolução muda depois da abertura, quando a câmera sobe para o máximo.
          onResize={(e) =>
            setTamanhoVideo({ largura: e.currentTarget.videoWidth, altura: e.currentTarget.videoHeight })
          }
          className="absolute inset-0 size-full object-cover"
        />

        {ativa && modo === "cartao" && (
          <svg className="pointer-events-none absolute inset-0 size-full" aria-hidden>
            <rect
              x={guiaCartao.x}
              y={guiaCartao.y}
              width={guiaCartao.largura}
              height={guiaCartao.altura}
              rx={14}
              fill="none"
              stroke="white"
              strokeWidth={3}
              strokeDasharray="14 10"
            />
          </svg>
        )}

        {capturando && <div className="pointer-events-none absolute inset-0 animate-pulse bg-white/30" aria-hidden />}

        <p
          aria-live="polite"
          className="absolute inset-x-6 top-[calc(env(safe-area-inset-top)+4.5rem)] z-10 mx-auto w-fit rounded-full bg-black/55 px-4 py-2 text-center text-sm font-medium"
        >
          {dica}
        </p>

        {/* Sem câmera ao vivo: explica e oferece as alternativas. */}
        {(estadoCamera === "negada" || estadoCamera === "indisponivel") && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-black p-8 pb-64 text-center">
            <Camera className="size-10 text-slate-400" aria-hidden />
            <h1 className="font-display text-lg font-bold">Câmera ao vivo indisponível</h1>
            <p className="text-sm text-slate-300">
              {estadoCamera === "negada"
                ? "O acesso à câmera foi negado. Libere a permissão nas configurações do navegador ou use as opções abaixo."
                : "Este navegador não liberou a câmera nesta página. No celular, ela só funciona com o app aberto por HTTPS."}
            </p>
            <div className="grid w-full max-w-xs gap-2.5">
              <button type="button" onClick={() => cameraSistema.current?.click()} className="flex min-h-12 items-center justify-center gap-2 rounded-xl bg-primaria font-semibold">
                <Camera className="size-5" aria-hidden /> Câmera do sistema
              </button>
              <button type="button" onClick={() => galeria.current?.click()} className="flex min-h-12 items-center justify-center gap-2 rounded-xl bg-white/10 font-semibold">
                <ImageIcon className="size-5" aria-hidden /> Galeria
              </button>
            </div>
          </div>
        )}

        {estadoCamera === "iniciando" && (
          <div className="absolute inset-0 flex items-center justify-center">
            <LoaderCircle className="size-8 animate-spin text-slate-300" aria-label="Abrindo a câmera" />
          </div>
        )}

        {processando && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-black/70" role="status">
            <LoaderCircle className="size-10 animate-spin" aria-hidden />
            <p className="text-sm font-medium">{processando}</p>
          </div>
        )}
      </div>

      {/* Controles por cima do vídeo, com um degradê para ficarem legíveis */}
      <div className="absolute inset-x-0 bottom-0 z-20 space-y-3 bg-gradient-to-t from-black/85 via-black/60 to-transparent px-3 pb-[max(1rem,env(safe-area-inset-bottom))] pt-14">
        {temFotoNoLote && (
          <div className="flex justify-center">
            <button
              type="button"
              onClick={concluir}
              disabled={Boolean(processando)}
              className="flex min-h-11 items-center gap-1.5 rounded-full bg-primaria px-5 text-sm font-semibold shadow-lg disabled:opacity-50"
            >
              <Check className="size-4" aria-hidden />
              Concluir ({capturadas.length})
            </button>
          </div>
        )}

        {/* Com fotos do lote esperando, trocar de modo as deixaria pela metade. */}
        <div className="flex justify-center">
          <div className="flex rounded-full bg-black/55 p-1" role="radiogroup" aria-label="Como fotografar">
            {OPCOES_CAPTURA.map(({ valor, rotulo }) => (
              <button
                key={valor}
                type="button"
                role="radio"
                aria-checked={opcaoAtual === valor}
                onClick={() => escolherOpcao(valor)}
                disabled={temFotoNoLote && valor !== "lote"}
                className={`min-h-10 whitespace-nowrap rounded-full px-4 text-[13px] font-semibold transition disabled:opacity-40 ${
                  opcaoAtual === valor ? "bg-white text-black" : "text-white"
                }`}
              >
                {rotulo}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-3 items-center">
          <button
            type="button"
            onClick={() => galeria.current?.click()}
            disabled={Boolean(processando)}
            aria-label="Escolher da galeria"
            className="flex size-12 items-center justify-center justify-self-start rounded-xl bg-black/50 disabled:opacity-50"
          >
            <ImageIcon className="size-5" aria-hidden />
          </button>

          <button
            ref={botaoFotografar}
            type="button"
            onClick={() => capturar()}
            disabled={!ativa || capturando || Boolean(processando)}
            aria-label={modo === "cartao" ? `Fotografar ${ladoAtual}` : "Fotografar"}
            className="relative flex size-20 items-center justify-center justify-self-center rounded-full disabled:opacity-60"
          >
            <svg viewBox="0 0 84 84" className="absolute inset-0 size-full" aria-hidden>
              <circle cx="42" cy="42" r="38" fill="none" stroke="white" strokeOpacity="0.35" strokeWidth="4" />
            </svg>
            <span className="size-[62px] rounded-full bg-white" />
          </button>

          {usaLote && capturadas.length > 0 ? (
            <button
              type="button"
              onClick={() => revisao.abrir(capturadas.length - 1)}
              disabled={Boolean(processando)}
              aria-label={`Revisar ${capturadas.length === 1 ? "a foto tirada" : `as ${capturadas.length} fotos tiradas`}`}
              className="relative size-12 justify-self-end overflow-hidden rounded-xl border-2 border-white"
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- miniatura local (blob) */}
              <img src={capturadas[capturadas.length - 1].original.url} alt="" className="size-full object-cover" />
              <span className="absolute -right-0.5 -top-0.5 flex size-6 items-center justify-center rounded-full bg-primaria text-xs font-bold">
                {capturadas.length}
              </span>
            </button>
          ) : modo === "cartao" && ladosCartao.length > 0 ? (
            <button
              type="button"
              onClick={() => finalizarCartao(ladosCartao)}
              disabled={Boolean(processando)}
              className="min-h-11 justify-self-end rounded-xl bg-black/50 px-3 text-xs font-semibold"
            >
              Sem verso
            </button>
          ) : (
            <span />
          )}
        </div>
      </div>

      {revisao.indice !== null && capturadas.length > 0 && (
        <VisualizadorPaginas
          imagens={fotosDaRevisao}
          nome="Foto"
          indice={Math.min(revisao.indice, capturadas.length - 1)}
          aoMudarIndice={revisao.mostrar}
          aoFechar={revisao.fechar}
          aoExcluir={excluirDaRevisao}
        />
      )}
    </main>
  );
}
