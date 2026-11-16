BEGIN;

DROP POLICY IF EXISTS "mvp_storage_delete" ON storage.objects;
DROP POLICY IF EXISTS "mvp_storage_update" ON storage.objects;
DROP POLICY IF EXISTS "mvp_storage_insert" ON storage.objects;
DROP POLICY IF EXISTS "mvp_storage_select" ON storage.objects;

DROP FUNCTION IF EXISTS public.search_miniscan_documents(TEXT);
DROP TRIGGER IF EXISTS trg_sync_page_count ON public.document_pages;
DROP FUNCTION IF EXISTS public.sync_document_page_count();
DROP TRIGGER IF EXISTS trg_document_pages_updated_at ON public.document_pages;
DROP TRIGGER IF EXISTS trg_documents_updated_at ON public.documents;
DROP FUNCTION IF EXISTS public.handle_updated_at();

DROP TABLE IF EXISTS public.document_pages;
DROP TABLE IF EXISTS public.documents;

COMMIT;
