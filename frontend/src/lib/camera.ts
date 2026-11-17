"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { lerQrcode } from "@/lib/api";
import type { Cantos } from "@/lib/tipos";

// ---------------------------------------------------------------------------
// Câmera
// ---------------------------------------------------------------------------

export type EstadoCamera = "iniciando" | "ativa" | "negada" | "indisponivel";

export interface QuadroCapturado {
  blob: Blob;
  largura: number;
  altura: number;
}

type CapacidadesComLanterna = MediaTrackCapabilities & { torch?: boolean };

/**
 * Abre a câmera traseira em tela cheia. `getUserMedia` exige contexto seguro:
 * funciona em https e em localhost; num IP da rede local via http fica "indisponivel"
 * e a tela oferece a câmera nativa do sistema como alternativa.
 */
export function useCameraAoVivo() {
  // A ref do <video> pertence a este hook: só ele liga e desliga o fluxo da câmera.
  const video = useRef<HTMLVideoElement>(null);
  const [estado, setEstado] = useState<EstadoCamera>("iniciando");
  const [lanternaSuportada, setLanternaSuportada] = useState(false);
  const [lanternaLigada, setLanternaLigada] = useState(false);
  const trilha = useRef<MediaStreamTrack | null>(null);

  useEffect(() => {
    let cancelado = false;
    let fluxo: MediaStream | null = null;

    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setEstado("indisponivel");
        return;
      }
      try {
        fluxo = await navigator.mediaDevices.getUserMedia({
          audio: false,
          // 4:3 é o formato nativo do sensor: mostra o campo de visão inteiro. Em 16:9
          // (ex.: 4K) muitos celulares recortam o sensor e a imagem parece com zoom.
          // Resolução alta evita página pequena e letras serrilhadas no P&B.
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 2560 },
            height: { ideal: 1920 },
            aspectRatio: { ideal: 4 / 3 },
          },
        });
        if (cancelado || !video.current) {
          fluxo.getTracks().forEach((t) => t.stop());
          return;
        }
        video.current.srcObject = fluxo;
        await video.current.play();
        trilha.current = fluxo.getVideoTracks()[0] ?? null;
        const capacidades = trilha.current?.getCapabilities?.() as CapacidadesComLanterna | undefined;
        setLanternaSuportada(Boolean(capacidades?.torch));
        // Foco contínuo onde existir (Chrome no Android); o Safari já faz sozinho.
        const modosFoco = (capacidades as { focusMode?: string[] } | undefined)?.focusMode;
        if (modosFoco?.includes("continuous")) {
          trilha.current
            ?.applyConstraints({ advanced: [{ focusMode: "continuous" } as MediaTrackConstraintSet] })
            .catch(() => {});
        }
        setEstado("ativa");
      } catch (erro) {
        if (cancelado) return;
        const nome = erro instanceof DOMException ? erro.name : "";
        setEstado(nome === "NotAllowedError" || nome === "SecurityError" ? "negada" : "indisponivel");
      }
    })();

    return () => {
      cancelado = true;
      fluxo?.getTracks().forEach((t) => t.stop());
      trilha.current = null;
    };
  }, []);

  const alternarLanterna = useCallback(async () => {
    const atual = trilha.current;
    if (!atual) return;
    const ligar = !lanternaLigada;
    try {
      await atual.applyConstraints({ advanced: [{ torch: ligar } as MediaTrackConstraintSet] });
      setLanternaLigada(ligar);
    } catch {
      setLanternaSuportada(false);
    }
  }, [lanternaLigada]);

  /** Copia o quadro atual do vídeo na resolução cheia da câmera, em JPEG. */
  const capturarQuadro = useCallback(async (): Promise<QuadroCapturado> => {
    const v = video.current;
    if (!v || !v.videoWidth) throw new Error("A câmera ainda não está pronta.");
    const tela = document.createElement("canvas");
    tela.width = v.videoWidth;
    tela.height = v.videoHeight;
    tela.getContext("2d")?.drawImage(v, 0, 0, tela.width, tela.height);
    const blob = await new Promise<Blob | null>((resolver) => tela.toBlob(resolver, "image/jpeg", 0.92));
    if (!blob) throw new Error("Não foi possível capturar a foto.");
    return { blob, largura: tela.width, altura: tela.height };
  }, []);

  return { video, estado, lanternaSuportada, lanternaLigada, alternarLanterna, capturarQuadro };
}

