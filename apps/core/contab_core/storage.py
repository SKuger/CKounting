"""SQLite storage per empresa (D-003, D-016, plan.md E1 schema)."""
from __future__ import annotations

import re
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
  sheet_name   TEXT,
  periodo      TEXT,          -- 'YYYY-MM' dominante del lote (0.1.4)
  deleted_at   TEXT           -- papelera (soft-delete) del lote (0.1.4)
);

CREATE TABLE IF NOT EXISTS excel_row (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  load_id      INTEGER NOT NULL REFERENCES excel_load(id) ON DELETE CASCADE,
  row_index    INTEGER NOT NULL,
  cufe_cude    TEXT,
  grupo        TEXT,
  tipo_doc     TEXT,
  data_json    TEXT NOT NULL,
  periodo      TEXT,          -- 'YYYY-MM' de la fila; movible entre meses (0.1.4)
  deleted_at   TEXT           -- papelera (soft-delete) de la fila (0.1.4)
);
CREATE INDEX IF NOT EXISTS idx_excel_row_load ON excel_row(load_id);
CREATE INDEX IF NOT EXISTS idx_excel_row_cufe ON excel_row(cufe_cude);

-- 0.1.4: carpeta de soportes (PDFs) por periodo (mes). La validación V1 de un lote
-- cruza sus CUFE contra la carpeta del periodo del lote (fallback: empresa_info.pdfs_folder).
CREATE TABLE IF NOT EXISTS periodo_folder (
  periodo     TEXT PRIMARY KEY,
  pdfs_folder TEXT
);

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


def _backfill_row_periodo(conn: sqlite3.Connection) -> None:
    """One-time: derive excel_row.periodo ('YYYY-MM') from data_json 'Fecha Emisión'."""
    import json as _json

    updates: list[tuple[str, int]] = []
    for r in conn.execute("SELECT id, data_json FROM excel_row WHERE periodo IS NULL").fetchall():
        try:
            d = _json.loads(r["data_json"])
        except Exception:
            continue
        fe = d.get("Fecha Emisión")
        if isinstance(fe, str) and len(fe) >= 7:
            updates.append((fe[:7], r["id"]))
    if updates:
        conn.executemany("UPDATE excel_row SET periodo = ? WHERE id = ?", updates)


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent migrations for older empresa.db files."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(empresa_info)").fetchall()}
    if "default_folder" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN default_folder TEXT")
    if "pdfs_folder" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN pdfs_folder TEXT")
    if "archived" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")

    # 0.1.4 — periodo (mes) + papelera (soft-delete) sobre excel_row / excel_load.
    row_cols = {r["name"] for r in conn.execute("PRAGMA table_info(excel_row)").fetchall()}
    if "deleted_at" not in row_cols:
        conn.execute("ALTER TABLE excel_row ADD COLUMN deleted_at TEXT")
    if "periodo" not in row_cols:
        conn.execute("ALTER TABLE excel_row ADD COLUMN periodo TEXT")
        _backfill_row_periodo(conn)
    # índice del periodo: aquí (no en SCHEMA_SQL) porque la columna puede acabar de
    # crearse por ALTER; IF NOT EXISTS lo hace idempotente para BD nuevas y viejas.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_excel_row_periodo ON excel_row(periodo)")

    load_cols = {r["name"] for r in conn.execute("PRAGMA table_info(excel_load)").fetchall()}
    if "deleted_at" not in load_cols:
        conn.execute("ALTER TABLE excel_load ADD COLUMN deleted_at TEXT")
    if "periodo" not in load_cols:
        conn.execute("ALTER TABLE excel_load ADD COLUMN periodo TEXT")
        # periodo del lote = el mes más frecuente entre sus filas.
        conn.execute(
            """
            UPDATE excel_load SET periodo = (
              SELECT er.periodo FROM excel_row er
              WHERE er.load_id = excel_load.id AND er.periodo IS NOT NULL
              GROUP BY er.periodo ORDER BY COUNT(*) DESC LIMIT 1
            ) WHERE periodo IS NULL
            """
        )


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


# ── 0.1.4: MESES (periodos) como contenedor + carpeta de soportes por mes ──────
# El mes es el contenedor: se crea un mes y dentro se carga SU Excel y se elige SU
# carpeta de soportes. NO hay carpeta de soportes global. No se opera a nivel de
# fila (la tabla del Excel no cambia); lo movible/borrable es el Excel cargado.

def _norm_periodo(periodo: str) -> str:
    p = (periodo or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}", p):
        raise ValueError("El periodo debe tener el formato AAAA-MM (p. ej. 2026-05).")
    return p


