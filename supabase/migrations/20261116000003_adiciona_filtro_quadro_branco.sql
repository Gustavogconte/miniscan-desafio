-- ============================================================================
-- Aceita o filtro "whiteboard" (quadro branco) em document_pages.filter_applied.
-- A restrição original foi criada sem nome explícito; o Postgres a nomeia
-- <tabela>_<coluna>_check.
-- ============================================================================

BEGIN;

ALTER TABLE public.document_pages
    DROP CONSTRAINT IF EXISTS document_pages_filter_applied_check;

ALTER TABLE public.document_pages
    ADD CONSTRAINT document_pages_filter_applied_check
    CHECK (filter_applied IN ('original', 'grayscale', 'bw', 'whiteboard'));

COMMIT;
