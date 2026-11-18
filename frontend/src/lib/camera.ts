"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type EstadoCamera = "iniciando" | "ativa" | "negada" | "indisponivel";

export interface QuadroCapturado {
  blob: Blob;
  largura: number;
  altura: number;
}

type CapacidadesComLanterna = MediaTrackCapabilities & { torch?: boolean };

// 4:3 é o formato nativo do sensor: mostra o campo de visão inteiro. Em 16:9 (ex.: 4K)
// muitos celulares recortam o sensor e a imagem parece com zoom. Resolução alta evita
// página pequena e letras serrilhadas no P&B.
const QUALIDADE: MediaTrackConstraints = {
  width: { ideal: 2560 },
  height: { ideal: 1920 },
  aspectRatio: { ideal: 4 / 3 },
};

// Câmeras "virtuais" (Dupla/Tripla no iPhone) trocam de lente sozinhas ao chegar perto
// da folha e parecem dar zoom; a teleobjetiva e a ultra-angular também não servem.
const LENTES_EVITADAS = /ultra|tele|dual|dupla|tripl|macro|wide angle|grande-angular/i;
const TRASEIRA = /back|rear|traseira|environment/i;

/**
 * Procura a câmera traseira principal (a "1x" do app Câmera) pelo nome. Os nomes só
 * aparecem depois que a permissão foi concedida, por isso roda após o primeiro acesso.
 */
async function idDaCameraPrincipal(): Promise<string | null> {
  const dispositivos = await navigator.mediaDevices.enumerateDevices();
  const traseiras = dispositivos.filter((d) => d.kind === "videoinput" && TRASEIRA.test(d.label));
  const principal = traseiras.find((d) => !LENTES_EVITADAS.test(d.label));
  return principal?.deviceId || null;
}

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
  /** Nome da câmera em uso (ex.: "Câmera Traseira"), para diagnosticar zoom. */
  const [nomeCamera, setNomeCamera] = useState("");
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
          video: { facingMode: { ideal: "environment" }, ...QUALIDADE },
        });
        // Se o navegador escolheu uma câmera virtual ou outra lente, troca pela principal.
        const principal = await idDaCameraPrincipal().catch(() => null);
        const atual = fluxo.getVideoTracks()[0]?.getSettings().deviceId;
        if (principal && principal !== atual && !cancelado) {
          fluxo.getTracks().forEach((t) => t.stop());
          fluxo = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: { deviceId: { exact: principal }, ...QUALIDADE },
          });
        }
        if (cancelado || !video.current) {
          fluxo.getTracks().forEach((t) => t.stop());
          return;
        }
        video.current.srcObject = fluxo;
        await video.current.play();
        trilha.current = fluxo.getVideoTracks()[0] ?? null;
        setNomeCamera(trilha.current?.label ?? "");
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

  return { video, estado, nomeCamera, lanternaSuportada, lanternaLigada, alternarLanterna, capturarQuadro };
}
