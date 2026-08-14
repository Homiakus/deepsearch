CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    external_id TEXT,
    document_type TEXT NOT NULL,
    title TEXT,
    abstract TEXT,
    source_url TEXT,
    canonical_url TEXT,
    doi TEXT UNIQUE,
    pmid TEXT,
    arxiv_id TEXT,
    publication_year INT,
    published_at TIMESTAMPTZ,
    language TEXT,
    license TEXT,
    is_open_access BOOLEAN DEFAULT false,
    source_provider TEXT,
    content_hash TEXT,
    parse_status TEXT DEFAULT 'pending',
    quality_score DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_authors (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    orcid TEXT,
    position INT
);

CREATE TABLE IF NOT EXISTS document_files (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    file_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    source_url TEXT,
    mime_type TEXT,
    size_bytes BIGINT,
    sha256 TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    section TEXT,
    content TEXT NOT NULL,
    chunk_index INT NOT NULL,
    token_count INT,
    source_start_offset INT,
    source_end_offset INT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id BIGINT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    embedding vector,
    model TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS search_jobs (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    params JSONB,
    progress JSONB,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS raw_search_results (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT REFERENCES search_jobs(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    url TEXT,
    title TEXT,
    snippet TEXT,
    raw JSONB,
    score DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_doi ON documents(doi);
CREATE INDEX IF NOT EXISTS idx_documents_title ON documents USING gin(to_tsvector('english', coalesce(title,'') || ' ' || coalesce(abstract,'')));
CREATE INDEX IF NOT EXISTS idx_chunks_content ON chunks USING gin(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
