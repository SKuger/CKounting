from pathlib import Path

import pytest

from contab_core import paths

SAMPLES_DIR = Path(__file__).resolve().parents[3] / "docs" / "samples"


@pytest.fixture(autouse=True)
def isolate_data_dir(monkeypatch, tmp_path):
    """Aísla TODA escritura de la suite a un tmp_path.

    Sin esto, en Windows los tests escriben en los datos REALES del usuario:
    `paths.data_dir()` solo consulta XDG_DATA_HOME en Linux, así que el
    `monkeypatch.setenv("XDG_DATA_HOME", ...)` que hacen algunos tests no aísla
    nada en win32 y se acaba operando sobre %APPDATA%\\Contab — incluyendo los
    tests que archivan y BORRAN empresas.

    Parchear `paths.data_dir` es independiente del SO; las variables de entorno
    se fijan además para cualquier código que las lea por su cuenta.
    """
    base = tmp_path / "datadir"
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(base))
    monkeypatch.setenv("APPDATA", str(base))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(paths, "data_dir", lambda: base / paths.APP_NAME)
    return base


@pytest.fixture(scope="session")
def sample_excel() -> Path:
    path = SAMPLES_DIR / "Ejemplo_LaDian.xlsx"
    assert path.exists(), f"Sample Excel missing at {path}"
    return path
