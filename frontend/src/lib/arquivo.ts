/** Nome de arquivo seguro: sem acentos, barras ou espaços. */
export function nomeDoArquivo(titulo: string): string {
  const limpo = titulo
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\w\- ]+/g, "")
    .trim()
    .replace(/\s+/g, "_");
  return `${limpo || "Documento_MiniScan"}.pdf`;
}

export function baixarArquivo(blob: Blob, nome: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export type ResultadoCompartilhar = "compartilhado" | "cancelado" | "baixado";

/**
 * Abre o menu de compartilhamento do celular com o PDF. Em navegadores que não
 * compartilham arquivos, baixa o PDF. Outras falhas são repassadas a quem chamou.
 */
export async function compartilharPdf(blob: Blob, nome: string, titulo: string): Promise<ResultadoCompartilhar> {
  const arquivo = new File([blob], nome, { type: "application/pdf" });
  if (!navigator.canShare?.({ files: [arquivo] })) {
    baixarArquivo(blob, nome);
    return "baixado";
  }
  try {
    await navigator.share({ files: [arquivo], title: titulo });
    return "compartilhado";
  } catch (erro) {
    if (erro instanceof DOMException && erro.name === "AbortError") return "cancelado";
    throw erro;
  }
}
