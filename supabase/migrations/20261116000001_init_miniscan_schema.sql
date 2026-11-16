BEGIN;

-- ============================================================================
-- FASE 1: TABELAS E RESTRIÇÕES DE INTEGRIDADE
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    title TEXT NOT NULL CHECK (char_length(trim(title)) > 0),
    pdf_url TEXT,
    page_count INTEGER NOT NULL DEFAULT 0 CHECK (page_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

CREATE TABLE IF NOT EXISTS public.document_pages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    page_order INTEGER NOT NULL DEFAULT 1 CHECK (page_order > 0),
    original_image_url TEXT NOT NULL CHECK (char_length(trim(original_image_url)) > 0),
    processed_image_url TEXT NOT NULL CHECK (char_length(trim(processed_image_url)) > 0),
    filter_applied TEXT NOT NULL CHECK (filter_applied IN ('original', 'grayscale', 'bw')),
    ocr_text TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_document_page_order UNIQUE (document_id, page_order)
);

-- ============================================================================
-- FASE 2: ÍNDICES E GATILHOS DE AUTOMAÇÃO (TRIGGERS)
-- ============================================================================

-- Índice para listar os documentos mais recentes na tela inicial
CREATE INDEX IF NOT EXISTS idx_documents_created_at 
    ON public.documents (created_at DESC);

-- Índice composto para otimizar junções de chave estrangeira e ordenação das páginas
CREATE INDEX IF NOT EXISTS idx_document_pages_doc_order 
    ON public.document_pages (document_id, page_order ASC);

-- Índices GIN para busca textual rápida (Full-Text Search) em português no título e OCR
CREATE INDEX IF NOT EXISTS idx_document_pages_ocr_fts 
    ON public.document_pages USING GIN (to_tsvector('portuguese', coalesce(ocr_text, '')));

CREATE INDEX IF NOT EXISTS idx_documents_title_fts 
    ON public.documents USING GIN (to_tsvector('portuguese', coalesce(title, '')));

-- Função de gatilho para atualizar automaticamente a coluna updated_at
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = timezone('utc', now());
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_documents_updated_at ON public.documents;
CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON public.documents
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_document_pages_updated_at ON public.document_pages;
CREATE TRIGGER trg_document_pages_updated_at
    BEFORE UPDATE ON public.document_pages
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- Função de gatilho para manter documents.page_count sincronizado automaticamente
CREATE OR REPLACE FUNCTION public.sync_document_page_count()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE public.documents
        SET page_count = (SELECT count(*) FROM public.document_pages WHERE document_id = NEW.document_id)
        WHERE id = NEW.document_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE public.documents
        SET page_count = (SELECT count(*) FROM public.document_pages WHERE document_id = OLD.document_id)
        WHERE id = OLD.document_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_page_count ON public.document_pages;
CREATE TRIGGER trg_sync_page_count
    AFTER INSERT OR DELETE ON public.document_pages
    FOR EACH ROW
    EXECUTE FUNCTION public.sync_document_page_count();

-- Função RPC auxiliar para busca unificada pelo título do documento ou texto do OCR
CREATE OR REPLACE FUNCTION public.search_miniscan_documents(search_query TEXT)
RETURNS SETOF public.documents
LANGUAGE sql
STABLE
AS $$
    SELECT DISTINCT d.*
    FROM public.documents d
    LEFT JOIN public.document_pages dp ON dp.document_id = d.id
    WHERE 
        trim(search_query) = ''
        OR to_tsvector('portuguese', coalesce(d.title, '')) @@ plainto_tsquery('portuguese', search_query)
        OR to_tsvector('portuguese', coalesce(dp.ocr_text, '')) @@ plainto_tsquery('portuguese', search_query)
        OR d.title ILIKE '%' || search_query || '%'
        OR dp.ocr_text ILIKE '%' || search_query || '%'
    ORDER BY d.created_at DESC;
$$;

-- ============================================================================
-- FASE 3: SEGURANÇA EM NÍVEL DE LINHA (RLS) E BUCKET DE ARMAZENAMENTO
-- ============================================================================

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_pages ENABLE ROW LEVEL SECURITY;

-- Políticas explícitas por tabela (acesso liberado para o MVP sem barreira de login)
DROP POLICY IF EXISTS "mvp_documents_all_access" ON public.documents;
CREATE POLICY "mvp_documents_all_access"
    ON public.documents
    FOR ALL
    TO anon, authenticated
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "mvp_document_pages_all_access" ON public.document_pages;
CREATE POLICY "mvp_document_pages_all_access"
    ON public.document_pages
    FOR ALL
    TO anon, authenticated
    USING (true)
    WITH CHECK (true);

-- Configuração do Bucket no Storage (limite de 15 MB, restrito a imagens e PDFs)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'miniscan-files',
    'miniscan-files',
    true,
    15728640, -- 15 MB
    ARRAY['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
)
ON CONFLICT (id) DO UPDATE SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS "mvp_storage_select" ON storage.objects;
CREATE POLICY "mvp_storage_select"
    ON storage.objects FOR SELECT
    TO anon, authenticated
    USING (bucket_id = 'miniscan-files');

DROP POLICY IF EXISTS "mvp_storage_insert" ON storage.objects;
CREATE POLICY "mvp_storage_insert"
    ON storage.objects FOR INSERT
    TO anon, authenticated
    WITH CHECK (bucket_id = 'miniscan-files');

DROP POLICY IF EXISTS "mvp_storage_update" ON storage.objects;
CREATE POLICY "mvp_storage_update"
    ON storage.objects FOR UPDATE
    TO anon, authenticated
    USING (bucket_id = 'miniscan-files')
    WITH CHECK (bucket_id = 'miniscan-files');

DROP POLICY IF EXISTS "mvp_storage_delete" ON storage.objects;
CREATE POLICY "mvp_storage_delete"
    ON storage.objects FOR DELETE
    TO anon, authenticated
    USING (bucket_id = 'miniscan-files');

COMMIT;
