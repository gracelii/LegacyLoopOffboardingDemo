-- Run this once against your Postgres database to set up the schema.
-- Requires the pgvector extension to be installed on the Postgres server.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    doc_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system   TEXT NOT NULL,          -- 'google_drive', 'confluence', etc.
    source_id       TEXT NOT NULL,          -- native file ID in that system
    title           TEXT NOT NULL,
    mime_type       TEXT,
    author          TEXT,
    last_modified   TIMESTAMPTZ,
    url             TEXT,
    raw_text        TEXT,
    ingested_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source_system, source_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    token_count     INTEGER,
    embedding       VECTOR(1536),           -- text-embedding-3-small dimension
    topic_labels    TEXT[],                 -- filled in during topic-extraction stage
    UNIQUE (doc_id, chunk_index)
);

-- Speeds up similarity search once you have a meaningful number of rows.
-- (Skip this until you have >1k chunks; it's not useful on tiny tables.)
-- CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_system, source_id);

-- Structured extraction (Step 2): one row per document, holds the
-- LLM-extracted structured fields as JSON for flexibility.
CREATE TABLE IF NOT EXISTS structured_knowledge (
    doc_id          UUID PRIMARY KEY REFERENCES documents(doc_id) ON DELETE CASCADE,
    project         TEXT,
    technologies    TEXT[],
    dependencies    TEXT[],
    contacts        TEXT[],
    deployment_process  TEXT,
    known_issues    TEXT,
    future_work     TEXT,
    raw_json        JSONB,          -- full extraction, in case the model returns extra fields
    extracted_at    TIMESTAMPTZ DEFAULT now()
);

-- Gap analysis (Step 3): tracks which knowledge categories are covered,
-- scoped per "project" since one corpus may span multiple systems/projects.
CREATE TABLE IF NOT EXISTS gap_analysis (
    gap_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project         TEXT NOT NULL,
    category        TEXT NOT NULL,   -- e.g. 'Known issues', 'Maintenance procedures'
    status          TEXT NOT NULL,   -- 'present', 'missing', 'thin'
    evidence_doc_ids UUID[],         -- doc_ids that cover this category, if any
    analyzed_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE (project, category)
);

-- Generated interview questions (Step 4) tied to specific gaps.
CREATE TABLE IF NOT EXISTS interview_questions (
    question_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project         TEXT NOT NULL,
    category        TEXT NOT NULL,
    question_text   TEXT NOT NULL,
    answer_text     TEXT,            -- filled in after Step 5 (interview)
    answered_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);
