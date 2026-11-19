"use client";

import { Camera, ScanLine, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import Lightbox from "yet-another-react-lightbox";
import Zoom from "yet-another-react-lightbox/plugins/zoom";
import "yet-another-react-lightbox/styles.css";

import { fonteDaImagem, rotuloDaPagina, type ImagemVisualizada } from "@/lib/visualizador";

const ROTULOS = {
  Lightbox: "Visualizador de páginas",
  "Photo gallery": "Páginas do documento",
  Carousel: "Páginas",
  Slide: "página",
  "{index} of {total}": "{index} de {total}",
  Previous: "Página anterior",
  Next: "Próxima página",
  Close: "Fechar",
  "Zoom in": "Ampliar",
  "Zoom out": "Reduzir",
};

export interface PropsVisualizador {
  imagens: ImagemVisualizada[];
  indice: number;
  aoMudarIndice: (indice: number) => void;
  aoFechar: () => void;
  /** Mostra o botão de excluir na barra de cima (revisão das fotos do lote). */
  aoExcluir?: (indice: number) => void;
  /** Como cada imagem é chamada no rótulo: "Página" (padrão) ou "Foto". */
  nome?: string;
}

/**
 * Página em tela cheia: pinça e toque duplo ampliam, arrastar move a parte ampliada,
 * deslizar para os lados troca de página e puxar para baixo fecha. No computador,
 * a roda do mouse amplia e as setas do teclado trocam de página.
 *
 * Fica num arquivo à parte (visualizador-sob-demanda.tsx): só as telas que usam o
 * visualizador baixam a biblioteca, sem pesar na abertura do app.
 */
export default function VisualizadorPaginas({
  imagens,
  indice,
  aoMudarIndice,
  aoFechar,
  aoExcluir,
  nome,
}: PropsVisualizador) {
  const [verOriginal, setVerOriginal] = useState(false);
  const atual = imagens[indice];
  const temOriginal = Boolean(atual?.srcOriginal);
  const mostrandoOriginal = verOriginal && temOriginal;
  const umaSo = imagens.length <= 1;

  const rotulo = (i: number, imagem: ImagemVisualizada) =>
    rotuloDaPagina(i, imagens.length, verOriginal && imagem.srcOriginal ? "foto original" : imagem.detalhe, nome);
  // Mesma lista enquanto nada muda: a biblioteca reprocessa os slides a cada lista nova,
  // e a tela de trás (a câmera) renderiza várias vezes por segundo.
  const slides = useMemo(
    () =>
      imagens.map((imagem, i) => ({
        src: fonteDaImagem(imagem, verOriginal),
        alt: rotuloDaPagina(i, imagens.length, verOriginal && imagem.srcOriginal ? "foto original" : imagem.detalhe, nome),
      })),
    [imagens, verOriginal, nome],
  );

  return (
    <Lightbox
      open
      close={aoFechar}
      index={indice}
      slides={slides}
      plugins={[Zoom]}
      labels={ROTULOS}
      on={{ view: ({ index }) => aoMudarIndice(index) }}
      carousel={{ finite: true, padding: 12, preload: 1 }}
      controller={{ closeOnPullDown: true, closeOnBackdropClick: false }}
      // Até 2 pixels da imagem por pixel da tela: dá para conferir letra pequena.
      zoom={{ maxZoomPixelRatio: 2, scrollToZoom: true, doubleClickMaxStops: 2 }}
      animation={{ fade: 200, swipe: 250 }}
      styles={{ container: { backgroundColor: "rgb(2 6 23)" } }}
      toolbar={{
        buttons: [
          aoExcluir ? (
            <button
              key="excluir"
              type="button"
              className="yarl__button"
              aria-label={`Excluir a foto ${indice + 1}`}
              title="Excluir esta foto"
              onClick={() => aoExcluir(indice)}
            >
              <Trash2 className="yarl__icon" aria-hidden />
            </button>
          ) : null,
          "zoom",
          "close",
        ],
      }}
      render={{
        buttonPrev: umaSo ? () => null : undefined,
        buttonNext: umaSo ? () => null : undefined,
        // Embaixo, longe da barra de botões de cima. O contêiner deixa passar os gestos.
        // A biblioteca já anuncia "N de total" ao leitor de tela: o rótulo é só visual.
        controls: () => (
          <div className="pointer-events-none absolute inset-x-0 bottom-[max(1rem,env(safe-area-inset-bottom))] flex flex-col items-center gap-2 pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))]">
            <p className="max-w-full truncate rounded-full bg-slate-950/80 px-3 py-1.5 font-mono text-xs font-semibold text-white ring-1 ring-white/15">
              {atual && rotulo(indice, atual)}
            </p>
            {temOriginal && (
              <button
                type="button"
                onClick={() => setVerOriginal((valor) => !valor)}
                className="pointer-events-auto flex min-h-11 items-center gap-2 whitespace-nowrap rounded-full bg-slate-950/85 px-4 text-sm font-semibold text-white shadow-lg ring-1 ring-white/20"
              >
                {mostrandoOriginal ? (
                  <ScanLine className="size-4" aria-hidden />
                ) : (
                  <Camera className="size-4" aria-hidden />
                )}
                {mostrandoOriginal ? "Ver página digitalizada" : "Ver foto original"}
              </button>
            )}
          </div>
        ),
      }}
    />
  );
}
