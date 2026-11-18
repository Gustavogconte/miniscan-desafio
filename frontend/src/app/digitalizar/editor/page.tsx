"use client";

import {
  ArrowRight,
  Camera,
  Crop,
  Expand,
  FileText,
  ImageIcon,
  LayoutGrid,
  LoaderCircle,
  Plus,
  RotateCw,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type MouseEvent } from "react";

import { useAviso } from "@/componentes/aviso";
import { CabecalhoEtapa } from "@/componentes/cabecalho-etapa";
import { useCapturaFoto } from "@/componentes/captura-foto";
import { GavetaOcr } from "@/componentes/gaveta-ocr";
import { GradePaginas } from "@/componentes/grade-paginas";
import { adiantarVisualizador, VisualizadorPaginas } from "@/componentes/visualizador-sob-demanda";
import { mensagemDeErro } from "@/lib/api";
import { useDigitalizacao } from "@/lib/estado-digitalizacao";
import { useProcessamento } from "@/lib/processamento";
import { FILTROS, ROTULO_FILTRO, type Filtro, type Pagina } from "@/lib/tipos";
import { useGuardaDigitalizacao } from "@/lib/usar-guarda";
import { useVisualizador } from "@/lib/usar-visualizador";
import type { ImagemVisualizada } from "@/lib/visualizador";

const DESCRICAO_FILTRO: Record<Filtro, string> = {
  original: "Cores da foto, só com a perspectiva corrigida",
  grayscale: "Tons de cinza com equalização de luz (CLAHE)",
  bw: "Preto e branco de scanner: nivela a luz e remove sombras",
};

const ID_MENU_PAGINA = "menu-nova-pagina";

function foiRecortada(pagina: Pagina): boolean {
  return Object.keys(pagina.processadas).length > 0;
}

/**
 * Versão da página mostrada nas miniaturas, na grade e no visualizador: a do filtro
 * escolhido ou, enquanto ela processa, outra já pronta. `filtro` é null na foto sem recorte.
 */
function versaoDaPagina(pagina: Pagina): { url: string; filtro: Filtro | null } {
  const escolhida = pagina.processadas[pagina.filtro];
  if (escolhida) return { url: escolhida.url, filtro: pagina.filtro };
  const outra = (Object.keys(pagina.processadas) as Filtro[])[0];
  if (outra) return { url: pagina.processadas[outra]!.url, filtro: outra };
  return { url: pagina.original.url, filtro: null };
}

function detalheDaVersao(filtro: Filtro | null): string {
  return filtro ? ROTULO_FILTRO[filtro] : "sem recorte";
}

export default function TelaEditor() {
  // Documento novo, tela nova: grade, gaveta de texto e visualizador recomeçam do zero.
  const { sessao } = useDigitalizacao();
  return <ConteudoEditor key={sessao} />;
}

