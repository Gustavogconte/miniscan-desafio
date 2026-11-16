"use client";

import { ArrowRight, Camera, FileText, ImageIcon, LoaderCircle, Plus, RotateCw, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAviso } from "@/componentes/aviso";
import { CabecalhoEtapa } from "@/componentes/cabecalho-etapa";
import { useCapturaFoto } from "@/componentes/captura-foto";
import { GavetaOcr } from "@/componentes/gaveta-ocr";
import { mensagemDeErro } from "@/lib/api";
import { useProcessamento } from "@/lib/processamento";
import { FILTROS, type Filtro } from "@/lib/tipos";
import { useGuardaDigitalizacao } from "@/lib/usar-guarda";

const DESCRICAO_FILTRO: Record<Filtro, string> = {
  original: "Cores da foto, só com a perspectiva corrigida",
  grayscale: "Tons de cinza com equalização de luz (CLAHE)",
  bw: "Limiarização adaptativa: remove sombras",
};

export default function TelaEditor() {
  const router = useRouter();
  const avisar = useAviso();
  const { paginaAtual: pagina, paginas, indiceAtual, atualizarPagina, removerPagina, selecionarPagina } =
    useGuardaDigitalizacao();
  const { garantirProcessada, executarOcr } = useProcessamento();
  const captura = useCapturaFoto();
  const [gavetaAberta, setGavetaAberta] = useState(false);
  const [menuPagina, setMenuPagina] = useState(false);
  const [falhaEm, setFalhaEm] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);

  const id = pagina?.id;
  const filtro = pagina?.filtro;
  const chave = id && filtro ? `${id}:${filtro}` : null;
  // Página recém-adicionada (ainda sem recorte confirmado) não deve ser processada aqui.
  const confirmada = pagina !== null && Object.keys(pagina.processadas).length > 0;
  const faltaImagem = confirmada && !pagina.processadas[pagina.filtro];
  const falhou = faltaImagem && falhaEm === chave;
  const carregandoFiltro = faltaImagem && !falhou;

  // Busca o filtro escolhido quando ele ainda não foi processado para esta página.
  useEffect(() => {
    if (!id || !filtro || !faltaImagem) return;
    let ativo = true;
    garantirProcessada(id, filtro).catch((erro) => {
      if (!ativo) return;
      setFalhaEm(`${id}:${filtro}`);
      avisar(mensagemDeErro(erro), "erro");
    });
    return () => {
      ativo = false;
    };
  }, [id, filtro, faltaImagem, tentativa, garantirProcessada, avisar]);

  if (!pagina) return null;

  // Enquanto o novo filtro carrega, mostra a versão anterior esmaecida.
  const imagem = pagina.processadas[pagina.filtro];
  const imagemExibida = imagem ?? Object.values(pagina.processadas)[0];
  const todasConfirmadas = paginas.every((p) => Object.keys(p.processadas).length > 0);
  const ocrPendente = paginas.some((p) => p.estadoOcr === "carregando" || p.estadoOcr === "pendente");

  function excluirPagina() {
    if (!window.confirm(`Excluir a página ${indiceAtual + 1}?`)) return;
    removerPagina(pagina!.id);
    avisar("Página excluída");
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      {captura.entradas}
      <CabecalhoEtapa
        titulo="Filtros e OCR"
        subtitulo={`Página ${indiceAtual + 1} de ${paginas.length}`}
        voltarPara="/digitalizar/recorte"
        rotuloVoltar="Ajustar o recorte desta página"
        acao={
          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuPagina((aberto) => !aberto)}
              aria-expanded={menuPagina}
              aria-haspopup="menu"
              disabled={captura.preparando}
              className="flex min-h-10 items-center gap-1 rounded-xl border border-borda bg-secundario px-3 text-xs font-semibold text-texto transition hover:opacity-90 disabled:opacity-60"
            >
              {captura.preparando ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
              ) : (
                <Plus className="size-4 text-primaria" aria-hidden />
              )}
              Página
            </button>
            {menuPagina && (
              <div
                role="menu"
                className="absolute right-0 top-12 z-20 w-44 overflow-hidden rounded-xl border border-borda bg-cartao shadow-lg"
              >
                {[
                  { rotulo: "Câmera", Icone: Camera, acao: captura.abrirCamera },
                  { rotulo: "Galeria", Icone: ImageIcon, acao: captura.abrirGaleria },
                ].map(({ rotulo, Icone, acao }) => (
                  <button
                    key={rotulo}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuPagina(false);
                      acao();
                    }}
                    className="flex min-h-12 w-full items-center gap-2.5 px-4 text-sm text-texto hover:bg-secundario"
                  >
                    <Icone className="size-4 text-texto-secundario" aria-hidden />
                    {rotulo}
                  </button>
                ))}
              </div>
            )}
          </div>
        }
      />

      <div className="relative flex min-h-0 flex-1 flex-col items-center justify-center gap-3 bg-fundo p-4">
        <div className="flex min-h-0 w-full flex-1 items-center justify-center">
          {imagemExibida ? (
            <div className="relative flex max-h-full max-w-full items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element -- imagem local (blob) */}
              <img
                src={imagemExibida.url}
                alt={`Página ${indiceAtual + 1} com filtro ${pagina.filtro}`}
                className={`max-h-full max-w-full rounded-lg border border-borda bg-white object-contain shadow-md transition-opacity ${
                  imagem ? "" : "opacity-40"
                }`}
              />
              {carregandoFiltro && (
                <LoaderCircle
                  className="absolute size-8 animate-spin text-primaria"
                  aria-label="Aplicando o filtro"
                />
              )}
              {falhou && (
                <button
                  type="button"
                  onClick={() => {
                    setFalhaEm(null);
                    setTentativa((t) => t + 1);
                  }}
                  className="absolute flex min-h-11 items-center gap-1.5 rounded-xl border border-borda bg-cartao px-4 text-xs font-semibold text-texto shadow-md"
                >
                  <RotateCw className="size-4 text-primaria" aria-hidden />
                  Tentar de novo
                </button>
              )}
            </div>
          ) : (
            <LoaderCircle className="size-8 animate-spin text-texto-suave" aria-label="Processando página" />
          )}
        </div>
        <p className="font-mono text-[11px] text-texto-secundario">{DESCRICAO_FILTRO[pagina.filtro]}</p>

        {paginas.length > 1 && (
          <div className="flex w-full items-center gap-2">
            <ol className="flex flex-1 gap-2 overflow-x-auto pb-1" aria-label="Páginas do documento">
              {paginas.map((p, indice) => {
                const miniatura = p.processadas[p.filtro] ?? p.original;
                return (
                  <li key={p.id} className="shrink-0">
                    <button
                      type="button"
                      onClick={() => selecionarPagina(indice)}
                      aria-label={`Página ${indice + 1}`}
                      aria-current={indice === indiceAtual ? "page" : undefined}
                      className={`relative block h-14 w-11 overflow-hidden rounded-md border-2 bg-white ${
                        indice === indiceAtual ? "border-primaria" : "border-borda"
                      }`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element -- imagem local (blob) */}
                      <img src={miniatura.url} alt="" className="size-full object-cover" />
                      <span className="absolute bottom-0 right-0 rounded-tl bg-slate-900/70 px-1 font-mono text-[9px] text-white">
                        {indice + 1}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
            <button
              type="button"
              onClick={excluirPagina}
              aria-label={`Excluir página ${indiceAtual + 1}`}
              className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-borda bg-cartao text-texto-secundario hover:text-perigo"
            >
              <Trash2 className="size-4" aria-hidden />
            </button>
          </div>
        )}
      </div>

      <div className="shrink-0 space-y-3 border-t border-borda bg-cartao p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div
          role="radiogroup"
          aria-label="Filtro da página"
          className="grid grid-cols-3 gap-1.5 rounded-xl border border-borda bg-secundario p-1.5"
        >
          {FILTROS.map(({ valor, rotulo }) => {
            const ativo = pagina.filtro === valor;
            return (
              <button
                key={valor}
                type="button"
                role="radio"
                aria-checked={ativo}
                onClick={() => atualizarPagina(pagina.id, { filtro: valor })}
                className={`min-h-11 rounded-lg text-xs transition ${
                  ativo
                    ? "bg-primaria font-semibold text-white shadow-sm"
                    : "font-medium text-texto-secundario hover:text-texto"
                }`}
              >
                {rotulo}
              </button>
            );
          })}
        </div>

        <div className="grid grid-cols-5 gap-2.5">
          <button
            type="button"
            onClick={() => setGavetaAberta(true)}
            className="col-span-2 flex min-h-12 items-center justify-center gap-1.5 rounded-xl border border-borda bg-secundario text-xs font-semibold text-texto transition hover:opacity-90"
          >
            {pagina.estadoOcr === "carregando" ? (
              <LoaderCircle className="size-4 animate-spin text-primaria" aria-hidden />
            ) : (
              <FileText className="size-4 text-primaria" aria-hidden />
            )}
            Texto OCR
          </button>
          <button
            type="button"
            onClick={() => router.push("/digitalizar/exportar")}
            disabled={!imagem || !todasConfirmadas}
            className="col-span-3 flex min-h-12 items-center justify-center gap-2 rounded-xl bg-primaria font-display text-sm font-bold text-white shadow-sm transition hover:bg-primaria-hover active:scale-[0.98] disabled:opacity-60"
          >
            Gerar PDF
            <ArrowRight className="size-4" aria-hidden />
          </button>
        </div>
        {ocrPendente && (
          <p className="text-center text-[11px] text-texto-secundario">O texto das páginas ainda está sendo lido…</p>
        )}
      </div>

      <GavetaOcr
        aberta={gavetaAberta}
        pagina={pagina}
        aoFechar={() => setGavetaAberta(false)}
        aoEditar={(texto) => atualizarPagina(pagina.id, { textoOcr: texto })}
        aoTentarDeNovo={() => executarOcr(pagina.id)}
      />
    </main>
  );
}
