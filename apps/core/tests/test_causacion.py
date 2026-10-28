"""Las reglas de causación — tarea 4.3.

Las dirige lo que respondió el contador: decide la cuenta mirando **la factura**,
salvo tres proveedores que van **siempre** a la misma cuenta «pase lo que pase».
De ahí que la regla del proveedor gane a la del texto.

Y la prueba que más importa para el producto: **lo que él decide una vez no se
le vuelve a preguntar**. Sin esa vuelta atrás, el segundo mes cuesta lo mismo
que el primero.
"""
from pathlib import Path

import pytest

from contab_core import causacion, storage


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, nit="900181831", dv="4", razon_social="REAL")
    c = storage.connect(db)
    storage.ensure_schema(c)
    yield c
    c.close()


def doc(nit="800144355", nombre="TELESENTINEL DE ANTIOQUIA LTDA", desc="Monitoreo de alarma"):
    return {"emisor_nit": nit, "emisor_nombre": nombre,
            "lineas": [{"descripcion": desc}]}


def test_sin_reglas_no_se_inventa_una_cuenta(conn):
    p = causacion.proponer(conn, doc())
    assert p.cuenta_puc is None and p.seguro is False
    assert "Ninguna regla" in p.por_que


def test_la_regla_del_proveedor_acierta(conn):
    causacion.guardar(conn, {"tercero_nit": "800144355", "cuenta_puc": "513535"})
    p = causacion.proponer(conn, doc())
    assert p.cuenta_puc == "513535" and p.seguro is True
    assert "siempre va a" in p.por_que


def test_la_regla_por_el_texto_de_la_factura(conn):
    """«¿Qué mira para decidir la cuenta?» → «LA FACTURA»."""
    causacion.guardar(conn, {"patron": "vigilancia", "cuenta_puc": "513530"})
    p = causacion.proponer(conn, doc(nit="900999888", nombre="SEGURIDAD X",
                                     desc="Servicio de VIGILANCIA mes de septiembre"))
    assert p.cuenta_puc == "513530"
    assert "La factura dice" in p.por_que


def test_el_patron_no_depende_de_tildes_ni_mayusculas(conn):
    causacion.guardar(conn, {"patron": "telefonía", "cuenta_puc": "513535"})
    p = causacion.proponer(conn, doc(desc="TELEFONIA MOVIL CORPORATIVA"))
    assert p.cuenta_puc == "513535"


def test_una_regla_sin_patron_es_el_pase_lo_que_pase(conn):
    """Las reglas SIN patrón son el «siempre a la misma cuenta», y se escriben
    a propósito para los pocos proveedores que lo merecen."""
    causacion.guardar(conn, {"patron": "monitoreo", "cuenta_puc": "519595"})
    causacion.guardar(conn, {"tercero_nit": "800144355", "cuenta_puc": "513535"})
    p = causacion.proponer(conn, doc())
    assert p.cuenta_puc == "513535"


def test_la_regla_que_acierta_las_dos_cosas_gana_a_las_dos(conn):
    causacion.guardar(conn, {"tercero_nit": "800144355", "cuenta_puc": "513535"})
    causacion.guardar(conn, {"tercero_nit": "800144355", "patron": "monitoreo",
                             "cuenta_puc": "519510"})
    assert causacion.proponer(conn, doc()).cuenta_puc == "519510"


def test_una_regla_de_otro_proveedor_no_se_aplica(conn):
    causacion.guardar(conn, {"tercero_nit": "900252156", "cuenta_puc": "513535"})
    assert causacion.proponer(conn, doc()).cuenta_puc is None


def test_el_nombre_del_emisor_tambien_cuenta_para_el_patron(conn):
    """A veces lo que identifica la factura está en el nombre, no en la línea."""
    causacion.guardar(conn, {"patron": "ultragas", "cuenta_puc": "513560"})
    p = causacion.proponer(conn, doc(nit="811046191", nombre="ULTRAGAS S.A.S.",
                                     desc="Suministro mensual"))
    assert p.cuenta_puc == "513560"


# ───────────── la vuelta atrás: lo que hace barato el segundo mes ──────────────

def test_lo_que_se_decide_una_vez_no_se_vuelve_a_preguntar(conn):
    d = doc(nit="900252156", nombre="TODO EN ARTES S.A.S", desc="Impresión de volantes")
    assert causacion.proponer(conn, d).seguro is False

    causacion.aprender(conn, cuenta_puc="523550", tercero_nit="900252156")

    de_nuevo = causacion.proponer(conn, d)
    assert de_nuevo.seguro is True and de_nuevo.cuenta_puc == "523550"


def test_aprender_dos_veces_lo_mismo_afina_en_vez_de_duplicar(conn):
    causacion.aprender(conn, cuenta_puc="523550", tercero_nit="900252156")
    causacion.aprender(conn, cuenta_puc="523595", tercero_nit="900252156")
    reglas = causacion.listar(conn)
    assert len(reglas) == 1 and reglas[0]["cuenta_puc"] == "523595"


