"""Additive photo entities; file assets are shared with the video library."""

MIGRATION = """
CREATE TABLE assets_photo_migration (
    id INTEGER PRIMARY KEY, uid TEXT NOT NULL UNIQUE,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    path TEXT NOT NULL, filename TEXT NOT NULL, local_path TEXT,
    size INTEGER, mtime REAL, quick_hash TEXT, content_hash TEXT,
    status TEXT NOT NULL DEFAULT 'new', duration REAL, width INTEGER, height INTEGER, fps REAL,
    tech TEXT NOT NULL DEFAULT '{}', summary TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL,
    media_kind TEXT NOT NULL DEFAULT 'video' CHECK(media_kind IN ('video','photo')),
    CHECK(media_kind='photo' OR (size IS NOT NULL AND mtime IS NOT NULL AND quick_hash IS NOT NULL))
);
INSERT INTO assets_photo_migration SELECT *, 'video' FROM assets;
DROP TABLE assets;
ALTER TABLE assets_photo_migration RENAME TO assets;
CREATE INDEX assets_hash ON assets(content_hash);
CREATE INDEX assets_quick ON assets(quick_hash);
CREATE INDEX assets_status ON assets(status);
CREATE INDEX assets_kind ON assets(media_kind, id);

CREATE TABLE photo_catalogs (
    uid TEXT PRIMARY KEY, path TEXT NOT NULL, name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '', last_sync REAL, sync_cursor INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL UNIQUE,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    catalog_uid TEXT REFERENCES photo_catalogs(uid), lr_id TEXT,
    master_lr_id TEXT, copy_name TEXT NOT NULL DEFAULT '', is_virtual INTEGER NOT NULL DEFAULT 0,
    capture_time TEXT, camera TEXT, lens TEXT, rating INTEGER NOT NULL DEFAULT 0,
    keywords TEXT NOT NULL DEFAULT '[]', metadata TEXT NOT NULL DEFAULT '{}',
    revision TEXT NOT NULL DEFAULT '', analysis_key TEXT NOT NULL DEFAULT '',
    availability TEXT NOT NULL DEFAULT 'original', status TEXT NOT NULL DEFAULT 'pending',
    error TEXT, evidence TEXT NOT NULL DEFAULT '{}', phash TEXT, burst_id TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL, seen_at REAL, deleted_at REAL,
    UNIQUE(catalog_uid, lr_id)
);
CREATE UNIQUE INDEX photos_folder_asset ON photos(asset_id) WHERE catalog_uid IS NULL;
CREATE INDEX photos_asset ON photos(asset_id);
CREATE INDEX photos_capture ON photos(capture_time, id);
CREATE INDEX photos_burst ON photos(burst_id, id);
CREATE INDEX photos_status ON photos(status, id);
CREATE INDEX photos_catalog ON photos(catalog_uid, lr_id);
CREATE VIRTUAL TABLE photo_fts USING fts5(filename, keywords, caption, camera, lens, location, tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER photo_fts_delete AFTER DELETE ON photos BEGIN DELETE FROM photo_fts WHERE rowid=old.id; END;
CREATE TABLE photo_vectors (
    photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    model TEXT NOT NULL, dim INTEGER NOT NULL, vec BLOB NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX photo_vectors_updated ON photo_vectors(updated_at);
CREATE TABLE photo_faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT, photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    box TEXT NOT NULL, score REAL NOT NULL, size_px INTEGER NOT NULL,
    embedding BLOB, identity_id INTEGER REFERENCES identities(id) ON DELETE SET NULL,
    assigned_by TEXT NOT NULL DEFAULT 'auto', evidence TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX photo_faces_photo ON photo_faces(photo_id);
CREATE INDEX photo_faces_identity ON photo_faces(identity_id);
CREATE TABLE photo_face_labels (
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    box TEXT NOT NULL, embedding BLOB NOT NULL, assigned_by TEXT NOT NULL,
    PRIMARY KEY(photo_id,identity_id)
);
CREATE TABLE photo_analysis_runs (
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    analyser TEXT NOT NULL, input_key TEXT NOT NULL, version TEXT NOT NULL,
    status TEXT NOT NULL, error TEXT, seconds REAL, updated_at REAL NOT NULL,
    PRIMARY KEY(photo_id, analyser)
);
CREATE TABLE photo_collection_items (
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    position INTEGER NOT NULL, added_at REAL NOT NULL,
    PRIMARY KEY(collection_id, photo_id)
);
CREATE TABLE photo_jobs (
    uid TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
    idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
    request TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
    result TEXT NOT NULL DEFAULT '{}', error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL, updated_at REAL NOT NULL,
    UNIQUE(owner, kind, idempotency_key)
);
CREATE INDEX photo_jobs_status ON photo_jobs(status, created_at);
CREATE TABLE photo_edit_sessions (
    uid TEXT PRIMARY KEY, owner TEXT NOT NULL,
    source_photo_id INTEGER NOT NULL REFERENCES photos(id),
    target_photo_id INTEGER REFERENCES photos(id), catalog_uid TEXT NOT NULL,
    target_lr_id TEXT, source_revision TEXT NOT NULL, revision TEXT NOT NULL DEFAULT '',
    baseline_snapshot TEXT, best_snapshot TEXT, iterations INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'creating', creative INTEGER NOT NULL DEFAULT 0,
    brief TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE photo_feedback (
    photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    favourite INTEGER, note TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL
);
"""
