"""La tabla de conceptos de nómina (D-145).

El contador, 2026-11-09: «hay pagos al empleado que pueden ser base de seguridad
social y otros que no; puede haber una tabla donde se matriculen las cuentas y
se informe si dicho pago es base para la seguridad social o no». Estas pruebas
cuidan eso, más lo que contestó en la misma tanda: los anticipos van a su
cuenta con el NIT del empleado, el riesgo es el I para todos, y el salario
mínimo y el auxilio de transporte son los mismos para todas las empresas.

Datos inventados: ni cédulas ni nombres de nadie.
"""
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from contab_core import nomina, program_db, siigo, storage

D = Decimal


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, nit="900181831", dv="4", razon_social="PRUEBA")
    c = storage.connect(db)
    storage.ensure_schema(c)
    yield c
    c.close()


def _quincena(**valores):
    e = nomina.Empleado(id="1001", nombre="EMPLEADO UNO",
                        valores={"salario": D("1000000"), **{k: D(v) for k, v in valores.items()}})
    return nomina.Quincena("1Q", [e])


def _p(conn):
    return nomina.plantilla(siigo.config(conn))


def _debito(lineas, descripcion):
    return sum((x.debito for x in lineas if x.descripcion == descripcion), D(0))


def test_lo_que_es_base_de_seguridad_social_entra_en_los_aportes(conn):
    """Sin marcar, el auxilio de datos no es base; marcado, la caja sube."""
    q = _quincena(aux_datos="500000")
    antes = _debito(nomina.armar(q, _p(conn))[0], "Caja de compensación")
    assert antes == D("40000"), "4 % del salario solo"

    tabla = nomina.conceptos(conn)
    fila = next(f for f in tabla["devengos"] if f["clave"] == "aux_datos")
    assert (fila["salarial"], fila["base_ss"]) == (False, False)
    fila["base_ss"] = True
    nomina.guardar_conceptos(conn, {"devengos": tabla["devengos"]})

    lineas = nomina.armar(q, _p(conn))[0]
    assert _debito(lineas, "Caja de compensación") == D("60000"), "4 % de salario + datos"
    assert _debito(lineas, "Cesantías") == D("83300"), "las provisiones siguen sobre lo salarial"


def test_un_concepto_propio_se_lee_del_excel_y_va_a_su_cuenta(conn, tmp_path):
    nomina.guardar_conceptos(conn, {"nuevos": [{
        "nombre": "Bonificación por ventas", "tipo": "devengo", "columna": "Bonificación",
        "cuenta": "51054501", "salarial": True, "base_ss": True}]})
    tabla = nomina.conceptos(conn)
    propio = next(f for f in tabla["devengos"] if f["propio"])
    assert (propio["nombre"], propio["cuenta"], propio["columna"]) == ("Bonificación por ventas", "51054501", "Bonificación")

    ruta = tmp_path / "NOMINA.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "1Q"
    for _ in range(7):
        ws.append([])
    ws.append([None, "Id", "Nombre del empleado", "Devengado", None, None, "Neto pagado"])
    ws.append([None, None, None, "Salario devengado", "Bonificación", "Total devengado", None])
    ws.append([])
    ws.append([None, 1001, "EMPLEADO UNO", 1000000, 200000, 1200000, 1200000])
    wb.save(ruta)
    q = nomina.leer_nomina(ruta, nomina.columnas_propias(_p(conn)))["1Q"]
    assert q.columnas_sin_leer == []
    clave = propio["clave"]
    assert q.empleados[0].v(clave) == D("200000")

    lineas = nomina.armar(q, _p(conn))[0]
    bono = next(x for x in lineas if x.descripcion == "Bonificación por ventas")
    assert (bono.cuenta, bono.debito) == ("51054501", D("200000"))
    assert _debito(lineas, "Cesantías") == D("99960"), "salarial: entra en la base de las provisiones"

    nomina.guardar_conceptos(conn, {"borrar": [clave]})
    assert not any(f["propio"] for f in nomina.conceptos(conn)["devengos"])


def test_los_anticipos_van_a_su_cuenta_con_el_nit_del_empleado(conn):
    tabla = nomina.conceptos(conn)
    for f in tabla["deducciones"]:
        if f["clave"] == "otras_deducciones":
            f["cuenta"] = "13301502"
    nomina.guardar_conceptos(conn, {"deducciones": tabla["deducciones"]})
    lineas, faltan = nomina.armar(_quincena(otras_deducciones="150000"), _p(conn))
    anticipo = next(x for x in lineas if x.descripcion == "Otras deducciones")
    assert (anticipo.cuenta, anticipo.tercero, anticipo.credito) == ("13301502", "1001", D("150000"))
    assert "nom:credito:otras_deducciones" not in faltan


def test_la_clase_de_riesgo_de_la_empresa_vale_para_quien_no_tiene_la_suya(conn):
    nomina.guardar_empresa(conn, {"riesgo_por_defecto": "I"})
    q = _quincena()
    p = _p(conn)
    assert _debito(nomina.armar(q, p)[0], "ARL") == D("5220")
    assert not any("clase de riesgo" in a for a in nomina.revisar(q, p, None))


def test_salario_minimo_y_auxilio_son_de_todas_las_empresas(conn, tmp_path):
    nomina.guardar_empresa(conn, {"smmlv": {"2026": "1.750.905"}, "aux_transporte": {"2026": "$249.095"}})
    assert program_db.get_settings()["nomina:smmlv:2026"] == "1750905"
    otra = tmp_path / "otra.db"
    storage.init_empresa_db(otra, nit="900181832", dv="1", razon_social="OTRA")
    c2 = storage.connect(otra)
    storage.ensure_schema(c2)
    try:
        params = nomina.parametros("2026", nomina.plantilla(siigo.config(c2)))
    finally:
        c2.close()
    assert params == {"smmlv": D("1750905"), "aux_transporte": D("249095")}


def test_el_auxilio_de_mas_de_un_mes_se_avisa_y_el_mensualizado_no(conn):
    p = _p(conn)
    mensual = nomina.revisar(_quincena(aux_transporte="249095"), p, D("1750905"), D("249095"))
    assert not any("auxilio" in a for a in mensual), "pagárselo mensualizado en una quincena está bien"
    doble = nomina.revisar(_quincena(aux_transporte="498190"), p, D("1750905"), D("249095"))
    assert any("mayor que el de un mes" in a for a in doble)


def test_una_cuenta_con_letras_se_rechaza(conn):
    with pytest.raises(ValueError, match="solo números"):
        nomina.guardar_conceptos(conn, {"neto": {"cuenta": "2505-01"}})
