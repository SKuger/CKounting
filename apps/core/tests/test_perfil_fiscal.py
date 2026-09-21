"""Perfil fiscal de la empresa y municipios de ICA (Fase 1.1 del plan DIAN → Siigo).

Lo que estos tests protegen de verdad es la **vigencia**: el perfil no es una fila
sino una lista fechada, porque a una empresa la nombran autorretenedora a mitad de
año y la causación de los meses anteriores tiene que seguir calculándose con lo
que la empresa era entonces.
"""
import pytest

from contab_core import perfil_fiscal, sidecar, storage
from contab_core.perfil_fiscal import PerfilFiscalError


@pytest.fixture()
def conn(tmp_path):
    db = tmp_path / "empresa.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL Seguros")
    c = storage.connect(db)
    storage.ensure_schema(c)
    yield c
    c.close()


BASE = {
    "vigencia_desde": "2026-01-01",
    "regimen": "ordinario",
    "responsable_iva": True,
    "periodicidad_iva": "bimestral",
}


# ── vigencia ─────────────────────────────────────────────────────────────────

def test_sin_perfil_devuelve_none(conn):
    """Una empresa sin configurar no inventa un perfil por defecto: quien calcule
    una retención sobre un supuesto hace más daño que quien no la calcula."""
    assert perfil_fiscal.perfil_vigente(conn) is None


def test_el_perfil_vigente_depende_de_la_fecha(conn):
    perfil_fiscal.guardar_perfil(conn, BASE)
    perfil_fiscal.guardar_perfil(
        conn, {**BASE, "vigencia_desde": "2026-08-01", "autorretenedor_renta": True}
    )

    assert perfil_fiscal.perfil_vigente(conn, fecha="2026-03-15")["autorretenedor_renta"] is False
    assert perfil_fiscal.perfil_vigente(conn, fecha="2026-09-15")["autorretenedor_renta"] is True


def test_un_perfil_futuro_no_manda_todavia(conn):
    perfil_fiscal.guardar_perfil(conn, BASE)
    perfil_fiscal.guardar_perfil(conn, {**BASE, "vigencia_desde": "2027-01-01", "regimen": "simple"})
    assert perfil_fiscal.perfil_vigente(conn, fecha="2026-06-01")["regimen"] == "ordinario"


def test_antes_de_la_primera_vigencia_no_hay_perfil(conn):
    perfil_fiscal.guardar_perfil(conn, BASE)
    assert perfil_fiscal.perfil_vigente(conn, fecha="2025-12-31") is None


def test_guardar_la_misma_fecha_actualiza_esa_version(conn):
    perfil_fiscal.guardar_perfil(conn, BASE)
    perfil_fiscal.guardar_perfil(conn, {**BASE, "gran_contribuyente": True})
    perfiles = perfil_fiscal.listar_perfiles(conn)
    assert len(perfiles) == 1, "misma vigencia = misma versión, no una segunda"
    assert perfiles[0]["gran_contribuyente"] is True


# ── validación ───────────────────────────────────────────────────────────────

def test_responsable_de_iva_exige_periodicidad(conn):
    with pytest.raises(PerfilFiscalError, match="periodicidad"):
        perfil_fiscal.guardar_perfil(conn, {**BASE, "periodicidad_iva": ""})


def test_no_responsable_de_iva_no_guarda_periodicidad(conn):
    guardado = perfil_fiscal.guardar_perfil(
        conn, {**BASE, "responsable_iva": False, "periodicidad_iva": "bimestral"}
    )
    assert guardado["periodicidad_iva"] is None


def test_regimen_desconocido_es_error(conn):
    with pytest.raises(PerfilFiscalError, match="régimen desconocido"):
        perfil_fiscal.guardar_perfil(conn, {**BASE, "regimen": "especial"})


def test_la_fecha_de_vigencia_se_valida(conn):
    with pytest.raises(PerfilFiscalError, match="AAAA-MM-DD"):
        perfil_fiscal.guardar_perfil(conn, {**BASE, "vigencia_desde": "01-01-2026"})
    with pytest.raises(PerfilFiscalError, match="no es una fecha real"):
        perfil_fiscal.guardar_perfil(conn, {**BASE, "vigencia_desde": "2026-02-31"})


