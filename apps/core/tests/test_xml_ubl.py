"""El parser del XML UBL — tarea 3.1.

Lo que de verdad importa aquí son dos cosas: que los importes **cuadren al
céntimo** y que un archivo que no se pueda leer **diga por qué** en vez de
devolver un documento vacío (D-080).
"""
from decimal import Decimal
from pathlib import Path

import pytest

from contab_core import xml_ubl

MUESTRAS = Path(__file__).resolve().parents[3] / "docs" / "samples" / "xml"

CUFE_FACTURA = "1" * 92 + "aaaa"
CUFE_NOTA = "3" * 92 + "cccc"


@pytest.fixture
def factura():
    return xml_ubl.leer(MUESTRAS / "factura-con-iva.xml")


def test_la_factura_se_lee_entera(factura):
    assert factura.estado == xml_ubl.ESTADO_OK
    d = factura.documento
    assert d.tipo == xml_ubl.TIPO_FACTURA
    assert d.cufe == CUFE_FACTURA
    assert d.numero == "SETP990000001"
    assert d.fecha_emision == "2026-09-15"
    assert d.moneda == "COP"


def test_el_nit_llega_sin_el_digito_de_verificacion(factura):
    """El XML trae «900181831-7»; el NIT es lo de antes del guion."""
    d = factura.documento
    assert d.emisor_nit == "800100200"
    assert d.receptor_nit == "900181831"
    assert d.emisor_nombre == "PAPELERIA LA FICTICIA SAS"


def test_los_importes_cuadran_al_centimo(factura):
    """Done-when de la fase: los totales coinciden con la fila del Excel."""
    d = factura.documento
    assert d.subtotal == Decimal("1500000.00")
    assert d.total == Decimal("1785000.00")
    # El subtotal es exactamente la suma de las líneas.
    assert sum(x.total for x in d.lineas) == d.subtotal
    # Y el total es el subtotal más el IVA, sin un céntimo de diferencia.
    iva = next(i for i in d.impuestos if i.tipo == "01")
    assert d.subtotal + iva.valor == d.total


def test_los_importes_son_decimal_y_no_float(factura):
    d = factura.documento
    assert isinstance(d.total, Decimal)
    assert all(isinstance(ln.total, Decimal) for ln in d.lineas)


def test_el_iva_trae_su_base_y_su_tarifa(factura):
    iva = [i for i in factura.documento.impuestos if i.tipo == "01"]
    assert len(iva) == 1
    assert iva[0].tarifa == Decimal("19.00")
    assert iva[0].base == Decimal("1500000.00")
    assert iva[0].valor == Decimal("285000.00")
    assert iva[0].es_retencion is False


def test_la_retencion_se_distingue_del_impuesto(factura):
    """Sumar una retención como si fuera IVA descuadra el mes entero."""
    rete = [i for i in factura.documento.impuestos if i.es_retencion]
    assert len(rete) == 1
    assert rete[0].tipo == "06"
    assert rete[0].tarifa == Decimal("2.50")
    assert rete[0].valor == Decimal("37500.00")
    # El total de impuestos NO incluye lo retenido.
    assert factura.documento.total_impuestos == Decimal("285000.00")


def test_las_lineas_traen_su_detalle(factura):
    lineas = factura.documento.lineas
    assert len(lineas) == 2
    assert lineas[0].descripcion == "Resma de papel carta"
    assert lineas[0].cantidad == Decimal("10.00")
    assert lineas[0].valor_unitario == Decimal("100000.00")
    assert lineas[0].impuestos[0].tarifa == Decimal("19.00")


def test_una_factura_exenta_no_inventa_impuestos():
    """La muestra real del portal era una póliza: sin `TaxTotal` ninguno."""
    r = xml_ubl.leer(MUESTRAS / "factura-exenta.xml")
    assert r.estado == xml_ubl.ESTADO_OK
    assert r.documento.impuestos == []
    assert r.documento.total_impuestos is None, "sin impuestos no es lo mismo que cero"
    assert r.documento.total == Decimal("143374.00")


def test_la_nota_credito_dice_a_que_factura_apunta():
    """Una nota sin origen no se puede imputar: es lo que caza la validación 3.4."""
    r = xml_ubl.leer(MUESTRAS / "nota-credito.xml")
    assert r.documento.tipo == xml_ubl.TIPO_NOTA_CREDITO
    refs = r.documento.referencias
    assert len(refs) == 1, "la misma referencia llega por dos caminos y se funde en una"
    assert refs[0].cufe == CUFE_FACTURA
    assert refs[0].numero == "SETP990000001"
    assert refs[0].motivo == "Anulacion de factura electronica"
    assert r.documento.lineas[0].cantidad == Decimal("1.00"), "CreditedQuantity, no Invoiced"


def test_el_adjunto_del_correo_se_desenvuelve():
    """Por correo la factura llega dentro de un CDATA; hay que sacarla."""
    r = xml_ubl.leer(MUESTRAS / "adjunto-por-correo.xml")
    assert r.estado == xml_ubl.ESTADO_OK
    assert r.documento.tipo == xml_ubl.TIPO_FACTURA
    assert r.documento.numero == "SETP990000009"
    assert r.documento.total == Decimal("1785000.00")
    assert len(r.documento.lineas) == 2


def test_un_archivo_que_no_es_xml_dice_por_que(tmp_path: Path):
    """Nunca «no hay datos» cuando lo que hay es un fallo técnico (D-080)."""
    malo = tmp_path / "roto.xml"
    malo.write_text("esto no es xml", encoding="utf-8")
    r = xml_ubl.leer(malo)
    assert r.documento is None
    assert r.estado == xml_ubl.ESTADO_NO_ES_XML
    assert r.error and "XML" in r.error


def test_un_archivo_que_no_existe_dice_por_que(tmp_path: Path):
    r = xml_ubl.leer(tmp_path / "no-esta.xml")
    assert r.documento is None
    assert r.estado == xml_ubl.ESTADO_ERROR
    assert r.error


def test_un_xml_que_no_es_un_documento_no_pasa_por_uno(tmp_path: Path):
    otro = tmp_path / "otro.xml"
    otro.write_text('<?xml version="1.0"?><ApplicationResponse/>', encoding="utf-8")
    r = xml_ubl.leer(otro)
    assert r.documento is None
    assert r.estado == xml_ubl.ESTADO_SIN_DOCUMENTO


def test_el_bom_no_rompe_la_lectura(tmp_path: Path):
    """Un BOM delante hacía fallar el parser con un error que no decía nada."""
    con_bom = tmp_path / "bom.xml"
    con_bom.write_bytes(
        b"\xef\xbb\xbf" + (MUESTRAS / "factura-exenta.xml").read_bytes())
    assert xml_ubl.leer(con_bom).estado == xml_ubl.ESTADO_OK


def test_el_nombre_del_archivo_delata_el_cufe():
    """El portal nombra cada archivo con su CUFE: sirve para emparejar sin abrir."""
    assert xml_ubl.cufe_del_nombre(f"/x/{CUFE_FACTURA}.xml") == CUFE_FACTURA
    assert xml_ubl.cufe_del_nombre("/x/factura-con-iva.xml") is None
