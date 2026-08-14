-- 001_initial_schema: core tables for DeepSearch
-- Up

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id              BIGSERIAL PRIMARY KEY,
    document_type   TEXT NOT NULL DEFAULT 'paper',
    title           TEXT NOT NULL DEFAULT '',
    abstract        TEXT NOT NULL DEFAULT '',
    source_url      TEXT NOT NULL DEFAULT '',
    doi             TEXT UNIQUE,
    publication_year INT,
    is_open_access  BOOLEAN NOT NULL DEFAULT false,
    source_provider TEXT NOT NULL DEFAULT 'unknown',
    parse_status    TEXT NOT NULL DEFAULT 'pending',
    license         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_documents_doi ON documents(doi);
CREATE INDEX IF NOT EXISTS idx_documents_parse_status ON documents(parse_status);

CREATE TABLE IF NOT EXISTS document_files (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    file_type    TEXT NOT NULL DEFAULT 'pdf',
    storage_path TEXT NOT NULL,
    source_url   TEXT NOT NULL DEFAULT '',
    mime_type    TEXT NOT NULL DEFAULT '',
    size_bytes   BIGINT NOT NULL DEFAULT 0,
    sha256       TEXT UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_document_files_document ON document_files(document_id);

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section     TEXT NOT NULL DEFAULT 'body',
    content     TEXT NOT NULL,
    chunk_index INT NOT NULL DEFAULT 0,
    token_count INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    id         BIGSERIAL PRIMARY KEY,
    chunk_id   BIGINT UNIQUE NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    embedding  vector(1536),
    model      TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_vector ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS search_jobs (
    id           TEXT PRIMARY KEY,
    query        TEXT NOT NULL DEFAULT '',
    mode         TEXT NOT NULL DEFAULT 'search',
    status       TEXT NOT NULL DEFAULT 'pending',
    params       JSONB NOT NULL DEFAULT '{}',
    progress     JSONB NOT NULL DEFAULT '{}',
    error        TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_search_jobs_status ON search_jobs(status);
