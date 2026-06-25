"""SQLite storage per empresa (D-003, D-016, plan.md E1 schema)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

# Single source of truth for the empresa.db schema in E1.
SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS empresa_info (
  nit            TEXT NOT NULL,
  dv             TEXT,
  razon_social   TEXT NOT NULL,
  default_folder TEXT,
  pdfs_folder    TEXT,
  archived       INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS excel_load (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path  TEXT NOT NULL,
  source_name  TEXT NOT NULL,
  loaded_at    TEXT NOT NULL DEFAULT (datetime('now')),
  total_rows   INTEGER NOT NULL,
  sheet_name   TEXT
);

CREATE TABLE IF NOT EXISTS excel_row (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  load_id      INTEGER NOT NULL REFERENCES excel_load(id) ON DELETE CASCADE,
  row_index    INTEGER NOT NULL,
  cufe_cude    TEXT,
  grupo        TEXT,
  tipo_doc     TEXT,
  data_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_excel_row_load ON excel_row(load_id);
CREATE INDEX IF NOT EXISTS idx_excel_row_cufe ON excel_row(cufe_cude);

CREATE TABLE IF NOT EXISTS validation_rule (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,
  description     TEXT,
  type            TEXT NOT NULL,
  scope_json      TEXT,
  params_json     TEXT NOT NULL,
  failure_message TEXT NOT NULL,
  severity        TEXT NOT NULL DEFAULT 'error',
  enabled         INTEGER NOT NULL DEFAULT 1,
  vigencia_desde  TEXT,
  vigencia_hasta  TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS validation_run (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  load_id       INTEGER NOT NULL REFERENCES excel_load(id) ON DELETE CASCADE,
  started_at    TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at   TEXT,
  total_rows    INTEGER,
  failing_rows  INTEGER,
  notes         TEXT
);

CREATE TABLE IF NOT EXISTS validation_failure (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id         INTEGER NOT NULL REFERENCES validation_run(id) ON DELETE CASCADE,
  rule_id        INTEGER REFERENCES validation_rule(id) ON DELETE SET NULL,
  row_index      INTEGER NOT NULL,
  cufe_cude      TEXT,
  column_name    TEXT,
  value_snapshot TEXT,
  rule_severity  TEXT,
  reason         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_failure_run_row ON validation_failure(run_id, row_index);

-- D-046: manual override per (load, row, validation_code). The presence of a
-- row here means "el contador aprobó esta fila manualmente — no marcarla como
-- no conforme para este código de validación". Por ahora solo 'V3' se usa.
CREATE TABLE IF NOT EXISTS validation_override (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  load_id         INTEGER NOT NULL REFERENCES excel_load(id) ON DELETE CASCADE,
  row_index       INTEGER NOT NULL,
  validation_code TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(load_id, row_index, validation_code)
);
CREATE INDEX IF NOT EXISTS idx_validation_override_load ON validation_override(load_id);

-- Empty in E1, populated in E4.
CREATE TABLE IF NOT EXISTS pdf_cufe_index (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  folder_path       TEXT NOT NULL,
  pdf_path          TEXT NOT NULL,
  pdf_mtime         INTEGER NOT NULL,
  pdf_size_bytes    INTEGER NOT NULL,
  extraction_status TEXT NOT NULL,
  extraction_error  TEXT,
  indexed_at        TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(folder_path, pdf_path)
);

CREATE TABLE IF NOT EXISTS pdf_cufe_value (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  pdf_index_id INTEGER NOT NULL REFERENCES pdf_cufe_index(id) ON DELETE CASCADE,
  cufe_cude    TEXT NOT NULL,
  label        TEXT,
  UNIQUE(pdf_index_id, cufe_cude)
);
CREATE INDEX IF NOT EXISTS idx_pdf_cufe_value_hex ON pdf_cufe_value(cufe_cude);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent migrations for older empresa.db files."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(empresa_info)").fetchall()}
    if "default_folder" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN default_folder TEXT")
    if "pdfs_folder" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN pdfs_folder TEXT")
    if "archived" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply CREATE-IF-NOT-EXISTS schema + migrations. Safe on existing DBs.
    Caller MUST NOT be inside a transaction — executescript commits."""
    conn.executescript(SCHEMA_SQL)
    _run_migrations(conn)
    existing = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    if existing == 0:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))


def init_empresa_db(db_path: str | Path, nit: str, dv: str | None, razon_social: str) -> None:
    """Create + populate empresa_info. Idempotent against existing schema."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        with transaction(conn):
            empresa_count = conn.execute("SELECT COUNT(*) FROM empresa_info").fetchone()[0]
            if empresa_count == 0:
                conn.execute(
                    "INSERT INTO empresa_info(nit, dv, razon_social) VALUES (?, ?, ?)",
                    (nit, dv, razon_social),
                )
    finally:
        conn.close()


def read_empresa_info(db_path: str | Path) -> dict | None:
    """Return {nit, dv, razon_social, default_folder, pdfs_folder, archived, created_at}."""
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT nit, dv, razon_social, default_folder, pdfs_folder, archived, created_at "
            "FROM empresa_info LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["archived"] = bool(data.get("archived", 0))
        return data
    finally:
        conn.close()


def update_razon_social(db_path: str | Path, razon_social: str) -> None:
    """D-041 — only razon_social is editable. NIT/DV stay immutable."""
    cleaned = (razon_social or "").strip()
    if not cleaned:
        raise ValueError("razon_social no puede quedar vacía")
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        with transaction(conn):
            conn.execute("UPDATE empresa_info SET razon_social = ?", (cleaned,))
    finally:
        conn.close()


def set_archived(db_path: str | Path, archived: bool) -> None:
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        with transaction(conn):
            conn.execute("UPDATE empresa_info SET archived = ?", (1 if archived else 0,))
    finally:
        conn.close()


def wal_checkpoint(db_path: str | Path) -> None:
    """Flush any pending WAL pages into the main .db so the file can be copied."""
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def list_overrides(conn: sqlite3.Connection, load_id: int, code: str = "V3") -> set[int]:
    """D-046 — return the set of row_index that have a manual override."""
    rows = conn.execute(
        "SELECT row_index FROM validation_override WHERE load_id = ? AND validation_code = ?",
        (load_id, code),
    ).fetchall()
    return {r["row_index"] for r in rows}


def toggle_override(
    conn: sqlite3.Connection,
    load_id: int,
    row_index: int,
    code: str,
    active: bool,
) -> None:
    """Insert (active=True) or delete (active=False) the override row."""
    if active:
        conn.execute(
            "INSERT OR IGNORE INTO validation_override(load_id, row_index, validation_code) "
            "VALUES (?, ?, ?)",
            (load_id, row_index, code),
        )
    else:
        conn.execute(
            "DELETE FROM validation_override "
            "WHERE load_id = ? AND row_index = ? AND validation_code = ?",
            (load_id, row_index, code),
        )


def set_default_folder(db_path: str | Path, folder: str | None) -> None:
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        normalized = (folder or "").strip() or None
        with transaction(conn):
            conn.execute("UPDATE empresa_info SET default_folder = ?", (normalized,))
    finally:
        conn.close()


def set_pdfs_folder(db_path: str | Path, folder: str | None) -> None:
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        normalized = (folder or "").strip() or None
        with transaction(conn):
            conn.execute("UPDATE empresa_info SET pdfs_folder = ?", (normalized,))
    finally:
        conn.close()
