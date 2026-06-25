"""Real-file tests for the PDF CUFE extractor + index. Uses docs/samples/*.pdf
(falsified data per the user)."""
from pathlib import Path

import pytest

from contab_core import storage
from contab_core.pdf_cufe import (
    EXTRACTION_STATUS_OK,
    extract_cufes,
    get_indexed_cufes,
    index_folder,
    list_indexed_pdfs,
)

SAMPLES = Path(__file__).resolve().parents[3] / "docs" / "samples" / "pdfs"

# Each entry is (expected_value, expected_label). One PDF = one CUFE/CUDE/CUDS,
# the PDF's OWN identifier (we ignore parent-references like the CUFE inside an NC).
EXPECTED_CUFES = {
    "09-02 ALMACENES EXITO NC TCNC1952292.pdf": (
        "71fdf3781e9e57c77d792f4f8dcea9c5853b8e8d85fe8cb9f00eca9765cd72884db68542af6472f6e72ba6e7dd066ba5",
        "CUDE",  # NC's own CUDE — NOT the parent factura's CUFE.
    ),
    "26-02 ANNY CASTANEDA FRA SP144.pdf": (
        "b49f9ecc41fac5566c46b49ae2810dfae43862f2ff3c1f49201c715172b6e33ba857d1f54537e756a8a7ec17ba185cbc",
        "CUFE",
    ),
    "26-02 D1 FRA 94DD49995.pdf": (
        "8dc7aa629731b81d691c61bf2e1edfb5177607a8e4d84d179c635091ae4484ac58edbbeb9d02540bea3b16f9bed3cb27",
        "CUDE",
    ),
    "dseDSE210.pdf": (
        "be6c31620a5bf5a8b66ee47379d13edcb5dffb12308e368f9985db48b05be1ae7472778f78775c418b17dda35a465111",
        "CUDS",
    ),
    "dseDSE211.pdf": (
        "a763959ca331e3e0d275ea2feb573d4d56b00f2257415c30476faeca116bee14bbb2bbb8c15fbbf9c38ad63d16d804e3",
        "CUDS",
    ),
    "24-02 MOVISTAR BEC-509558651.pdf": (
        "75bd83fa68390920a0f9bb663577d4e12265339c7a04f4eaeb3e7d95029bb06daaae438f78dfd20f633912f657d6a935",
        "CUFE",  # QR fallback (obfuscated font) — still labeled in the QR payload.
    ),
}


@pytest.mark.parametrize("pdf_name,expected", EXPECTED_CUFES.items())
def test_extracts_expected_cufe(pdf_name: str, expected: tuple[str, str]):
    pdf_path = SAMPLES / pdf_name
    if not pdf_path.exists():
        pytest.skip(f"missing sample: {pdf_path}")
    expected_value, expected_label = expected
    result = extract_cufes(pdf_path)
    assert result.status == EXTRACTION_STATUS_OK, f"{pdf_name}: status={result.status}"
    # Each PDF must yield exactly ONE CUFE/CUDE/CUDS (the document's own).
    assert len(result.cufes) == 1, (
        f"{pdf_name}: expected exactly 1 CUFE, got {len(result.cufes)}: "
        f"{[(c.value[:14], c.label) for c in result.cufes]}"
    )
    cufe = result.cufes[0]
    assert cufe.value == expected_value, (
        f"{pdf_name}: expected {expected_value[:14]}…, got {cufe.value[:14]}…"
    )
    assert cufe.label == expected_label, (
        f"{pdf_name}: expected label {expected_label}, got {cufe.label}"
    )


def test_index_folder_caches(tmp_path: Path):
    """Re-running index_folder should hit the cache for unchanged PDFs."""
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    # Copy a couple of sample PDFs in.
    for name in ("26-02 ANNY CASTANEDA FRA SP144.pdf", "dseDSE210.pdf"):
        src = SAMPLES / name
        if not src.exists():
            pytest.skip(f"missing sample: {src}")
        (pdfs_dir / name).write_bytes(src.read_bytes())

    db_path = tmp_path / "empresa.db"
    storage.init_empresa_db(db_path, nit="900181831", dv="4", razon_social="REAL")
    conn = storage.connect(db_path)
    try:
        with storage.transaction(conn):
            first = index_folder(conn, pdfs_dir)
        assert first.total_pdfs == 2
        assert first.indexed_now == 2
        assert first.cached == 0

        # Second pass should be 100% cached.
        with storage.transaction(conn):
            second = index_folder(conn, pdfs_dir)
        assert second.cached == 2
        assert second.indexed_now == 0

        cufes = get_indexed_cufes(conn, pdfs_dir)
        assert len(cufes) >= 2

        listing = list_indexed_pdfs(conn, pdfs_dir)
        assert len(listing) == 2
        for entry in listing:
            assert entry["extraction_status"] == EXTRACTION_STATUS_OK
            assert entry["cufe_count"] >= 1
    finally:
        conn.close()


def test_index_handles_non_pdf_files_silently(tmp_path: Path):
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    (pdfs_dir / "notes.txt").write_text("ignore me")
    (pdfs_dir / "subdir").mkdir()  # ignored (non-recursive)

    db_path = tmp_path / "empresa.db"
    storage.init_empresa_db(db_path, nit="900181831", dv="4", razon_social="REAL")
    conn = storage.connect(db_path)
    try:
        with storage.transaction(conn):
            stats = index_folder(conn, pdfs_dir)
        assert stats.total_pdfs == 0
        assert get_indexed_cufes(conn, pdfs_dir) == set()
    finally:
        conn.close()
