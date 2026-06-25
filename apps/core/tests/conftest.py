from pathlib import Path

import pytest

SAMPLES_DIR = Path(__file__).resolve().parents[3] / "docs" / "samples"


@pytest.fixture(scope="session")
def sample_excel() -> Path:
    path = SAMPLES_DIR / "Ejemplo_LaDian.xlsx"
    assert path.exists(), f"Sample Excel missing at {path}"
    return path
