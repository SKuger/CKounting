"""Smoke tests for the list_folder_files sidecar handler (via direct call)."""
from pathlib import Path

import pytest

from contab_core import storage
from contab_core.sidecar import HANDLERS


@pytest.fixture
def empresa_with_folder(tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "test.db"
    folder = tmp_path / "files"
    folder.mkdir()
    storage.init_empresa_db(db_path, nit="900181831", dv="4", razon_social="REAL Seguros")
    storage.set_default_folder(db_path, str(folder))
    return db_path, folder


def test_lists_xlsx_only(empresa_with_folder):
    db_path, folder = empresa_with_folder
    (folder / "good.xlsx").write_bytes(b"x")
    (folder / "good.xls").write_bytes(b"x")
    (folder / "ignored.txt").write_bytes(b"x")
    (folder / "~lock.xlsx").write_bytes(b"x")
    (folder / "subdir").mkdir()

    result = HANDLERS["list_folder_files"]({"db_path": str(db_path)})
    names = {f["name"] for f in result["files"]}
    assert names == {"good.xlsx", "good.xls"}


def test_marks_imported_files(empresa_with_folder, sample_excel):
    db_path, folder = empresa_with_folder
    target = folder / "Ejemplo_LaDian.xlsx"
    target.write_bytes(Path(sample_excel).read_bytes())

    # Import via direct call to the sidecar import_excel handler.
    HANDLERS["import_excel"]({
        "db_path": str(db_path),
        "source_path": str(target),
    })

    result = HANDLERS["list_folder_files"]({"db_path": str(db_path)})
    assert len(result["files"]) == 1
    entry = result["files"][0]
    assert entry["imported"] is True
    assert entry["imported_as_load_id"] is not None


def test_returns_empty_when_no_folder(tmp_path: Path):
    db_path = tmp_path / "test2.db"
    storage.init_empresa_db(db_path, nit="900181831", dv="4", razon_social="REAL")
    result = HANDLERS["list_folder_files"]({"db_path": str(db_path)})
    assert result["folder"] is None
    assert result["files"] == []


def test_reports_error_for_missing_folder(tmp_path: Path):
    db_path = tmp_path / "test3.db"
    storage.init_empresa_db(db_path, nit="900181831", dv="4", razon_social="REAL")
    storage.set_default_folder(db_path, str(tmp_path / "no_such_folder"))
    result = HANDLERS["list_folder_files"]({"db_path": str(db_path)})
    assert result["files"] == []
    assert result["error"] and "no existe" in result["error"]
