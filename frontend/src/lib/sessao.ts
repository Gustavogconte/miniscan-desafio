"use client";

import { useSyncExternalStore } from "react";

/**
 * Sessão da conta, guardada no navegador.
 *
 * A API devolve um token em /entrar e /cadastrar, e o app o envia em toda chamada
 * (Authorization: Bearer). Fica no localStorage, e não num cookie, porque o app
 * (Vercel) e a API (VPS) têm domínios diferentes, e o Safari do iPhone bloqueia
 * cookie de outro site. No PWA instalado, o iPhone guarda à parte: é preciso entrar
 * uma vez no app instalado.
 */

export interface UsuarioSessao {
  id: string;
  nome: string;
  email: string;
}

export interface Sessao {
  token: string;
  expiraEm: string;
  usuario: UsuarioSessao;
}

const CHAVE = "miniscan-sessao";
const ouvintes = new Set<() => void>();

// Sem localStorage (navegação privada antiga), a sessão vale só enquanto a aba está aberta.
let memoria: string | null = null;
// useSyncExternalStore exige o mesmo objeto enquanto o texto guardado não muda.
let ultimoTexto: string | null = null;
let ultimaSessao: Sessao | null = null;

function lerTexto(): string | null {
  try {
    return localStorage.getItem(CHAVE);
  } catch {
    return memoria;
  }
}

function gravarTexto(texto: string | null) {
  memoria = texto;
  try {
    if (texto === null) localStorage.removeItem(CHAVE);
    else localStorage.setItem(CHAVE, texto);
  } catch {
    // fica só na memória
  }
  ouvintes.forEach((ouvinte) => ouvinte());
}

function interpretar(texto: string | null): Sessao | null {
  if (!texto) return null;
  try {
    const dados = JSON.parse(texto) as Partial<Sessao>;
    if (typeof dados.token !== "string" || typeof dados.expiraEm !== "string" || !dados.usuario) return null;
    // Vencida no relógio do aparelho: nem tenta usar.
    if (Date.parse(dados.expiraEm) <= Date.now()) return null;
    return dados as Sessao;
  } catch {
    return null;
  }
}

export function obterSessao(): Sessao | null {
  const texto = lerTexto();
  if (texto !== ultimoTexto) {
    ultimoTexto = texto;
    ultimaSessao = interpretar(texto);
  }
  return ultimaSessao;
}

export function guardarSessao(sessao: Sessao) {
  gravarTexto(JSON.stringify(sessao));
}

export function encerrarSessao() {
  gravarTexto(null);
}

function assinar(ouvinte: () => void) {
  ouvintes.add(ouvinte);
  // Entrar ou sair em outra aba vale para esta também.
  const aoMudarEmOutraAba = (evento: StorageEvent) => {
    if (evento.key === CHAVE || evento.key === null) ouvinte();
  };
  window.addEventListener("storage", aoMudarEmOutraAba);
  return () => {
    ouvintes.delete(ouvinte);
    window.removeEventListener("storage", aoMudarEmOutraAba);
  };
}

/** `undefined` enquanto o app ainda não leu o navegador (no servidor e antes da hidratação). */
export function useSessao(): Sessao | null | undefined {
  return useSyncExternalStore<Sessao | null | undefined>(assinar, obterSessao, () => undefined);
}
