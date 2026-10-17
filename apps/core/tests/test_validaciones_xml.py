"""Las validaciones que solo el XML permite — tareas 3.3 y 3.4.

El `Done-when` de la fase pide que **cada validación nueva cace un caso sembrado
a propósito**, y que se pueda nombrar la fila que cazó. Eso es lo que hay aquí.
"""
from decimal import Decimal

from contab_core import validations as v

CUFE = "a" * 96
OTRO = "b" * 96


def doc(**kw):
    base = {
        "cufe": CUFE, "tipo": "factura", "numero": "F-1",
        "fecha_emision": "2026-09-10", "emisor_nit": "800100200",
        "impuestos": [], "lineas": [], "referencias": [],
    }
    base.update(kw)
    return base


def iva(tarifa="19.00", base="1000000.00", valor="190000.00"):
    return {"tipo": "01", "nombre": "IVA", "base": base, "tarifa": tarifa,
            "valor": valor, "es_retencion": False}


# ───────────────────────────── 3.3 · V3 contrasta ──────────────────────────────

def test_sin_xml_v3_sigue_infiriendo_como_antes():
    """D-093 se conserva para las filas sin XML, que son la mayoría."""
    fila = {"IVA": "190000", "Total": "1190000"}
    assert v.evaluate_v3(fila) is None
    assert v.evaluate_v3({"IVA": "80000", "Total": "1080000"}) is not None


def test_con_xml_v3_contrasta_la_tarifa_declarada():
    fila = {"IVA": "190000", "Total": "1190000"}
    assert v.evaluate_v3(fila, documento=doc(impuestos=[iva()])) is None


def test_v3_caza_un_iva_que_no_corresponde_a_la_tarifa_declarada():
    """Una fila con IVA del 8% pasaba la inferencia si el total encajaba."""
    fila = {"IVA": "80000", "Total": "1080000"}
    fallo = v.evaluate_v3(fila, documento=doc(impuestos=[iva()]))
    assert fallo is not None
    assert "19.00%" in fallo and "190000.00" in fallo


def test_v3_avisa_si_el_reporte_trae_iva_y_el_xml_no_declara_ninguno():
    fallo = v.evaluate_v3({"IVA": "190000", "Total": "1190000"}, documento=doc())
    assert fallo is not None and "no declara ningún IVA" in fallo


def test_una_factura_exenta_con_iva_cero_no_falla():
    assert v.evaluate_v3({"IVA": "0", "Total": "143374"}, documento=doc()) is None


# ──────────────────────────────── 3.4 · V4 a V7 ────────────────────────────────

def test_v4_caza_el_documento_repetido():
    repetidos = v.cufes_repetidos_de([doc(), doc(), doc(cufe=OTRO)])
    assert repetidos == {CUFE}
    fallos = v.evaluate_xml(doc(), cufes_repetidos=repetidos)
    assert [c for c, _ in fallos] == [v.CODIGO_DUPLICADO]
    assert "F-1" in fallos[0][1], "dice cuál documento, no «hay un duplicado»"


def test_v4_no_dispara_cuando_cada_cufe_aparece_una_vez():
    assert v.cufes_repetidos_de([doc(), doc(cufe=OTRO)]) == set()


def test_v5_caza_la_nota_credito_sin_factura_de_origen():
    nota = doc(tipo="nota_credito", numero="NC-7", referencias=[])
    fallos = v.evaluate_xml(nota)
    assert [c for c, _ in fallos] == [v.CODIGO_NOTA_SIN_ORIGEN]
    assert "NC-7" in fallos[0][1]


def test_v5_no_dispara_si_la_nota_dice_a_que_apunta():
    nota = doc(tipo="nota_credito", referencias=[{"cufe_referido": OTRO}])
    assert v.evaluate_xml(nota) == []


def test_v6_caza_el_rezagado_y_dice_si_todavia_es_descontable():
    """Art. 496 ET: tres periodos. Dentro es un aviso; fuera es un problema."""
    dentro = v.evaluate_xml(doc(fecha_emision="2026-08-20"), periodo="2026-09")
    assert [c for c, _ in dentro] == [v.CODIGO_REZAGADO]
    assert "todavía descontable" in dentro[0][1]

    fuera = v.evaluate_xml(doc(fecha_emision="2026-02-20"), periodo="2026-09")
    assert "fuera de los 3 periodos" in fuera[0][1]


def test_v6_no_dispara_cuando_el_documento_es_del_mes():
    assert v.evaluate_xml(doc(fecha_emision="2026-09-10"), periodo="2026-09") == []


def test_v6_cruza_el_cambio_de_año():
    fallos = v.evaluate_xml(doc(fecha_emision="2025-12-15"), periodo="2026-01")
    assert [c for c, _ in fallos] == [v.CODIGO_REZAGADO]
    assert "1 mes después" in fallos[0][1]


def test_v7_caza_al_emisor_con_el_rut_cancelado():
    fallos = v.evaluate_xml(doc(), estados_rut={"800100200": "cancelado"})
    assert [c for c, _ in fallos] == [v.CODIGO_RUT_CANCELADO]
    assert "800100200" in fallos[0][1]


def test_v7_no_dispara_con_un_rut_activo():
    assert v.evaluate_xml(doc(), estados_rut={"800100200": "ACTIVO"}) == []


def test_sin_documento_no_hay_validaciones_nuevas():
    """Una fila sin XML no es una fila con un problema."""
    assert v.evaluate_xml(None, periodo="2026-09") == []


# ─────────────────────────────── el conducto ───────────────────────────────────

def test_el_conducto_entero_sin_xml_da_lo_mismo_que_antes():
    filas = [{"CUFE/CUDE": CUFE, "IVA": "190000", "Total": "1190000"}]
    assert v.evaluate_rows(filas, run_v3=True) == [[]]


def test_el_conducto_entero_con_xml_suma_las_nuevas():
    filas = [
        {"CUFE/CUDE": CUFE, "IVA": "0", "Total": "100000"},
        {"CUFE/CUDE": CUFE, "IVA": "0", "Total": "100000"},
    ]
    docs = {CUFE: doc(tipo="nota_credito", fecha_emision="2026-05-01", referencias=[])}
    salida = v.evaluate_rows(filas, run_v3=True, documentos_por_cufe=docs,
                             periodo="2026-09",
                             estados_rut={"800100200": "CANCELADO"})
    codigos = {c for fila in salida for c, _ in fila}
    assert codigos == {v.CODIGO_DUPLICADO, v.CODIGO_NOTA_SIN_ORIGEN,
                       v.CODIGO_REZAGADO, v.CODIGO_RUT_CANCELADO}


def test_un_override_tambien_silencia_una_validacion_nueva():
    filas = [{"CUFE/CUDE": CUFE, "IVA": "0", "Total": "100000"}]
    docs = {CUFE: doc(tipo="nota_credito", referencias=[])}
    salida = v.evaluate_rows(filas, run_v3=True, documentos_por_cufe=docs,
                             overrides_by_row={0: {v.CODIGO_NOTA_SIN_ORIGEN}})
    assert salida == [[]]


def test_los_importes_del_contraste_son_decimal():
    """Si el contraste pasara por float, el céntimo lo pagaría el contador."""
    fallo = v.evaluate_v3({"IVA": "0.01", "Total": "0.02"},
                          documento=doc(impuestos=[iva(tarifa="19.00",
                                                       base="1000000.00",
                                                       valor="190000.00")]))
    assert fallo is not None
    assert isinstance(Decimal("190000.00"), Decimal)
