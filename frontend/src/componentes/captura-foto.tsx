"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type ChangeEvent } from "react";

import { useAviso } from "@/componentes/aviso";
import { useDigitalizacao } from "@/lib/estado-digitalizacao";
import { prepararFoto } from "@/lib/imagem";
import { novaPagina } from "@/lib/paginas";
import { detectarNaCaptura } from "@/lib/processamento";

/**
 * Entrada de arquivo da galeria: a foto escolhida vira uma página nova e vai para o
 * recorte. Para fotografar, o app usa o scanner ao vivo (/camera), que tem a câmera
 * nativa do celular como alternativa quando a câmera ao vivo não está disponível.
 */
export function useCapturaFoto() {
  const router = useRouter();
  const avisar = useAviso();
  const { adicionarPagina } = useDigitalizacao();
  const galeria = useRef<HTMLInputElement>(null);
  const [preparando, setPreparando] = useState(false);

  async function aoEscolher(evento: ChangeEvent<HTMLInputElement>) {
    const arquivo = evento.target.files?.[0];
    evento.target.value = ""; // permite escolher a mesma foto de novo
    if (!arquivo) return;
    setPreparando(true);
    try {
      const foto = await prepararFoto(arquivo);
      const pagina = novaPagina(foto.blob, foto.largura, foto.altura);
      adicionarPagina(pagina);
      detectarNaCaptura(pagina.id, foto.copiaDeteccao);
      router.push("/digitalizar/recorte");
    } catch (erro) {
      avisar(erro instanceof Error ? erro.message : "Não foi possível abrir a imagem.", "erro");
    } finally {
      setPreparando(false);
    }
  }

  const entradas = (
    <input
      ref={galeria}
      type="file"
      accept="image/*"
      className="hidden"
      onChange={aoEscolher}
      aria-hidden
      tabIndex={-1}
    />
  );

  return {
    entradas,
    preparando,
    abrirGaleria: () => galeria.current?.click(),
  };
}
