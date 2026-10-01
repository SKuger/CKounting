"""Los eventos RADIAN no son documentos: no hay soporte que ir a buscarles.

En el septiembre real del usuario, 9 de 41 filas eran «Application response».
Mandarlas al bajador era gastar una cuarta parte de la corrida persiguiendo PDFs
que no existen, y devolverlas como «la DIAN no lo tiene» — que parece un problema
y no lo es.
"""
from pathlib import Path

import pytest

from contab_core import storage
from contab_core.sidecar import HANDLERS


@pytest.fixture
def empresa(tmp_path: Path) -> Path:
    db_path = tmp_path / "empresa.db"
    storage.init_empresa_db(db_path, nit="900921756", dv="1", razon_social="ALAGUNA")
    conn = storage.connect(db_path)
    try:
        storage.ensure_schema(conn)
        conn.execute(
            "INSERT INTO excel_load(id, source_path, source_name, total_rows, periodo) "
            "VALUES (1, 'x.xlsx', 'x.xlsx', 4, '2026-09')"
        )
        filas = [
            ("a" * 96, "Factura electrónica"),
            ("b" * 96, "Nota de crédito electrónica"),
            ("c" * 96, "Application response"),
            ("d" * 96, "Application response"),
        ]
        for i, (cufe, tipo) in enumerate(filas):
            conn.execute(
                "INSERT INTO excel_row(load_id, row_index, cufe_cude, grupo, tipo_doc,"
                " data_json, periodo) VALUES (1, ?, ?, NULL, ?, '{}', '2026-09')",
                (i, cufe, tipo),
            )
        conn.commit()
    finally:
        conn.close()
    carpeta = tmp_path / "soportes"
    carpeta.mkdir()
    storage.set_periodo_folder(db_path, "2026-09", str(carpeta))
    return db_path


def test_no_persigue_eventos_radian(empresa: Path):
    res = HANDLERS["documentos_sin_soporte"]({"db_path": str(empresa), "periodo": "2026-09"})
    cufes = {d["cufe"] for d in res["faltan"]}
    assert cufes == {"a" * 96, "b" * 96}
    assert res["total"] == 2, "el total también cuenta solo documentos de verdad"


def test_consulta_con_el_nit_de_la_empresa(empresa: Path):
    """El portal acepta el NIT del emisor o el del receptor, y la empresa siempre
    es uno de los dos: por eso se consulta con el suyo y no con el de la fila."""
    res = HANDLERS["documentos_sin_soporte"]({"db_path": str(empresa), "periodo": "2026-09"})
    assert {d["nit"] for d in res["faltan"]} == {"900921756"}