// ---------------------------------------------------------------------------
// Detecção da folha ao vivo (OpenCV.js num Web Worker)
// ---------------------------------------------------------------------------

const LADO_ANALISE = 360; // quadro reduzido enviado ao worker: rápido e suficiente para achar a folha
const INTERVALO_MINIMO_MS = 70; // no máximo ~14 análises por segundo
const LIMIAR_MOVIMENTO = 0.012; // deslocamento máximo de um canto (fração da imagem) para contar como parado
const QUADROS_ESTAVEIS = 8; // ~0,7 s parado = pronto para a captura automática
const QUADROS_PERDIDOS = 4; // tolera falhas curtas sem apagar o contorno
const SUAVIZACAO = 0.5;
// Depois de uma captura automática, só captura de novo quando a folha some ou se
// move bastante (outra página no lugar): evita fotografar a mesma página duas vezes.
const MOVIMENTO_NOVA_PAGINA = 0.06;

export interface DeteccaoAoVivo {
  /** Cantos suavizados da folha no quadro atual (normalizados 0..1), ou null. */
  cantos: Cantos | null;
  /** 0..1: quanto falta para a folha ser considerada parada. */
  estabilidade: number;
  /** O OpenCV.js terminou de carregar. */
  pronto: boolean;
  /** O detector não pôde ser carregado neste aparelho (sobra a foto manual). */
  falhou: boolean;
}

interface RespostaWorker {
  tipo: "pronto" | "cantos";
  resultado?: { cantos: Cantos; area: number } | null;
}

export function useDetectorAoVivo(
  video: RefObject<HTMLVideoElement | null>,
  ativo: boolean,
  aoEstabilizar?: (cantos: Cantos) => void,
): DeteccaoAoVivo {
  const retorno = useRef(aoEstabilizar);
  useEffect(() => {
    retorno.current = aoEstabilizar;
  }, [aoEstabilizar]);
  const [deteccao, setDeteccao] = useState<DeteccaoAoVivo>({
    cantos: null,
    estabilidade: 0,
    pronto: false,
    falhou: false,
  });

  useEffect(() => {
    if (!ativo) return;
    const worker = new Worker("/workers/detector-documento.js");
    const tela = document.createElement("canvas");
    const contexto = tela.getContext("2d", { willReadFrequently: true });
    let parar = false;
    let ocupado = false;
    let temporizador: ReturnType<typeof setTimeout> | undefined;
    let ultimoEnvio = 0;
    let suavizados: Cantos | null = null;
    let anteriores: Cantos | null = null;
    let estaveis = 0;
    let perdidos = 0;
    let travado = false;
    let cantosDaCaptura: Cantos | null = null;

    function agendar(espera = Math.max(0, INTERVALO_MINIMO_MS - (performance.now() - ultimoEnvio))) {
      if (!parar) temporizador = setTimeout(enviar, espera);
    }

    function enviar() {
      const v = video.current;
      if (parar || ocupado || !contexto) return;
      if (!v || v.readyState < 2 || !v.videoWidth) return agendar(150);
      const escala = LADO_ANALISE / Math.max(v.videoWidth, v.videoHeight);
      tela.width = Math.round(v.videoWidth * escala);
      tela.height = Math.round(v.videoHeight * escala);
      contexto.drawImage(v, 0, 0, tela.width, tela.height);
      const quadro = contexto.getImageData(0, 0, tela.width, tela.height);
      ocupado = true;
      ultimoEnvio = performance.now();
      worker.postMessage({ largura: tela.width, altura: tela.height, pixels: quadro.data.buffer }, [
        quadro.data.buffer,
      ]);
    }

    // Falha ao baixar ou iniciar o OpenCV.js (rede, memória, navegador antigo).
    worker.onerror = (evento) => {
      evento.preventDefault();
      parar = true;
      setDeteccao({ cantos: null, estabilidade: 0, pronto: false, falhou: true });
    };

    worker.onmessage = (evento: MessageEvent<RespostaWorker>) => {
      if (evento.data.tipo === "pronto") {
        setDeteccao((atual) => ({ ...atual, pronto: true }));
        return agendar(0);
      }
      ocupado = false;
      const novos = evento.data.resultado?.cantos ?? null;
      if (novos) {
        perdidos = 0;
        const movimento = anteriores
          ? Math.max(...novos.map((c, i) => Math.hypot(c.x - anteriores![i].x, c.y - anteriores![i].y)))
          : 1;
        estaveis = movimento < LIMIAR_MOVIMENTO ? estaveis + 1 : 0;
        anteriores = novos;
        if (travado && cantosDaCaptura) {
          const deslocamento = Math.max(
            ...novos.map((c, i) => Math.hypot(c.x - cantosDaCaptura![i].x, c.y - cantosDaCaptura![i].y)),
          );
          if (deslocamento > MOVIMENTO_NOVA_PAGINA) travado = false;
        }
        suavizados = suavizados
          ? (suavizados.map((c, i) => ({
              x: c.x * SUAVIZACAO + novos[i].x * (1 - SUAVIZACAO),
              y: c.y * SUAVIZACAO + novos[i].y * (1 - SUAVIZACAO),
            })) as Cantos)
          : novos;
      } else {
        perdidos += 1;
        estaveis = 0;
        if (perdidos >= QUADROS_PERDIDOS) {
          suavizados = null;
          anteriores = null;
          travado = false;
        }
      }
      if (!travado && suavizados && estaveis >= QUADROS_ESTAVEIS && retorno.current) {
        travado = true;
        cantosDaCaptura = suavizados;
        retorno.current(suavizados);
      }
      setDeteccao({
        cantos: suavizados,
        estabilidade: travado ? 0 : Math.min(1, estaveis / QUADROS_ESTAVEIS),
        pronto: true,
        falhou: false,
      });
      agendar();
    };

    return () => {
      parar = true;
      clearTimeout(temporizador);
      worker.terminate();
    };
  }, [ativo, video]);

  return ativo ? deteccao : { cantos: null, estabilidade: 0, pronto: deteccao.pronto, falhou: deteccao.falhou };
}

