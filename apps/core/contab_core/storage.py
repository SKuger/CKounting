"""SQLite storage per empresa (D-003, D-016, plan.md E1 schema)."""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from . import log

SCHEMA_VERSION = 15

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
-- ── Fase 3: el XML como fuente de verdad ──────────────────────────────────────
-- El XML es una CAPA PEGADA al Excel, nunca su reemplazo (D-039, D-064). La tabla
-- que el contador reconoce sigue saliendo de `excel_row.data_json`; esto se le
-- añade por CUFE. Si se reemplazara, cada columna que él reconoce cambiaría de
-- sitio, y con ella la confianza que costó construir en E1.
CREATE TABLE IF NOT EXISTS xml_index (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  folder_path     TEXT NOT NULL,
  xml_path        TEXT NOT NULL,
  xml_mtime       INTEGER NOT NULL,
  xml_size_bytes  INTEGER NOT NULL,
  estado          TEXT NOT NULL,          -- ok | no_es_xml | sin_documento | error
  error           TEXT,
  parser_version  INTEGER NOT NULL DEFAULT 0,  -- al subirlo se re-lee lo viejo (D-067)
  indexed_at      TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(folder_path, xml_path)
);

CREATE TABLE IF NOT EXISTS documento (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  cufe            TEXT NOT NULL UNIQUE,
  tipo            TEXT NOT NULL,          -- factura | nota_credito | nota_debito
  numero          TEXT,
  fecha_emision   TEXT,
  hora_emision    TEXT,
  moneda          TEXT,
  emisor_nit      TEXT,
  emisor_nombre   TEXT,
  receptor_nit    TEXT,
  receptor_nombre TEXT,
  -- Lo que la FACTURA declara del emisor (cbc:TaxLevelCode del anexo DIAN).
  -- Es lo que el contador mira cuando no tiene el RUT del proveedor.
  emisor_responsabilidades TEXT,
  -- Los importes se guardan como TEXT a propósito: SQLite solo tiene REAL, y un
  -- REAL es float. Los lee `Decimal(texto)` sin perder un céntimo (D-075).
  subtotal        TEXT,
  total_impuestos TEXT,
  total           TEXT,
  xml_path        TEXT,
  parser_version  INTEGER NOT NULL DEFAULT 0,
  leido_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documento_linea (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  documento_id    INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
  numero          INTEGER NOT NULL,
  descripcion     TEXT,
  cantidad        TEXT,
  valor_unitario  TEXT,
  total           TEXT
);
CREATE INDEX IF NOT EXISTS ix_documento_linea_doc ON documento_linea(documento_id);

CREATE TABLE IF NOT EXISTS documento_impuesto (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  documento_id    INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
  linea_id        INTEGER REFERENCES documento_linea(id) ON DELETE CASCADE,
  tipo            TEXT NOT NULL,          -- código DIAN: 01 IVA, 06 ReteFuente…
  nombre          TEXT,
  base            TEXT,
  tarifa          TEXT,
  valor           TEXT,
  es_retencion    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_documento_impuesto_doc ON documento_impuesto(documento_id);

CREATE TABLE IF NOT EXISTS documento_referencia (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  documento_id    INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
  cufe_referido   TEXT,
  numero_referido TEXT,
  fecha_referida  TEXT,
  codigo_motivo   TEXT,
  motivo          TEXT
);
CREATE INDEX IF NOT EXISTS ix_documento_referencia_doc ON documento_referencia(documento_id);

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
-- ── Fase 4.1: los parámetros que son LEY y cambian por decreto ───────────────
-- Se importan del Excel del contador (D-102). Si los sembrara el programa, cada
-- enero habría que publicar una versión para cambiar un número, y quien no
-- actualizara liquidaría con las del año pasado sin enterarse.
CREATE TABLE IF NOT EXISTS uvt (
  anio        INTEGER PRIMARY KEY,
  valor       TEXT NOT NULL,        -- pesos. TEXT + Decimal: el REAL de SQLite es float (D-075)
  norma       TEXT,                 -- «Resolución DIAN 000238 de 2025» — la trazabilidad del número
  fuente      TEXT NOT NULL DEFAULT 'manual',   -- 'excel' | 'manual'
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Un concepto de retención por fila. El mismo concepto puede aparecer dos veces
-- con tarifas distintas según el tercero sea declarante o no: por eso la llave
-- incluye `aplica_a`.
CREATE TABLE IF NOT EXISTS retencion_concepto (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  concepto        TEXT NOT NULL,
  aplica_a        TEXT NOT NULL DEFAULT '',   -- 'declarantes' | 'no_declarantes' | 'ambos' | texto
  -- 'base'  → la tarifa se aplica sobre la base gravable (retefuente)
  -- 'iva'   → la tarifa se aplica sobre el IVA facturado (ReteIVA)
  -- Sin esta marca, ReteIVA se calcularía sobre la base y saldría mal.
  sobre           TEXT NOT NULL DEFAULT 'base',
  tarifa          TEXT,               -- porcentaje, p.ej. '11' = 11%. NULL si no es numérica
  tarifa_texto    TEXT,               -- lo que decía el Excel cuando no era un número
  base_minima_uvt TEXT,               -- NULL = no hay mínimo: se retiene desde el primer peso
  cuenta_puc      TEXT,
  codigo_siigo    TEXT,               -- el código de este impuesto en el catálogo de Siigo (D-128)
  vigencia_desde  TEXT,               -- 'AAAA-MM-DD'
  observaciones   TEXT,
  fuente          TEXT NOT NULL DEFAULT 'manual',   -- 'excel' | 'manual'
  archivado       INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(concepto, aplica_a, vigencia_desde)
);
CREATE INDEX IF NOT EXISTS ix_retencion_concepto_vig ON retencion_concepto(vigencia_desde);

CREATE TABLE IF NOT EXISTS tarifas_import (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name   TEXT NOT NULL,
  uvt_filas     INTEGER NOT NULL DEFAULT 0,
  conceptos     INTEGER NOT NULL DEFAULT 0,
  imported_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Fase 4.3: las reglas de causación ────────────────────────────────────────
-- «Cuando llega una factura de un proveedor nuevo, ¿qué mira para decidir la
-- cuenta?» → «LA FACTURA». Y aparte: hay proveedores que SIEMPRE van a la misma
-- cuenta pase lo que pase. De ahí las dos formas de regla y su orden.
--
-- SIN centro de costo (D-112): el contador respondió que no los usa.
-- ── Fase 4.4: la propuesta de asiento del mes ────────────────────────────────
-- Una cabecera por documento y sus líneas de débito y crédito. Es una PROPUESTA:
-- nada sale hacia Siigo hasta que el contador la apruebe (Fase 4.5).
CREATE TABLE IF NOT EXISTS asiento_propuesto (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  periodo       TEXT NOT NULL,
  cufe          TEXT NOT NULL,
  tercero_nit   TEXT,
  fecha         TEXT,
  -- 'completo'  se puede aprobar en lote
  -- 'revisar'   falta algo o hay una duda que el contador tiene que resolver
  estado        TEXT NOT NULL DEFAULT 'revisar',
  avisos        TEXT,                -- por qué hay que revisarlo, en su idioma
  regla_id      INTEGER,
  -- compra | venta | doc_soporte (D-127): qué líneas lleva y quién es el tercero
  naturaleza    TEXT NOT NULL DEFAULT 'compra',
  numero        TEXT,                -- el número del documento, como lo imprime (D-128)
  tipo_doc      TEXT,                -- factura | nota_credito
  siigo_consecutivo INTEGER,         -- el que se le dio al exportar; no cambia ni se repite
  aprobado      INTEGER NOT NULL DEFAULT 0,
  aprobado_at   TEXT,
  generado_at   TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(periodo, cufe)
);
CREATE INDEX IF NOT EXISTS ix_asiento_periodo ON asiento_propuesto(periodo);

CREATE TABLE IF NOT EXISTS asiento_linea (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  asiento_id    INTEGER NOT NULL REFERENCES asiento_propuesto(id) ON DELETE CASCADE,
  orden         INTEGER NOT NULL DEFAULT 0,
  cuenta_puc    TEXT,
  descripcion   TEXT,
  -- TEXT y Decimal: el REAL de SQLite es float y ahí se pierde el céntimo (D-075)
  debito        TEXT NOT NULL DEFAULT '0',
  credito       TEXT NOT NULL DEFAULT '0',
  rol           TEXT,                -- gasto | ingreso | iva | retencion | cartera (D-128)
  base          TEXT,                -- la base de una línea de impuesto o retención
  concepto_id   INTEGER,             -- el concepto de retención, para su código de Siigo
  codigo_siigo  TEXT                 -- el código de impuesto decidido para esta línea
);
CREATE INDEX IF NOT EXISTS ix_asiento_linea ON asiento_linea(asiento_id);
CREATE TABLE IF NOT EXISTS siigo_config (clave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS siigo_impuesto (
  codigo      TEXT NOT NULL,
  contexto    TEXT NOT NULL,   -- venta | compra | dev_venta | dev_compra
  nombre      TEXT,
  tipo        TEXT,
  tarifa      TEXT,
  cuenta      TEXT,
  descripcion TEXT,
  PRIMARY KEY (codigo, contexto)
);

CREATE TABLE IF NOT EXISTS regla_causacion (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  tercero_nit           TEXT,              -- NULL = cualquier proveedor
  patron                TEXT,              -- texto a buscar en la factura; NULL = cualquiera
  cuenta_puc            TEXT NOT NULL,     -- a dónde va el gasto
  concepto_retencion_id INTEGER REFERENCES retencion_concepto(id),
  -- 1 = «a este proveedor NO se le retiene», dicho a propósito. Hay que poder
  -- distinguirlo de «nadie lo ha dicho todavía»: lo primero se puede aprobar en
  -- lote, lo segundo hay que preguntarlo. Con un solo NULL no se distinguen, y
  -- confundirlos significa dejar de retener sin que nadie lo decida.
  sin_retencion         INTEGER NOT NULL DEFAULT 0,
  -- compra | venta | doc_soporte: la cuenta de una regla es de gasto o de ingreso
  naturaleza            TEXT NOT NULL DEFAULT 'compra',
  iva_codigo            TEXT,              -- qué IVA factura (código de Siigo), aprendido al aprobar
  vigencia_desde        TEXT,
  veces_usada           INTEGER NOT NULL DEFAULT 0,
  -- 'manual'    la escribió el contador
  -- 'aprendida' salió de una decisión suya en la bandeja de aprobación
  origen                TEXT NOT NULL DEFAULT 'manual',
  archivada             INTEGER NOT NULL DEFAULT 0,
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at            TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(tercero_nit, patron, vigencia_desde)
);
CREATE INDEX IF NOT EXISTS ix_regla_tercero ON regla_causacion(tercero_nit);

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
-- Bitácora de las ingestas desde el portal de la DIAN (Fase 2.5).
-- Qué se intentó, cuándo, por qué camino y cómo salió. El portal falla de formas
-- raras —mantenimiento, sesión vencida, bloqueo de seguridad— y sin registro cada
-- fallo se investiga desde cero.
-- `error` se guarda SIEMPRE enmascarado: el enlace de acceso no puede acabar aquí.
CREATE TABLE IF NOT EXISTS ingesta_run (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  periodo      TEXT NOT NULL,
  camino       TEXT NOT NULL,                 -- 'portal' | 'manual'
  estado       TEXT NOT NULL,                 -- 'ok' | 'error'
  documentos   INTEGER,
  archivo      TEXT,
  error        TEXT,
  empresa_dian TEXT,                          -- cómo se identificó el portal
  corrio_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ingesta_run_periodo ON ingesta_run(periodo);

-- Catálogo de terceros de la empresa (Fase 1.3). Vive DENTRO de la .db de cada
-- empresa y no en un catálogo central: D-100 descartó el caché compartido porque
-- habría necesitado una excepción escrita a D-003, y esa regla vale más que las
-- consultas ahorradas.
--
-- `responsabilidades` va como JSON (lista de códigos del RUT) igual que `data_json`
-- en excel_row: es una lista corta y variable, y una tabla aparte solo añadiría
-- dos joins sin darnos nada que consultar por separado.
CREATE TABLE IF NOT EXISTS tercero (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  nit               TEXT NOT NULL,
  dv                TEXT,
  razon_social      TEXT NOT NULL DEFAULT '',
  tipo              TEXT,                -- 'empresa' | 'persona' | NULL
  responsabilidades TEXT,                -- JSON: ["O-13", "O-15", ...]
  ciiu              TEXT,
  municipio         TEXT,
  estado_rut        TEXT,
  consultado_at     TEXT,                -- cuándo se leyó el RUT; distingue dato fresco de viejo
  origen            TEXT NOT NULL DEFAULT 'excel',   -- 'excel' | 'rut' | 'manual'
  notas             TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(nit)
);

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


def _m015_catalogo_de_siigo(conn: sqlite3.Connection) -> None:
    """Migración 15 — el catálogo de impuestos de Siigo, con sus cuatro cuentas.

    El catálogo real del contador (2026-10-28) enseñó que un código de impuesto
    de Siigo no tiene UNA cuenta: tiene cuatro, según el comprobante —venta,
    compra, devolución en venta, devolución en compra—. El IVA 19 % de
    servicios es `24080504` al vender, `24081501` al comprar y `24082004` en una
    nota crédito de venta. Con el catálogo cargado, la cuenta de cada línea de
    IVA y de retención sale de aquí, y las «cuentas de IVA» de la empresa
    quedan como respaldo para cuando no hay catálogo.

    `regla_causacion.iva_codigo`: qué IVA factura este proveedor (bienes o
    servicios, 19 o 5), que es lo único del IVA que el documento no dice y el
    contador sí sabe. Se aprende al aprobar, como la retención.
    `asiento_linea.codigo_siigo`: el código que se decidió para esa línea, para
    que el archivo no lo tenga que adivinar después.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS siigo_impuesto (
          codigo      TEXT NOT NULL,
          contexto    TEXT NOT NULL,   -- venta | compra | dev_venta | dev_compra
          nombre      TEXT,
          tipo        TEXT,            -- iva | retefuente | reteiva | reteica | autorretencion | otro
          tarifa      TEXT,
          cuenta      TEXT,
          descripcion TEXT,
          PRIMARY KEY (codigo, contexto)
        )""")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(regla_causacion)").fetchall()}
    if "iva_codigo" not in cols:
        conn.execute("ALTER TABLE regla_causacion ADD COLUMN iva_codigo TEXT")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(asiento_linea)").fetchall()}
    if "codigo_siigo" not in cols:
        conn.execute("ALTER TABLE asiento_linea ADD COLUMN codigo_siigo TEXT")


def _m014_archivo_de_siigo(conn: sqlite3.Connection) -> None:
    """Migración 14 — lo que el archivo de importación de Siigo exige (D-128).

    El archivo (`docs/siigo-import-structure.md`) pide cosas que el asiento no
    guardaba: **qué es cada línea** (gasto, IVA, retención, cartera) y su base,
    para ponerle el código de impuesto y la base gravable; el **número del
    documento**, que va en la línea de cartera y en la descripción; y el
    **consecutivo de Siigo** que se le asignó al exportar, que no puede cambiar
    ni repetirse entre dos exportaciones.

    `siigo_config` es clave-valor a propósito: los tipos de comprobante, los
    últimos consecutivos y los códigos de IVA son del catálogo de cada empresa en
    Siigo y no se deducen; una tabla por cada uno sería esquema para tres filas.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(retencion_concepto)").fetchall()}
    if "codigo_siigo" not in cols:
        conn.execute("ALTER TABLE retencion_concepto ADD COLUMN codigo_siigo TEXT")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(asiento_propuesto)").fetchall()}
    for col, ddl in (("numero", "TEXT"), ("tipo_doc", "TEXT"), ("siigo_consecutivo", "INTEGER")):
        if col not in cols:
            conn.execute(f"ALTER TABLE asiento_propuesto ADD COLUMN {col} {ddl}")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(asiento_linea)").fetchall()}
    for col, ddl in (("rol", "TEXT"), ("base", "TEXT"), ("concepto_id", "INTEGER")):
        if col not in cols:
            conn.execute(f"ALTER TABLE asiento_linea ADD COLUMN {col} {ddl}")
    conn.execute("CREATE TABLE IF NOT EXISTS siigo_config (clave TEXT PRIMARY KEY, valor TEXT)")


def _m013_ventas_y_documento_soporte(conn: sqlite3.Connection) -> None:
    """Migración 13 — lo que la empresa emite también se causa (D-127).

    Lo pidió el contador el 2026-10-27, probando la 0.11: el reporte de la DIAN
    trae lo que la empresa **emitió** —ventas, notas crédito de venta y
    documentos soporte a no obligados— y eso también se contabiliza, con el
    **receptor** como tercero. Tres cosas nuevas, todas con valor por defecto
    para que lo que ya existe siga significando lo mismo:

    - `asiento_propuesto.naturaleza`: `compra` (lo de siempre), `venta` o
      `doc_soporte`. Decide qué líneas lleva el asiento.
    - `regla_causacion.naturaleza`: una regla de ingreso para un cliente no es la
      regla de gasto para ese mismo NIT cuando además es proveedor.
    - `empresa_info.cuenta_clientes` y `cuenta_iva_generado`: las dos cuentas de
      una venta que Contab tampoco puede deducir, y tampoco se ponen por defecto.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(empresa_info)").fetchall()}
    if "cuenta_clientes" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN cuenta_clientes TEXT")
    if "cuenta_iva_generado" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN cuenta_iva_generado TEXT")
    for tabla in ("asiento_propuesto", "regla_causacion"):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        if "naturaleza" not in cols:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN naturaleza TEXT NOT NULL DEFAULT 'compra'")


def _m012_regla_sin_retencion(conn: sqlite3.Connection) -> None:
    """Migración 12 — «a este proveedor no se le retiene», dicho a propósito.

    `regla_causacion` ya existe en las bases con esquema 10, así que la columna
    se añade aquí. Sin ella, un concepto de retención vacío significaba a la vez
    «no se retiene» y «nadie lo ha decidido», y el asiento quedaba marcado para
    siempre aunque el contador ya lo hubiera aprobado.
    """
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(regla_causacion)").fetchall()}
    if cols and "sin_retencion" not in cols:
        conn.execute(
            "ALTER TABLE regla_causacion ADD COLUMN sin_retencion"
            " INTEGER NOT NULL DEFAULT 0")


def _m011_asiento_y_cuentas_de_la_empresa(conn: sqlite3.Connection) -> None:
    """Migración 11 — la propuesta de asiento, y las dos cuentas que Contab no sabe.

    Un asiento de compra necesita, además de la cuenta del gasto, **el pasivo con
    el proveedor** y, si la empresa es responsable de IVA, **el IVA descontable**.
    Ninguna de las dos se puede deducir: son del PUC de cada empresa.

    No se ponen por defecto a propósito. Poner `220505` porque «es lo habitual»
    produciría un mes entero contabilizado contra una cuenta que puede no ser la
    suya, y eso se descubre tarde. Vacías, la propuesta sale marcada diciendo
    cuál falta.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(empresa_info)").fetchall()}
    if "cuenta_proveedores" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN cuenta_proveedores TEXT")
    if "cuenta_iva_descontable" not in cols:
        conn.execute("ALTER TABLE empresa_info ADD COLUMN cuenta_iva_descontable TEXT")


def _m010_reglas_causacion(conn: sqlite3.Connection) -> None:
    """Migración 10 — las reglas de causación (Fase 4.3).

    La tabla se declara en SCHEMA_SQL con `IF NOT EXISTS`. **Sin columna de
    centro de costo** (D-112): el contador respondió que no los usa, y un campo
    que nadie llena solo sirve para llenarse mal.
    """
    return None


def _m009_responsabilidades_del_xml(conn: sqlite3.Connection) -> None:
    """Migración 9 — lo que la factura declara del emisor (Fase 4.2).

    `documento` ya existe en las bases creadas con el esquema 7, así que la
    columna hay que añadirla aquí y no basta con declararla en SCHEMA_SQL.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(documento)").fetchall()}
    if "emisor_responsabilidades" not in cols:
        conn.execute("ALTER TABLE documento ADD COLUMN emisor_responsabilidades TEXT")


def _m008_tarifas(conn: sqlite3.Connection) -> None:
    """Migración 8 — UVT y conceptos de retención (Fase 4.1).

    Las tablas se declaran en SCHEMA_SQL con `IF NOT EXISTS`. **No hay tabla de
    tarifas de ICA**: ninguna de las cinco empresas del contador es agente de
    ReteICA, y lo confirmó por escrito el 2026-10-20. Construirla «por si acaso»
    sería esquema muerto desde el primer día (D-085); cuando alguna lo sea, se
    añade.
    """
    return None


def _m007_documentos_xml(conn: sqlite3.Connection) -> None:
    """Migración 7 — el documento del XML: líneas, impuestos y referencias (Fase 3.2).

    Las cinco tablas se declaran en SCHEMA_SQL con `IF NOT EXISTS`, así que el
    `executescript` las crea en cualquier BD y aquí no hay nada que mover.

    **No se toca ni una tabla existente.** `excel_row` sigue siendo la fuente de lo
    que el contador ve; el documento del XML se le engancha por CUFE. Un mes sin
    XML tiene que comportarse exactamente igual que antes, y eso es lo que la
    suite vieja en verde demuestra.
    """
    return None


def _m006_bitacora_ingesta(conn: sqlite3.Connection) -> None:
    """Migración 6 — bitácora de las ingestas desde el portal (Fase 2.5).

    La tabla y su índice se declaran en SCHEMA_SQL con `IF NOT EXISTS`, así que el
    `executescript` los crea en cualquier BD. El índice puede ir ahí y no acá
    —al revés que en la migración 3— porque la tabla es nueva: se crea en el mismo
    script, dos líneas antes.
    """
    return None


def _m005_terceros(conn: sqlite3.Connection) -> None:
    """Migración 5 — catálogo de terceros por empresa (Fase 1.3).

    La tabla se declara en SCHEMA_SQL con `IF NOT EXISTS`, igual que las de la
    migración 4. La siembra desde las filas del Excel NO se hace aquí: es una
    operación que el contador dispara y cuyo resultado quiere ver (cuántos
    terceros aparecieron, cuántos ya estaban), no un efecto silencioso de abrir
    la empresa. Vive en `terceros.sembrar_desde_excel`.
    """
    return None


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
    (5, _m005_terceros),
    (6, _m006_bitacora_ingesta),
    (7, _m007_documentos_xml),
    (8, _m008_tarifas),
    (9, _m009_responsabilidades_del_xml),
    (10, _m010_reglas_causacion),
    (11, _m011_asiento_y_cuentas_de_la_empresa),
    (12, _m012_regla_sin_retencion),
    (13, _m013_ventas_y_documento_soporte),
    (14, _m014_archivo_de_siigo),
    (15, _m015_catalogo_de_siigo),
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
            "SELECT nit, dv, razon_social, default_folder, pdfs_folder, archived, created_at, "
            "cuenta_proveedores, cuenta_iva_descontable "
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


def periodo_folders(db_path: str | Path) -> dict[str, str | None]:
    """{periodo: carpeta de soportes} de todos los meses conocidos."""
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        return {
            r["periodo"]: r["pdfs_folder"]
            for r in conn.execute("SELECT periodo, pdfs_folder FROM periodo_folder").fetchall()
        }
    finally:
        conn.close()


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
            carpeta = folders.get(p)
            out.append({
                "periodo": p,
                "load_count": agg["lc"],
                "row_count": agg["rc"],
                "pdfs_folder": carpeta,
                # Una carpeta configurada que ya no está en disco NO es lo mismo que
                # «no hay soportes»: el usuario la movió o cambió de máquina, y sin
                # decirlo la pantalla muestra 0 CUFE y parece que faltan documentos.
                # Es la firma que D-080 prohíbe: causa técnica disfrazada de dato.
                "pdfs_folder_existe": bool(carpeta) and Path(carpeta).is_dir(),
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
