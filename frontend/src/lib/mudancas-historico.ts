import type { DocumentoHistorico } from "@/lib/tipos";

// Documentos excluídos e renomeados desde a última vez que a lista veio da API. O Next
// guarda a tela inicial escondida e a mostra de novo antes de buscar a lista: sem isto,
// o documento excluído aparecia por um instante, ou com o nome antigo.
const excluidos = new Set<string>();
const nomesNovos = new Map<string, string>();

export function marcarExcluido(id: string) {
  excluidos.add(id);
}

export function marcarRenomeado(id: string, titulo: string) {
  nomesNovos.set(id, titulo);
}

/** A lista nova da API já tem as mudanças: daqui em diante vale só ela. */
export function limparMudancas() {
  excluidos.clear();
  nomesNovos.clear();
}

export function aplicarMudancas(documentos: DocumentoHistorico[]): DocumentoHistorico[] {
  const lista: DocumentoHistorico[] = [];
  for (const documento of documentos) {
    if (excluidos.has(documento.id)) continue;
    const titulo = nomesNovos.get(documento.id);
    lista.push(titulo ? { ...documento, titulo } : documento);
  }
  return lista;
}
