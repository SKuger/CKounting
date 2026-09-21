"""SQLite storage per empresa (D-003, D-016, plan.md E1 schema)."""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from . import log

SCHEMA_VERSION = 4

# Cuánto espera una escritura a que se libere el lock antes de rendirse (ms).
BUSY_TIMEOUT_MS = 5_000

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
  data_json    TEXT NOT NULL,   -- fila COMPLETA, fuente de verdad (D-039)
  periodo      TEXT,          -- 'YYYY-MM' de la fila (0.1.4)
  -- D-091: proyección de los campos consultables, para poder sumar, agrupar y
  -- filtrar en SQL sin cargar el lote entero a memoria. Los importes van en
  -- CENTAVOS como INTEGER: suman exacto (un REAL reintroduciría el binario que
  -- evitamos en D-075; un TEXT no suma).
  total_centavos INTEGER,
  iva_centavos   INTEGER,
  nit_emisor     TEXT,
  fecha_emision  TEXT
  -- D-085: no hay papelera POR FILA. La que existe es la del LOTE
  -- (excel_load.deleted_at). La columna `deleted_at` de aquí nunca se escribió.
);
CREATE INDEX IF NOT EXISTS idx_excel_row_load ON excel_row(load_id);
CREATE INDEX IF NOT EXISTS idx_excel_row_cufe ON excel_row(cufe_cude);
-- Los índices de las columnas nuevas NO van aquí: en una BD antigua la tabla ya
-- existe sin ellas (CREATE TABLE IF NOT EXISTS no las añade) y el índice falla.
-- Se crean en la migración que añade las columnas, igual que idx_excel_row_periodo.

-- 0.1.4: carpeta de soportes (PDFs) por periodo (mes). La validación V1 de un lote
-- cruza sus CUFE contra la carpeta del periodo del lote (fallback: empresa_info.pdfs_folder).
CREATE TABLE IF NOT EXISTS periodo_folder (
  periodo     TEXT PRIMARY KEY,
  pdfs_folder TEXT
);

-- D-085: aquí vivía `validation_rule`, un motor de reglas con vigencias que
-- NUNCA se implementó (ninguna línea la leía ni la escribía). Las validaciones
-- V1/V2/V3 están en validations.py. Si algún día se hace el motor de verdad,
-- esta tabla vuelve con una migración numerada.

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
  extractor_version INTEGER NOT NULL DEFAULT 0,  -- bumped when the algorithm improves → old entries re-extract (D-067)
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

-- Plan Único de Cuentas (PUC) — a nivel EMPRESA (E5, D-070). Se sube un dump Excel
-- que hace upsert por 'codigo' (fusionar): las cuentas manuales que no vienen en el
-- dump se conservan. 'fuente' distingue dump vs manual; 'archived' es soft-hide.
CREATE TABLE IF NOT EXISTS puc_account (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo              TEXT NOT NULL,
  nombre              TEXT NOT NULL DEFAULT '',
  categoria           TEXT,
  clase               TEXT,
  relacion_con        TEXT,
  maneja_vencimientos TEXT,
  diferencia_fiscal   TEXT,
  activo              INTEGER NOT NULL DEFAULT 1,     -- Sí/No del Excel → 1/0
  nivel_agrupacion    TEXT,                            -- 'Transaccional' | 'Agrupación' | ...
  nivel               INTEGER NOT NULL DEFAULT 1,      -- 1..N derivado de la longitud del código
  fuente              TEXT NOT NULL DEFAULT 'manual',  -- 'dump' | 'manual'
  archived            INTEGER NOT NULL DEFAULT 0,
  created_at          TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(codigo)
);
CREATE INDEX IF NOT EXISTS idx_puc_account_nivel ON puc_account(nivel);
CREATE INDEX IF NOT EXISTS idx_puc_account_clase ON puc_account(clase);
CREATE INDEX IF NOT EXISTS idx_puc_account_archived ON puc_account(archived);

