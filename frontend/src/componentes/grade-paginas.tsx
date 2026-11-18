export interface ItemDaGrade {
  id: string;
  src: string;
  /** Texto ao lado do número, ex.: o filtro aplicado. */
  detalhe: string;
  /** Página ainda sem recorte: aparece esmaecida. */
  pendente?: boolean;
}

interface Props {
  itens: ItemDaGrade[];
  aoEscolher: (indice: number) => void;
  /** Verbo do rótulo acessível de cada página, ex.: "Ampliar" ou "Editar". */
  acao: string;
  /** Página em destaque (a que está selecionada no editor). */
  atual?: number;
}

/** Todas as páginas do documento numa grade, na ordem do PDF. */
export function GradePaginas({ itens, aoEscolher, acao, atual }: Props) {
  return (
    <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-label="Todas as páginas">
      {itens.map((item, indice) => (
        <li key={item.id}>
          <button
            type="button"
            onClick={() => aoEscolher(indice)}
            aria-label={`${acao} a página ${indice + 1}`}
            aria-current={indice === atual ? "true" : undefined}
            className={`block w-full overflow-hidden rounded-xl border-2 bg-cartao text-left shadow-cartao transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primaria-texto ${
              indice === atual ? "border-primaria-texto" : "border-borda hover:border-primaria/50"
            }`}
          >
            <span className="block aspect-[3/4] bg-white">
              {/* eslint-disable-next-line @next/next/no-img-element -- imagem local (blob) ou do Storage */}
              <img
                src={item.src}
                alt=""
                loading="lazy"
                className={`size-full object-contain ${item.pendente ? "opacity-40" : ""}`}
              />
            </span>
            <span className="flex items-center justify-between gap-2 border-t border-borda px-2.5 py-1.5 text-[11px]">
              <span className="font-mono font-semibold text-texto">{indice + 1}</span>
              <span className="truncate text-texto-secundario">{item.detalhe}</span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
