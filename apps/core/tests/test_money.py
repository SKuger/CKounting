"""Importes en Decimal de punta a punta (D-075)."""
import json
from decimal import Decimal

import pytest

from contab_core import excel, money, storage
from contab_core.sidecar import _json_default


def test_redondeo_contable_no_binario():
    """round() de float redondea 2.675 a 2.67 porque 2.675 no existe en binario.
    La convención contable (y la de la DIAN) es medio hacia ARRIBA."""
    assert round(2.675, 2) == 2.67          # el comportamiento que dejamos atrás
    assert money.to_money("2.675") == Decimal("2.68")
    assert money.to_money("0.005") == Decimal("0.01")
    assert money.to_money("-2.675") == Decimal("-2.68")


def test_float_entra_por_repr_no_por_binario():
    """Decimal(0.1) es 0.1000000000000000055511151231257827…; Decimal(repr(0.1)) es 0.1.
    Importa al leer data_json de cargas viejas, donde los importes son floats."""
    assert money.to_money(0.1) == Decimal("0.10")
    assert money.to_money(48150.0) == Decimal("48150.00")


def test_base_iva_queda_cuantizada():
    """IVA/0.19 es periódico. Antes se guardaba y exportaba crudo
    (40463.15789473684) en una columna que ve el contador."""
    valor_base, base_iva, diferencia = excel.compute_iva_columns(
        Decimal("7688"), Decimal("48150")
    )
    assert valor_base == Decimal("40462.00")
    assert base_iva == Decimal("40463.16")
    assert diferencia == Decimal("-1.16")
    for v in (valor_base, base_iva, diferencia):
        assert -v.as_tuple().exponent == 2, "todo importe sale con 2 decimales exactos"


def test_importes_del_excel_son_decimal(sample_excel):
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        for col in excel.MONEY_COLUMNS:
            assert isinstance(row[col], Decimal), f"{col} debe ser Decimal"


def test_roundtrip_persistir_releer_es_exacto(tmp_path, sample_excel):
    """Persistir y releer no puede alterar un importe ni en un centavo."""
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL")
    conn = storage.connect(db)
    try:
        loaded = excel.load_excel(sample_excel)
        load_id = excel.persist_load(conn, "x.xlsx", loaded, periodo="2024-02")

        # En data_json el importe va como STRING exacto, no como número JSON:
        # un float en el archivo reintroduce la representación binaria.
        raw = conn.execute(
            "SELECT data_json FROM excel_row WHERE load_id = ? ORDER BY row_index",
            (load_id,),
        ).fetchone()
        assert isinstance(json.loads(raw["data_json"])["Total"], str)

        back = excel.fetch_load_rows(conn, load_id)
        for original, leido in zip(loaded.rows, back, strict=False):
            for col in excel.MONEY_COLUMNS:
                assert leido[col] == original[col], f"{col} cambió al ir y volver"
    finally:
        conn.close()


def test_carga_vieja_con_floats_sigue_leyendose(tmp_path):
    """Compatibilidad: las BD existentes tienen los importes como número JSON."""
    db = tmp_path / "vieja.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL")
    conn = storage.connect(db)
    try:
        fila = dict.fromkeys(excel.DIAN_COLUMNS)
        fila.update({
            "Tipo de documento": "Factura electrónica",
            "CUFE/CUDE": "a" * 96, "Prefijo": "FELE", "Folio": "827",
            "Fecha Emisión": "2024-02-26",
            "IVA": 7688.0, "Total": 48150.0,
            "Valor Base": 40462.0,
            "Base IVA": 40463.15789473684,        # el ruido que producía el código viejo
            "Diferencia": -1.1578947368398076,
        })
        with storage.transaction(conn):
            cur = conn.execute(
                "INSERT INTO excel_load(source_path, source_name, total_rows, sheet_name, periodo)"
                " VALUES ('v', 'v.xlsx', 1, 'h', '2024-02')"
            )
            load_id = cur.lastrowid
            conn.execute(
                "INSERT INTO excel_row(load_id, row_index, cufe_cude, grupo, tipo_doc, data_json, periodo)"
                " VALUES (?, 0, ?, NULL, ?, ?, '2024-02')",
                (load_id, "a" * 96, "Factura electrónica", json.dumps(fila)),
            )

        row = excel.fetch_load_rows(conn, load_id)[0]
        assert row["Total"] == Decimal("48150.00")
        assert row["IVA"] == Decimal("7688.00")
        assert row["Base IVA"] == Decimal("40463.16"), "se recalcula limpia, sin el ruido"
    finally:
        conn.close()


def test_la_ui_recibe_numeros_no_cadenas():
    """El `default=str` anterior habría mandado "48150.00" a la tabla y le habría
    roto el orden y el formato. Decimal debe salir como número JSON."""
    payload = {"rows": [{"Total": Decimal("48150.00"), "Nombre": "ACME"}]}
    back = json.loads(json.dumps(payload, default=_json_default))
    assert isinstance(back["rows"][0]["Total"], float)
    assert back["rows"][0]["Total"] == 48150.0


def test_v2_inversion_conserva_el_centavo():
    from contab_core import validations

    row = {"Tipo de documento": "Nota de crédito electrónica",
           "IVA": Decimal("2447.16"), "Total": Decimal("15399.99")}
    inv = validations.apply_v2_inversion(row)
    assert inv["IVA"] == Decimal("-2447.16")
    assert inv["Total"] == Decimal("-15399.99")
    assert inv["Valor Base"] == Decimal("-12952.83")


def test_importe_no_numerico_sigue_siendo_error():
    with pytest.raises(ValueError):
        money.to_money("no aplica")
    with pytest.raises(ValueError):
        money.to_money(True)
