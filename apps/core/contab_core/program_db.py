"""Program-level DB (contab.db) — app/user data that is cross-empresa.

Two-tier model (0.1.4): this global DB holds the user profile, app settings, and a
central registry of empresas (with room for firmas/correos/fechas). The heavy fiscal
data stays in one SQLite file per empresa (D-003 intact); the registry only REFERENCES
each empresa .db by path — it never mixes empresa data here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import paths, storage

PROGRAM_SCHEMA_VERSION = 1

PROGRAM_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS program_schema_version (
  version INTEGER PRIMARY KEY
);

-- Single-user (D-004): a single row (id = 1) holds the profile.
CREATE TABLE IF NOT EXISTS program_user (
  id         INTEGER PRIMARY KEY CHECK (id = 1),
  name       TEXT,
  email      TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS program_settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- Central catalog of empresas. Each row references a per-empresa .db by path.
-- meta_json is growth space for firmas/correos/fechas without a migration each time.
CREATE TABLE IF NOT EXISTS empresa_registry (
  empresa_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  db_path        TEXT NOT NULL UNIQUE,
  nit            TEXT,
  dv             TEXT,
  razon_social   TEXT,
  archived       INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  last_opened_at TEXT,
  meta_json      TEXT
);
"""


def _conn() -> sqlite3.Connection:
    conn = storage.connect(paths.program_db_path())
    ensure_program_schema(conn)
    return conn


def ensure_program_schema(conn: sqlite3.Connection) -> None:
    """Apply CREATE-IF-NOT-EXISTS schema. Safe/idempotent. Must not be inside a txn."""
    conn.executescript(PROGRAM_SCHEMA_SQL)
    if conn.execute("SELECT COUNT(*) FROM program_schema_version").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO program_schema_version(version) VALUES (?)",
            (PROGRAM_SCHEMA_VERSION,),
        )


# ── user ─────────────────────────────────────────────────────────────────────
def get_user() -> dict | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT name, email, created_at, updated_at FROM program_user WHERE id = 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_user(name: str | None = None, email: str | None = None) -> dict:
    """Upsert the single user row. Only provided fields change (partial update)."""
    n = (name or "").strip() or None
    e = (email or "").strip() or None
    conn = _conn()
    try:
        with storage.transaction(conn):
            conn.execute(
                """
                INSERT INTO program_user(id, name, email) VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  name       = COALESCE(excluded.name, program_user.name),
                  email      = COALESCE(excluded.email, program_user.email),
                  updated_at = datetime('now')
                """,
                (n, e),
            )
    finally:
        conn.close()
    return get_user() or {}


# ── settings ─────────────────────────────────────────────────────────────────
def get_settings() -> dict:
    conn = _conn()
    try:
        rows = conn.execute("SELECT key, value FROM program_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


def save_settings(patch: dict) -> dict:
    if not isinstance(patch, dict):
        raise ValueError("patch debe ser un objeto de ajustes")
    conn = _conn()
    try:
        with storage.transaction(conn):
            for k, v in patch.items():
                conn.execute(
                    "INSERT INTO program_settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(k), None if v is None else str(v)),
                )
    finally:
        conn.close()
    return get_settings()


# ── empresa registry ─────────────────────────────────────────────────────────
def register_empresa(
    db_path: str | Path,
    nit: str | None = None,
    dv: str | None = None,
    razon_social: str | None = None,
) -> int:
    """Idempotent upsert by db_path. Returns empresa_id."""
    p = str(db_path)
    conn = _conn()
    try:
        with storage.transaction(conn):
            conn.execute(
                """
                INSERT INTO empresa_registry(db_path, nit, dv, razon_social) VALUES (?, ?, ?, ?)
                ON CONFLICT(db_path) DO UPDATE SET
                  nit          = COALESCE(excluded.nit, empresa_registry.nit),
                  dv           = COALESCE(excluded.dv, empresa_registry.dv),
                  razon_social = COALESCE(excluded.razon_social, empresa_registry.razon_social)
                """,
                (p, nit, dv, razon_social),
            )
        row = conn.execute(
            "SELECT empresa_id FROM empresa_registry WHERE db_path = ?", (p,)
        ).fetchone()
        return int(row["empresa_id"])
    finally:
        conn.close()


def touch_empresa(db_path: str | Path) -> None:
    conn = _conn()
    try:
        with storage.transaction(conn):
            conn.execute(
                "UPDATE empresa_registry SET last_opened_at = datetime('now') WHERE db_path = ?",
                (str(db_path),),
            )
    finally:
        conn.close()


def set_registry_archived(db_path: str | Path, archived: bool) -> None:
    conn = _conn()
    try:
        with storage.transaction(conn):
            conn.execute(
                "UPDATE empresa_registry SET archived = ? WHERE db_path = ?",
                (1 if archived else 0, str(db_path)),
            )
    finally:
        conn.close()


def list_registry(include_archived: bool = False) -> list[dict]:
    conn = _conn()
    try:
        sql = (
            "SELECT empresa_id, db_path, nit, dv, razon_social, archived, created_at, "
            "last_opened_at FROM empresa_registry"
        )
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY razon_social COLLATE NOCASE"
        out = []
        for r in conn.execute(sql).fetchall():
            d = dict(r)
            d["archived"] = bool(d.get("archived", 0))
            out.append(d)
        return out
    finally:
        conn.close()


def unregister_empresa(db_path: str | Path) -> bool:
    """Saca una empresa del catálogo central. Devuelve True si había fila.

    Sin esto, `delete_empresa_file` borraba el .db pero dejaba su fila para
    siempre: el catálogo seguía anunciando empresas que ya no existen (D-077)."""
    conn = _conn()
    try:
        with storage.transaction(conn):
            cur = conn.execute("DELETE FROM empresa_registry WHERE db_path = ?", (str(db_path),))
        return cur.rowcount > 0
    finally:
        conn.close()


def sync_registry() -> dict:
    """Reconcilia el catálogo central con lo que hay en disco: registra los .db
    nuevos y PURGA las filas cuyo archivo ya no existe (D-077).

    Antes solo añadía, así que el catálogo solo podía divergir hacia arriba."""
    en_disco = {str(p) for p in paths.scan_empresa_dbs()}
    purged = 0
    conn = _conn()
    try:
        registradas = [r["db_path"] for r in conn.execute("SELECT db_path FROM empresa_registry")]
        huerfanas = [p for p in registradas if p not in en_disco and not Path(p).exists()]
        if huerfanas:
            with storage.transaction(conn):
                conn.executemany(
                    "DELETE FROM empresa_registry WHERE db_path = ?", [(p,) for p in huerfanas]
                )
            purged = len(huerfanas)
    finally:
        conn.close()

    registered = 0
    for db in paths.scan_empresa_dbs():
        info = None
        try:
            info = storage.read_empresa_info(db)
        except Exception:
            info = None
        register_empresa(
            db,
            nit=(info or {}).get("nit"),
            dv=(info or {}).get("dv"),
            razon_social=(info or {}).get("razon_social"),
        )
        registered += 1
    return {"registered": registered, "purged": purged}
