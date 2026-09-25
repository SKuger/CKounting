"""Versionado de esquema (#22, D-084) y retirada del esquema muerto (#21, D-085)."""
import json
import sqlite3

import pytest

from contab_core import excel, storage

# Esquema tal y como era en la versión 1: con `validation_rule`, el `rule_id` que
# la apuntaba y el `excel_row.deleted_at` que nunca se escribió.
ESQUEMA_V1 = """
CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
INSERT INTO schema_version VALUES (1);
CREATE TABLE empresa_info (nit TEXT NOT NULL, dv TEXT, razon_social TEXT NOT NULL,
  default_folder TEXT, pdfs_folder TEXT, archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE excel_load (id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT NOT NULL,
  source_name TEXT NOT NULL, loaded_at TEXT, total_rows INTEGER NOT NULL, sheet_name TEXT,
  periodo TEXT, deleted_at TEXT);
CREATE TABLE excel_row (id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER NOT NULL
  REFERENCES excel_load(id) ON DELETE CASCADE, row_index INTEGER NOT NULL, cufe_cude TEXT,
  grupo TEXT, tipo_doc TEXT, data_json TEXT NOT NULL, periodo TEXT, deleted_at TEXT);
CREATE TABLE validation_rule (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  description TEXT, type TEXT NOT NULL, scope_json TEXT, params_json TEXT NOT NULL,
  failure_message TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'error',
  enabled INTEGER NOT NULL DEFAULT 1, vigencia_desde TEXT, vigencia_hasta TEXT,
  created_at TEXT, updated_at TEXT);
CREATE TABLE validation_run (id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER NOT NULL
  REFERENCES excel_load(id) ON DELETE CASCADE, started_at TEXT, finished_at TEXT,
  total_rows INTEGER, failing_rows INTEGER, notes TEXT);
CREATE TABLE validation_failure (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL
  REFERENCES validation_run(id) ON DELETE CASCADE,
  rule_id INTEGER REFERENCES validation_rule(id) ON DELETE SET NULL,
  row_index INTEGER NOT NULL, cufe_cude TEXT, column_name TEXT, value_snapshot TEXT,
  rule_severity TEXT, reason TEXT NOT NULL);
CREATE TABLE validation_override (id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER NOT NULL,
  row_index INTEGER NOT NULL, validation_code TEXT NOT NULL, created_at TEXT,
  UNIQUE(load_id,row_index,validation_code));
CREATE TABLE pdf_cufe_index (id INTEGER PRIMARY KEY AUTOINCREMENT, folder_path TEXT NOT NULL,
  pdf_path TEXT NOT NULL, pdf_mtime INTEGER NOT NULL, pdf_size_bytes INTEGER NOT NULL,
  extraction_status TEXT NOT NULL, extraction_error TEXT, indexed_at TEXT,
  UNIQUE(folder_path,pdf_path));
CREATE TABLE pdf_cufe_value (id INTEGER PRIMARY KEY AUTOINCREMENT, pdf_index_id INTEGER NOT NULL
  REFERENCES pdf_cufe_index(id) ON DELETE CASCADE, cufe_cude TEXT NOT NULL, label TEXT);
CREATE TABLE periodo_folder (periodo TEXT PRIMARY KEY, pdfs_folder TEXT);
"""


def _db_v1_con_datos(path):
    """Una BD como las que hay instaladas: esquema v1 y contabilidad dentro."""
    c = sqlite3.connect(path)
    c.executescript(ESQUEMA_V1)
    c.execute("INSERT INTO empresa_info(nit,dv,razon_social) VALUES ('900181831','4','REAL Seguros')")
    c.execute(
        "INSERT INTO excel_load(source_path,source_name,total_rows,periodo)"
        " VALUES ('x','x.xlsx',2,'2024-02')"
    )
    for i, (cufe, total) in enumerate([("a" * 96, 48150.0), ("b" * 96, 99999.5)]):
        c.execute(
            "INSERT INTO excel_row(load_id,row_index,cufe_cude,tipo_doc,data_json,periodo)"
            " VALUES (1,?,?,?,?,'2024-02')",
            (i, cufe, "Factura electrónica",
             json.dumps({"Total": total, "IVA": 0, "CUFE/CUDE": cufe,
                         "Fecha Emisión": "2024-02-26"})),
        )
    c.execute("INSERT INTO validation_run(load_id,total_rows,failing_rows) VALUES (1,2,1)")
    c.execute(
        "INSERT INTO validation_failure(run_id,rule_id,row_index,cufe_cude,reason)"
        " VALUES (1,NULL,0,?,'sin soporte')", ("a" * 96,),
    )
    c.execute("INSERT INTO validation_override(load_id,row_index,validation_code) VALUES (1,1,'V3')")
    c.commit()
    c.close()


