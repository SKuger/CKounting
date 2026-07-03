"""Meses (periodos) como contenedor + carpeta de soportes por mes + papelera del Excel (0.1.4).

Modelo: el MES es el contenedor. Se crea un mes y dentro se carga SU Excel y se elige SU
carpeta de soportes. No hay carpeta global. No se opera a nivel de fila (la tabla no cambia);
lo movible/borrable es el Excel cargado.
"""
import json
import sqlite3

from contab_core import storage
from contab_core.sidecar import handle_request


def _call(method, **params):
    r = handle_request({"id": "t", "method": method, "params": params})
    assert "error" not in r, f"{method}: {r.get('error')}"
    return r["result"]


def _new_empresa(tmp_path):
    db = str(tmp_path / "e.db")
    storage.init_empresa_db(db, "900181831", "4", "Real Seguros Ltda")
    return db


def _import(db, sample_excel, periodo):
    return _call("import_excel", db_path=db, source_path=str(sample_excel), periodo=periodo)


def test_import_requires_periodo(tmp_path, sample_excel):
    db = _new_empresa(tmp_path)
    r = handle_request({
        "id": "t", "method": "import_excel",
        "params": {"db_path": db, "source_path": str(sample_excel)},  # sin periodo
    })
    assert "error" in r  # el mes es obligatorio


def test_import_loads_into_the_chosen_month(tmp_path, sample_excel):
    db = _new_empresa(tmp_path)
    r = _import(db, sample_excel, "2026-05")  # el mes lo elige el usuario, NO se deriva
    assert r["periodo"] == "2026-05"
    loads = _call("list_loads", db_path=db, periodo="2026-05")
    assert len(loads) == 1 and loads[0]["periodo"] == "2026-05"


def test_create_empty_month_shows_in_list(tmp_path):
    db = _new_empresa(tmp_path)
    _call("create_periodo", db_path=db, periodo="2026-07")
    months = {p["periodo"]: p for p in _call("list_periodos", db_path=db)}
    assert "2026-07" in months and months["2026-07"]["load_count"] == 0


def test_per_month_folder_and_no_global_fallback(tmp_path, sample_excel):
    db = _new_empresa(tmp_path)
    _import(db, sample_excel, "2026-05")
    folder = str(tmp_path / "soportes-mayo")
    _call("set_periodo_pdfs_folder", db_path=db, periodo="2026-05", folder=folder)
    months = {p["periodo"]: p for p in _call("list_periodos", db_path=db)}
    assert months["2026-05"]["pdfs_folder"] == folder
    # sin carpeta del mes → None (NO hay fallback a una carpeta global)
    conn = storage.connect(db)
    storage.ensure_schema(conn)
    assert storage.periodo_pdfs_folder(conn, "2099-01") is None
    conn.close()


def test_move_excel_between_months(tmp_path, sample_excel):
    db = _new_empresa(tmp_path)
    lid = _import(db, sample_excel, "2026-05")["load_id"]
    _call("set_load_periodo", db_path=db, load_id=lid, periodo="2026-06")
    assert _call("list_loads", db_path=db, periodo="2026-05") == []
    assert len(_call("list_loads", db_path=db, periodo="2026-06")) == 1


def test_soft_delete_and_restore_the_excel(tmp_path, sample_excel):
    db = _new_empresa(tmp_path)
    lid = _import(db, sample_excel, "2026-05")["load_id"]
    _call("soft_delete_load", db_path=db, load_id=lid)
    assert _call("list_loads", db_path=db) == []
    assert len(_call("list_loads", db_path=db, include_deleted=True)) == 1
    _call("restore_load", db_path=db, load_id=lid)
    assert len(_call("list_loads", db_path=db)) == 1


def test_delete_month_removes_its_excel(tmp_path, sample_excel):
    db = _new_empresa(tmp_path)
    _import(db, sample_excel, "2026-05")
    _call("delete_periodo", db_path=db, periodo="2026-05")
    assert _call("list_loads", db_path=db, include_deleted=True) == []
    assert all(p["periodo"] != "2026-05" for p in _call("list_periodos", db_path=db))


def test_table_unchanged_no_meta_keys(tmp_path, sample_excel):
    """La tabla del Excel queda como antes: NO se inyectan row_index/periodo en las filas."""
    db = _new_empresa(tmp_path)
    lid = _import(db, sample_excel, "2026-05")["load_id"]
    rows = _call("get_load_rows", db_path=db, load_id=lid)["rows"]
    assert "row_index" not in rows[0]
    assert "periodo" not in rows[0]


def test_migration_backfills_load_periodo_from_fecha_emision(tmp_path):
    old = str(tmp_path / "old.db")
    c = sqlite3.connect(old)
    c.executescript(
        "CREATE TABLE excel_load(id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT NOT NULL,"
        " source_name TEXT NOT NULL, loaded_at TEXT, total_rows INTEGER NOT NULL, sheet_name TEXT);"
        "CREATE TABLE excel_row(id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER NOT NULL,"
        " row_index INTEGER NOT NULL, cufe_cude TEXT, grupo TEXT, tipo_doc TEXT, data_json TEXT NOT NULL);"
    )
    c.execute("INSERT INTO excel_load(source_path,source_name,total_rows) VALUES (?,?,?)", ("x", "x.xlsx", 1))
    c.execute(
        "INSERT INTO excel_row(load_id,row_index,data_json) VALUES (?,?,?)",
        (1, 0, json.dumps({"Fecha Emisión": "2025-03-14T10:00:00"})),
    )
    c.commit()
    c.close()

    conn = storage.connect(old)
    storage.ensure_schema(conn)  # migración + backfill del periodo del lote
    assert conn.execute("SELECT periodo FROM excel_load WHERE id=1").fetchone()["periodo"] == "2025-03"
    storage.ensure_schema(conn)  # idempotente
    conn.close()
