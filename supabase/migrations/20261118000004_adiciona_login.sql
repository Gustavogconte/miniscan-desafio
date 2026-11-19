-- ============================================================================
-- Login próprio e histórico separado por conta.
--
-- As contas ficam em public.usuarios, com a senha em hash Argon2id feito pela API
-- (não usa o Supabase Auth). As sessões ficam em public.sessoes, só com o SHA-256
-- do token: o token em si só existe no navegador da pessoa.
--
-- A partir desta migração, nada é lido com a chave pública: a API lê e grava tudo
-- com a chave secreta e filtra pelo dono. O bucket vira privado e os arquivos só
-- abrem por links assinados que a API gera (valem 1 hora).
--
-- Documentos salvos antes desta migração ficam sem dono e somem do histórico. Para
-- passá-los a uma conta, depois de criá-la no app:
--   UPDATE public.documents SET usuario_id = (
--     SELECT id FROM public.usuarios WHERE email = 'seu-email@exemplo.com'
--   ) WHERE usuario_id IS NULL;
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Contas e sessões
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.usuarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome TEXT NOT NULL CHECK (char_length(trim(nome)) BETWEEN 1 AND 80),
    -- A API grava o e-mail já em minúsculas e sem espaços nas pontas.
    email TEXT NOT NULL CHECK (email = lower(trim(email)) AND char_length(email) BETWEEN 3 AND 254),
    senha_hash TEXT NOT NULL CHECK (senha_hash LIKE '$argon2id$%'),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_usuarios_email UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS public.sessoes (
    -- SHA-256 do token, em hexadecimal.
    token_hash TEXT PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    usuario_id UUID NOT NULL REFERENCES public.usuarios(id) ON DELETE CASCADE,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    expira_em TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessoes_usuario ON public.sessoes (usuario_id);

-- RLS ligado e nenhuma política: só a chave secreta (que ignora o RLS) enxerga.
ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessoes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.usuarios, public.sessoes FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- Dono de cada documento
-- ----------------------------------------------------------------------------

ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS usuario_id UUID REFERENCES public.usuarios(id) ON DELETE CASCADE;

-- Lista da tela inicial: documentos de uma conta, do mais novo ao mais antigo.
CREATE INDEX IF NOT EXISTS idx_documents_usuario_created_at
    ON public.documents (usuario_id, created_at DESC);

-- Daqui em diante as colunas pdf_url, original_image_url e processed_image_url
-- guardam o caminho do arquivo no bucket (documentos/<id>/...), e não um link.

-- ----------------------------------------------------------------------------
-- Fim da leitura pública
-- ----------------------------------------------------------------------------

DROP POLICY IF EXISTS "public_documents_read" ON public.documents;
DROP POLICY IF EXISTS "public_document_pages_read" ON public.document_pages;
REVOKE ALL ON public.documents, public.document_pages FROM anon, authenticated;

-- A busca antiga varria o histórico de todo mundo.
REVOKE EXECUTE ON FUNCTION public.search_miniscan_documents(TEXT) FROM PUBLIC, anon, authenticated;

-- Busca no título e no texto do OCR (português), só entre os documentos do dono.
-- O termo entra como texto literal no ILIKE: % e _ digitados não viram curinga.
CREATE OR REPLACE FUNCTION public.buscar_documentos_usuario(termo TEXT, dono UUID)
RETURNS SETOF public.documents
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    WITH busca AS (
        SELECT
            trim(termo) AS texto,
            '%' || replace(replace(replace(trim(termo), '\', '\\'), '%', '\%'), '_', '\_') || '%' AS padrao
    )
    SELECT d.*
    FROM public.documents d, busca b
    WHERE d.usuario_id = dono
      AND (
        b.texto = ''
        OR to_tsvector('portuguese', coalesce(d.title, '')) @@ plainto_tsquery('portuguese', b.texto)
        OR d.title ILIKE b.padrao
        OR EXISTS (
            SELECT 1
            FROM public.document_pages dp
            WHERE dp.document_id = d.id
              AND (
                to_tsvector('portuguese', coalesce(dp.ocr_text, '')) @@ plainto_tsquery('portuguese', b.texto)
                OR dp.ocr_text ILIKE b.padrao
              )
        )
      )
    ORDER BY d.created_at DESC;
$$;

REVOKE EXECUTE ON FUNCTION public.buscar_documentos_usuario(TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.buscar_documentos_usuario(TEXT, UUID) TO service_role;

-- ----------------------------------------------------------------------------
-- Storage privado
-- ----------------------------------------------------------------------------

UPDATE storage.buckets SET public = false WHERE id = 'miniscan-files';
DROP POLICY IF EXISTS "mvp_storage_select" ON storage.objects;

-- ----------------------------------------------------------------------------
-- Tabelas e funções futuras
-- ----------------------------------------------------------------------------

-- O Supabase dá a anon e authenticated acesso a toda tabela e função nova do schema
-- public. Como o app não usa mais a chave pública, uma migração futura que esquecesse
-- o REVOKE deixaria os dados abertos pela API REST. Daqui em diante, o acesso desses
-- papéis só existe se for concedido de propósito.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

COMMIT;
