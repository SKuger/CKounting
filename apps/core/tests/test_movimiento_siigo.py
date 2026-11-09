"""El movimiento de Siigo como fuente de la plantilla y de las reglas (2026-11-09).

El contador mandó el movimiento del año de ALAGUNA en el reporte «Movimiento por
cuenta contable», no en el modelo de importación. Contab no lo leía, y entonces
no aprendía la nómina de una empresa que sí la tiene en Siigo: la nómina no se
podía armar ni, por tanto, llegar al archivo. Al leerlo aparecieron tres cosas
más, que estas pruebas reproducen en pequeño:

- la primera quincena se emparejaba con el 992 de **febrero**, porque el neto
  coincidía por dos pesos;
- ALAGUNA provisiona al 8,333 % y al 4,167 %, y el pasivo se buscaba al 8,33 %
  con un peso de margen: nunca se encontraba;
- con el medio peso del auxilio la quincena quedaba descuadrada por uno o dos
  pesos, y una quincena descuadrada no se puede aprobar.
"""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from contab_core import causacion, nomina, siigo, storage
from contab_core.nomina import ETIQUETA, LineaNomina

from .test_nomina import ARL, CAJA, EMPLEADOS, EPS, FONDO, _al_peso, _excel_nomina, _neto
from .test_siigo import _excel_catalogo_real

CABECERA = ["Cod. Cta", "Nit", "CV", "Fecha elaboración", "Débito", "Crédito", "Nombre tercero",
            "Valor base", "Ctro", "Descripción", "Nombre cuenta contable", "Valor Neto", "Mes", "Nv_1", "Nv_2"]


