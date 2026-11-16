-- Reverte 20261116000003_adiciona_filtro_quadro_branco.sql.
-- Páginas salvas como quadro branco passam a constar como "original" antes de a
-- restrição antiga voltar, para o ALTER não falhar.

BEGIN;

UPDATE public.document_pages SET filter_applied = 'original' WHERE filter_applied = 'whiteboard';

ALTER TABLE public.document_pages
    DROP CONSTRAINT IF EXISTS document_pages_filter_applied_check;

ALTER TABLE public.document_pages
    ADD CONSTRAINT document_pages_filter_applied_check
    CHECK (filter_applied IN ('original', 'grayscale', 'bw'));

COMMIT;