def test_lo_aprendido_queda_marcado_como_tal(conn):
    r = causacion.aprender(conn, cuenta_puc="523550", tercero_nit="900252156")
    assert r["origen"] == causacion.ORIGEN_APRENDIDA
    m = causacion.guardar(conn, {"tercero_nit": "811046191", "cuenta_puc": "513560"})
    assert m["origen"] == causacion.ORIGEN_MANUAL


# ─────────────────────── lo que no se deja hacer ──────────────────────────────

def test_una_regla_sin_proveedor_ni_texto_se_rechaza(conn):
    """Se aplicaría a todas las facturas del mes."""
    with pytest.raises(ValueError, match="proveedor o a qué texto"):
        causacion.guardar(conn, {"cuenta_puc": "513535"})
    with pytest.raises(ValueError):
        causacion.aprender(conn, cuenta_puc="513535")


def test_una_regla_sin_cuenta_se_rechaza(conn):
    with pytest.raises(ValueError, match="sin cuenta"):
        causacion.guardar(conn, {"tercero_nit": "800144355", "cuenta_puc": ""})


def test_una_regla_archivada_deja_de_aplicar(conn):
    r = causacion.guardar(conn, {"tercero_nit": "800144355", "cuenta_puc": "513535"})
    causacion.archivar(conn, r["id"])
    assert causacion.proponer(conn, doc()).cuenta_puc is None
    assert causacion.listar(conn) == []
    assert len(causacion.listar(conn, incluir_archivadas=True)) == 1


def test_se_cuenta_cuantas_veces_sirvio_cada_regla(conn):
    r = causacion.guardar(conn, {"tercero_nit": "800144355", "cuenta_puc": "513535"})
    causacion.marcar_usada(conn, r["id"])
    causacion.marcar_usada(conn, r["id"])
    conn.commit()
    assert causacion.listar(conn)[0]["veces_usada"] == 2


# ───── «si el concepto cambia, me presentas la nueva propuesta» (22-oct) ──────

def test_un_proveedor_conocido_que_factura_otra_cosa_se_vuelve_a_preguntar(conn):
    """Lo precisó el contador: lo aprendido vale mientras el concepto sea el
    mismo. Si cambia, quiere ver la propuesta nueva antes de aprobarla."""
    causacion.aprender(conn, cuenta_puc="513535", tercero_nit="800144355",
                       patron="monitoreo de alarma")

    igual = causacion.proponer(conn, doc(desc="Monitoreo de alarma octubre"))
    assert igual.seguro is True and igual.cuenta_puc == "513535"

    distinto = causacion.proponer(conn, doc(desc="Instalación de cámaras"))
    assert distinto.seguro is False
    assert distinto.concepto_nuevo is True, "no es un proveedor nuevo"
    assert "suele facturar" in distinto.por_que
    assert "monitoreo de alarma" in distinto.por_que


def test_un_proveedor_nuevo_se_dice_distinto_que_un_concepto_nuevo(conn):
    """Son dos cosas y la bandeja las separa: «no lo conozco» no es lo mismo
    que «lo conozco y está facturando otra cosa»."""
    nuevo = causacion.proponer(conn, doc(nit="999999999", nombre="DESCONOCIDA SAS"))
    assert nuevo.concepto_nuevo is False
    assert "Ninguna regla" in nuevo.por_que


def test_el_pase_lo_que_pase_gana_aunque_el_concepto_cambie(conn):
    """Los tres proveedores que él nombró: siempre a la misma cuenta."""
    causacion.guardar(conn, {"tercero_nit": "800144355", "cuenta_puc": "513535"})
    causacion.aprender(conn, cuenta_puc="519510", tercero_nit="800144355",
                       patron="monitoreo")
    p = causacion.proponer(conn, doc(desc="Cualquier otra cosa"))
    assert p.seguro is True and p.cuenta_puc == "513535"


def test_editar_una_regla_conserva_iva_y_lo_que_retiene_el_cliente(conn):
    """La pantalla de reglas manda el registro entero; nada se pierde al guardar."""
    r = causacion.guardar(conn, {"tercero_nit": "860037013", "cuenta_puc": "41503001",
                                 "naturaleza": "venta", "iva_codigo": "02",
                                 "retenciones_cliente": "05:1.8,07,11"})
    r = causacion.guardar(conn, {**r, "cuenta_puc": "41553001"})
    assert (r["cuenta_puc"], r["iva_codigo"], r["retenciones_cliente"]) == ("41553001", "02", "05:1.8,07,11")
    assert causacion.listar(conn)[0]["tercero_nombre"] is None, "sin el tercero en el catálogo, sin nombre"
