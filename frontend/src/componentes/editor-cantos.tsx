"use client";

import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import type { Cantos, Ponto } from "@/lib/tipos";

export const NOMES_CANTOS = ["superior esquerdo", "superior direito", "inferior direito", "inferior esquerdo"];
export const PASSO_TECLADO = 0.005;
const PASSO_TECLADO_RAPIDO = 0.03;
const ZOOM_LUPA = 2.5;
const TAMANHO_LUPA = 96;

interface Props {
  imagemUrl: string;
  largura: number;
  altura: number;
  cantos: Cantos;
  aoMudar: (cantos: Cantos) => void;
  /** Canto que as setas de ajuste fino movem (o último tocado ou focado). */
  cantoAtivo: number;
  aoSelecionarCanto: (indice: number) => void;
}

export const limitar = (valor: number) => Math.min(1, Math.max(0, valor));

export function EditorCantos({ imagemUrl, largura, altura, cantos, aoMudar, cantoAtivo, aoSelecionarCanto }: Props) {
  const palco = useRef<HTMLDivElement>(null);
  const [arrastando, setArrastando] = useState<number | null>(null);
  const [larguraPalco, setLarguraPalco] = useState(0);
  const proporcao = largura / altura;

  function moverPara(indice: number, ponto: Ponto) {
    const novos = cantos.map((c, i) => (i === indice ? { x: limitar(ponto.x), y: limitar(ponto.y) } : c));
    aoMudar(novos as Cantos);
  }

  function pontoDoEvento(evento: PointerEvent): Ponto | null {
    const area = palco.current?.getBoundingClientRect();
    if (!area) return null;
    return { x: (evento.clientX - area.left) / area.width, y: (evento.clientY - area.top) / area.height };
  }

  function aoPressionar(indice: number, evento: PointerEvent<HTMLButtonElement>) {
    evento.preventDefault();
    evento.currentTarget.setPointerCapture(evento.pointerId);
    evento.currentTarget.focus();
    setLarguraPalco(palco.current?.clientWidth ?? 0);
    setArrastando(indice);
    aoSelecionarCanto(indice);
  }

  function aoMover(indice: number, evento: PointerEvent<HTMLButtonElement>) {
    if (arrastando !== indice) return;
    const ponto = pontoDoEvento(evento);
    if (ponto) moverPara(indice, ponto);
  }

  function aoTeclar(indice: number, evento: KeyboardEvent<HTMLButtonElement>) {
    const passo = evento.shiftKey ? PASSO_TECLADO_RAPIDO : PASSO_TECLADO;
    const deslocamentos: Record<string, [number, number]> = {
      ArrowLeft: [-passo, 0],
      ArrowRight: [passo, 0],
      ArrowUp: [0, -passo],
      ArrowDown: [0, passo],
    };
    const deslocamento = deslocamentos[evento.key];
    if (!deslocamento) return;
    evento.preventDefault();
    const atual = cantos[indice];
    moverPara(indice, { x: atual.x + deslocamento[0], y: atual.y + deslocamento[1] });
  }

  const pontosSvg = cantos.map((c) => `${c.x * 100},${c.y * 100}`).join(" ");
  const cantoLupa = arrastando !== null ? cantos[arrastando] : null;

  return (
    // O palco ocupa o maior retângulo com a proporção da foto que cabe na área disponível.
    <div className="flex size-full items-center justify-center [container-type:size]">
      <div
        ref={palco}
        className="relative touch-none select-none"
        style={{ width: `min(100cqw, calc(100cqh * ${proporcao}))`, aspectRatio: `${largura} / ${altura}` }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- imagem local (blob) */}
        <img src={imagemUrl} alt="Foto capturada" draggable={false} className="size-full rounded-lg object-fill" />

        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 size-full">
          <defs>
            <mask id="mascara-recorte">
              <rect width="100" height="100" fill="white" />
              <polygon points={pontosSvg} fill="black" />
            </mask>
          </defs>
          <rect width="100" height="100" fill="rgb(2 6 23 / 0.55)" mask="url(#mascara-recorte)" />
          <polygon
            points={pontosSvg}
            fill="rgb(0 71 224 / 0.12)"
            stroke="var(--primaria-texto)"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
          />
        </svg>

        {cantos.map((canto, indice) => (
          <button
            key={NOMES_CANTOS[indice]}
            type="button"
            aria-label={`Canto ${NOMES_CANTOS[indice]}, ${Math.round(canto.x * 100)}% da largura e ${Math.round(canto.y * 100)}% da altura`}
            aria-pressed={cantoAtivo === indice}
            onFocus={() => aoSelecionarCanto(indice)}
            onPointerDown={(e) => aoPressionar(indice, e)}
            onPointerMove={(e) => aoMover(indice, e)}
            onPointerUp={() => setArrastando(null)}
            onPointerCancel={() => setArrastando(null)}
            onKeyDown={(e) => aoTeclar(indice, e)}
            className="group absolute flex size-12 -translate-x-1/2 -translate-y-1/2 cursor-grab touch-none items-center justify-center rounded-full focus-visible:outline-none active:cursor-grabbing"
            style={{ left: `${canto.x * 100}%`, top: `${canto.y * 100}%` }}
          >
            <span
              className={`size-5 rounded-full border-[3px] border-white bg-primaria shadow-md transition group-focus-visible:ring-4 group-focus-visible:ring-white/60 group-active:scale-125 ${
                cantoAtivo === indice ? "ring-4 ring-white/50" : ""
              }`}
            />
          </button>
        ))}

        {cantoLupa && (
          <div
            aria-hidden
            className="pointer-events-none absolute overflow-hidden rounded-full border-2 border-white shadow-xl"
            style={{
              width: TAMANHO_LUPA,
              height: TAMANHO_LUPA,
              // Fica acima do dedo; perto do topo, desce para baixo do canto.
              left: `calc(${cantoLupa.x * 100}% - ${TAMANHO_LUPA / 2}px)`,
              top:
                cantoLupa.y < 0.3
                  ? `calc(${cantoLupa.y * 100}% + 40px)`
                  : `calc(${cantoLupa.y * 100}% - ${TAMANHO_LUPA + 40}px)`,
              backgroundImage: `url(${imagemUrl})`,
              backgroundRepeat: "no-repeat",
              backgroundSize: `calc(var(--largura-palco) * ${ZOOM_LUPA}) auto`,
              backgroundPosition: `calc(${TAMANHO_LUPA / 2}px - var(--largura-palco) * ${ZOOM_LUPA} * ${cantoLupa.x}) calc(${TAMANHO_LUPA / 2}px - var(--largura-palco) * ${ZOOM_LUPA} / ${proporcao} * ${cantoLupa.y})`,
              ["--largura-palco" as string]: `${larguraPalco}px`,
            }}
          >
            <span className="absolute left-1/2 top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-primaria" />
          </div>
        )}
      </div>
    </div>
  );
}
