"""La propuesta de asiento del mes — tarea 4.4.

Junta las tres tareas anteriores. Lo que estas pruebas vigilan, por orden de
importancia:

1. **Que el asiento cuadre.** Un asiento descuadrado contabilizado es trabajo
   que alguien deshace a mano.
2. **Que no se invente las cuentas que no sabe.** El pasivo con el proveedor y
   el IVA descontable son del PUC de cada empresa.
3. **Que volver a generar no borre lo aprobado.** Rehacer la propuesta después
   de que el contador aprobó media mañana le borraría esa mañana.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from contab_core import asiento, causacion, documentos, perfil_fiscal, storage, tarifas, xml_ubl

CUFE = "1" * 92 + "aaaa"
MUESTRAS = Path(__file__).resolve().parents[3] / "docs" / "samples" / "xml"


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, nit="900181831", dv="4", razon_social="REAL")
    c = storage.connect(db)
    storage.ensure_schema(c)

    perfil_fiscal.guardar_perfil(c, {
        "vigencia_desde": "2026-01-01", "regimen": "ordinario", "responsable_iva": 1,
        "periodicidad_iva": "cuatrimestral",   # la de REAL Seguros
        "agente_retefuente": 1, "agente_reteiva": 1})
    tarifas.guardar_uvt(c, 2026, "52374")
    tarifas.guardar_concepto(c, {
        "concepto": "Compras.", "aplica_a": "ambos", "sobre": "base",
        "tarifa": "2.5", "base_minima_uvt": "10", "cuenta_puc": "23654001",
        "vigencia_desde": "2026-01-01"})

    # La factura de muestra: 1.500.000 + IVA 285.000 = 1.785.000
    lectura = xml_ubl.leer(MUESTRAS / "factura-con-iva.xml")
    documentos.guardar(c, lectura.documento, MUESTRAS / "factura-con-iva.xml")
    c.execute("INSERT INTO excel_load(id, source_path, source_name, total_rows, periodo)"
              " VALUES (1,'x.xlsx','x.xlsx',1,'2026-09')")
    c.execute("INSERT INTO excel_row(load_id,row_index,cufe_cude,data_json,periodo)"
              " VALUES (1,0,?,'{}','2026-09')", (CUFE,))
    c.commit()
    yield c
    c.close()


def _cuentas(conn, proveedores="220505", iva="240810"):
    conn.execute("UPDATE empresa_info SET cuenta_proveedores = ?,"
                 " cuenta_iva_descontable = ?", (proveedores, iva))
    conn.commit()


def _regla(conn):
    concepto = tarifas.listar_conceptos(conn)[0]["id"]
    causacion.guardar(conn, {"tercero_nit": "800100200", "cuenta_puc": "519530",
                             "concepto_retencion_id": concepto})


# ─────────────────────────── el asiento cuadra ────────────────────────────────

def test_el_asiento_cuadra_al_peso(conn):
    _cuentas(conn)
    _regla(conn)
    asiento.generar(conn, "2026-09")

    a = asiento.listar(conn, "2026-09")[0]
    debitos = sum(Decimal(x["debito"]) for x in a["lineas"])
    creditos = sum(Decimal(x["credito"]) for x in a["lineas"])
    assert debitos == creditos, a["avisos"]
    assert debitos == Decimal("1785000")


def test_las_lineas_son_las_que_debe_ser(conn):
    _cuentas(conn)
    _regla(conn)
    asiento.generar(conn, "2026-09")
    lineas = {x["cuenta_puc"]: x for x in asiento.listar(conn, "2026-09")[0]["lineas"]}

    assert Decimal(lineas["519530"]["debito"]) == Decimal("1500000"), "el gasto"
    assert Decimal(lineas["240810"]["debito"]) == Decimal("285000"), "el IVA descontable"
    assert Decimal(lineas["23654001"]["credito"]) == Decimal("37500"), "2,5% de 1.500.000"
    assert Decimal(lineas["220505"]["credito"]) == Decimal("1747500"), \
        "1.785.000 menos lo retenido"


def test_el_credito_al_proveedor_es_el_resto(conn):
    """Así cuadra por construcción y no por una suma que pueda salir mal."""
    _cuentas(conn)
    _regla(conn)
    asiento.generar(conn, "2026-09")
    lineas = asiento.listar(conn, "2026-09")[0]["lineas"]
    proveedor = next(x for x in lineas if x["descripcion"] == "Proveedores")
    otros_creditos = sum(Decimal(x["credito"]) for x in lineas
                         if x["descripcion"] != "Proveedores")
    assert Decimal(proveedor["credito"]) + otros_creditos == Decimal("1785000")


# ─────────────────── lo que no se sabe no se inventa ──────────────────────────

def test_sin_la_cuenta_del_proveedor_el_asiento_queda_marcado(conn):
    _regla(conn)
    r = asiento.generar(conn, "2026-09")
    assert r["completos"] == 0 and r["revisar"] == 1
    assert any("pasivo con el proveedor" in a for a in r["avisos"])
    assert asiento.listar(conn, "2026-09")[0]["estado"] == asiento.ESTADO_REVISAR


def test_sin_la_cuenta_del_iva_se_dice_cual_falta(conn):
    _cuentas(conn, iva="")
    _regla(conn)
    asiento.generar(conn, "2026-09")
    a = asiento.listar(conn, "2026-09")[0]
    assert any("IVA descontable" in x for x in a["avisos"])


def test_sin_regla_el_documento_queda_para_decidir(conn):
    """«380 con regla conocida [aprobar todos] · 32 nuevos [decidir]»."""
    _cuentas(conn)
    r = asiento.generar(conn, "2026-09")
    assert r["completos"] == 0 and r["revisar"] == 1
    a = asiento.listar(conn, "2026-09")[0]
    assert a["lineas"][0]["cuenta_puc"] is None
    assert any("Ninguna regla" in x for x in a["avisos"])


def test_sin_regla_y_sin_saber_del_proveedor_queda_para_revisar(conn):
    """Con 21 de 25 terceros en blanco, esto es el caso corriente la primera
    vez: propone la retención ordinaria pero no la da por buena."""
    _cuentas(conn)
    conn.execute("UPDATE documento SET emisor_responsabilidades = NULL")
    conn.commit()
    r = asiento.generar(conn, "2026-09")
    assert r["revisar"] == 1
    assert any("no se sabe" in x.lower()
               for x in asiento.listar(conn, "2026-09")[0]["avisos"])


def test_si_ya_hay_regla_no_se_vuelve_a_preguntar_por_el_tercero(conn):
    """La promesa central: aprobar la primera factura de un proveedor sirve
    para las siguientes. Si el motor siguiera pidiendo revisión por no conocer
    sus responsabilidades, aprobar la primera no habría servido de nada."""
    _cuentas(conn)
    _regla(conn)
    conn.execute("UPDATE documento SET emisor_responsabilidades = NULL")
    conn.commit()
    r = asiento.generar(conn, "2026-09")
    assert r["completos"] == 1 and r["revisar"] == 0
    avisos = asiento.listar(conn, "2026-09")[0]["avisos"]
    assert any("se decidió la primera vez" in x for x in avisos), \
        "sigue diciéndolo, pero ya no bloquea"


def test_con_regla_el_documento_se_puede_aprobar_en_lote(conn):
    """La factura declara las responsabilidades del emisor, así que no hay nada
    que preguntarle al contador."""
    _cuentas(conn)
    _regla(conn)
    r = asiento.generar(conn, "2026-09")
    assert r["completos"] == 1 and r["revisar"] == 0
    assert r["porcentaje_completo"] == 100


# ───────────────────────── volver a generar ───────────────────────────────────

def test_volver_a_generar_no_duplica(conn):
    _cuentas(conn)
    _regla(conn)
    asiento.generar(conn, "2026-09")
    asiento.generar(conn, "2026-09")
    assert len(asiento.listar(conn, "2026-09")) == 1
    assert len(asiento.listar(conn, "2026-09")[0]["lineas"]) == 4


def test_lo_aprobado_no_se_rehace(conn):
    """Rehacer después de que aprobó media mañana le borraría esa mañana."""
    _cuentas(conn)
    _regla(conn)
    asiento.generar(conn, "2026-09")
    conn.execute("UPDATE asiento_propuesto SET aprobado = 1,"
                 " avisos = '[\"lo tocó una persona\"]'")
    conn.commit()

    asiento.generar(conn, "2026-09")
    a = asiento.listar(conn, "2026-09")[0]
    assert a["aprobado"] == 1
    assert a["avisos"] == ["lo tocó una persona"], "no se regeneró encima"


# ─────────────────────────────── el resumen ───────────────────────────────────

def test_el_resumen_cuenta_lo_que_la_pantalla_necesita(conn):
    _cuentas(conn)
    _regla(conn)
    asiento.generar(conn, "2026-09")
    r = asiento.resumen(conn, "2026-09")
    assert r == {"periodo": "2026-09", "total": 1, "completos": 1, "revisar": 0,
                 "aprobados": 0, "porcentaje_completo": 100}


def test_se_cuentan_las_filas_del_mes_que_no_tienen_xml(conn):
    """Sin XML no hay propuesta, y el contador tiene que saber cuántas son."""
    conn.execute("INSERT INTO excel_row(load_id,row_index,cufe_cude,data_json,periodo)"
                 " VALUES (1,1,?,'{}','2026-09')", ("9" * 96,))
    conn.commit()
    r = asiento.generar(conn, "2026-09")
    assert r["sin_xml"] == 1


# ───────── 4.5 · aprobar es enseñarle a Contab lo que acaba de decidir ────────
# «Para el primer registro de un proveedor me muestras cómo sería, yo lo valido
# y en caso de un cambio lo pueda realizar yo; y como por lo general el concepto
# que factura es el mismo, las siguientes se registrarían de esa forma.»

def test_al_aprobar_corrigiendo_la_cuenta_se_aprende_la_regla(conn):
    _cuentas(conn)
    asiento.generar(conn, "2026-09")
    a = asiento.listar(conn, "2026-09")[0]
    assert a["estado"] == asiento.ESTADO_REVISAR, "sin regla, él decide"

    asiento.aprobar(conn, a["id"], cuenta_puc="519530", patron="resma de papel")

    reglas = causacion.listar(conn)
    assert len(reglas) == 1
    assert reglas[0]["cuenta_puc"] == "519530"
    assert reglas[0]["tercero_nit"] == "800100200"
    assert reglas[0]["origen"] == causacion.ORIGEN_APRENDIDA


def test_la_siguiente_factura_del_mismo_proveedor_ya_sale_sola(conn):
    """Es el punto entero del producto: que el segundo mes sea barato."""
    _cuentas(conn)
    asiento.generar(conn, "2026-09")
    a = asiento.listar(conn, "2026-09")[0]
    asiento.aprobar(conn, a["id"], cuenta_puc="519530", patron="resma de papel")

    documento = documentos.documento_por_cufe(conn, CUFE)
    p = causacion.proponer(conn, documento)
    assert p.seguro is True and p.cuenta_puc == "519530"


def test_al_aprobar_se_guardan_las_cuentas_de_esa_empresa(conn):
    """«Las cuentas pueden variar por cada una de las empresas» — y como cada
    empresa tiene su propia base (D-003), no hay forma de mezclarlas."""
    asiento.generar(conn, "2026-09")
    a = asiento.listar(conn, "2026-09")[0]
    asiento.aprobar(conn, a["id"], cuenta_puc="519530",
                    cuenta_proveedores="220510", cuenta_iva_descontable="240820")

    info = dict(conn.execute(
        "SELECT cuenta_proveedores, cuenta_iva_descontable FROM empresa_info").fetchone())
    assert info["cuenta_proveedores"] == "220510"
    assert info["cuenta_iva_descontable"] == "240820"


def test_el_asiento_aprobado_se_rehace_con_lo_corregido(conn):
    asiento.generar(conn, "2026-09")
    a = asiento.listar(conn, "2026-09")[0]
    r = asiento.aprobar(conn, a["id"], cuenta_puc="519530",
                        cuenta_proveedores="220510", cuenta_iva_descontable="240820")
    cuentas = {x["cuenta_puc"] for x in r["lineas"]}
    assert "519530" in cuentas and "220510" in cuentas and "240820" in cuentas
    assert r["aprobado"] == 1 and r["estado"] == asiento.ESTADO_COMPLETO


def test_aprobar_en_lote_solo_toca_lo_completo(conn):
    _cuentas(conn)
    _regla(conn)
    asiento.generar(conn, "2026-09")
    r = asiento.aprobar_lote(conn, "2026-09")
    assert r["aprobados"] == 1 and r["aprobados"] == r["total"]


def test_lo_marcado_no_se_aprueba_en_lote(conn):
    _cuentas(conn)
    asiento.generar(conn, "2026-09")          # sin regla → queda en revisar
    r = asiento.aprobar_lote(conn, "2026-09")
    assert r["aprobados"] == 0


def test_aprobar_por_error_se_puede_deshacer(conn):
    _cuentas(conn)
    _regla(conn)
    asiento.generar(conn, "2026-09")
    a = asiento.listar(conn, "2026-09")[0]
    asiento.aprobar(conn, a["id"])
    vuelto = asiento.desaprobar(conn, a["id"])
    assert vuelto["aprobado"] == 0


def test_se_puede_aprobar_sin_aprender_nada(conn):
    """Una factura rara de un proveedor no tiene por qué volverse su regla."""
    _cuentas(conn)
    asiento.generar(conn, "2026-09")
    a = asiento.listar(conn, "2026-09")[0]
    asiento.aprobar(conn, a["id"], cuenta_puc="519530", aprender_regla=False)
    assert causacion.listar(conn) == []


# ──────── lo que la revisión adversarial destapó: la UI no podía decidir ───────

def test_aprobar_diciendo_sin_retencion_libera_a_los_hermanos(conn):
    """Desde la pantalla no se podía elegir retención ni «ninguna», así que la
    regla aprendida no contaba como decisión y aprobar la primera factura no
    liberaba las siguientes. Es la promesa central, y estaba rota en la UI."""
    _cuentas(conn)
    conn.execute("UPDATE documento SET emisor_responsabilidades = NULL")
    conn.commit()
    asiento.generar(conn, "2026-09")
    a = asiento.listar(conn, "2026-09")[0]
    assert a["estado"] == asiento.ESTADO_REVISAR

    asiento.aprobar(conn, a["id"], cuenta_puc="519530", sin_retencion=True)

    regla = causacion.listar(conn)[0]
    assert regla["sin_retencion"] == 1, "la decisión queda en la regla"
    # Otra factura del mismo proveedor: tiene que salir lista, sin retención.
    conn.execute("UPDATE asiento_propuesto SET aprobado = 0")
    conn.commit()
    r = asiento.generar(conn, "2026-09")
    assert r["completos"] == 1 and r["revisar"] == 0
    lineas = asiento.listar(conn, "2026-09")[0]["lineas"]
    assert not any("%" in ln["descripcion"] for ln in lineas), "ninguna línea de retención"