def test_migra_de_v1_a_la_version_actual_sin_perder_datos(tmp_path):
    db = tmp_path / "vieja.db"
    _db_v1_con_datos(db)

    conn = storage.connect(db)
    try:
        storage.ensure_schema(conn)

        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == \
            storage.SCHEMA_VERSION

        # Lo que importa: la contabilidad sigue entera.
        assert conn.execute("SELECT razon_social FROM empresa_info").fetchone()[0] == "REAL Seguros"
        assert conn.execute("SELECT COUNT(*) FROM excel_row").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM validation_failure").fetchone()[0] == 1
        assert conn.execute("SELECT reason FROM validation_failure").fetchone()[0] == "sin soporte"
        assert conn.execute("SELECT COUNT(*) FROM validation_override").fetchone()[0] == 1

        totales = [str(r["Total"]) for r in excel.fetch_load_rows(conn, 1)]
        assert totales == ["48150.00", "99999.50"]
    finally:
        conn.close()


def test_la_migracion_retira_el_esquema_muerto(tmp_path):
    """#21 — esquema que describía un sistema que no existe."""
    db = tmp_path / "vieja.db"
    _db_v1_con_datos(db)

    conn = storage.connect(db)
    try:
        storage.ensure_schema(conn)
        tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "validation_rule" not in tablas, "motor de reglas que nunca se implementó"

        cols_fila = {r["name"] for r in conn.execute("PRAGMA table_info(excel_row)")}
        assert "deleted_at" not in cols_fila, "la papelera por fila nunca existió"

        cols_fallo = {r["name"] for r in conn.execute("PRAGMA table_info(validation_failure)")}
        assert "rule_id" not in cols_fallo, "la FK a la tabla retirada"

        # La papelera que SÍ funciona (por lote) no se toca.
        assert "deleted_at" in {r["name"] for r in conn.execute("PRAGMA table_info(excel_load)")}
    finally:
        conn.close()


def test_no_borra_validation_rule_si_alguien_tuviera_datos(tmp_path):
    """Si hubiera filas, se conserva y se avisa: no se destruyen datos ajenos."""
    db = tmp_path / "conreglas.db"
    _db_v1_con_datos(db)
    c = sqlite3.connect(db)
    c.execute(
        "INSERT INTO validation_rule(name,type,params_json,failure_message)"
        " VALUES ('R','x','{}','msg')"
    )
    c.commit()
    c.close()

    conn = storage.connect(db)
    try:
        storage.ensure_schema(conn)
        tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "validation_rule" in tablas
        assert conn.execute("SELECT COUNT(*) FROM validation_rule").fetchone()[0] == 1
    finally:
        conn.close()


def test_bloquea_abrir_una_bd_de_una_version_posterior(tmp_path):
    """#22 — con auto-update, una versión vieja puede toparse con una BD nueva.

    Antes SCHEMA_VERSION llevaba en 1 desde el primer día y la app abría y
    ESCRIBÍA en cualquier BD, viniera de donde viniera."""
    db = tmp_path / "futura.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL")
    conn = storage.connect(db)
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version VALUES (?)", (storage.SCHEMA_VERSION + 50,))
    conn.close()

    with pytest.raises(storage.EsquemaMasNuevoQueLaApp, match="más reciente"):
        storage.read_empresa_info(db)


def test_ensure_schema_sale_temprano_si_ya_esta_al_dia(tmp_path):
    """Antes corría el executescript entero y todos los PRAGMA en CADA llamada RPC."""
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL")
    # `sqlite3.Connection.executescript` es de solo lectura, así que se cuenta a
    # través de set_trace_callback: registra cada sentencia que SQLite ejecuta.
    conn = storage.connect(db)
    try:
        sentencias: list[str] = []
        conn.set_trace_callback(sentencias.append)
        storage.ensure_schema(conn)
        conn.set_trace_callback(None)

        ddl = [s for s in sentencias if s.lstrip().upper().startswith(("CREATE", "ALTER", "DROP"))]
        assert ddl == [], f"no debe reaplicar DDL estando al día, pero ejecutó {len(ddl)}"
        assert len(sentencias) <= 2, f"debería bastar con leer la versión: {sentencias}"
    finally:
        conn.close()


