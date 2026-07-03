"""Periodos (mes) + papelera (soft-delete) + carpeta de soportes por mes (0.1.4)."""
import json
import sqlite3

from contab_core import excel, storage
from contab_core.sidecar import handle_request


def _call(method, **params):
    r = handle_request({"id": "t", "method": method, "params": params})
    assert "error" not in r, f"{method}: {r.get('error')}"
    return r["result"]


def _make_db(tmp_path, sample_excel):
    db = str(tmp_path / "e.db")
    storage.init_empresa_db(db, "900181831", "4", "Real Seguros Ltda")
    loaded = excel.load_excel(sample_excel)
    conn = storage.connect(db)
    storage.ensure_schema(conn)
    lid = excel.persist_load(conn, str(sample_excel), loaded)
    conn.close()
    return db, lid


def test_import_assigns_periodo_and_row_index(tmp_path, sample_excel):
    db, lid = _make_db(tmp_path, sample_excel)
    conn = storage.connect(db)
    storage.ensure_schema(conn)
    rows = excel.fetch_load_rows(conn, lid)
    conn.close()
    assert all(r["periodo"] == "2026-02" for r in rows)
    # row_index explícito y contiguo (aún sin papelera)
    assert [r["row_index"] for r in rows] == list(range(len(rows)))


def test_migration_backfills_periodo_from_fecha_emision(tmp_path):
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
    storage.ensure_schema(conn)  # dispara la migración + backfill
    assert conn.execute("SELECT periodo FROM excel_row WHERE row_index=0").fetchone()["periodo"] == "2025-03"
    assert conn.execute("SELECT periodo FROM excel_load WHERE id=1").fetchone()["periodo"] == "2025-03"
    storage.ensure_schema(conn)  # idempotente: no falla la 2ª vez
    conn.close()


def test_move_rows_between_periodos(tmp_path, sample_excel):
    db, lid = _make_db(tmp_path, sample_excel)
    storage.move_rows_periodo(db, lid, [0, 1, 2], "2030-01")
    counts = {p["periodo"]: p["row_count"] for p in storage.list_periodos(db)}
    assert counts["2030-01"] == 3
    assert counts["2026-02"] == 8


def test_soft_delete_hides_from_reads(tmp_path, sample_excel):
    db, lid = _make_db(tmp_path, sample_excel)
    storage.soft_delete_rows(db, lid, [0, 1])
    conn = storage.connect(db)
    storage.ensure_schema(conn)
    assert len(excel.fetch_load_rows(conn, lid)) == 9
    assert len(excel.fetch_load_rows(conn, lid, include_deleted=True)) == 11
    conn.close()
    storage.restore_rows(db, lid, [0, 1])
    conn = storage.connect(db)
    storage.ensure_schema(conn)
    assert len(excel.fetch_load_rows(conn, lid)) == 11
    conn.close()


def test_soft_delete_load_hidden_from_list_loads(tmp_path, sample_excel):
    db, lid = _make_db(tmp_path, sample_excel)
    _call("soft_delete_load", db_path=db, load_id=lid)
    assert _call("list_loads", db_path=db) == []
    assert len(_call("list_loads", db_path=db, include_deleted=True)) == 1
    _call("restore_load", db_path=db, load_id=lid)
    assert len(_call("list_loads", db_path=db)) == 1


def test_validations_key_by_row_index_survive_soft_delete(tmp_path, sample_excel):
    """El fix crítico: fallas y overrides se identifican por row_index REAL; ocultar
    una fila NO debe correr el mapeo (que antes era posicional)."""
    db, lid = _make_db(tmp_path, sample_excel)

    base = _call("run_validations", db_path=db, load_id=lid)
    failing = sorted(f["row_index"] for f in base["failures"])
    assert len(failing) >= 2, "la muestra debe tener ≥2 no conformes (V3)"

    # aprobar (override V3) una fila que falla → deja de aparecer
    f0 = failing[0]
    _call("toggle_validation_override", db_path=db, load_id=lid, row_index=f0, code="V3", active=True)
    after = _call("run_validations", db_path=db, load_id=lid)
    remaining = sorted(f["row_index"] for f in after["failures"])
    assert f0 not in remaining

    # ocultar (papelera) una fila NO-fallida y ANTERIOR → fuerza corrimiento de posiciones
    non_failing = [i for i in range(11) if i not in failing]
    del_idx = min(non_failing)
    _call("soft_delete_rows", db_path=db, load_id=lid, row_indexes=[del_idx])

    after2 = _call("run_validations", db_path=db, load_id=lid)
    remaining2 = sorted(f["row_index"] for f in after2["failures"])
    # mismos documentos fallan, con el MISMO row_index (no corrido por el borrado);
    # el override sigue aplicando a la fila correcta.
    assert remaining2 == [r for r in remaining if r != del_idx]
    assert f0 not in remaining2
