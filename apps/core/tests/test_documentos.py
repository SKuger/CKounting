"""El documento del XML en la base — tarea 3.2, con su caché.

Dos cosas que importan más que guardar bien: que **un mes sin XML se comporte
igual que antes** (el XML es una capa pegada al Excel, D-039/D-064), y que subir
la versión del parser **vuelva a leer** lo que ya estaba — sin eso, mejorar el
parser no llega jamás a los documentos viejos.
"""
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from contab_core import documentos, storage, xml_ubl

MUESTRAS = Path(__file__).resolve().parents[3] / "docs" / "samples" / "xml"
CUFE_FACTURA = "1" * 92 + "aaaa"


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "empresa.db"
    storage.init_empresa_db(db, nit="900181831", dv="7", razon_social="PRUEBA")
    c = storage.connect(db)
    storage.ensure_schema(c)
    yield c
    c.close()


@pytest.fixture
def carpeta(tmp_path: Path) -> Path:
    destino = tmp_path / "soportes"
    destino.mkdir()
    for x in MUESTRAS.glob("*.xml"):
        shutil.copy(x, destino / x.name)
    return destino


def test_guarda_el_documento_con_sus_hijos(conn, carpeta: Path):
    res = documentos.indexar_carpeta(conn, carpeta)
    assert res.leidos == 4 and res.fallidos == 0

    doc = documentos.documento_por_cufe(conn, CUFE_FACTURA)
    assert doc is not None
    assert doc["tipo"] == "factura"
    assert len(doc["lineas"]) == 2
    assert len(doc["impuestos"]) == 2, "IVA y retefuente a nivel de documento"


def test_los_importes_vuelven_como_decimal_sin_perder_centimos(conn, carpeta: Path):
    """Se guardan como TEXT a propósito: SQLite solo tiene REAL, y REAL es float."""
    documentos.indexar_carpeta(conn, carpeta)
    doc = documentos.documento_por_cufe(conn, CUFE_FACTURA)
    assert Decimal(doc["total"]) == Decimal("1785000.00")
    assert Decimal(doc["subtotal"]) + Decimal(doc["total_impuestos"]) == Decimal(doc["total"])


def test_la_retencion_queda_marcada_como_tal(conn, carpeta: Path):
    documentos.indexar_carpeta(conn, carpeta)
    doc = documentos.documento_por_cufe(conn, CUFE_FACTURA)
    retenciones = [i for i in doc["impuestos"] if i["es_retencion"]]
    assert len(retenciones) == 1 and retenciones[0]["tipo"] == "06"


def test_la_segunda_pasada_no_vuelve_a_leer_nada(conn, carpeta: Path):
    documentos.indexar_carpeta(conn, carpeta)
    otra = documentos.indexar_carpeta(conn, carpeta)
    assert otra.leidos == 0 and otra.desde_cache == 4


def test_subir_la_version_del_parser_obliga_a_releer(conn, carpeta: Path, monkeypatch):
    """Si no, una mejora del parser no alcanza nunca a lo ya leído (D-067)."""
    documentos.indexar_carpeta(conn, carpeta)
    monkeypatch.setattr(xml_ubl, "PARSER_VERSION", xml_ubl.PARSER_VERSION + 1)
    otra = documentos.indexar_carpeta(conn, carpeta)
    assert otra.leidos == 4 and otra.desde_cache == 0


def test_releer_no_duplica_lineas(conn, carpeta: Path, monkeypatch):
    """Releer con UPDATE dejaría las líneas sobrantes de la lectura anterior."""
    documentos.indexar_carpeta(conn, carpeta)
    monkeypatch.setattr(xml_ubl, "PARSER_VERSION", xml_ubl.PARSER_VERSION + 1)
    documentos.indexar_carpeta(conn, carpeta)
    doc = documentos.documento_por_cufe(conn, CUFE_FACTURA)
    assert len(doc["lineas"]) == 2
    assert conn.execute("SELECT COUNT(*) FROM documento WHERE cufe = ?",
                        (CUFE_FACTURA,)).fetchone()[0] == 1


def test_un_xml_roto_no_tumba_la_carpeta(conn, carpeta: Path):
    (carpeta / "roto.xml").write_text("no soy xml", encoding="utf-8")
    res = documentos.indexar_carpeta(conn, carpeta)
    assert res.leidos == 4 and res.fallidos == 1
    assert res.errores[0]["archivo"] == "roto.xml"
    assert res.errores[0]["estado"] == xml_ubl.ESTADO_NO_ES_XML


def test_una_carpeta_que_no_existe_es_un_error_no_una_carpeta_vacia(conn, tmp_path: Path):
    """Un fallo técnico disfrazado de «no hay documentos» es lo que D-080 prohíbe."""
    with pytest.raises(FileNotFoundError):
        documentos.indexar_carpeta(conn, tmp_path / "no-existe")


def test_los_documentos_del_mes_salen_por_el_cufe_del_excel(conn, carpeta: Path):
    documentos.indexar_carpeta(conn, carpeta)
    conn.execute(
        "INSERT INTO excel_load(id, source_path, source_name, total_rows, periodo)"
        " VALUES (1, 'x.xlsx', 'x.xlsx', 1, '2026-09')")
    conn.execute(
        "INSERT INTO excel_row(load_id, row_index, cufe_cude, data_json, periodo)"
        " VALUES (1, 0, ?, '{}', '2026-09')", (CUFE_FACTURA,))
    conn.commit()

    delmes = documentos.documentos_del_periodo(conn, "2026-09")
    assert [d["cufe"] for d in delmes] == [CUFE_FACTURA], \
        "solo los que el Excel de ese mes trae, no todos los XML de la carpeta"


def test_sin_xml_la_base_queda_exactamente_igual(conn, tmp_path: Path):
    """La guarda de regresión: un mes sin XML se comporta como antes."""
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    res = documentos.indexar_carpeta(conn, vacia)
    assert res.leidos == 0 and res.fallidos == 0
    assert documentos.cufes_con_documento(conn) == set()


def test_una_nota_credito_recibida_sale_con_signo_negativo(conn):
    """Sin esto se causaría como una compra más, al revés (D-045)."""
    conn.execute(
        "INSERT INTO excel_load(id, source_path, source_name, total_rows, periodo)"
        " VALUES (7, 'x.xlsx', 'x.xlsx', 1, '2026-10')")
    conn.execute(
        "INSERT INTO excel_row(load_id, row_index, cufe_cude, tipo_doc, data_json, periodo)"
        " VALUES (7, 0, ?, 'Nota de crédito electrónica', ?, '2026-10')",
        ("c" * 96, '{"Grupo":"Recibido","NIT Emisor":"800100200","Total":"119000","IVA":"19000"}'))
    conn.commit()
    doc = next(d for d in documentos.documentos_a_causar(conn, "2026-10") if d["cufe"] == "c" * 96)
    assert doc["tipo"] == "nota_credito"
    assert Decimal(doc["total"]) == Decimal("-119000")
    assert Decimal(doc["subtotal"]) == Decimal("-100000")
    assert doc["origen"] == documentos.ORIGEN_EXCEL
