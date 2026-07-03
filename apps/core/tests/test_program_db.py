"""BD del programa (contab.db) — usuario, ajustes, registro central (0.1.4)."""
from contab_core import paths, program_db, storage


def test_user_persists_and_partial_update(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert program_db.get_user() is None
    u = program_db.save_user(name="Samuel", email="a@b.com")
    assert u["name"] == "Samuel" and u["email"] == "a@b.com"
    # actualización parcial: solo email; el nombre se conserva
    u2 = program_db.save_user(email="c@d.com")
    assert u2["name"] == "Samuel" and u2["email"] == "c@d.com"
    # persiste al reabrir (nueva conexión)
    assert program_db.get_user()["name"] == "Samuel"


def test_settings_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    program_db.save_settings({"tema": "oscuro", "densidad": "compacta"})
    program_db.save_settings({"tema": "claro"})  # merge parcial
    s = program_db.get_settings()
    assert s["tema"] == "claro" and s["densidad"] == "compacta"


def test_register_idempotent_and_sync(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    dbp = paths.empresa_db_path("900181831", "Real Seguros Ltda")
    storage.init_empresa_db(dbp, "900181831", "4", "Real Seguros Ltda")

    # sync registra las empresas ya existentes en disco (migración)
    assert program_db.sync_registry()["registered"] >= 1
    reg = program_db.list_registry()
    assert any(e["razon_social"] == "Real Seguros Ltda" for e in reg)

    # upsert idempotente por db_path → mismo empresa_id
    eid1 = program_db.register_empresa(str(dbp))
    eid2 = program_db.register_empresa(str(dbp), razon_social="Real Seguros Ltda")
    assert eid1 == eid2

    # archivar filtra del listado por defecto
    program_db.set_registry_archived(str(dbp), True)
    assert not any(e["db_path"] == str(dbp) for e in program_db.list_registry())
    assert any(e["db_path"] == str(dbp) for e in program_db.list_registry(include_archived=True))
