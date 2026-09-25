"""Catálogo de terceros (Fase 1.3) y tablero multiempresa (Fase 1.5).

Lo que estos tests protegen: que el tercero salga del LADO correcto de la fila
—el proveedor en una compra, el cliente en una venta— y que el tablero no se caiga
entero porque una empresa no se pueda leer.
"""
import json

import pytest

from contab_core import nit as nit_module
from contab_core import sidecar, storage, tablero, terceros


@pytest.fixture()
def conn(tmp_path):
    db = tmp_path / "empresa.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL Seguros")
    c = storage.connect(db)
    storage.ensure_schema(c)
    yield c
    c.close()


def _fila(conn, grupo, nit_emisor, nombre_emisor, nit_receptor, nombre_receptor):
    data = {
        "NIT Emisor": nit_emisor, "Nombre Emisor": nombre_emisor,
        "NIT Receptor": nit_receptor, "Nombre Receptor": nombre_receptor,
        "Grupo": grupo,
    }
    conn.execute(
        "INSERT INTO excel_load(source_path, source_name, total_rows) VALUES ('/x', 'x', 1)"
    )
    load_id = conn.execute("SELECT MAX(id) FROM excel_load").fetchone()[0]
    conn.execute(
        "INSERT INTO excel_row(load_id, row_index, grupo, data_json) VALUES (?, 0, ?, ?)",
        (load_id, grupo, json.dumps(data)),
    )


# ── de qué lado sale el tercero ──────────────────────────────────────────────

def test_en_una_compra_el_tercero_es_el_emisor(conn):
    _fila(conn, "Recibido", "830008686", "D1 SAS", "900181831", "REAL Seguros")
    terceros.sembrar_desde_excel(conn)
    assert [t["nit"] for t in terceros.listar(conn)] == ["830008686"]


def test_en_una_venta_el_tercero_es_el_receptor(conn):
    _fila(conn, "Emitido", "900181831", "REAL Seguros", "901111111", "Cliente SAS")
    terceros.sembrar_desde_excel(conn)
    assert [t["nit"] for t in terceros.listar(conn)] == ["901111111"]


def test_un_grupo_desconocido_se_omite_en_vez_de_adivinarse(conn):
    """Si la DIAN añade un valor nuevo a Grupo, preferimos un tercero que falta a
    uno inventado del lado equivocado."""
    _fila(conn, "Trasladado", "830008686", "D1 SAS", "900181831", "REAL Seguros")
    assert terceros.sembrar_desde_excel(conn)["encontrados"] == 0
    assert terceros.listar(conn) == []


def test_sembrar_dos_veces_no_duplica(conn):
    _fila(conn, "Recibido", "830008686", "D1 SAS", "900181831", "REAL")
    _fila(conn, "Recibido", "830008686", "D1 SAS", "900181831", "REAL")
    primera = terceros.sembrar_desde_excel(conn)
    segunda = terceros.sembrar_desde_excel(conn)
    assert primera["nuevos"] == 1
    assert segunda["nuevos"] == 0
    assert len(terceros.listar(conn)) == 1


def test_el_dv_se_calcula_al_sembrar(conn):
    """El Excel de la DIAN no trae el DV del tercero; se calcula al darlo de alta,
    porque la consulta del RUT lo pide."""
    _fila(conn, "Recibido", "830008686", "D1 SAS", "900181831", "REAL")
    terceros.sembrar_desde_excel(conn)
    assert terceros.obtener(conn, "830008686")["dv"] == nit_module.compute_dv("830008686")


def test_el_nit_se_normaliza(conn):
    _fila(conn, "Recibido", "830.008.686", "D1 SAS", "900181831", "REAL")
    terceros.sembrar_desde_excel(conn)
    assert terceros.obtener(conn, "830008686") is not None


# ── el RUT manda sobre el Excel ──────────────────────────────────────────────

def test_lo_consultado_en_el_rut_no_lo_pisa_el_excel(conn):
    _fila(conn, "Recibido", "830008686", "D1 SAS", "900181831", "REAL")
    terceros.sembrar_desde_excel(conn)
    terceros.actualizar_desde_rut(conn, "830008686", {
        "razon_social": "ALMACENES D1 S.A.S.", "tipo": "empresa",
    })
    terceros.sembrar_desde_excel(conn)
    assert terceros.obtener(conn, "830008686")["razon_social"] == "ALMACENES D1 S.A.S."


def test_una_consulta_sin_razon_social_no_borra_la_que_habia(conn):
    terceros.guardar(conn, {"nit": "830008686", "razon_social": "D1 SAS"})
    terceros.actualizar_desde_rut(conn, "830008686", {"estado_rut": "ACTIVA"})
    t = terceros.obtener(conn, "830008686")
    assert t["razon_social"] == "D1 SAS"
    assert t["estado_rut"] == "ACTIVA"


