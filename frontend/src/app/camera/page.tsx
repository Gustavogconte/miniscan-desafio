"use client";

import { Camera, Check, Copy, ExternalLink, Flashlight, FlashlightOff, ImageIcon, LoaderCircle, QrCode, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ChangeEvent, type MouseEvent } from "react";

import { useAviso } from "@/componentes/aviso";
import { lerQrcode, mensagemDeErro } from "@/lib/api";
import { useCameraAoVivo, useDetectorAoVivo, useLeitorQr } from "@/lib/camera";
import { useDigitalizacao } from "@/lib/estado-digitalizacao";
import { prepararFoto } from "@/lib/imagem";
import { filtroDoModo, novaPagina } from "@/lib/paginas";
import { useProcessamento, type LadoDoCartao } from "@/lib/processamento";
import { MODOS, type Cantos, type FormatoCartao, type Ponto } from "@/lib/tipos";

/** Proporção (largura/altura) dos formatos de cartão, para a moldura-guia. */
const PROPORCAO_CARTAO: Record<FormatoCartao, number> = { id: 85.6 / 54, passaporte: 125 / 88 };
const LADOS_DO_CARTAO: Record<FormatoCartao, number> = { id: 2, passaporte: 1 };

interface Tamanho {
  largura: number;
  altura: number;
}

/** Converte coordenadas entre o vídeo (0..1) e a tela, considerando o object-cover do <video>. */
function geometria(tela: Tamanho, video: Tamanho) {
  const escala = Math.max(tela.largura / video.largura, tela.altura / video.altura);
  const largura = video.largura * escala;
  const altura = video.altura * escala;
  const dx = (tela.largura - largura) / 2;
  const dy = (tela.altura - altura) / 2;
  return {
    paraTela: (p: Ponto) => ({ x: p.x * largura + dx, y: p.y * altura + dy }),
    paraVideo: (x: number, y: number): Ponto => ({
      x: Math.min(1, Math.max(0, (x - dx) / largura)),
      y: Math.min(1, Math.max(0, (y - dy) / altura)),
    }),
  };
}

