"""E2 — backup/restore roundtrip + archive + update razon_social + hard delete."""
import zipfile
from pathlib import Path

import pytest

from contab_core import backup, excel, storage


@pytest.fixture
def empresa_setup(tmp_path: Path, sample_excel: Path) -> dict:
    """A fully-populated empresa: db + 1 imported Excel + a PDFs folder with 1 file."""
    empresas_dir = tmp_path / "empresas"
    empresas_dir.mkdir()
    db_path = empresas_dir / "900181831_real-seguros.db"
    storage.init_empresa_db(db_path, nit="900181831", dv="4", razon_social="REAL Seguros")

    # Import the sample Excel in-place (we just register the source_path).
    excels_dir = tmp_path / "files" / "excels"
    excels_dir.mkdir(parents=True)
    excel_copy = excels_dir / "Ejemplo_LaDian.xlsx"
    excel_copy.write_bytes(Path(sample_excel).read_bytes())

    loaded = excel.load_excel(excel_copy)
    conn = storage.connect(db_path)
    try:
        excel.persist_load(conn, str(excel_copy), loaded)
    finally:
        conn.close()

    # Tiny PDF placeholder (just bytes — backup zips whatever is .pdf).
    pdfs_dir = tmp_path / "files" / "pdfs"
    pdfs_dir.mkdir(parents=True)
    (pdfs_dir / "fake.pdf").write_bytes(b"%PDF-1.4\nstub for tests")

    storage.set_default_folder(db_path, str(excels_dir))
    storage.set_pdfs_folder(db_path, str(pdfs_dir))

    return {
        "tmp": tmp_path,
        "empresas_dir": empresas_dir,
        "db_path": db_path,
        "excel": excel_copy,
        "pdf": pdfs_dir / "fake.pdf",
    }


def test_update_razon_social_persists(empresa_setup):
    storage.update_razon_social(empresa_setup["db_path"], "REAL Seguros S.A.S.")
    info = storage.read_empresa_info(empresa_setup["db_path"])
    assert info["razon_social"] == "REAL Seguros S.A.S."
    assert info["nit"] == "900181831"  # NIT must not change (D-041).


def test_update_razon_social_rejects_empty(empresa_setup):
    with pytest.raises(ValueError):
        storage.update_razon_social(empresa_setup["db_path"], "   ")


def test_archive_and_unarchive(empresa_setup):
    storage.set_archived(empresa_setup["db_path"], True)
    assert storage.read_empresa_info(empresa_setup["db_path"])["archived"] is True
    storage.set_archived(empresa_setup["db_path"], False)
    assert storage.read_empresa_info(empresa_setup["db_path"])["archived"] is False


def test_backup_creates_zip_with_all_artifacts(empresa_setup, tmp_path: Path):
    dest = tmp_path / "backups"
    result = backup.backup_empresa(empresa_setup["db_path"], dest)
    out = Path(result.path)
    assert out.exists()
    assert result.excels_included == 1
    assert result.pdfs_included == 1

    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        assert backup.ZIP_DB_NAME in names
        assert backup.ZIP_META_NAME in names
        excels = [n for n in names if n.startswith(backup.ZIP_EXCELS_PREFIX)]
        pdfs = [n for n in names if n.startswith(backup.ZIP_PDFS_PREFIX)]
        assert len(excels) == 1
        assert len(pdfs) == 1
        meta = z.read(backup.ZIP_META_NAME).decode("utf-8")
        assert "REAL Seguros" in meta
        assert "900181831" in meta


def test_restore_roundtrip(empresa_setup, tmp_path: Path):
    dest = tmp_path / "backups"
    backup_path = backup.backup_empresa(empresa_setup["db_path"], dest).path

    # Restore into a fresh empresas dir.
    restore_target = tmp_path / "fresh_empresas"
    result = backup.restore_empresa(backup_path, restore_target)
    assert Path(result.db_path).exists()
    assert result.excels_restored == 1
    assert result.pdfs_restored == 1
    # Folders are repointed to the restored locations.
    info = storage.read_empresa_info(result.db_path)
    assert info["default_folder"] == result.excels_folder
    assert info["pdfs_folder"] == result.pdfs_folder
    assert Path(result.excels_folder).is_dir()
    assert Path(result.pdfs_folder).is_dir()


def test_restore_into_dir_with_conflict_renames(empresa_setup, tmp_path: Path):
    dest = tmp_path / "backups"
    backup_path = backup.backup_empresa(empresa_setup["db_path"], dest).path

    # Restore once into a target dir, then restore again — second should rename.
    target = tmp_path / "shared_empresas"
    first = backup.restore_empresa(backup_path, target)
    assert first.conflict_action is None
    second = backup.restore_empresa(backup_path, target)
    assert second.conflict_action is not None
    assert Path(first.db_path).name != Path(second.db_path).name
    assert Path(first.db_path).exists() and Path(second.db_path).exists()


def test_delete_empresa_requires_matching_nit(empresa_setup):
    with pytest.raises(ValueError):
        backup.delete_empresa_file(empresa_setup["db_path"], "999999999")
    # The file must still exist after the failed attempt.
    assert empresa_setup["db_path"].exists()
    # Correct NIT → deletes.
    result = backup.delete_empresa_file(empresa_setup["db_path"], "900181831")
    assert empresa_setup["db_path"].name in result["deleted"]
    assert not empresa_setup["db_path"].exists()
