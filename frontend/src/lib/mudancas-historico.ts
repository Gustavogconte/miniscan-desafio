import type { DocumentoHistorico } from "@/lib/tipos";

// Documentos excluídos e renomeados nesta visita. O Next guarda a tela inicial escondida
// e a mostra de novo antes de buscar a lista na API: sem isto, o documento excluído
// aparecia por um instante, ou com o nome antigo.
const excluidos = new Set<string>();
const nomesNovos = new Map<string, string>();

export function marcarExcluido(id: string) {
  excluidos.add(id);
}

export function marcarRenomeado(id: string, titulo: string) {
  nomesNovos.set(id, titulo);
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
