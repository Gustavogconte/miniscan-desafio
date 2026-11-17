"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

type Tema = "light" | "dark";
const CHAVE = "miniscan-tema";
/** Cor da barra do navegador/sistema em cada tema (igual ao fundo do app). */
const COR_BARRA: Record<Tema, string> = { light: "#f8fafc", dark: "#0f172a" };

/**
 * Script executado antes da pintura da página (no <head>) para aplicar o tema salvo
 * sem "piscar" o tema claro. Sem preferência salva, segue o sistema operacional.
 */
export const SCRIPT_TEMA_INICIAL = `(function(){try{var t=localStorage.getItem("${CHAVE}");if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.setAttribute("data-theme",t);var c=t==="dark"?"${COR_BARRA.dark}":"${COR_BARRA.light}";var f=function(){var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute("content",c);return!!m};if(!f())document.addEventListener("DOMContentLoaded",f)}catch(e){document.documentElement.setAttribute("data-theme","light")}})();`;

const ouvintes = new Set<() => void>();

function lerTema(): Tema {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function aplicarTema(tema: Tema) {
  document.documentElement.setAttribute("data-theme", tema);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", COR_BARRA[tema]);
  try {
    localStorage.setItem(CHAVE, tema);
  } catch {
    // navegação privada: o tema vale só nesta sessão
  }
  ouvintes.forEach((ouvinte) => ouvinte());
}

function assinar(ouvinte: () => void) {
  ouvintes.add(ouvinte);
  return () => ouvintes.delete(ouvinte);
}

function useTema() {
  const tema = useSyncExternalStore(assinar, lerTema, () => "light" as Tema);
  return { tema, alternar: () => aplicarTema(tema === "dark" ? "light" : "dark") };
}

export function BotaoTema() {
  const { tema, alternar } = useTema();
  const escuro = tema === "dark";
  return (
    <button
      type="button"
      onClick={alternar}
      aria-label={escuro ? "Usar tema claro" : "Usar tema escuro"}
      className="flex size-11 items-center justify-center rounded-xl border border-borda bg-cartao text-texto-secundario transition hover:bg-secundario hover:text-texto"
    >
      {escuro ? <Sun className="size-5" aria-hidden /> : <Moon className="size-5" aria-hidden />}
    </button>
  );
}
