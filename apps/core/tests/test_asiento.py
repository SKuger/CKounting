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


# ───────── D-127 · lo que la empresa emite también se causa ──────────────────
# Lo pidió el contador el 2026-10-27 probando la 0.11: el reporte trae lo que la
# empresa EMITIÓ, y eso también se contabiliza, con el receptor como tercero.

def _fila(conn, cufe, tipo, grupo, *, nit_otro, total, iva, idx):
    import json as _j
    datos = {"Grupo": grupo, "Total": total, "IVA": iva,
             "NIT Emisor": "900181831" if grupo == "Emitido" else nit_otro,
             "NIT Receptor": nit_otro if grupo == "Emitido" else "900181831",
             "Nombre Receptor": "CLIENTE SAS", "Nombre Emisor": "REAL"}
    conn.execute(
        "INSERT INTO excel_row(load_id,row_index,cufe_cude,tipo_doc,data_json,periodo)"
        " VALUES (1,?,?,?,?,'2026-09')", (idx, cufe, tipo, _j.dumps(datos)))
    conn.commit()


def _todas_las_cuentas(conn):
    conn.execute("UPDATE empresa_info SET cuenta_proveedores='220505',"
                 " cuenta_iva_descontable='240810', cuenta_clientes='130505',"
                 " cuenta_iva_generado='240805'")
    conn.commit()


def _por_cufe(conn, cufe):
    return next(a for a in asiento.listar(conn, "2026-09") if a["cufe"] == cufe)


def test_una_venta_se_causa_contra_clientes_con_iva_generado(conn):
    _todas_las_cuentas(conn)
    _fila(conn, "v" * 96, "Factura electrónica", "Emitido",
          nit_otro="901111111", total="119000", iva="19000", idx=5)
    causacion.guardar(conn, {"tercero_nit": "901111111", "cuenta_puc": "413505",
                             "naturaleza": "venta"})
    asiento.generar(conn, "2026-09")
    a = _por_cufe(conn, "v" * 96)
    assert a["naturaleza"] == "venta"
    assert a["tercero_nit"] == "901111111", "el tercero es el receptor"
    assert a["estado"] == "completo"
    por_cuenta = {ln["cuenta_puc"]: (Decimal(ln["debito"]), Decimal(ln["credito"]))
                  for ln in a["lineas"]}
    assert por_cuenta["130505"] == (Decimal("119000"), Decimal("0"))
    assert por_cuenta["413505"] == (Decimal("0"), Decimal("100000"))
    assert por_cuenta["240805"] == (Decimal("0"), Decimal("19000"))
    assert not any("retenci" in ln["descripcion"].lower() for ln in a["lineas"]), \
        "en una venta no retenemos nosotros"


def test_la_regla_de_venta_no_se_confunde_con_la_de_compra_del_mismo_nit(conn):
    """El mismo NIT puede ser cliente y proveedor: la cuenta del gasto no es la
    del ingreso."""
    _todas_las_cuentas(conn)
    causacion.guardar(conn, {"tercero_nit": "901111111", "cuenta_puc": "519530"})
    _fila(conn, "v" * 96, "Factura electrónica", "Emitido",
          nit_otro="901111111", total="119000", iva="19000", idx=5)
    asiento.generar(conn, "2026-09")
    a = _por_cufe(conn, "v" * 96)
    assert a["estado"] == "revisar", "la regla de gasto no vale para la venta"
    assert a["lineas"][1]["cuenta_puc"] is None


def test_una_nota_credito_de_venta_sale_en_negativo(conn):
    _todas_las_cuentas(conn)
    _fila(conn, "n" * 96, "Nota de crédito electrónica", "Emitido",
          nit_otro="901111111", total="119000", iva="19000", idx=6)
    asiento.generar(conn, "2026-09")
    a = _por_cufe(conn, "n" * 96)
    assert Decimal(a["lineas"][0]["debito"]) == Decimal("-119000")


def test_el_documento_soporte_se_causa_sin_iva_y_con_el_receptor(conn):
    _todas_las_cuentas(conn)
    _fila(conn, "s" * 96, "Documento soporte con no obligados", "Emitido",
          nit_otro="1017173047", total="1000000", iva="0", idx=7)
    concepto = tarifas.listar_conceptos(conn)[0]["id"]
    causacion.guardar(conn, {"tercero_nit": "1017173047", "cuenta_puc": "519530",
                             "concepto_retencion_id": concepto,
                             "naturaleza": "doc_soporte"})
    asiento.generar(conn, "2026-09")
    a = _por_cufe(conn, "s" * 96)
    assert a["naturaleza"] == "doc_soporte"
    assert a["tercero_nit"] == "1017173047"
    cuentas = [ln["cuenta_puc"] for ln in a["lineas"]]
    assert "240810" not in cuentas, "sin IVA descontable"
    assert cuentas[0] == "519530" and cuentas[-1] == "220505"
    assert "23654001" in cuentas, "la retención sí: es una compra a un no obligado"
    assert sum(Decimal(ln["debito"]) for ln in a["lineas"]) == \
        sum(Decimal(ln["credito"]) for ln in a["lineas"])


def test_la_nomina_no_se_causa(conn):
    _todas_las_cuentas(conn)
    _fila(conn, "w" * 96, "Nomina Individual", "Emitido",
          nit_otro="1017173047", total="2000000", iva="0", idx=8)
    asiento.generar(conn, "2026-09")
    assert all(a["cufe"] != "w" * 96 for a in asiento.listar(conn, "2026-09"))


def test_sin_cuenta_de_clientes_la_venta_queda_marcada(conn):
    _cuentas(conn)
    _fila(conn, "v" * 96, "Factura electrónica", "Emitido",
          nit_otro="901111111", total="119000", iva="19000", idx=5)
    causacion.guardar(conn, {"tercero_nit": "901111111", "cuenta_puc": "413505",
                             "naturaleza": "venta"})
    asiento.generar(conn, "2026-09")
    a = _por_cufe(conn, "v" * 96)
    assert a["estado"] == "revisar"
    assert any("IVA generado" in x for x in a["avisos"])


def test_al_aprobar_una_venta_se_aprende_una_regla_de_venta(conn):
    _todas_las_cuentas(conn)
    _fila(conn, "v" * 96, "Factura electrónica", "Emitido",
          nit_otro="901111111", total="119000", iva="19000", idx=5)
    asiento.generar(conn, "2026-09")
    a = _por_cufe(conn, "v" * 96)
    asiento.aprobar(conn, a["id"], cuenta_puc="413505")
    reglas = causacion.listar(conn)
    assert [(r["naturaleza"], r["cuenta_puc"]) for r in reglas] == [("venta", "413505")]
    a = _por_cufe(conn, "v" * 96)
    assert a["aprobado"] == 1 and a["lineas"][1]["cuenta_puc"] == "413505"