def create_periodo(db_path: str | Path, periodo: str) -> dict:
    """Crea un mes (ambiente) vacío. Idempotente."""
    p = _norm_periodo(periodo)
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        with transaction(conn):
            conn.execute("INSERT OR IGNORE INTO periodo_folder(periodo) VALUES (?)", (p,))
    finally:
        conn.close()
    return {"periodo": p}


def periodo_pdfs_folder(conn: sqlite3.Connection, periodo: str | None) -> str | None:
    """Carpeta de soportes DEL MES. Sin fallback global (0.1.4: no hay carpeta global)."""
    if not periodo:
        return None
    row = conn.execute(
        "SELECT pdfs_folder FROM periodo_folder WHERE periodo = ?", (periodo,)
    ).fetchone()
    return row["pdfs_folder"] if row else None


def set_periodo_folder(db_path: str | Path, periodo: str, folder: str | None) -> dict:
    """Carpeta de soportes del mes. El mes queda creado aunque se limpie la carpeta."""
    p = _norm_periodo(periodo)
    normalized = (folder or "").strip() or None
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        with transaction(conn):
            conn.execute(
                "INSERT INTO periodo_folder(periodo, pdfs_folder) VALUES (?, ?) "
                "ON CONFLICT(periodo) DO UPDATE SET pdfs_folder = excluded.pdfs_folder",
                (p, normalized),
            )
    finally:
        conn.close()
    return {"periodo": p, "pdfs_folder": normalized}


def list_periodos(db_path: str | Path, include_deleted: bool = False) -> list[dict]:
    """Meses de la empresa: los creados (periodo_folder) ∪ los que ya tienen Excel.
    Incluye meses creados aún sin Excel. Conteos a nivel de LOTE (Excel)."""
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        del_filter = "" if include_deleted else "AND deleted_at IS NULL"
        months: set[str] = {
            r["periodo"] for r in conn.execute("SELECT periodo FROM periodo_folder").fetchall()
        }
        for r in conn.execute(
            f"SELECT DISTINCT periodo FROM excel_load WHERE periodo IS NOT NULL {del_filter}"
        ).fetchall():
            months.add(r["periodo"])
        folders = {
            r["periodo"]: r["pdfs_folder"]
            for r in conn.execute("SELECT periodo, pdfs_folder FROM periodo_folder").fetchall()
        }
        out = []
        for p in months:
            agg = conn.execute(
                f"SELECT COUNT(*) AS lc, COALESCE(SUM(total_rows), 0) AS rc "
                f"FROM excel_load WHERE periodo = ? {del_filter}",
                (p,),
            ).fetchone()
            out.append({
                "periodo": p,
                "load_count": agg["lc"],
                "row_count": agg["rc"],
                "pdfs_folder": folders.get(p),
            })
        out.sort(key=lambda d: d["periodo"], reverse=True)
        return out
    finally:
        conn.close()


def delete_periodo(db_path: str | Path, periodo: str) -> dict:
    """Borra el mes y su(s) Excel (hard delete; cascada a filas/validaciones)."""
    p = _norm_periodo(periodo)
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        with transaction(conn):
            conn.execute("DELETE FROM excel_load WHERE periodo = ?", (p,))
            conn.execute("DELETE FROM periodo_folder WHERE periodo = ?", (p,))
    finally:
        conn.close()
    return {"periodo": p, "deleted": True}


def set_load_periodo(db_path: str | Path, load_id: int, periodo: str) -> dict:
    """Mover el Excel cargado a otro mes (crea el mes destino si no existe)."""
    p = _norm_periodo(periodo)
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        with transaction(conn):
            conn.execute("INSERT OR IGNORE INTO periodo_folder(periodo) VALUES (?)", (p,))
            conn.execute("UPDATE excel_load SET periodo = ? WHERE id = ?", (p, int(load_id)))
    finally:
        conn.close()
    return {"load_id": int(load_id), "periodo": p}


def _set_load_deleted(db_path, load_id, deleted: bool) -> None:
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        value = "datetime('now')" if deleted else "NULL"
        with transaction(conn):
            conn.execute(f"UPDATE excel_load SET deleted_at = {value} WHERE id = ?", (int(load_id),))
    finally:
        conn.close()


def soft_delete_load(db_path: str | Path, load_id: int) -> dict:
    _set_load_deleted(db_path, load_id, True)
    return {"load_id": int(load_id), "deleted": True}


def restore_load(db_path: str | Path, load_id: int) -> dict:
    _set_load_deleted(db_path, load_id, False)
    return {"load_id": int(load_id), "deleted": False}
