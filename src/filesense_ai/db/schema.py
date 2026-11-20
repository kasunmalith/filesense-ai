SCHEMA_VERSION = 1

SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS roots (
  id TEXT PRIMARY KEY, path TEXT NOT NULL, normalized_path TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, excluded_patterns TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY, root_id TEXT NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
  path TEXT NOT NULL UNIQUE, normalized_path TEXT NOT NULL UNIQUE, size INTEGER NOT NULL,
  mtime_ns INTEGER NOT NULL, sha256 TEXT, mime TEXT NOT NULL, kind TEXT NOT NULL,
  indexed_at TEXT NOT NULL, status TEXT NOT NULL, error TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_files_root ON files(root_id);
CREATE INDEX IF NOT EXISTS idx_files_kind ON files(kind);
CREATE TABLE IF NOT EXISTS segments (
  id INTEGER PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  locator TEXT NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_segments_file ON segments(file_id);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL, text TEXT NOT NULL, embedding_model TEXT, embedding_blob BLOB,
  UNIQUE(segment_id, ordinal)
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(chunk_id UNINDEXED, file_id UNINDEXED, filename, path, text, tokenize='unicode61 remove_diacritics 0');
CREATE TABLE IF NOT EXISTS images (
  file_id TEXT PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
  width INTEGER NOT NULL, height INTEGER NOT NULL, phash TEXT,
  clip_model TEXT, clip_embedding_blob BLOB, thumbnail_key TEXT
);
CREATE TABLE IF NOT EXISTS indexing_runs (
  id TEXT PRIMARY KEY, root_id TEXT NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
  started_at TEXT NOT NULL, completed_at TEXT, status TEXT NOT NULL,
  scanned INTEGER NOT NULL DEFAULT 0, indexed INTEGER NOT NULL DEFAULT 0,
  skipped INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
PRAGMA user_version=1;
COMMIT;
"""