function ehLink(texto: string): boolean {
  try {
    const url = new URL(texto);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export default function TelaCamera() {
  const router = useRouter();
  const avisar = useAviso();
  const { modo, formatoCartao, configurar, paginas, adicionarPagina } = useDigitalizacao();
  const { concluirLote, montarCartao } = useProcessamento();

  const area = useRef<HTMLDivElement>(null);
  const galeria = useRef<HTMLInputElement>(null);
  const cameraSistema = useRef<HTMLInputElement>(null);
  const ocupado = useRef(false);

  const {
    video,
    estado: estadoCamera,
    lanternaSuportada,
    lanternaLigada,
    alternarLanterna,
    capturarQuadro,
  } = useCameraAoVivo();
  const ativa = estadoCamera === "ativa";
  const [tamanhoTela, setTamanhoTela] = useState<Tamanho>({ largura: 1, altura: 1 });
  const [tamanhoVideo, setTamanhoVideo] = useState<Tamanho>({ largura: 1, altura: 1 });
  const [lote, setLote] = useState(false);
  const [automatico, setAutomatico] = useState(true);
  const [capturando, setCapturando] = useState(false);
  const [processando, setProcessando] = useState<string | null>(null);
  const [ladosCartao, setLadosCartao] = useState<LadoDoCartao[]>([]);
  const [copiado, setCopiado] = useState(false);

  const { paraTela, paraVideo } = geometria(tamanhoTela, tamanhoVideo);
  const capturadas = paginas.filter((p) => Object.keys(p.processadas).length === 0);
  const usaLote = lote && modo !== "cartao" && modo !== "qrcode";

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

  async function registrarFoto(blob: Blob, largura: number, altura: number, cantos: Cantos | null) {
    if (modo === "cartao") {
      const lados = [...ladosCartao, { blob, cantos }];
      if (lados.length < LADOS_DO_CARTAO[formatoCartao]) {
        setLadosCartao(lados);
        avisar("Frente capturada. Agora vire o documento.");
        return;
      }
      await finalizarCartao(lados);
      return;
    }
    adicionarPagina(novaPagina(blob, largura, altura, { cantos, filtro: filtroDoModo(modo) }));
    if (usaLote) avisar(`Página ${capturadas.length + 1} capturada`);
    else router.push("/digitalizar/recorte");
  }

  async function capturar(cantosVivos: Cantos | null) {
    if (ocupado.current || processando) return;
    ocupado.current = true;
    setCapturando(true);
    try {
      const quadro = await capturarQuadro();
      const cantos = modo === "cartao" ? (cantosVivos ?? cantosDaGuia()) : cantosVivos;
      await registrarFoto(quadro.blob, quadro.largura, quadro.altura, cantos);
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
    } finally {
      ocupado.current = false;
      setCapturando(false);
    }
  }

  async function finalizarCartao(lados: LadoDoCartao[]) {
    setProcessando("Montando o documento em tamanho real…");
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
      const foto = await prepararFoto(arquivo);
      if (modo === "qrcode") {
        const textos = await lerQrcode(foto.blob);
        if (textos.length > 0) qr.mostrar(textos);
        else avisar("Nenhum QR code encontrado nessa imagem.", "erro");
        return;
      }
      await registrarFoto(foto.blob, foto.largura, foto.altura, null);
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
    }
  }

  const deteccao = useDetectorAoVivo(video, ativa && modo !== "qrcode" && !processando, (cantos) => {
    if (automatico) void capturar(cantos);
  });
  const qr = useLeitorQr(video, ativa && modo === "qrcode");

  function confirmarSaida(evento: MouseEvent<HTMLAnchorElement>) {
    const total = capturadas.length + ladosCartao.length;
    if (total > 0 && !window.confirm(`Descartar ${total === 1 ? "a foto tirada" : `as ${total} fotos tiradas`}?`)) {
      evento.preventDefault();
    }
  }

  async function copiarQr(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      avisar("Não foi possível copiar.", "erro");
    }
  }

  // Com artigo: "a frente", "o verso".
  const ladoAtual = ladosCartao.length === 0 ? "a frente" : "o verso";
  const dica = (() => {
    if (processando) return processando;
    if (modo === "qrcode") return "Aponte para o QR code";
    if (modo === "cartao") return `Encaixe ${ladoAtual} do documento na moldura`;
    if (deteccao.falhou) return "Recorte ao vivo indisponível aqui: toque no botão para fotografar";
    if (!deteccao.pronto) return "Carregando o recorte ao vivo (3,5 MB)…";
    if (capturando) return "Capturando…";
    if (!deteccao.cantos) return MODOS.find((m) => m.valor === modo)?.dica ?? "Enquadre o documento";
    if (!automatico) return "Toque no botão para fotografar";
    return "Segure firme…";
  })();

  const poligono = deteccao.cantos?.map((c) => paraTela(c));
  const estavel = deteccao.estabilidade > 0.5;
  const raioAnel = 38;
  const perimetroAnel = 2 * Math.PI * raioAnel;

  return (
    <main className="relative flex min-h-0 flex-1 flex-col bg-black text-white">
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
          href="/"
          onClick={confirmarSaida}
          aria-label="Fechar a câmera"
          className="flex size-11 items-center justify-center rounded-full bg-black/40"
        >
          <X className="size-6" aria-hidden />
        </Link>
        {estadoCamera === "ativa" && tamanhoVideo.largura > 1 && (
          // Resolução real entregue pela câmera: ajuda a entender fotos com pouca nitidez.
          <span className="mr-auto rounded-full bg-black/40 px-2.5 py-1 font-mono text-[11px] text-white/80">
            {tamanhoVideo.largura}×{tamanhoVideo.altura}
          </span>
        )}
        <div className="flex items-center gap-2">
          {modo !== "qrcode" && (
            <button
              type="button"
              onClick={() => setAutomatico((a) => !a)}
              aria-pressed={automatico}
              className={`min-h-11 rounded-full px-4 text-xs font-semibold ${automatico ? "bg-white text-black" : "bg-black/40 text-white"}`}
            >
              Auto {automatico ? "ligado" : "desligado"}
            </button>
          )}
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

      {/* Vídeo e sobreposições */}
      <div ref={area} className="relative min-h-0 flex-1 overflow-hidden">
        <video
          ref={video}
          playsInline
          muted
          autoPlay
          onLoadedMetadata={(e) =>
            setTamanhoVideo({ largura: e.currentTarget.videoWidth, altura: e.currentTarget.videoHeight })
          }
          className="absolute inset-0 size-full object-cover"
        />

        {ativa && (
          <svg className="pointer-events-none absolute inset-0 size-full" aria-hidden>
            {modo === "cartao" && (
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
            )}
            {modo === "qrcode" && (
              <rect
                x={tamanhoTela.largura * 0.18}
                y={tamanhoTela.altura / 2 - tamanhoTela.largura * 0.32}
                width={tamanhoTela.largura * 0.64}
                height={tamanhoTela.largura * 0.64}
                rx={18}
                fill="none"
                stroke="white"
                strokeWidth={3}
              />
            )}
            {poligono && modo !== "qrcode" && (
              <polygon
                points={poligono.map((p) => `${p.x},${p.y}`).join(" ")}
                fill={estavel ? "rgb(34 197 94 / 0.22)" : "rgb(59 130 246 / 0.18)"}
                stroke={estavel ? "#4ade80" : "#60a5fa"}
                strokeWidth={3}
                strokeLinejoin="round"
              />
            )}
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
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-black p-8 text-center">
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

        {/* Resultado do QR code */}
        {modo === "qrcode" && qr.textos.length > 0 && (
          <div role="dialog" aria-label="QR code lido" className="absolute inset-x-3 bottom-3 z-20 space-y-3 rounded-2xl bg-cartao p-4 text-texto shadow-xl">
            <p className="flex items-center gap-2 text-xs font-semibold text-texto-secundario">
              <QrCode className="size-4" aria-hidden /> QR code lido
            </p>
            {qr.textos.map((texto) => (
              <div key={texto} className="space-y-2.5">
                <p className="break-all font-mono text-sm">{texto}</p>
                <div className="grid grid-cols-2 gap-2">
                  {ehLink(texto) ? (
                    <a href={texto} target="_blank" rel="noopener noreferrer" className="flex min-h-11 items-center justify-center gap-1.5 rounded-xl bg-primaria text-sm font-semibold text-white">
                      <ExternalLink className="size-4" aria-hidden /> Abrir link
                    </a>
                  ) : (
                    <span />
                  )}
                  <button type="button" onClick={() => copiarQr(texto)} className="flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-borda bg-secundario text-sm font-semibold">
                    {copiado ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
                    <span aria-live="polite">{copiado ? "Copiado" : "Copiar"}</span>
                  </button>
                </div>
              </div>
            ))}
            <button type="button" onClick={qr.lerOutro} className="min-h-11 w-full rounded-xl text-sm font-semibold text-primaria-texto">
              Ler outro QR code
            </button>
          </div>
        )}

        {processando && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-black/70" role="status">
            <LoaderCircle className="size-10 animate-spin" aria-hidden />
            <p className="text-sm font-medium">{processando}</p>
          </div>
        )}
      </div>

      {/* Controles inferiores */}
      <div className="z-20 shrink-0 space-y-3 bg-black px-3 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
        {modo === "cartao" && (
          <div className="flex justify-center gap-2" role="radiogroup" aria-label="Tipo de documento">
            {(
              [
                { valor: "id", rotulo: "RG, CNH ou cartão" },
                { valor: "passaporte", rotulo: "Passaporte" },
              ] as const
            ).map(({ valor, rotulo }) => (
              <button
                key={valor}
                type="button"
                role="radio"
                aria-checked={formatoCartao === valor}
                onClick={() => {
                  configurar({ formatoCartao: valor });
                  setLadosCartao([]);
                }}
                className={`min-h-9 rounded-full px-3.5 text-xs font-semibold ${formatoCartao === valor ? "bg-white text-black" : "bg-white/10 text-white"}`}
              >
                {rotulo}
              </button>
            ))}
          </div>
        )}
        {modo !== "cartao" && modo !== "qrcode" && (
          <div className="flex justify-center">
            <div className="flex rounded-full bg-white/10 p-1" role="radiogroup" aria-label="Quantidade de páginas">
              {[
                { valor: false, rotulo: "Único" },
                { valor: true, rotulo: "Lote" },
              ].map(({ valor, rotulo }) => (
                <button
                  key={rotulo}
                  type="button"
                  role="radio"
                  aria-checked={lote === valor}
                  onClick={() => setLote(valor)}
                  className={`min-h-9 rounded-full px-4 text-xs font-semibold ${lote === valor ? "bg-white text-black" : "text-white"}`}
                >
                  {rotulo}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Carrossel de modos */}
        <nav aria-label="Modo da câmera" className="-mx-3 overflow-x-auto px-3 [scrollbar-width:none]">
          <ul className="flex w-max gap-1.5">
            {MODOS.map(({ valor, rotulo }) => (
              <li key={valor}>
                <button
                  type="button"
                  aria-pressed={modo === valor}
                  onClick={() => {
                    configurar({ modo: valor });
                    setLadosCartao([]);
                  }}
                  className={`min-h-10 whitespace-nowrap rounded-full px-3.5 text-[13px] font-semibold transition ${
                    modo === valor ? "bg-primaria text-white" : "text-slate-300 hover:text-white"
                  }`}
                >
                  {rotulo}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <div className="grid grid-cols-3 items-center">
          <button
            type="button"
            onClick={() => galeria.current?.click()}
            disabled={Boolean(processando)}
            aria-label="Escolher da galeria"
            className="flex size-12 items-center justify-center justify-self-start rounded-xl bg-white/10 disabled:opacity-50"
          >
            <ImageIcon className="size-5" aria-hidden />
          </button>

          {modo !== "qrcode" ? (
            <button
              type="button"
              onClick={() => capturar(deteccao.cantos)}
              disabled={!ativa || capturando || Boolean(processando)}
              aria-label={modo === "cartao" ? `Fotografar ${ladoAtual}` : "Fotografar"}
              className="relative flex size-20 items-center justify-center justify-self-center rounded-full disabled:opacity-60"
            >
              <svg viewBox="0 0 84 84" className="absolute inset-0 size-full -rotate-90" aria-hidden>
                <circle cx="42" cy="42" r={raioAnel} fill="none" stroke="white" strokeOpacity="0.35" strokeWidth="4" />
                {automatico && (
                  <circle
                    cx="42"
                    cy="42"
                    r={raioAnel}
                    fill="none"
                    stroke="#4ade80"
                    strokeWidth="4"
                    strokeLinecap="round"
                    strokeDasharray={perimetroAnel}
                    strokeDashoffset={perimetroAnel * (1 - deteccao.estabilidade)}
                    className="transition-[stroke-dashoffset] duration-150"
                  />
                )}
              </svg>
              <span className="size-[62px] rounded-full bg-white" />
            </button>
          ) : (
            <span />
          )}

          {usaLote && capturadas.length > 0 ? (
            <button
              type="button"
              onClick={concluir}
              disabled={Boolean(processando)}
              aria-label={`Concluir com ${capturadas.length} ${capturadas.length === 1 ? "página" : "páginas"}`}
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
              className="min-h-11 justify-self-end rounded-xl bg-white/10 px-3 text-xs font-semibold"
            >
              Sem verso
            </button>
          ) : (
            <span />
          )}
        </div>
      </div>
    </main>
  );
}