// ---------------------------------------------------------------------------
// Leitura de QR code ao vivo
// ---------------------------------------------------------------------------

interface DetectorDeCodigos {
  detect(fonte: CanvasImageSource): Promise<{ rawValue: string }[]>;
}
type ConstrutorDetector = new (opcoes: { formats: string[] }) => DetectorDeCodigos;

const INTERVALO_QR_NATIVO_MS = 300;
const INTERVALO_QR_SERVIDOR_MS = 900;

/**
 * Lê QR codes do vídeo: usa o BarcodeDetector do navegador quando existe (Chrome no
 * Android) e, nos outros (Safari, Firefox), manda um quadro ao backend periodicamente.
 */
export function useLeitorQr(video: RefObject<HTMLVideoElement | null>, ativo: boolean) {
  const [textos, setTextos] = useState<string[]>([]);

  useEffect(() => {
    if (!ativo) return;
    let parar = false;
    let temporizador: ReturnType<typeof setTimeout> | undefined;
    const Construtor = (globalThis as { BarcodeDetector?: ConstrutorDetector }).BarcodeDetector;
    const nativo = Construtor ? new Construtor({ formats: ["qr_code"] }) : null;
    const tela = document.createElement("canvas");

    async function ler() {
      const v = video.current;
      if (parar) return;
      if (v && v.readyState >= 2 && v.videoWidth) {
        try {
          let encontrados: string[] = [];
          if (nativo) {
            encontrados = (await nativo.detect(v)).map((c) => c.rawValue);
          } else {
            const escala = Math.min(1, 1024 / Math.max(v.videoWidth, v.videoHeight));
            tela.width = Math.round(v.videoWidth * escala);
            tela.height = Math.round(v.videoHeight * escala);
            tela.getContext("2d")?.drawImage(v, 0, 0, tela.width, tela.height);
            const blob = await new Promise<Blob | null>((r) => tela.toBlob(r, "image/jpeg", 0.85));
            if (blob) encontrados = await lerQrcode(blob);
          }
          if (!parar && encontrados.length > 0) {
            setTextos(encontrados);
            return; // pausa até o usuário pedir outra leitura
          }
        } catch {
          // quadro ruim ou rede instável: tenta no próximo
        }
      }
      temporizador = setTimeout(ler, nativo ? INTERVALO_QR_NATIVO_MS : INTERVALO_QR_SERVIDOR_MS);
    }

    if (textos.length === 0) void ler();
    return () => {
      parar = true;
      clearTimeout(temporizador);
    };
  }, [ativo, video, textos.length]);

  /** `mostrar`: exibe QR codes lidos por outro caminho (ex.: foto da galeria). */
  return { textos, lerOutro: () => setTextos([]), mostrar: (lidos: string[]) => setTextos(lidos) };
}