def test_el_ciiu_son_cuatro_digitos(conn):
    with pytest.raises(PerfilFiscalError, match="CIIU"):
        perfil_fiscal.guardar_perfil(conn, {**BASE, "ciiu": "62"})


# ── ICA ──────────────────────────────────────────────────────────────────────

def test_la_tarifa_de_ica_acepta_coma_y_no_pasa_por_float(conn):
    """6,9 por mil en binario no es 6,9 (D-075). Se guarda como texto decimal."""
    guardado = perfil_fiscal.guardar_municipio_ica(
        conn,
        {"municipio": "Medellín", "codigo_dane": "05001",
         "tarifa_por_mil": "6,9", "vigencia_desde": "2026-01-01"},
    )
    assert guardado["tarifa_por_mil"] == "6.9"


def test_una_empresa_puede_declarar_ica_en_varios_municipios(conn):
    for muni, dane, tarifa in (("Medellín", "05001", "6.9"), ("Bogotá", "11001", "9.66")):
        perfil_fiscal.guardar_municipio_ica(
            conn, {"municipio": muni, "codigo_dane": dane,
                   "tarifa_por_mil": tarifa, "vigencia_desde": "2026-01-01"}
        )
    assert {m["municipio"] for m in perfil_fiscal.listar_municipios_ica(conn)} == {"Medellín", "Bogotá"}


def test_la_tarifa_de_ica_tambien_tiene_vigencia(conn):
    for vig, tarifa in (("2026-01-01", "6.9"), ("2026-07-01", "7.0")):
        perfil_fiscal.guardar_municipio_ica(
            conn, {"municipio": "Medellín", "tarifa_por_mil": tarifa, "vigencia_desde": vig}
        )
    vigentes = perfil_fiscal.listar_municipios_ica(conn, fecha="2026-03-01")
    assert [m["tarifa_por_mil"] for m in vigentes] == ["6.9"]
    vigentes = perfil_fiscal.listar_municipios_ica(conn, fecha="2026-08-01")
    assert [m["tarifa_por_mil"] for m in vigentes] == ["7.0"], "solo la que manda ese día"


def test_tarifa_de_ica_invalida_es_error(conn):
    with pytest.raises(PerfilFiscalError, match="no es un número"):
        perfil_fiscal.guardar_municipio_ica(
            conn, {"municipio": "Medellín", "tarifa_por_mil": "seis", "vigencia_desde": "2026-01-01"}
        )


def test_codigo_dane_invalido_es_error(conn):
    with pytest.raises(PerfilFiscalError, match="DANE"):
        perfil_fiscal.guardar_municipio_ica(
            conn, {"municipio": "Medellín", "codigo_dane": "5001",
                   "tarifa_por_mil": "6.9", "vigencia_desde": "2026-01-01"}
        )


# ── RPCs ─────────────────────────────────────────────────────────────────────

def test_los_rpc_guardan_y_devuelven_el_perfil(tmp_path):
    creada = sidecar._h_create_empresa({"nit": "900181831", "razon_social": "REAL Seguros"})
    db_path = creada["db_path"]

    vacio = sidecar._h_get_perfil_fiscal({"db_path": db_path})
    assert vacio["perfil"] is None and vacio["perfiles"] == []

    sidecar._h_save_perfil_fiscal({"db_path": db_path, "perfil": {**BASE, "agente_reteica": True}})
    sidecar._h_save_municipio_ica({
        "db_path": db_path,
        "municipio": {"municipio": "Medellín", "tarifa_por_mil": "6,9", "vigencia_desde": "2026-01-01"},
    })

    leido = sidecar._h_get_perfil_fiscal({"db_path": db_path, "fecha": "2026-06-01"})
    assert leido["perfil"]["agente_reteica"] is True
    assert leido["municipios_ica"][0]["municipio"] == "Medellín"

    sidecar._h_delete_perfil_fiscal({"db_path": db_path, "vigencia_desde": "2026-01-01"})
    assert sidecar._h_get_perfil_fiscal({"db_path": db_path})["perfiles"] == []
