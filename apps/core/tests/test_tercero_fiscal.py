"""Los datos fiscales de un tercero, que hay que escribir a mano.

La consulta pública de la DIAN devuelve razón social y tipo, y nada más —
comprobado el 2026-10-17; la otra página, *Consulta Estado RUT*, está fuera de
servicio—. Las responsabilidades y el estado viven en el certificado de RUT, que
es un PDF autenticado.

Esto importa porque **la validación V7 lee `estado_rut`**, y hasta ahora ningún
camino lo escribía: era una validación que no podía dispararse nunca.
"""
from pathlib import Path

import pytest

from contab_core import storage, terceros, validations
from contab_core.sidecar import HANDLERS


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, nit="900181831", dv="7", razon_social="PRUEBA")
    c = storage.connect(db)
    storage.ensure_schema(c)
    yield c
    c.close()


def test_el_catalogo_sale_de_un_solo_sitio():
    """La pantalla y el motor leen la misma lista; dos copias divergen."""
    cat = HANDLERS["catalogo_tercero"]({})
    codigos = [r["codigo"] for r in cat["responsabilidades"]]
    assert codigos == list(terceros.CODIGOS_RESPONSABILIDAD)
    assert "O-13" in codigos and "O-15" in codigos
    assert cat["estados_rut"] == list(terceros.ESTADOS_RUT)


def test_guardar_a_mano_el_estado_del_rut(conn):
    terceros.guardar(conn, {"nit": "830008686", "razon_social": "D1",
                            "estado_rut": "CANCELADO"})
    t = terceros.obtener(conn, "830008686")
    assert t["estado_rut"] == "CANCELADO"


def test_v7_se_dispara_con_lo_que_se_escribio_a_mano(conn):
    """El recorrido entero: se teclea el estado y la validación lo caza."""
    terceros.guardar(conn, {"nit": "800100200", "razon_social": "PROVEEDOR",
                            "estado_rut": "CANCELADO"})
    estados = {r["nit"]: r["estado_rut"] for r in
               conn.execute("SELECT nit, estado_rut FROM tercero"
                            " WHERE estado_rut IS NOT NULL").fetchall()}
    documento = {"cufe": "a" * 96, "tipo": "factura", "numero": "F-1",
                 "emisor_nit": "800100200", "impuestos": [], "referencias": []}
    fallos = validations.evaluate_xml(documento, estados_rut=estados)
    assert [c for c, _ in fallos] == [validations.CODIGO_RUT_CANCELADO]


def test_las_responsabilidades_se_guardan_como_lista_desde_texto(conn):
    """La pantalla manda texto; el motor necesita códigos sueltos."""
    terceros.guardar(conn, {"nit": "830008686", "razon_social": "D1",
                            "responsabilidades": "O-13, O-15 O-23"})
    t = terceros.obtener(conn, "830008686")
    assert t["responsabilidades"] == ["O-13", "O-15", "O-23"]


def test_preguntar_por_una_responsabilidad_tolera_el_formato():
    assert terceros.tiene_responsabilidad({"responsabilidades": ["O-13"]}, "o-13")
    assert terceros.tiene_responsabilidad({"responsabilidades": "O-15, O-23"}, "O-23")
    assert not terceros.tiene_responsabilidad({"responsabilidades": ["O-48"]}, "O-13")
    assert not terceros.tiene_responsabilidad(None, "O-13")


def test_un_codigo_que_no_esta_en_la_lista_tambien_se_guarda(conn):
    """La lista son las que cambian el cálculo, no el catálogo entero del RUT."""
    terceros.guardar(conn, {"nit": "830008686", "razon_social": "D1",
                            "responsabilidades": "O-13, O-99"})
    assert terceros.obtener(conn, "830008686")["responsabilidades"] == ["O-13", "O-99"]
