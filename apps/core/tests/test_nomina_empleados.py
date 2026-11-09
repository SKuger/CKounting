"""Los empleados de la nómina y sus entidades, y lo que se revisa contra la ley (D-142).

Datos inventados: ni cédulas ni nombres de nadie.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from contab_core import nomina, siigo, storage

D = Decimal


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, nit="900181831", dv="4", razon_social="PRUEBA")
    c = storage.connect(db)
    storage.ensure_schema(c)
    yield c
    c.close()


def _empleado(i="1001", nombre="EMPLEADO UNO", salario="2000000", **otros):
    e = nomina.Empleado(id=i, nombre=nombre, valores={"salario": D(salario)})
    base = D(salario)
    e.valores.update({"salud": base * 4 / 100, "pension": base * 4 / 100})
    e.valores.update({k: D(v) for k, v in otros.items()})
    return e


def test_el_empleado_se_guarda_con_sus_entidades_y_su_riesgo(conn):
    nomina.guardar_empleado(conn, {
        "id": "1001", "nombre": "EMPLEADO UNO", "riesgo": "iii",
        "salud": {"cuenta": "23700501", "nit": "800000001-1"},
        "pension": {"cuenta": "23803001", "nit": "800000002"},
        "cesantias": {"nit": "800000003"}, "caja": {"cuenta": "23704001", "nit": "800000004"}})
    [e] = nomina.empleados(conn)["empleados"]
    assert e["riesgo"] == "III"
    assert e["salud"] == {"cuenta": "23700501", "nit": "800000001"}, "el NIT sin el DV"
    assert e["cesantias"] == {"cuenta": "", "nit": "800000003"}


def test_una_clase_de_riesgo_que_no_existe_se_rechaza(conn):
    with pytest.raises(ValueError, match="I, II, III, IV o V"):
        nomina.guardar_empleado(conn, {"id": "1001", "riesgo": "VI"})


def test_la_arl_de_la_empresa_reemplaza_la_de_cada_empleado(conn):
    siigo.guardar_config(conn, {"nom:entidad:1001:arl": "23700601|800000009"})
    r = nomina.guardar_empresa(conn, {"arl": {"cuenta": "23700601", "nit": "800000010"},
                                      "smmlv": {"2026": "1.000.000"}})
    assert r["arl"] == {"cuenta": "23700601", "nit": "800000010"}
    assert "nom:entidad:1001:arl" not in siigo.config(conn)
    assert r["parametros"]["2026"]["smmlv"] == "1000000", "el salario mínimo es de todas las empresas"


def test_la_arl_sale_de_la_clase_de_riesgo_del_empleado(conn):
    q = nomina.Quincena("1Q", [_empleado()])
    p = nomina.plantilla({"nom:debito:arl": "51056801", "nom:riesgo:1001": "III"})
    lineas, _faltan = nomina.armar(q, p)
    arl = next(x for x in lineas if x.descripcion.lower().startswith("arl") and x.debito)
    assert arl.debito == Decimal("48720"), "2.000.000 × 2,436 %"


def test_lo_que_el_excel_trae_distinto_de_la_ley_se_avisa():
    p = nomina.plantilla({"nom:riesgo:1001": "I"})
    bien = nomina.revisar(nomina.Quincena("1Q", [_empleado(salario="1500000")]), p, D("1000000"))
    assert bien == []
    mal = _empleado(salario="1500000", salud="70000")
    avisos = nomina.revisar(nomina.Quincena("1Q", [mal]), p, D("1000000"))
    assert any("es 70000" in a and "4 %" in a for a in avisos)


def test_desde_4_minimos_pide_solidaridad_y_desde_10_avisa_la_exoneracion():
    p = nomina.plantilla({"nom:riesgo:1001": "I"})
    # La hoja es de una quincena: 4 mínimos al mes son 2 en la quincena.
    cuatro = nomina.revisar(nomina.Quincena("1Q", [_empleado(salario="2000000")]), p, D("1000000"))
    assert any("solidaridad" in a for a in cuatro)
    assert not any("exonerado" in a for a in cuatro)
    diez = nomina.revisar(nomina.Quincena("1Q", [_empleado(salario="5000000", fsp="50000")]), p, D("1000000"))
    assert any("exonerado" in a for a in diez)
    assert not any("solidaridad" in a for a in diez)


def test_sin_clase_de_riesgo_se_avisa():
    avisos = nomina.revisar(nomina.Quincena("1Q", [_empleado()]), nomina.plantilla({}), None)
    assert any("clase de riesgo" in a for a in avisos)
