"""SQLite storage: connection handling and schema migrations.

The library lives in one SQLite database in WAL mode. Machine output and human
corrections are stored in separate tables; the effective record is always
machine output overlaid with corrections (see ``records.py``), so
re-processing can never overwrite a human decision.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

MIGRATIONS: list[str] = [
    # ---------------------------------------------------------------- v1
    """
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

    CREATE TABLE sources (
        id INTEGER PRIMARY KEY,
        uri TEXT NOT NULL UNIQUE,           -- /abs/path or s3://bucket/prefix
        kind TEXT NOT NULL,                 -- folder | s3
        watch INTEGER NOT NULL DEFAULT 1,
        priority INTEGER NOT NULL DEFAULT 0,
        options TEXT NOT NULL DEFAULT '{}',
        last_scan REAL,
        created_at REAL NOT NULL
    );

    CREATE TABLE assets (
        id INTEGER PRIMARY KEY,
        uid TEXT NOT NULL UNIQUE,
        source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
        path TEXT NOT NULL,                 -- primary location (local path or s3 uri)
        filename TEXT NOT NULL,
        local_path TEXT,                    -- readable cached copy for remote sources
        size INTEGER NOT NULL,
        mtime REAL NOT NULL,
        quick_hash TEXT NOT NULL,           -- size + sampled chunks, used for change detection
        content_hash TEXT,                  -- full BLAKE2b, used for duplicate detection
        status TEXT NOT NULL DEFAULT 'new', -- new | processing | ready | error | missing
        duration REAL, width INTEGER, height INTEGER, fps REAL,
        tech TEXT NOT NULL DEFAULT '{}',    -- full technical metadata (json)
        summary TEXT NOT NULL DEFAULT '{}', -- asset rollup (json)
        priority INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        deleted_at REAL
    );
    CREATE INDEX assets_hash ON assets(content_hash);
    CREATE INDEX assets_quick ON assets(quick_hash);
    CREATE INDEX assets_status ON assets(status);

    -- Every path where a file with the same content was found (duplicates).
    CREATE TABLE asset_paths (
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        path TEXT NOT NULL UNIQUE,
        mtime REAL, size INTEGER,
        seen_at REAL NOT NULL
    );

    CREATE TABLE shots (
        id INTEGER PRIMARY KEY,
        uid TEXT NOT NULL UNIQUE,           -- <asset uid>-<start frame>, stable across re-runs
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        idx INTEGER NOT NULL,
        start_s REAL NOT NULL, end_s REAL NOT NULL,
        start_frame INTEGER NOT NULL, end_frame INTEGER NOT NULL,
        kind TEXT NOT NULL DEFAULT 'shot',  -- shot | segment (part of a long take)
        transition_in TEXT NOT NULL DEFAULT 'cut',
        segmenter TEXT NOT NULL,            -- analyser@version that produced it
        keyframes TEXT NOT NULL DEFAULT '[]',
        active INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX shots_asset ON shots(asset_id, idx);

    CREATE TABLE moments (
        id INTEGER PRIMARY KEY,
        shot_id INTEGER REFERENCES shots(id) ON DELETE CASCADE,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,                 -- speech | text | face | sound | object | segment
        start_s REAL NOT NULL, end_s REAL NOT NULL,
        text TEXT NOT NULL DEFAULT '',
        data TEXT NOT NULL DEFAULT '{}',
        source TEXT NOT NULL, model_version TEXT NOT NULL,
        confidence REAL
    );
    CREATE INDEX moments_shot ON moments(shot_id, kind);
    CREATE INDEX moments_asset ON moments(asset_id, kind, start_s);

    -- Machine signals. One row per (target, name, source). Replaced when the
    -- producing analyser re-runs; never touched by humans.
    CREATE TABLE signals (
        id INTEGER PRIMARY KEY,
        level TEXT NOT NULL,                -- asset | shot | moment
        target_id INTEGER NOT NULL,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        value TEXT NOT NULL,                -- json
        source TEXT NOT NULL,               -- analyser name
        confidence REAL,
        model_version TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE INDEX signals_target ON signals(level, target_id, name);
    CREATE INDEX signals_asset_source ON signals(asset_id, source);

    -- Human corrections. Anchored by asset uid + time span so they re-attach
    -- to the right shot if segmentation changes.
    CREATE TABLE corrections (
        id INTEGER PRIMARY KEY,
        level TEXT NOT NULL,                -- asset | shot
        asset_uid TEXT NOT NULL,
        shot_uid TEXT,
        anchor_start REAL, anchor_end REAL,
        field TEXT NOT NULL,
        op TEXT NOT NULL,                   -- set | add | remove
        value TEXT NOT NULL,                -- json
        note TEXT NOT NULL DEFAULT '',
        user_id INTEGER, actor TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX corrections_asset ON corrections(asset_uid, active);

    CREATE TABLE analysis_runs (
        id INTEGER PRIMARY KEY,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        analyser TEXT NOT NULL,
        version TEXT NOT NULL,
        input_key TEXT NOT NULL,            -- hash of content + version + config + upstream keys
        status TEXT NOT NULL,               -- done | failed | unavailable
        output TEXT NOT NULL DEFAULT '{}',
        error TEXT,
        started_at REAL, finished_at REAL, seconds REAL,
        UNIQUE(asset_id, analyser)
    );

    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        analyser TEXT NOT NULL,
        input_key TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'queued', -- queued | running | done | failed | cancelled
        attempts INTEGER NOT NULL DEFAULT 0,
        run_after REAL NOT NULL DEFAULT 0,
        lease_until REAL,
        worker TEXT,
        error TEXT,
        created_at REAL NOT NULL, updated_at REAL NOT NULL,
        UNIQUE(asset_id, analyser, input_key)
    );
    CREATE INDEX jobs_pick ON jobs(status, priority DESC, id);

    -- Denormalised, query-ready view of each shot's effective record
    -- (machine + corrections), rebuilt by the indexer.
    CREATE TABLE shot_index (
        shot_id INTEGER PRIMARY KEY REFERENCES shots(id) ON DELETE CASCADE,
        asset_id INTEGER NOT NULL,
        duration REAL, start_s REAL, end_s REAL,
        width INTEGER, height INTEGER, fps REAL, aspect REAL,
        log_profile INTEGER, hdr INTEGER,
        people_count INTEGER, faces INTEGER,
        speech INTEGER, music INTEGER,
        motion_energy REAL, pace TEXT,
        shot_size TEXT, camera_movement TEXT, role TEXT, time_of_day TEXT,
        usable INTEGER, quality REAL,
        capture_date TEXT, location TEXT, edit_type TEXT,
        caption TEXT,
        doc TEXT NOT NULL,                  -- full effective record json
        vec_row INTEGER,                    -- row in the visual vector store
        updated_at REAL NOT NULL
    );
    CREATE INDEX si_asset ON shot_index(asset_id);
    CREATE INDEX si_dur ON shot_index(duration);
    CREATE INDEX si_res ON shot_index(height);

    -- Multi-valued controlled-vocabulary terms per shot, for filters and facets.
    CREATE TABLE shot_terms (
        shot_id INTEGER NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
        vocab TEXT NOT NULL,
        term TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1,
        source TEXT NOT NULL,
        PRIMARY KEY (shot_id, vocab, term)
    );
    CREATE INDEX st_term ON shot_terms(vocab, term, shot_id);

    CREATE VIRTUAL TABLE shot_fts USING fts5(
        caption, transcript, ocr, tags, place, filename,
        tokenize = 'unicode61 remove_diacritics 2'
    );

    CREATE TABLE rights (
        id INTEGER PRIMARY KEY,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        shot_id INTEGER REFERENCES shots(id) ON DELETE CASCADE, -- null = asset level
        source TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '',
        licence TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'unknown',   -- cleared | restricted | not_cleared | unknown
        permitted_uses TEXT NOT NULL DEFAULT '[]',
        channels TEXT NOT NULL DEFAULT '[]',
        territories TEXT NOT NULL DEFAULT '[]',   -- ISO 3166 alpha-2, or ["WW"]
        excluded_territories TEXT NOT NULL DEFAULT '[]',
        starts TEXT, expires TEXT,                 -- ISO dates
        model_release TEXT NOT NULL DEFAULT 'unknown',
        property_release TEXT NOT NULL DEFAULT 'unknown',
        brand_safety TEXT NOT NULL DEFAULT 'unknown',
        attribution TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        updated_by TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL,
        UNIQUE(asset_id, shot_id)
    );

    CREATE TABLE collections (
        id INTEGER PRIMARY KEY,
        uid TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT 'collection',   -- collection | selects | package
        brief TEXT NOT NULL DEFAULT '',
        owner TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL, updated_at REAL NOT NULL
    );
    CREATE TABLE collection_items (
        id INTEGER PRIMARY KEY,
        collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
        shot_id INTEGER NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        in_s REAL, out_s REAL,
        note TEXT NOT NULL DEFAULT '',
        added_by TEXT NOT NULL DEFAULT '',
        added_at REAL NOT NULL
    );
    CREATE INDEX ci_coll ON collection_items(collection_id, position);

    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL,                 -- viewer | editor | admin | agent
        password_hash TEXT,
        disabled INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL
    );
    CREATE TABLE tokens (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        prefix TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        scopes TEXT NOT NULL,               -- json list
        kind TEXT NOT NULL DEFAULT 'api',   -- api | session
        created_at REAL NOT NULL, last_used REAL, expires_at REAL,
        revoked INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY,
        at REAL NOT NULL,
        user_id INTEGER, actor TEXT NOT NULL, role TEXT NOT NULL DEFAULT '',
        via TEXT NOT NULL,                  -- api | mcp | ui | cli | system
        action TEXT NOT NULL,
        target TEXT NOT NULL DEFAULT '',
        detail TEXT NOT NULL DEFAULT '{}',
        ok INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX audit_at ON audit_log(at);

    -- Embeddings (float16). The source of truth; the in-memory ANN index is a
    -- rebuildable cache synchronised by id.
    CREATE TABLE vectors (
        id INTEGER PRIMARY KEY,
        shot_id INTEGER NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
        asset_id INTEGER NOT NULL,
        space TEXT NOT NULL,                -- visual | text | audio
        dim INTEGER NOT NULL,
        vec BLOB NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE INDEX vectors_space ON vectors(space, id);
    CREATE INDEX vectors_shot ON vectors(shot_id, space);
    CREATE INDEX vectors_asset ON vectors(asset_id, space);

    -- Admin extensions to the controlled vocabularies.
    CREATE TABLE vocab_terms (
        vocab TEXT NOT NULL, term TEXT NOT NULL,
        label TEXT NOT NULL, definition TEXT NOT NULL DEFAULT '',
        synonyms TEXT NOT NULL DEFAULT '[]', broader TEXT,
        created_by TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL,
        PRIMARY KEY (vocab, term)
    );
    """,
    # ---------------------------------------------------------------- v2: search performance at scale
    """
    CREATE INDEX st_conf ON shot_terms(vocab, term, confidence DESC);
    CREATE VIRTUAL TABLE shot_fts_vocab USING fts5vocab(shot_fts, 'row');
    """,
    # ---------------------------------------------------------------- v3: incremental vector index maintenance
    # Monotonic vector ids (never reused) plus a deletion log, so the ANN cache removes exactly the
    # deleted keys instead of rebuilding when an asset is re-analysed.
    """
    CREATE TABLE vectors_v3 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shot_id INTEGER NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
        asset_id INTEGER NOT NULL,
        space TEXT NOT NULL,
        dim INTEGER NOT NULL,
        vec BLOB NOT NULL,
        created_at REAL NOT NULL
    );
    INSERT INTO vectors_v3(id, shot_id, asset_id, space, dim, vec, created_at) SELECT id, shot_id, asset_id, space, dim, vec, created_at FROM vectors;
    DROP TABLE vectors;
    ALTER TABLE vectors_v3 RENAME TO vectors;
    CREATE INDEX vectors_space ON vectors(space, id);
    CREATE INDEX vectors_shot ON vectors(shot_id, space);
    CREATE INDEX vectors_asset ON vectors(asset_id, space);
    CREATE TABLE vector_deletes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vector_id INTEGER NOT NULL,
        space TEXT NOT NULL
    );
    CREATE INDEX vector_deletes_space ON vector_deletes(space, id);
    CREATE TRIGGER vectors_deleted AFTER DELETE ON vectors BEGIN INSERT INTO vector_deletes(vector_id, space) VALUES(old.id, old.space); END;
    """,
    # ---------------------------------------------------------------- v4: browse order without a sort
    """
    CREATE INDEX si_browse ON shot_index(asset_id, start_s);
    """,
]


def dumps(v: Any) -> str:
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def _json_default(o: Any) -> Any:
    try:
        import numpy as np

        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:  # pragma: no cover
        pass
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serialisable: {type(o)}")


def loads(s: str | bytes | None, default: Any = None) -> Any:
    if s is None or s == "":
        return default
    return json.loads(s)


class Database:
    """Thread-safe-ish wrapper: one connection per thread, WAL mode."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._local = threading.local()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=60, isolation_level=None, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=60000")
            conn.execute("PRAGMA cache_size=-65536")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA mmap_size=1073741824")
            self._local.conn = conn
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self.connect()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Write transaction. BEGIN IMMEDIATE so writers queue instead of deadlocking."""
        conn = self.conn
        if conn.in_transaction:  # nested: join the outer transaction
            yield conn
            return
        for attempt in range(50):
            try:
                conn.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError as e:  # pragma: no cover - contention
                if "locked" not in str(e) or attempt == 49:
                    raise
                time.sleep(0.05 * (attempt + 1))
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def q(self, sql: str, params: Any = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def q1(self, sql: str, params: Any = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def x(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def migrate(self) -> None:
        conn = self.conn
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        current = int(row[0]) if row else 0
        for i in range(current, len(MIGRATIONS)):
            with self.tx() as c:
                for stmt in _split_sql(MIGRATIONS[i]):
                    c.execute(stmt)
                c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)", (str(i + 1),))
        # Keep planner statistics fresh (sampled, so this stays fast on large libraries).
        conn.execute("PRAGMA analysis_limit=1000")
        conn.execute("PRAGMA optimize")

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        r = self.q1("SELECT value FROM meta WHERE key=?", (key,))
        return r[0] if r else default

    def set_meta(self, key: str, value: str) -> None:
        self.x("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, value))


def _split_sql(script: str) -> list[str]:
    """Split a migration into statements (no semicolons inside our literals)."""
    out, buf = [], []
    for line in script.splitlines():
        stripped = line.split("--", 1)[0] if "--" in line else line
        buf.append(stripped)
        if stripped.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt.strip(";").strip():
                out.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def now() -> float:
    return time.time()