def test_es_idempotente(tmp_path):
    db = tmp_path / "vieja.db"
    _db_v1_con_datos(db)
    conn = storage.connect(db)
    try:
        for _ in range(3):
            storage.ensure_schema(conn)
        assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM excel_row").fetchone()[0] == 2
    finally:
        conn.close()


# ── #23 (D-091) — columnas consultables fuera del blob JSON ─────────────────

def test_migracion_rellena_las_columnas_consultables(tmp_path):
    """Una BD existente debe quedar consultable sin recargar los Excel."""
    db = tmp_path / "vieja.db"
    _db_v1_con_datos(db)

    conn = storage.connect(db)
    try:
        storage.ensure_schema(conn)
        filas = conn.execute(
            "SELECT total_centavos, iva_centavos, nit_emisor, fecha_emision"
            " FROM excel_row ORDER BY row_index"
        ).fetchall()
        assert [f["total_centavos"] for f in filas] == [4815000, 9999950]
        assert all(f["fecha_emision"] == "2024-02-26" for f in filas)
    finally:
        conn.close()


def test_suma_en_sql_exacta_y_coincide_con_python(tmp_path, sample_excel):
    """El punto del cambio: sumar un mes sin cargarlo entero a memoria, y que el
    resultado sea EXACTO. Por eso los importes van en centavos como INTEGER: un
    REAL reintroduciría el binario del que salimos en D-075."""
    from decimal import Decimal

    from contab_core import money

    db = tmp_path / "e.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL")
    conn = storage.connect(db)
    try:
        loaded = excel.load_excel(sample_excel)
        load_id = excel.persist_load(conn, "x.xlsx", loaded, periodo="2024-02")

        en_sql = money.de_centavos(
            conn.execute("SELECT SUM(total_centavos) FROM excel_row").fetchone()[0]
        )
        en_python = sum(
            (r["Total"] for r in excel.fetch_load_rows(conn, load_id)), Decimal("0.00")
        )
        assert en_sql == en_python
    finally:
        conn.close()


def test_resumen_por_periodo_agrupa_en_sql(tmp_path, sample_excel):
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL")
    conn = storage.connect(db)
    try:
        loaded = excel.load_excel(sample_excel)
        excel.persist_load(conn, "feb.xlsx", loaded, periodo="2024-02")
        excel.persist_load(conn, "mar.xlsx", loaded, periodo="2024-03")

        resumen = excel.resumen_por_periodo(conn)
        assert [r["periodo"] for r in resumen] == ["2024-03", "2024-02"], "más reciente primero"
        assert all(r["documentos"] == len(loaded.rows) for r in resumen)
        assert resumen[0]["total"] == resumen[1]["total"] > 0
        assert resumen[0]["emisores"] > 0
    finally:
        conn.close()


def test_resumen_por_emisor_ordena_por_importe(tmp_path, sample_excel):
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL")
    conn = storage.connect(db)
    try:
        excel.persist_load(conn, "x.xlsx", excel.load_excel(sample_excel), periodo="2024-02")
        emisores = excel.resumen_por_emisor(conn, "2024-02")
        assert len(emisores) > 1
        totales = [e["total"] for e in emisores]
        assert totales == sorted(totales, reverse=True)
        assert all(e["nit"] for e in emisores)
    finally:
        conn.close()


def test_el_resumen_ignora_los_lotes_en_la_papelera(tmp_path, sample_excel):
    """La papelera del lote (excel_load.deleted_at) es la que SÍ existe."""
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL")
    conn = storage.connect(db)
    try:
        load_id = excel.persist_load(
            conn, "x.xlsx", excel.load_excel(sample_excel), periodo="2024-02"
        )
        assert excel.resumen_por_periodo(conn) != []

        with storage.transaction(conn):
            conn.execute(
                "UPDATE excel_load SET deleted_at = datetime('now') WHERE id = ?", (load_id,)
            )
        assert excel.resumen_por_periodo(conn) == []
    finally:
        conn.close()


def test_centavos_van_y_vuelven_sin_perder_nada():
    from decimal import Decimal

    from contab_core import money

    for v in ("0.00", "0.01", "-0.01", "48150.00", "15399.99", "99999999.99", "-2447.16"):
        d = Decimal(v)
        assert money.de_centavos(money.a_centavos(d)) == d, v