function ConteudoEditor() {
  const router = useRouter();
  const avisar = useAviso();
  const { paginaAtual: pagina, paginas, indiceAtual, atualizarPagina, removerPagina, selecionarPagina } =
    useGuardaDigitalizacao();
  const { garantirProcessada, executarOcr } = useProcessamento();
  const captura = useCapturaFoto();
  const [gavetaAberta, setGavetaAberta] = useState(false);
  const [falhaEm, setFalhaEm] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const [verTodas, setVerTodas] = useState(false);
  const visualizador = useVisualizador();

  const id = pagina?.id;
  const filtro = pagina?.filtro;
  const chave = id && filtro ? `${id}:${filtro}` : null;
  // Página recém-adicionada (ainda sem recorte confirmado) não deve ser processada aqui.
  const confirmada = pagina !== null && foiRecortada(pagina);
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

  // Adianta o download do visualizador, para o primeiro toque em "Ampliar" abrir na hora.
  useEffect(() => {
    adiantarVisualizador();
  }, []);

  const imagensDoVisualizador = useMemo<ImagemVisualizada[]>(
    () =>
      paginas.map((p) => {
        const versao = versaoDaPagina(p);
        return {
          id: p.id,
          src: versao.url,
          srcOriginal: foiRecortada(p) ? p.original.url : undefined,
          detalhe: detalheDaVersao(versao.filtro),
        };
      }),
    [paginas],
  );

  if (!pagina) return null;

  // Enquanto o novo filtro carrega, mostra a versão anterior esmaecida.
  const imagem = pagina.processadas[pagina.filtro];
  const imagemExibida = imagem ?? Object.values(pagina.processadas)[0];
  // Página que voltou da câmera sem recorte confirmado (ex.: gesto de voltar do sistema).
  const indicePendente = paginas.findIndex((p) => !foiRecortada(p));
  const todasConfirmadas = indicePendente === -1;
  const rotuloFiltro = FILTROS.find((f) => f.valor === pagina.filtro)?.rotulo ?? pagina.filtro;
  const gradeVisivel = verTodas && paginas.length > 1;

  function escolherNaGrade(indice: number) {
    selecionarPagina(indice);
    setVerTodas(false);
  }

  function confirmarDescarte(evento: MouseEvent<HTMLAnchorElement>) {
    const total = paginas.length;
    const mensagem = `Descartar ${total === 1 ? "a página digitalizada" : `as ${total} páginas digitalizadas`}?`;
    if (!window.confirm(mensagem)) evento.preventDefault();
  }

  function excluirPagina() {
    if (!window.confirm(`Excluir a página ${indiceAtual + 1}?`)) return;
    // Com uma página só, a grade some; não deve voltar sozinha quando entrar outra.
    if (paginas.length <= 2) setVerTodas(false);
    removerPagina(pagina!.id);
    avisar("Página excluída");
  }

  function adicionarPor(origem: "camera" | "galeria") {
    document.getElementById(ID_MENU_PAGINA)?.hidePopover();
    // Câmera = o scanner do app (recorte ao vivo e captura automática), que acrescenta
    // a página a este documento e volta para cá.
    if (origem === "camera") router.push("/camera");
    else captura.abrirGaleria();
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      {captura.entradas}
      <CabecalhoEtapa
        titulo="Filtros e OCR"
        subtitulo={`Página ${indiceAtual + 1} de ${paginas.length}`}
        voltarPara="/"
        aoVoltar={confirmarDescarte}
        rotuloVoltar="Descartar a digitalização e voltar ao início"
      />

      <div className="relative flex min-h-0 flex-1 flex-col items-center justify-center gap-2 bg-fundo p-3">
        <div className="flex min-h-0 w-full flex-1 items-center justify-center [container-type:size]">
          {gradeVisivel ? (
            <div className="size-full overflow-y-auto px-1 py-1">
              <GradePaginas
                itens={imagensDoVisualizador.map((imagem, indice) => ({
                  id: imagem.id,
                  src: imagem.src,
                  detalhe: imagem.detalhe ?? "",
                  pendente: !foiRecortada(paginas[indice]),
                }))}
                aoEscolher={escolherNaGrade}
                acao="Editar"
                atual={indiceAtual}
              />
            </div>
          ) : imagemExibida ? (
            <div className="relative flex max-h-full max-w-full items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element -- imagem local (blob) */}
              <img
                src={imagemExibida.url}
                alt={`Página ${indiceAtual + 1} com filtro ${rotuloFiltro}`}
                className={`max-h-[100cqh] max-w-[100cqw] rounded-lg border border-borda bg-white object-contain shadow-md transition-opacity ${
                  imagem ? "" : "opacity-40"
                }`}
              />
              {/* Toque em qualquer ponto da página abre o visualizador em tela cheia. */}
              <button
                type="button"
                onClick={() => visualizador.abrir(indiceAtual)}
                aria-label={`Ampliar a página ${indiceAtual + 1}`}
                className="absolute inset-0 flex cursor-zoom-in items-end justify-end rounded-lg p-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primaria-texto"
              >
                <span className="flex min-h-11 items-center gap-1.5 rounded-xl bg-slate-900/75 px-3 text-xs font-semibold text-white">
                  <Expand className="size-4" aria-hidden />
                  Ampliar
                </span>
              </button>
              {/* Refazer o recorte depois de pronto; no Cartão ID, os cantos da frente e do verso. */}
              <Link
                href="/digitalizar/recorte"
                className="absolute bottom-2 left-2 flex min-h-11 items-center gap-1.5 rounded-xl bg-slate-900/75 px-3 text-xs font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primaria-texto"
              >
                <Crop className="size-4" aria-hidden />
                Recortar
              </Link>
              {carregandoFiltro && (
                <LoaderCircle className="pointer-events-none absolute size-8 animate-spin text-primaria-texto" aria-hidden />
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
                  <RotateCw className="size-4 text-primaria-texto" aria-hidden />
                  Tentar de novo
                </button>
              )}
            </div>
          ) : confirmada ? (
            <LoaderCircle className="size-8 animate-spin text-texto-suave" aria-hidden />
          ) : (
            <div className="relative flex max-h-full max-w-full items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element -- imagem local (blob) */}
              <img
                src={pagina.original.url}
                alt={`Página ${indiceAtual + 1}, ainda sem recorte`}
                className="max-h-[100cqh] max-w-[100cqw] rounded-lg border border-borda object-contain opacity-40"
              />
              <Link
                href="/digitalizar/recorte"
                className="absolute flex min-h-11 items-center gap-1.5 rounded-xl bg-primaria px-4 text-xs font-semibold text-white shadow-md"
              >
                <Crop className="size-4" aria-hidden />
                Recortar esta página
              </Link>
            </div>
          )}
        </div>
        <p className="font-mono text-[11px] text-texto-secundario [@media(max-height:700px)]:hidden">
          {gradeVisivel ? "Toque numa página para editá-la" : DESCRICAO_FILTRO[pagina.filtro]}
        </p>
        <p className="sr-only" aria-live="polite">
          {carregandoFiltro ? `Aplicando o filtro ${rotuloFiltro}…` : imagem ? `Filtro ${rotuloFiltro} aplicado` : ""}
          {pagina.estadoOcr === "pronto" ? " Texto da página lido." : ""}
        </p>

        <div className="flex w-full items-center gap-2">
          <ol className="flex flex-1 items-center gap-2 overflow-x-auto pb-1" aria-label="Páginas do documento">
            {paginas.map((p, indice) => {
              const miniatura = imagensDoVisualizador[indice].src;
              return (
                <li key={p.id} className="shrink-0">
                  <button
                    type="button"
                    onClick={() => selecionarPagina(indice)}
                    aria-label={`Página ${indice + 1}`}
                    aria-current={indice === indiceAtual ? "page" : undefined}
                    className={`relative block h-14 w-11 overflow-hidden rounded-md border-2 bg-white ${
                      indice === indiceAtual ? "border-primaria-texto" : "border-borda"
                    }`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element -- imagem local (blob) */}
                    <img src={miniatura} alt="" className="size-full object-cover" />
                    <span className="absolute bottom-0 right-0 rounded-tl bg-slate-900/75 px-1 font-mono text-[11px] text-white">
                      {indice + 1}
                    </span>
                  </button>
                </li>
              );
            })}
            <li className="shrink-0">
              <button
                type="button"
                popoverTarget={ID_MENU_PAGINA}
                aria-label="Adicionar página"
                disabled={captura.preparando}
                className="flex h-14 min-w-14 flex-col items-center justify-center gap-0.5 rounded-md border-2 border-dashed border-primaria-texto/70 bg-primaria-suave px-2 text-primaria-texto transition hover:bg-secundario disabled:opacity-60"
              >
                {captura.preparando ? (
                  <LoaderCircle className="size-5 animate-spin" aria-hidden />
                ) : (
                  <Plus className="size-5" aria-hidden />
                )}
                <span className="text-[11px] font-semibold leading-none">Página</span>
              </button>
            </li>
          </ol>
          {paginas.length > 1 && (
            <button
              type="button"
              onClick={() => setVerTodas((valor) => !valor)}
              aria-pressed={gradeVisivel}
              aria-label="Ver todas as páginas"
              className={`flex size-11 shrink-0 items-center justify-center rounded-xl border transition ${
                gradeVisivel
                  ? "border-primaria-texto bg-primaria-suave text-primaria-texto"
                  : "border-borda bg-cartao text-texto-secundario hover:text-texto"
              }`}
            >
              <LayoutGrid className="size-4" aria-hidden />
            </button>
          )}
          {paginas.length > 1 && (
            <button
              type="button"
              onClick={excluirPagina}
              aria-label={`Excluir página ${indiceAtual + 1}`}
              className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-borda bg-cartao text-texto-secundario hover:text-perigo"
            >
              <Trash2 className="size-4" aria-hidden />
            </button>
          )}
        </div>

        {/* Popover nativo: fecha com Esc e ao tocar fora, e devolve o foco ao botão. */}
        <div
          id={ID_MENU_PAGINA}
          popover="auto"
          aria-label="Adicionar página por"
          className="fixed inset-x-4 bottom-[calc(env(safe-area-inset-bottom)+9rem)] top-auto mx-auto w-auto max-w-sm overflow-hidden rounded-2xl border border-borda bg-cartao p-0 text-texto shadow-xl backdrop:bg-slate-950/30"
        >
          <p className="px-4 pb-1 pt-3 text-xs font-semibold text-texto-secundario">Adicionar página</p>
          <button
            type="button"
            onClick={() => adicionarPor("camera")}
            className="flex min-h-12 w-full items-center gap-3 px-4 text-sm hover:bg-secundario"
          >
            <Camera className="size-4 text-texto-secundario" aria-hidden />
            Escanear com a câmera
          </button>
          <button
            type="button"
            onClick={() => adicionarPor("galeria")}
            className="mb-1 flex min-h-12 w-full items-center gap-3 px-4 text-sm hover:bg-secundario"
          >
            <ImageIcon className="size-4 text-texto-secundario" aria-hidden />
            Escolher da galeria
          </button>
        </div>
      </div>

      <div className="shrink-0 space-y-3 border-t border-borda bg-cartao p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <fieldset className="grid grid-cols-3 gap-1.5 rounded-xl border border-borda bg-secundario p-1.5">
          <legend className="sr-only">Filtro da página</legend>
          {FILTROS.map(({ valor, rotulo }) => (
            <label key={valor} className="relative">
              <input
                type="radio"
                name="filtro"
                value={valor}
                checked={pagina.filtro === valor}
                onChange={() => atualizarPagina(pagina.id, { filtro: valor })}
                className="peer sr-only"
              />
              <span className="flex min-h-11 cursor-pointer items-center justify-center rounded-lg text-xs font-medium text-texto-secundario transition hover:text-texto peer-checked:bg-primaria peer-checked:font-semibold peer-checked:text-white peer-checked:shadow-sm peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primaria-texto">
                {rotulo}
              </span>
            </label>
          ))}
        </fieldset>

        {!todasConfirmadas && indicePendente !== indiceAtual && (
          <button
            type="button"
            onClick={() => selecionarPagina(indicePendente)}
            className="w-full text-center text-xs font-semibold text-primaria-texto underline underline-offset-2"
          >
            Falta recortar a página {indicePendente + 1} para gerar o PDF
          </button>
        )}

        <div className="grid grid-cols-5 gap-2.5">
          <button
            type="button"
            onClick={() => setGavetaAberta(true)}
            className="col-span-2 flex min-h-12 items-center justify-center gap-1.5 rounded-xl border border-borda bg-secundario text-xs font-semibold text-texto transition hover:opacity-90"
          >
            {pagina.estadoOcr === "carregando" || pagina.estadoOcr === "pendente" ? (
              <LoaderCircle className="size-4 animate-spin text-primaria-texto" aria-hidden />
            ) : (
              <FileText className="size-4 text-primaria-texto" aria-hidden />
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
      </div>

      {visualizador.indice !== null && (
        <VisualizadorPaginas
          imagens={imagensDoVisualizador}
          indice={Math.min(visualizador.indice, paginas.length - 1)}
          aoMudarIndice={(indice) => {
            visualizador.mostrar(indice);
            selecionarPagina(indice);
          }}
          aoFechar={visualizador.fechar}
        />
      )}

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
