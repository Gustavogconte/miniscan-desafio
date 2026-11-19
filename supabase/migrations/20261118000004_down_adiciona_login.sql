-- ============================================================================
-- Desfaz 20261118000004_adiciona_login.sql: volta ao histórico público e sem contas.
--
-- ATENÇÃO: não rode em produção com dados reais. Apaga as contas e as sessões e
-- volta a PUBLICAR todos os documentos e arquivos, inclusive os salvos pelas contas
-- depois do login (RG, CNH, CPF): qualquer pessoa com a chave pública passa a ler e
-- listar tudo. Os salvos depois do login guardam só o caminho do arquivo (e não a
-- URL pública), e o app antigo não consegue abrir esses arquivos.
-- ============================================================================

BEGIN;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated;

-- Storage público de novo, com leitura para os papéis públicos.
UPDATE storage.buckets SET public = true WHERE id = 'miniscan-files';
DROP POLICY IF EXISTS "mvp_storage_select" ON storage.objects;
CREATE POLICY "mvp_storage_select"
    ON storage.objects FOR SELECT
    TO anon, authenticated
    USING (bucket_id = 'miniscan-files');

DROP FUNCTION IF EXISTS public.buscar_documentos_usuario(TEXT, UUID);
GRANT EXECUTE ON FUNCTION public.search_miniscan_documents(TEXT) TO anon, authenticated;

-- Leitura pública das tabelas, como na migração 20261116000002.
GRANT SELECT ON public.documents, public.document_pages TO anon, authenticated;
DROP POLICY IF EXISTS "public_documents_read" ON public.documents;
CREATE POLICY "public_documents_read"
    ON public.documents FOR SELECT
    TO anon, authenticated
    USING (true);
DROP POLICY IF EXISTS "public_document_pages_read" ON public.document_pages;
CREATE POLICY "public_document_pages_read"
    ON public.document_pages FOR SELECT
    TO anon, authenticated
    USING (true);

DROP INDEX IF EXISTS public.idx_documents_usuario_created_at;
ALTER TABLE public.documents DROP COLUMN IF EXISTS usuario_id;

DROP TABLE IF EXISTS public.sessoes;
DROP TABLE IF EXISTS public.usuarios;

COMMIT;
