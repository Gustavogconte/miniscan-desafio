import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import type { DocumentoHistorico } from "@/lib/tipos";

const URL_SUPABASE = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
// Chave pública (publishable): só tem permissão de leitura graças ao RLS.
const CHAVE_PUBLICA = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";

let cliente: SupabaseClient | null = null;

function obterCliente(): SupabaseClient {
  if (!URL_SUPABASE || !CHAVE_PUBLICA) {
    throw new Error("Configure a URL e a chave pública do Supabase no arquivo .env.local.");
  }
  cliente ??= createClient(URL_SUPABASE, CHAVE_PUBLICA, { auth: { persistSession: false } });
  return cliente;
}

const CAMPOS =
  "id, title, pdf_url, page_count, created_at, document_pages(processed_image_url, ocr_text, filter_applied, page_order)";

/**
 * Lista o histórico usando a mesma função de busca do banco: com texto vazio ela
 * devolve todos os documentos; com texto, procura no título e no OCR (português).
 */
export async function buscarDocumentos(termo: string): Promise<DocumentoHistorico[]> {
  const { data, error } = await obterCliente()
    .rpc("search_miniscan_documents", { search_query: termo.trim() })
    .select(CAMPOS)
    .order("created_at", { ascending: false })
    .order("page_order", { referencedTable: "document_pages", ascending: true })
    .limit(1, { referencedTable: "document_pages" })
    .limit(50);
  if (error) throw new Error("Não foi possível carregar o histórico.");
  return (data ?? []) as unknown as DocumentoHistorico[];
}
