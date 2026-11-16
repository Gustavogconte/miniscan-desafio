-- ============================================================================
-- Restringe o papel anônimo à leitura.
--
-- A partir desta migração, todas as gravações passam pela API (POST /documentos),
-- que usa a chave secreta do Supabase e não depende destas políticas. O front-end,
-- com a chave pública, continua listando e buscando o histórico, mas não consegue
-- mais inserir, alterar ou apagar documentos nem arquivos.
-- ============================================================================

BEGIN;

-- Tabelas: troca o acesso total por leitura.
DROP POLICY IF EXISTS "mvp_documents_all_access" ON public.documents;
DROP POLICY IF EXISTS "public_documents_read" ON public.documents;
CREATE POLICY "public_documents_read"
    ON public.documents
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS "mvp_document_pages_all_access" ON public.document_pages;
DROP POLICY IF EXISTS "public_document_pages_read" ON public.document_pages;
CREATE POLICY "public_document_pages_read"
    ON public.document_pages
    FOR SELECT
    TO anon, authenticated
    USING (true);

-- Defesa em profundidade: mesmo que alguém crie uma política permissiva por engano,
-- os papéis públicos não têm permissão de escrita nas tabelas.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.documents FROM anon, authenticated;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.document_pages FROM anon, authenticated;

-- Storage: mantém a leitura (o bucket é público para os links de download)
-- e remove upload, alteração e exclusão pelo papel anônimo.
DROP POLICY IF EXISTS "mvp_storage_insert" ON storage.objects;
DROP POLICY IF EXISTS "mvp_storage_update" ON storage.objects;
DROP POLICY IF EXISTS "mvp_storage_delete" ON storage.objects;

COMMIT;