def _movimiento(ruta: Path, comprobantes):
    """comprobantes: [(cv, fecha, [(cuenta, nit, débito, crédito)])], con los
    títulos arriba y la cabecera en la fila 6, como lo exporta Siigo."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Mov-cuenta-contable"
    for titulo in ("EMPRESA DE PRUEBA", "NIT", "Movimiento por cuenta contable", "Enero a septiembre"):
        ws.append([titulo])
    ws.append([])
    ws.append(CABECERA)
    for cv, fecha, lineas in comprobantes:
        for cuenta, nit, deb, cre in lineas:
            ws.append([cuenta, nit, cv, datetime.fromisoformat(fecha), deb, cre, "TERCERO", 0, 0,
                       "detalle", "cuenta", deb - cre, None, None, None])
    wb.save(ruta)


def _p(x) -> int:
    return int(Decimal(x).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))


def _lineas_992(salario_cta: str):
    """El 992 de la quincena como lo lleva ALAGUNA: provisiones al 8,333 % y al
    4,167 %, y el pasivo de cada una con la cédula del empleado."""
    out = []
    for e in EMPLEADOS:
        _id, _n, sal, aux, salud, pen, fsp, ret, otras, rod, otros = e
        ces = _p(Decimal(sal) * Decimal("0.08333"))
        out.append((salario_cta, _id, sal, 0))
        if aux:
            out.append(("51052701", _id, _al_peso(aux), 0))
        if rod:
            out.append(("51054801", _id, rod, 0))
        if otros:
            out.append(("51054802", _id, otros, 0))
        for d, c, v in (("51053001", "25101001", ces), ("51053301", "25101002", _p(ces * Decimal("0.12"))),
                        ("51053601", "25101004", ces), ("51053901", "25101003", _p(Decimal(sal) * Decimal("0.04167")))):
            out += [(d, _id, v, 0), (c, _id, 0, v)]
        er, caja, arl = (_p(Decimal(sal) * Decimal(t)) for t in ("0.12", "0.04", "0.00522"))
        out += [("51057001", _id, er, 0), ("51057201", _id, caja, 0), ("51056801", _id, arl, 0),
                ("23700501", EPS, 0, salud), ("23704501", FONDO, 0, pen), ("23704501", FONDO, 0, er),
                ("23701001", CAJA, 0, caja), ("23700601", ARL, 0, arl)]
        if fsp:
            out.append(("23704501", FONDO, 0, fsp))
        if ret:
            out.append(("23650501", _id, 0, ret))
        if otras:
            out.append(("13301502", _id, 0, otras))
        out.append(("25050501", _id, 0, _al_peso(_neto(e))))
    return out


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, nit="900181831", dv="4", razon_social="PRUEBA")
    c = storage.connect(db)
    storage.ensure_schema(c)
    siigo.guardar_config(c, {"tipo:nomina": "992", "ultimo:992": "66"})
    yield c
    c.close()


def test_el_reporte_de_movimiento_se_lee_como_el_modelo(tmp_path):
    ruta = tmp_path / "Movimiento SIIGO 2026.xlsx"
    _movimiento(ruta, [("CC-992-15", "2026-09-15", [("51050601", "123", 1000, 0), ("25050501", "123", 0, 1000)]),
                       ("CC-11-452", "2026-09-03", [("51359501", "800100200", 500, 0)])])
    filas = siigo._filas_siigo(ruta)
    assert len(filas) == 3
    assert filas[0]["Tipo de comprobante"] == "992" and filas[0]["Consecutivo comprobante"] == 15
    assert filas[0]["Código cuenta contable"] == "51050601"
    assert filas[0]["Identificación tercero"] == "123" and filas[0]["Débito"] == 1000
    assert str(filas[2]["Fecha de elaboración"])[:10] == "2026-09-03"


def test_la_nomina_se_aprende_del_992_del_mismo_mes(conn, tmp_path):
    """Febrero tiene el mismo neto y otra cuenta de salario: con el mes, gana
    septiembre. Y del 992 salen el pasivo de cada provisión y sus tarifas."""
    n, k = tmp_path / "NOMINA.xlsx", tmp_path / "MOV.xlsx"
    _excel_nomina(n)
    _movimiento(k, [("CC-992-3", "2026-02-15", _lineas_992("51050699")),
                    ("CC-992-15", "2026-09-15", _lineas_992("51050601"))])
    r = nomina.aprender(conn, n, k, periodo="2026-09")
    cuentas = r["cuentas"]
    assert cuentas["nom:debito:salario"] == "51050601", "el de septiembre, no el de febrero"
    assert (cuentas["nom:credito:cesantias"], cuentas["nom:credito:intereses"],
            cuentas["nom:credito:prima"], cuentas["nom:credito:vacaciones"]) == (
        "25101001", "25101002", "25101004", "25101003"), "el pasivo al 8,333 % sí se encuentra"
    assert (cuentas["nom:tarifa:cesantias"], cuentas["nom:tarifa:prima"],
            cuentas["nom:tarifa:vacaciones"], cuentas["nom:tarifa:intereses"]) == ("8.333", "8.333", "4.167", "12")
    assert r["faltan"] == []


def test_un_peso_de_redondeo_se_absorbe_en_el_neto():
    lineas = [LineaNomina("51050601", "1", "Salario", debito=Decimal("1002")),
              LineaNomina("25050501", "1", ETIQUETA["neto"], credito=Decimal("600")),
              LineaNomina("25050501", "2", ETIQUETA["neto"], credito=Decimal("400"))]
    assert nomina._ajustar_redondeo(lineas, Decimal("2")) == Decimal("2")
    assert sum(x.debito for x in lineas) == sum(x.credito for x in lineas)


def test_mas_de_un_peso_por_empleado_no_es_redondeo():
    lineas = [LineaNomina("51050601", "1", "Salario", debito=Decimal("1005")),
              LineaNomina("25050501", "1", ETIQUETA["neto"], credito=Decimal("1000"))]
    assert nomina._ajustar_redondeo(lineas, Decimal("5")) == Decimal("0")
    assert lineas[1].credito == Decimal("1000")


def test_del_movimiento_se_siembra_la_regla_con_el_iva_deducido_de_la_cuenta(conn, tmp_path):
    """El reporte no trae «Código impuesto»: el catálogo dice qué código tiene
    la cuenta 24081501 en compras."""
    cat = tmp_path / "cat.xlsx"
    _excel_catalogo_real(cat)
    siigo.aplicar_catalogo(conn, siigo.cargar_catalogo(cat))
    mov = tmp_path / "MOV.xlsx"
    _movimiento(mov, [("CC-11-452", "2026-09-03", [("51359501", "800100200", 100000, 0),
                                                   ("24081501", "800100200", 19000, 0),
                                                   ("22050501", "800100200", 0, 119000)])])
    assert siigo.sembrar_reglas(conn, mov)["nuevas"] == 1
    regla = next(x for x in causacion.listar(conn) if x["tercero_nit"] == "800100200")
    assert (regla["cuenta_puc"], regla["iva_codigo"]) == ("51359501", "02")
