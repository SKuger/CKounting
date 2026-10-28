"""El motor de retenciones — tarea 4.2.

Dos cosas dirigen estas pruebas, y las dos vienen de lo que respondió el
contador el 2026-10-21:

1. Cuando no tiene el RUT de un proveedor, **mira la factura**. Así que el motor
   mira el catálogo primero y la factura después, y cuando ninguno dice nada
   **marca la fila para revisar** en vez de decidir en silencio.
2. Sus empresas son agentes de ReteIVA **únicamente frente a proveedores del
   régimen simple**.

Y el `Done-when` de la fase pide explícitamente esto: dos terceros distintos
sobre la misma factura tienen que dar retenciones distintas.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from contab_core import retenciones, storage, tarifas


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, nit="900181831", dv="4", razon_social="REAL")
    c = storage.connect(db)
    storage.ensure_schema(c)
    # Las tarifas, como las entregó el contador.
    tarifas.guardar_uvt(c, 2026, "52374", "Resolución DIAN 000238 de 2025")
    tarifas.guardar_concepto(c, {
        "concepto": "Compras.", "aplica_a": "declarantes", "sobre": "base",
        "tarifa": "2.5", "base_minima_uvt": "10", "cuenta_puc": "23654001",
        "vigencia_desde": "2026-01-01"})
    tarifas.guardar_concepto(c, {
        "concepto": "Honorarios", "aplica_a": "ambos", "sobre": "base",
        "tarifa": "11", "base_minima_uvt": "", "cuenta_puc": "23651503",
        "vigencia_desde": "2026-01-01"})
    tarifas.guardar_concepto(c, {
        "concepto": "ReteIVA servicios", "aplica_a": "ambos", "sobre": "iva",
        "tarifa": "15", "cuenta_puc": "23670103", "vigencia_desde": "2026-01-01"})
    yield c
    c.close()


PERFIL = {"agente_retefuente": 1, "agente_reteiva": 1, "agente_reteica": 0,
          "autorretenedor_renta": 0, "gran_contribuyente": 0, "regimen": "ordinario"}


def ident(concepto: str, conn) -> int:
    return next(x["id"] for x in tarifas.listar_conceptos(conn)
                if x["concepto"] == concepto)


def doc(**kw):
    base = {"cufe": "a" * 96, "tipo": "factura", "numero": "F-1",
            "fecha_emision": "2026-09-15", "emisor_nit": "800100200",
            "subtotal": "1000000", "total_impuestos": "190000",
            "emisor_responsabilidades": []}
    base.update(kw)
    return base


# ───────────── de dónde sale lo que se sabe del tercero ────────────────────────

def test_el_catalogo_manda_sobre_la_factura():
    resp, origen = retenciones.datos_del_tercero(
        {"responsabilidades": ["O-13"]}, doc(emisor_responsabilidades=["O-15"]))
    assert resp == ["O-13"] and origen == retenciones.ORIGEN_CATALOGO


def test_sin_catalogo_se_mira_la_factura():
    """Es literalmente lo que hace el contador."""
    resp, origen = retenciones.datos_del_tercero(
        None, doc(emisor_responsabilidades=["O-15", "O-48"]))
    assert resp == ["O-15", "O-48"] and origen == retenciones.ORIGEN_FACTURA


def test_si_nadie_dice_nada_se_admite_que_no_se_sabe():
    resp, origen = retenciones.datos_del_tercero(None, doc())
    assert resp == [] and origen == retenciones.ORIGEN_SIN_DATOS


# ───────────────────────── retención en la fuente ──────────────────────────────

def test_compras_a_un_declarante(conn):
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(),
                             tercero={"responsabilidades": ["O-13"]},
                             concepto_id=ident("Compras.", conn))
    rf = [x for x in r.retenciones if x.tipo == "retefuente"]
    assert len(rf) == 1
    assert rf[0].valor == Decimal("25000"), "2,5% de 1.000.000"
    assert rf[0].cuenta_puc == "23654001"


def test_el_mismo_documento_con_otro_tercero_da_otra_cosa(conn):
    """Done-when de la fase, literal."""
    declarante = retenciones.calcular(
        conn, perfil=PERFIL, documento=doc(), tercero={"responsabilidades": ["O-13"]},
        concepto_id=ident("Compras.", conn))
    autorretenedor = retenciones.calcular(
        conn, perfil=PERFIL, documento=doc(), tercero={"responsabilidades": ["O-15"]},
        concepto_id=ident("Compras.", conn))
    assert declarante.total == Decimal("25000")
    assert autorretenedor.total == Decimal("0")
    assert any("autorretenedor" in a for a in autorretenedor.avisos)


def test_no_se_retiene_por_debajo_de_la_base_minima(conn):
    """10 UVT de 2026 son 523.740 pesos."""
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(subtotal="400000"),
                             tercero={"responsabilidades": ["O-13"]},
                             concepto_id=ident("Compras.", conn))
    assert r.retenciones == []
    assert any("base mínima" in a for a in r.avisos)


def test_un_concepto_sin_minimo_retiene_desde_el_primer_peso(conn):
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(subtotal="50000"),
                             tercero={"responsabilidades": []},
                             concepto_id=ident("Honorarios", conn))
    rf = [x for x in r.retenciones if x.tipo == "retefuente"]
    assert rf[0].valor == Decimal("5500"), "11% de 50.000"


def test_el_concepto_que_eligio_se_aplica_aunque_el_tercero_no_sea_gran_contribuyente(conn):
    """Hasta la 0.17 «declarante» se leía como «gran contribuyente» (O-13): a un
    proveedor común, «Compras de declarantes» no se le aplicaba y el asiento
    salía completo y sin retención. Lo vio el ensayo de la guía de octubre."""
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(),
                             tercero={"responsabilidades": ["O-48"]},
                             concepto_id=ident("Compras.", conn))
    rf = [x for x in r.retenciones if x.tipo == "retefuente"]
    assert [x.valor for x in rf] == [Decimal("25000")]
    assert not r.revisar


def test_un_concepto_de_no_declarantes_a_una_empresa_se_marca(conn):
    """Una empresa siempre declara renta: «no declarantes» a una empresa es un
    error casi seguro. Se calcula igual, pero no se aprueba en lote."""
    conn.execute("UPDATE retencion_concepto SET aplica_a = 'no_declarantes' WHERE concepto = 'Compras.'")
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(emisor_nit="800100200"),
                             concepto_id=ident("Compras.", conn))
    assert r.revisar and any("no declarantes" in a for a in r.avisos)
    persona = retenciones.calcular(conn, perfil=PERFIL, documento=doc(emisor_nit="1000000003"),
                                   concepto_id=ident("Compras.", conn))
    assert not any("no declarantes" in a for a in persona.avisos), "de una persona natural no se sabe"


def test_una_empresa_que_no_es_agente_no_retiene(conn):
    r = retenciones.calcular(conn, perfil={**PERFIL, "agente_retefuente": 0},
                             documento=doc(), tercero={"responsabilidades": ["O-13"]},
                             concepto_id=ident("Compras.", conn))
    assert [x for x in r.retenciones if x.tipo == "retefuente"] == []


# ───────────────────────────────── ReteIVA ─────────────────────────────────────

def test_reteiva_solo_al_regimen_simple(conn):
    """Lo confirmó el contador: «únicamente frente a proveedores del régimen simple»."""
    simple = retenciones.calcular(
        conn, perfil=PERFIL, documento=doc(), tercero={"responsabilidades": ["O-47"]},
        concepto_id=ident("Honorarios", conn))
    riva = [x for x in simple.retenciones if x.tipo == "reteiva"]
    assert len(riva) == 1
    assert riva[0].base == Decimal("190000"), "se calcula sobre el IVA, no sobre la base"
    assert riva[0].valor == Decimal("28500"), "15% de 190.000"


def test_a_un_proveedor_ordinario_no_se_le_practica_reteiva(conn):
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(),
                             tercero={"responsabilidades": ["O-48"]},
                             concepto_id=ident("Honorarios", conn))
    assert [x for x in r.retenciones if x.tipo == "reteiva"] == []


def test_sin_iva_no_hay_reteiva(conn):
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(total_impuestos="0"),
                             tercero={"responsabilidades": ["O-47"]},
                             concepto_id=ident("Honorarios", conn))
    assert [x for x in r.retenciones if x.tipo == "reteiva"] == []


# ─────────────── lo que pasa con los 21 terceros en blanco ─────────────────────

def test_sin_datos_propone_lo_ordinario_y_marca_para_revisar(conn):
    """Es lo que hace que esto sirva desde el primer día."""
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(),
                             tercero=None, concepto_id=ident("Honorarios", conn))
    assert r.origen_tercero == retenciones.ORIGEN_SIN_DATOS
    assert r.revisar is True
    assert r.total == Decimal("110000"), "11% de 1.000.000 — la ordinaria"
    assert any("conviene mirarla" in a for a in r.avisos)


def test_lo_que_dice_la_factura_evita_tener_que_revisar(conn):
    r = retenciones.calcular(
        conn, perfil=PERFIL,
        documento=doc(emisor_responsabilidades=["O-15"]),
        tercero=None, concepto_id=ident("Honorarios", conn))
    assert r.origen_tercero == retenciones.ORIGEN_FACTURA
    assert r.revisar is False
    assert r.total == Decimal("0"), "autorretenedor: no se le retiene renta"


# ──────────────────────── lo que NO se calcula en silencio ─────────────────────

def test_sin_perfil_fiscal_no_se_inventa_nada(conn):
    r = retenciones.calcular(conn, perfil=None, documento=doc(),
                             concepto_id=ident("Honorarios", conn))
    assert r.retenciones == [] and r.revisar is True
    assert any("perfil fiscal" in a for a in r.avisos)


def test_sin_xml_no_se_calcula(conn):
    r = retenciones.calcular(conn, perfil=PERFIL, documento=None)
    assert r.retenciones == [] and r.revisar is True


def test_sin_concepto_se_pide_en_vez_de_adivinar(conn):
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(),
                             tercero={"responsabilidades": ["O-13"]})
    assert [x for x in r.retenciones if x.tipo == "retefuente"] == []
    assert r.revisar is True


def test_los_importes_son_decimal_y_se_redondean_al_peso(conn):
    r = retenciones.calcular(conn, perfil=PERFIL, documento=doc(subtotal="333333"),
                             tercero={"responsabilidades": []},
                             concepto_id=ident("Honorarios", conn))
    v = r.retenciones[0].valor
    assert isinstance(v, Decimal)
    assert v == Decimal("36667"), "11% de 333.333 = 36.666,63 → 36.667"
    assert v == v.to_integral_value(), "la DIAN no liquida céntimos"
