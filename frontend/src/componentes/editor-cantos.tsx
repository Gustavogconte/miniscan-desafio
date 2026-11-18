"use client";

import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import type { Cantos, Ponto } from "@/lib/tipos";

const NOMES_CANTOS = ["superior esquerdo", "superior direito", "inferior direito", "inferior esquerdo"];
const PASSO_TECLADO = 0.005;
const PASSO_TECLADO_RAPIDO = 0.03;
const ZOOM_LUPA = 3;
const TAMANHO_LUPA = 120;
const MARGEM_LUPA = 8;
/** Até quantos pixels do canto o toque ainda pega a bolinha: o dedo não precisa acertar em cima dela. */
const ALCANCE_TOQUE = 48;

interface Props {
  imagemUrl: string;
  largura: number;
  altura: number;
  cantos: Cantos;
  aoMudar: (cantos: Cantos) => void;
}

const limitar = (valor: number) => Math.min(1, Math.max(0, valor));

interface Arraste {
  indice: number;
  /** O dedo que está arrastando: outro dedo na tela não mexe neste canto. */
  ponteiro: number;
  /** Distância do dedo até o canto no toque: o canto acompanha o dedo sem pular para ele. */
  deslocamento: Ponto;
}

export function EditorCantos({ imagemUrl, largura, altura, cantos, aoMudar }: Props) {
  const palco = useRef<HTMLDivElement>(null);
  const botoes = useRef<(HTMLButtonElement | null)[]>([]);
  const [arraste, setArraste] = useState<Arraste | null>(null);
  const [tamanhoPalco, setTamanhoPalco] = useState({ largura: 0, altura: 0 });
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

  // O canto mais perto do toque, se estiver ao alcance do dedo; null se o toque foi longe de todos.
  function cantoMaisPerto(evento: PointerEvent): number | null {
    const area = palco.current?.getBoundingClientRect();
    if (!area) return null;
    let escolhido: number | null = null;
    let menorDistancia = ALCANCE_TOQUE;
    for (let i = 0; i < cantos.length; i++) {
      const dx = area.left + cantos[i].x * area.width - evento.clientX;
      const dy = area.top + cantos[i].y * area.height - evento.clientY;
      const distancia = Math.hypot(dx, dy);
      if (distancia <= menorDistancia) {
        menorDistancia = distancia;
        escolhido = i;
      }
    }
    return escolhido;
  }

  function aoPressionar(evento: PointerEvent<HTMLDivElement>) {
    const indice = cantoMaisPerto(evento);
    const ponto = pontoDoEvento(evento);
    if (indice === null || !ponto) return;
    evento.preventDefault();
    evento.currentTarget.setPointerCapture(evento.pointerId);
    botoes.current[indice]?.focus();
    setTamanhoPalco({ largura: palco.current?.clientWidth ?? 0, altura: palco.current?.clientHeight ?? 0 });
    const canto = cantos[indice];
    setArraste({ indice, ponteiro: evento.pointerId, deslocamento: { x: canto.x - ponto.x, y: canto.y - ponto.y } });
  }

  function aoMover(evento: PointerEvent<HTMLDivElement>) {
    if (arraste?.ponteiro !== evento.pointerId) return;
    const ponto = pontoDoEvento(evento);
    if (ponto) moverPara(arraste.indice, { x: ponto.x + arraste.deslocamento.x, y: ponto.y + arraste.deslocamento.y });
  }

  function aoSoltar(evento: PointerEvent<HTMLDivElement>) {
    if (arraste?.ponteiro === evento.pointerId) setArraste(null);
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
  const cantoLupa = arraste ? cantos[arraste.indice] : null;
  // A lupa fica presa no alto do palco, do lado oposto ao canto que está sendo arrastado:
  // nunca embaixo do dedo, que fica sobre o próprio canto.
  const lupaADireita = cantoLupa !== null && cantoLupa.x < 0.5;

  return (
    // A área toda, com a margem em volta da foto, recebe o toque: o dedo pega o canto mesmo fora da bolinha.
    <div
      className="size-full touch-none select-none p-5"
      onPointerDown={aoPressionar}
      onPointerMove={aoMover}
      onPointerUp={aoSoltar}
      onPointerCancel={aoSoltar}
    >
      {/* O palco ocupa o maior retângulo com a proporção da foto que cabe na área disponível. */}
      <div className="flex size-full items-center justify-center [container-type:size]">
        <div
          ref={palco}
          className="relative"
          style={{ width: `min(100cqw, calc(100cqh * ${proporcao}))`, aspectRatio: `${largura} / ${altura}` }}
        >
          {/* Sem receber toque: segurar o dedo na foto não abre o menu de salvar imagem do iPhone. */}
          {/* eslint-disable-next-line @next/next/no-img-element -- imagem local (blob) */}
          <img
            src={imagemUrl}
            alt="Foto capturada"
            draggable={false}
            className="pointer-events-none size-full rounded-lg object-fill"
          />

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
              ref={(elemento) => {
                botoes.current[indice] = elemento;
              }}
              type="button"
              aria-label={`Canto ${NOMES_CANTOS[indice]}, ${Math.round(canto.x * 100)}% da largura e ${Math.round(canto.y * 100)}% da altura`}
              onKeyDown={(e) => aoTeclar(indice, e)}
              className="group absolute flex size-12 -translate-x-1/2 -translate-y-1/2 cursor-grab items-center justify-center rounded-full focus-visible:outline-none"
              style={{ left: `${canto.x * 100}%`, top: `${canto.y * 100}%` }}
            >
              <span
                className={`size-5 rounded-full border-[3px] border-white bg-primaria shadow-md transition group-focus-visible:ring-4 group-focus-visible:ring-white/60 ${
                  arraste?.indice === indice ? "scale-125" : ""
                }`}
              />
            </button>
          ))}

          {cantoLupa && (
            <div
              aria-hidden
              className="pointer-events-none absolute z-10 overflow-hidden rounded-full border-2 border-white bg-black shadow-xl"
              style={{
                width: TAMANHO_LUPA,
                height: TAMANHO_LUPA,
                top: MARGEM_LUPA,
                ...(lupaADireita ? { right: MARGEM_LUPA } : { left: MARGEM_LUPA }),
              }}
            >
              {/* Só a foto ampliada, com o canto arrastado no centro: as linhas do recorte cobriam a borda do papel. */}
              <div
                className="absolute left-0 top-0 origin-top-left"
                style={{
                  width: tamanhoPalco.largura,
                  height: tamanhoPalco.altura,
                  transform: `translate(${TAMANHO_LUPA / 2 - cantoLupa.x * tamanhoPalco.largura * ZOOM_LUPA}px, ${
                    TAMANHO_LUPA / 2 - cantoLupa.y * tamanhoPalco.altura * ZOOM_LUPA
                  }px) scale(${ZOOM_LUPA})`,
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- imagem local (blob) */}
                <img src={imagemUrl} alt="" draggable={false} className="size-full object-fill" />
              </div>
              {/* Cruz de mira meio transparente: o centro é onde o canto vai ficar, e o papel aparece por trás das linhas. */}
              <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-white/70 shadow-[0_0_0_1px_rgb(0_0_0_/_0.3)]" />
              <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-white/70 shadow-[0_0_0_1px_rgb(0_0_0_/_0.3)]" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