def test_consultar_el_rut_sella_la_fecha(conn):
    """`consultado_at` distingue un dato fresco de uno de hace un año."""
    terceros.guardar(conn, {"nit": "830008686", "razon_social": "D1"})
    assert terceros.obtener(conn, "830008686")["consultado_at"] is None
    terceros.actualizar_desde_rut(conn, "830008686", {"razon_social": "D1"})
    assert terceros.obtener(conn, "830008686")["consultado_at"] is not None


def test_las_responsabilidades_van_y_vuelven_como_lista(conn):
    terceros.guardar(conn, {
        "nit": "830008686", "razon_social": "D1", "responsabilidades": ["O-13", "O-15"],
    })
    assert terceros.obtener(conn, "830008686")["responsabilidades"] == ["O-13", "O-15"]


def test_el_ciiu_se_valida(conn):
    with pytest.raises(ValueError, match="CIIU"):
        terceros.guardar(conn, {"nit": "830008686", "ciiu": "62"})


def test_contar_separa_los_que_tienen_rut(conn):
    terceros.guardar(conn, {"nit": "830008686", "razon_social": "D1"})
    terceros.guardar(conn, {"nit": "901111111", "razon_social": "Otro"})
    terceros.actualizar_desde_rut(conn, "830008686", {"razon_social": "D1"})
    assert terceros.contar(conn) == {"total": 2, "con_rut": 1, "sin_rut": 1}


# ── tablero ──────────────────────────────────────────────────────────────────

def test_el_tablero_lista_las_empresas_del_catalogo():
    sidecar._h_create_empresa({"nit": "900181831", "razon_social": "REAL Seguros"})
    sidecar._h_create_empresa({"nit": "901234567", "razon_social": "Otra SAS"})
    t = tablero.tablero("2026-09")
    assert t["periodo"] == "2026-09"
    assert {e["razon_social"] for e in t["empresas"]} == {"REAL Seguros", "Otra SAS"}
    assert t["resumen"]["empresas"] == 2
    assert t["resumen"]["con_excel"] == 0


def test_una_empresa_sin_mes_creado_se_muestra_igual():
    """El tablero tiene que decir «sin cargar», no esconder la empresa."""
    sidecar._h_create_empresa({"nit": "900181831", "razon_social": "REAL Seguros"})
    fila = tablero.tablero("2026-09")["empresas"][0]
    assert fila["mes_creado"] is False and fila["cargas"] == 0 and fila["error"] is None


def test_el_tablero_ve_el_perfil_fiscal():
    creada = sidecar._h_create_empresa({"nit": "900181831", "razon_social": "REAL Seguros"})
    assert tablero.tablero("2026-09")["empresas"][0]["perfil_fiscal"] is False
    sidecar._h_save_perfil_fiscal({"db_path": creada["db_path"], "perfil": {
        "vigencia_desde": "2026-01-01", "regimen": "ordinario",
    }})
    assert tablero.tablero("2026-09")["empresas"][0]["perfil_fiscal"] is True


def test_una_empresa_ilegible_no_tumba_el_tablero(tmp_path):
    """Un .db corrupto deja su fila con el motivo y las demás siguen."""
    sidecar._h_create_empresa({"nit": "900181831", "razon_social": "REAL Seguros"})
    creada = sidecar._h_create_empresa({"nit": "901234567", "razon_social": "Rota SAS"})
    from pathlib import Path
    Path(creada["db_path"]).write_bytes(b"esto no es una base de datos")

    t = tablero.tablero("2026-09")
    assert len(t["empresas"]) == 2
    rota = next(e for e in t["empresas"] if e["nit"] == "901234567")
    sana = next(e for e in t["empresas"] if e["nit"] == "900181831")
    assert rota["error"] is not None
    assert sana["error"] is None
    assert t["resumen"]["ilegibles"] == 1


def test_el_tablero_cuenta_las_cargas_del_mes(sample_excel):
    creada = sidecar._h_create_empresa({"nit": "900181831", "razon_social": "REAL Seguros"})
    sidecar._h_create_periodo({"db_path": creada["db_path"], "periodo": "2026-02"})
    sidecar._h_import_excel({
        "db_path": creada["db_path"], "source_path": str(sample_excel), "periodo": "2026-02",
    })
    con_cargas = [e for e in tablero.tablero("2026-02")["empresas"] if e["cargas"]]
    assert len(con_cargas) == 1
    assert con_cargas[0]["filas"] > 0