-- Historial de dumps de PUC importados (auditoría del cruce empresa/NIT).
CREATE TABLE IF NOT EXISTS puc_import (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT,
  excel_nit   TEXT,
  excel_razon TEXT,
  total_rows  INTEGER NOT NULL DEFAULT 0,
  inserted    INTEGER NOT NULL DEFAULT 0,
  updated     INTEGER NOT NULL DEFAULT 0,
  imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Perfil fiscal de la empresa (Fase 1.1 del plan de automatización).
-- Es una LISTA de versiones fechadas, no una fila: las responsabilidades cambian
-- (a alguien lo nombran autorretenedor en agosto) y la contabilidad de marzo no
-- puede recalcularse con lo que la empresa es hoy. Se lee la vigente a una fecha.
CREATE TABLE IF NOT EXISTS empresa_perfil_fiscal (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  vigencia_desde       TEXT NOT NULL,                      -- 'AAAA-MM-DD'
  regimen              TEXT NOT NULL DEFAULT 'ordinario',  -- 'ordinario' | 'simple'
  responsable_iva      INTEGER NOT NULL DEFAULT 0,
  periodicidad_iva     TEXT,                               -- 'bimestral' | 'cuatrimestral' | NULL
  agente_retefuente    INTEGER NOT NULL DEFAULT 0,
  agente_reteiva       INTEGER NOT NULL DEFAULT 0,
  agente_reteica       INTEGER NOT NULL DEFAULT 0,
  autorretenedor_renta INTEGER NOT NULL DEFAULT 0,
  gran_contribuyente   INTEGER NOT NULL DEFAULT 0,
  ciiu                 TEXT,
  notas                TEXT,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(vigencia_desde)
);

-- Municipios donde la empresa declara ICA, con su tarifa. El ICA es municipal:
-- la misma empresa retiene a tarifas distintas en municipios distintos.
-- La tarifa va como TEXT y se lee con Decimal (D-075: nada de float en importes).
CREATE TABLE IF NOT EXISTS empresa_municipio_ica (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  municipio      TEXT NOT NULL,
  codigo_dane    TEXT,
  actividad      TEXT,
  tarifa_por_mil TEXT NOT NULL,
  vigencia_desde TEXT NOT NULL,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(municipio, actividad, vigencia_desde)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Sin esto, cualquier escritura que coincida con otra en curso falla al instante
    # con "database is locked" en vez de esperar su turno. Con WAL y varias
    # conexiones (indexado + consulta) es un choque normal, no un error.
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
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
            log.warn("data_json ilegible en excel_row id=%s; se omite del backfill", r["id"])
            continue
        fe = d.get("Fecha Emisión")
        if isinstance(fe, str) and len(fe) >= 7:
            updates.append((fe[:7], r["id"]))
    if updates:
        conn.executemany("UPDATE excel_row SET periodo = ? WHERE id = ?", updates)


def _m001_columnas_anteriores(conn: sqlite3.Connection) -> None:
    """Migración 1 — columnas añadidas entre 0.1.0 y 0.2.1, sin versionar.

    Se conserva tal cual (a base de `PRAGMA table_info` + ALTER idempotentes)
    porque es lo que ya corrió en las BD instaladas: reescribirla cambiaría el
    resultado para alguien. Las migraciones NUEVAS van numeradas (D-084)."""
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

    # 0.1.6 (D-067) — extractor_version en pdf_cufe_index: entradas cacheadas por
    # el extractor viejo (version 0) se re-extraen al subir pdf_cufe.EXTRACTOR_VERSION.
    idx_cols = {r["name"] for r in conn.execute("PRAGMA table_info(pdf_cufe_index)").fetchall()}
    if "extractor_version" not in idx_cols:
        conn.execute("ALTER TABLE pdf_cufe_index ADD COLUMN extractor_version INTEGER NOT NULL DEFAULT 0")

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


def _m002_esquema_muerto(conn: sqlite3.Connection) -> None:
    """Migración 2 — retira el esquema que describía un sistema inexistente (D-085).

    - `validation_rule`: tabla completa con `severity`, `vigencia_desde/hasta` y
      `params_json` que NADA leía ni escribía. Las reglas están en Python con dos
      tarifas fijas. Prometía un motor de reglas con vigencias que no existe.
    - `validation_failure.rule_id`: la clave foránea que la apuntaba.
    - `excel_row.deleted_at`: papelera por fila que nunca se implementó (la que sí
      funciona es la del LOTE, `excel_load.deleted_at`). Peor que inútil: si algún
      día se filtrara por ella en `fetch_load_rows`, el `enumerate(rows)` de
      validations dejaría de coincidir con el `row_index` de los overrides y las
      aprobaciones manuales se aplicarían a filas equivocadas.

    Solo se borra si están VACÍAS/sin usar: si alguien tuviera datos ahí, se deja
    y se avisa, en vez de destruirlos.
    """
    tablas = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "validation_rule" in tablas:
        n = conn.execute("SELECT COUNT(*) FROM validation_rule").fetchone()[0]
        if n:
            log.warn("validation_rule tiene %s filas: no se borra (esquema muerto D-085)", n)
        else:
            # Hay que soltar primero la FK, que vive en validation_failure.
            _rebuild_validation_failure_sin_rule_id(conn)
            conn.execute("DROP TABLE validation_rule")

    row_cols = {r["name"] for r in conn.execute("PRAGMA table_info(excel_row)").fetchall()}
    if "deleted_at" in row_cols:
        usados = conn.execute(
            "SELECT COUNT(*) FROM excel_row WHERE deleted_at IS NOT NULL"
        ).fetchone()[0]
        if usados:
            log.warn("excel_row.deleted_at tiene %s filas marcadas: no se borra", usados)
        else:
            conn.execute("ALTER TABLE excel_row DROP COLUMN deleted_at")


def _rebuild_validation_failure_sin_rule_id(conn: sqlite3.Connection) -> None:
    """Recrea validation_failure sin la columna `rule_id`.

    SQLite no permite quitar una columna con clave foránea mediante ALTER, así que
    toca el ciclo tabla nueva → copiar → renombrar."""
    conn.executescript(
        """
        CREATE TABLE validation_failure_nueva (
          id             INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id         INTEGER NOT NULL REFERENCES validation_run(id) ON DELETE CASCADE,
          row_index      INTEGER NOT NULL,
          cufe_cude      TEXT,
          column_name    TEXT,
          value_snapshot TEXT,
          rule_severity  TEXT,
          reason         TEXT NOT NULL
        );
        INSERT INTO validation_failure_nueva
          (id, run_id, row_index, cufe_cude, column_name, value_snapshot, rule_severity, reason)
          SELECT id, run_id, row_index, cufe_cude, column_name, value_snapshot, rule_severity, reason
          FROM validation_failure;
        DROP TABLE validation_failure;
        ALTER TABLE validation_failure_nueva RENAME TO validation_failure;
        CREATE INDEX IF NOT EXISTS idx_failure_run_row ON validation_failure(run_id, row_index);
        """
    )


COLUMNAS_CONSULTABLES = """
ALTER TABLE excel_row ADD COLUMN total_centavos  INTEGER;
ALTER TABLE excel_row ADD COLUMN iva_centavos    INTEGER;
ALTER TABLE excel_row ADD COLUMN nit_emisor      TEXT;
ALTER TABLE excel_row ADD COLUMN fecha_emision   TEXT;
CREATE INDEX IF NOT EXISTS idx_excel_row_nit_emisor ON excel_row(nit_emisor);
CREATE INDEX IF NOT EXISTS idx_excel_row_fecha ON excel_row(fecha_emision);
"""


def _m004_perfil_fiscal(conn: sqlite3.Connection) -> None:
    """Migración 4 — perfil fiscal de la empresa y sus municipios de ICA.

    Las dos tablas se declaran en SCHEMA_SQL con `IF NOT EXISTS`, así que el
    `executescript` de `ensure_schema` ya las crea tanto en una BD nueva como en
    una que venía de la 3. Esta entrada existe porque la versión del esquema solo
    avanza DENTRO del bucle de MIGRACIONES: sin ella, `SCHEMA_VERSION = 4` no se
    escribiría nunca y `ensure_schema` volvería a ejecutar el esquema entero en
    cada llamada RPC — justo la regresión que D-084 arregló.

    No hay backfill: el perfil fiscal es información que solo tiene el contador.
    Una empresa sin perfil se comporta exactamente como antes de esta migración.
    """
    return None


def _m003_columnas_consultables(conn: sqlite3.Connection) -> None:
    """Migración 3 — saca de `data_json` los campos que hay que consultar (D-091).

    Toda la fila del Excel vivía como un blob JSON, así que no se podía sumar,
    agrupar ni filtrar en SQL: cualquier total pasaba por cargar el lote entero a
    memoria en Python. Eso bloquea cualquier reporte agregado, comparar meses o
    prácticamente lo que un contador pida de verdad.

    `data_json` sigue siendo la fuente de verdad de la fila completa (D-039: no se
    renombran los headers de la DIAN). Estas columnas son una proyección de los
    campos consultables, que se rellena al persistir.

    Los importes van en **centavos como INTEGER**: suman exacto en SQL. Un REAL
    reintroduciría el binario del que salimos en D-075 y un TEXT no suma.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(excel_row)").fetchall()}
    if "total_centavos" not in cols:
        conn.executescript(COLUMNAS_CONSULTABLES)

    # Backfill desde data_json de lo ya cargado.
    import json as _json

    from . import money as _money

    updates: list[tuple] = []
    for r in conn.execute(
        "SELECT id, data_json FROM excel_row WHERE total_centavos IS NULL"
    ).fetchall():
        try:
            d = _json.loads(r["data_json"])
        except Exception:
            log.warn("data_json ilegible en excel_row id=%s; sin columnas consultables", r["id"])
            continue
        try:
            total = _money.a_centavos(_money.to_money(d.get("Total") or 0))
            iva = _money.a_centavos(_money.to_money(d.get("IVA") or 0))
        except ValueError:
            total = iva = None
        updates.append((total, iva, d.get("NIT Emisor"), d.get("Fecha Emisión"), r["id"]))

    if updates:
        conn.executemany(
            "UPDATE excel_row SET total_centavos = ?, iva_centavos = ?, nit_emisor = ?,"
            " fecha_emision = ? WHERE id = ?",
            updates,
        )
        log.info("columnas consultables rellenadas en %s filas", len(updates))


# Migraciones NUMERADAS. Cada una lleva su número y corre una sola vez, en orden.
# Añadir una: escribir la función, ponerla aquí y subir SCHEMA_VERSION.
MIGRACIONES: list[tuple[int, object]] = [
    (1, _m001_columnas_anteriores),
    (2, _m002_esquema_muerto),
    (3, _m003_columnas_consultables),
    (4, _m004_perfil_fiscal),
]


class EsquemaMasNuevoQueLaApp(RuntimeError):
    """La BD la escribió una versión posterior de Contab."""


def _leer_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    except sqlite3.OperationalError:
        return 0  # BD nueva: la tabla aún no existe
    return int(row[0]) if row and row[0] is not None else 0


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Crea el esquema y aplica las migraciones pendientes (D-084).

    Caller MUST NOT be inside a transaction — executescript commits.

    Dos cosas que antes no hacía:

    1. **Bloquea el downgrade.** `SCHEMA_VERSION` llevaba en 1 desde el primer día
       pese a los cambios de 0.1.4, 0.1.6 y 0.2.0, y una versión vieja de la app
       abría una BD nueva y escribía tan tranquila. Con auto-update activo eso pasa.
    2. **Sale temprano si no hay nada que hacer.** Antes ejecutaba el `executescript`
       entero (decenas de DDL y PRAGMAs) y todos los `PRAGMA table_info` en CADA
       llamada RPC, o sea en cada clic.
    """
    version = _leer_version(conn)

    if version > SCHEMA_VERSION:
        raise EsquemaMasNuevoQueLaApp(
            f"Esta empresa fue abierta con una versión más reciente de Contab "
            f"(esquema {version}; esta versión entiende hasta {SCHEMA_VERSION}). "
            "Actualiza Contab para abrirla. No se modificó nada."
        )

    if version == SCHEMA_VERSION:
        return  # nada que hacer: el camino habitual

    conn.executescript(SCHEMA_SQL)
    for numero, migracion in MIGRACIONES:
        if numero > version:
            migracion(conn)  # type: ignore[operator]
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (numero,))
            log.info("empresa.db migrada al esquema %s", numero)


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
