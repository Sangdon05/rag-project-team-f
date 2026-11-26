-- Install pgvector in public separately before running this file.
-- Apply only to the designated team database, never to the source database.
CREATE SCHEMA solar_handoff;
CREATE TABLE solar_handoff.chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL
);
CREATE TABLE solar_handoff.vectors (
    chunk_id TEXT PRIMARY KEY REFERENCES solar_handoff.chunks(chunk_id),
    embedding public.vector(1024) NOT NULL
);
CREATE TABLE solar_handoff.index_info (
    id TEXT PRIMARY KEY,
    config JSONB NOT NULL
);
