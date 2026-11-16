"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type ChangeEvent } from "react";

import { useAviso } from "@/componentes/aviso";
import { criarImagemLocal, useDigitalizacao } from "@/lib/estado-digitalizacao";
import { prepararFoto } from "@/lib/imagem";

function novoId(): string {
  // crypto.randomUUID só existe em contexto seguro (HTTPS); no teste pela rede local não.
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Entradas de arquivo para câmera e galeria. Usar <input capture> em vez de getUserMedia
 * abre a câmera nativa do celular, com foco e flash, e funciona igual no iOS e no Android.
 */
export function useCapturaFoto() {
  const router = useRouter();
  const avisar = useAviso();
  const { adicionarPagina } = useDigitalizacao();
  const camera = useRef<HTMLInputElement>(null);
  const galeria = useRef<HTMLInputElement>(null);
  const [preparando, setPreparando] = useState(false);

  async function aoEscolher(evento: ChangeEvent<HTMLInputElement>) {
    const arquivo = evento.target.files?.[0];
    evento.target.value = ""; // permite escolher a mesma foto de novo
    if (!arquivo) return;
    setPreparando(true);
    try {
      const foto = await prepararFoto(arquivo);
      adicionarPagina({
        id: novoId(),
        original: criarImagemLocal(foto.blob),
        largura: foto.largura,
        altura: foto.altura,
        cantos: null,
        cantosDetectados: null,
        cantosConfirmados: null,
        detectado: false,
        filtro: "bw",
        processadas: {},
        regioesGraficas: null,
        textoOcr: "",
        estadoOcr: "pendente",
      });
      router.push("/digitalizar/recorte");
    } catch (erro) {
      avisar(erro instanceof Error ? erro.message : "Não foi possível abrir a imagem.", "erro");
    } finally {
      setPreparando(false);
    }
  }

  const entradas = (
    <>
      <input
        ref={camera}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={aoEscolher}
        aria-hidden
        tabIndex={-1}
      />
      <input
        ref={galeria}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={aoEscolher}
        aria-hidden
        tabIndex={-1}
      />
    </>
  );

  return {
    entradas,
    preparando,
    abrirCamera: () => camera.current?.click(),
    abrirGaleria: () => galeria.current?.click(),
  };
}
