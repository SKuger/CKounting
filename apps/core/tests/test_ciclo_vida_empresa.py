"""Ciclo de vida de una empresa: crear, borrar, recuperar, y el catálogo central.
Hallazgos #11 (D-079), #12 (D-077) y #13 (D-078) de la revisión."""
import pytest

from contab_core import backup, paths, program_db, sidecar, storage


def _crear(nit="900181831", razon="REAL Seguros"):
    return sidecar._h_create_empresa({"nit": nit, "razon_social": razon})


# ── #11 — crear una empresa que ya existe ────────────────────────────────────

def test_crear_la_misma_empresa_dos_veces_falla():
    """Antes `init_empresa_db` era idempotente y el handler devolvía éxito con la
    razón social ENVIADA, aunque la BD conservara la anterior: el usuario creía
    haber creado una empresa nueva y estaba editando otra."""
    _crear()
    with pytest.raises(ValueError, match="Ya existe una empresa"):
        _crear()


def test_crear_no_pisa_la_razon_social_existente():
    """El caso peligroso: mismo NIT y mismo slug, razón social distinta."""
    primera = _crear(razon="REAL Seguros")
    with pytest.raises(ValueError):
        _crear(nit="900181831", razon="REAL Seguros SAS")
    info = storage.read_empresa_info(primera["db_path"])
    assert info["razon_social"] == "REAL Seguros", "la existente no se toca"


def test_mismo_nit_con_otro_nombre_avisa_en_vez_de_duplicar():
    """Otro nombre → otro archivo → dos contabilidades del mismo contribuyente."""
    _crear(razon="REAL Seguros")
    with pytest.raises(ValueError, match="ya está registrado"):
        _crear(nit="900181831", razon="Otra Cosa Ltda")
    assert len(paths.scan_empresa_dbs()) == 1


def test_el_nit_se_compara_normalizado():
    _crear(nit="900181831", razon="REAL")
    with pytest.raises(ValueError, match="ya está registrado"):
        _crear(nit="900.181.831", razon="Distinta SA")


# ── #13 — borrar va a la papelera, no al vacío ───────────────────────────────

def test_borrar_mueve_a_la_papelera_y_es_recuperable():
    """Borrar una empresa es borrar la contabilidad de un cliente, con obligación
    legal de conservación: no puede depender de un clic bien dado."""
    emp = _crear()
    res = sidecar._h_delete_empresa({"db_path": emp["db_path"], "confirm_nit": "900181831"})

    from pathlib import Path
    assert not Path(emp["db_path"]).exists(), "sale de la carpeta de empresas"
    assert Path(res["papelera"]).is_file(), "pero sigue existiendo en la papelera"

    enPapelera = backup.listar_papelera()
    assert len(enPapelera) == 1
    assert enPapelera[0]["nit"] == "900181831"
    assert enPapelera[0]["dias_restantes"] <= backup.PAPELERA_RETENCION_DIAS

    vuelta = backup.restaurar_de_papelera(enPapelera[0]["archivo"])
    assert Path(vuelta["db_path"]).is_file()
    assert storage.read_empresa_info(vuelta["db_path"])["razon_social"] == "REAL Seguros"
    assert backup.listar_papelera() == []


def test_borrar_sigue_exigiendo_el_nit_correcto():
    emp = _crear()
    with pytest.raises(ValueError, match="no coincide"):
        sidecar._h_delete_empresa({"db_path": emp["db_path"], "confirm_nit": "123"})
    from pathlib import Path
    assert Path(emp["db_path"]).exists(), "no se movió nada"


def test_la_papelera_se_purga_a_los_n_dias(monkeypatch):
    import os
    import time

    emp = _crear()
    res = sidecar._h_delete_empresa({"db_path": emp["db_path"], "confirm_nit": "900181831"})

    from pathlib import Path
    viejo = Path(res["papelera"])
    antiguo = time.time() - (backup.PAPELERA_RETENCION_DIAS + 1) * 86400
    os.utime(viejo, (antiguo, antiguo))

    assert backup.purgar_papelera() == 1
    assert not viejo.exists()


# ── #12 — el catálogo central deja de mentir ─────────────────────────────────

def test_borrar_desregistra_del_catalogo():
    """Antes la fila quedaba para siempre: el catálogo anunciaba empresas que ya
    no existían."""
    emp = _crear()
    assert any(e["db_path"] == emp["db_path"] for e in program_db.list_registry())

    sidecar._h_delete_empresa({"db_path": emp["db_path"], "confirm_nit": "900181831"})
    assert not any(e["db_path"] == emp["db_path"] for e in program_db.list_registry())


def test_sync_registry_purga_filas_huerfanas():
    """`sync_registry` solo añadía, así que el catálogo solo divergía hacia arriba."""
    emp = _crear()
    from pathlib import Path
    Path(emp["db_path"]).unlink()  # desaparición por fuera de la app

    res = program_db.sync_registry()
    assert res["purged"] == 1
    assert not any(e["db_path"] == emp["db_path"] for e in program_db.list_registry())


def test_restaurar_backup_registra_en_el_catalogo(tmp_path):
    """Antes la empresa restaurada no aparecía hasta el siguiente arranque."""
    emp = _crear()
    zip_res = backup.backup_empresa(emp["db_path"], str(tmp_path))
    sidecar._h_delete_empresa({"db_path": emp["db_path"], "confirm_nit": "900181831"})

    restaurada = backup.restore_empresa(zip_res.path)
    assert any(e["db_path"] == restaurada.db_path for e in program_db.list_registry())
