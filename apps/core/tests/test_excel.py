import os
from decimal import Decimal
from pathlib import Path

import pytest

from contab_core import excel, money


def test_loads_sample(sample_excel):
    loaded = excel.load_excel(sample_excel)
    assert len(loaded.rows) == 11, "muestra tiene 11 filas de datos"
    # All 32 DIAN columns must be present.
    for col in excel.DIAN_COLUMNS:
        assert col in loaded.columns
    # Derived columns are added per row (D-024 + D-045).
    for row in loaded.rows:
        assert "# de factura" in row
        assert "Valor Base" in row
        assert "Base IVA" in row
        assert "Diferencia" in row


def test_diferencia_near_zero_when_iva_at_19pct(sample_excel):
    """FELE-827 matches 19% within the 5-peso tolerance → Diferencia ~ 0 (D-046)."""
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        if row["# de factura"] == "FELE-827":
            assert abs(row["Valor Base"] - Decimal("40462")) < 1
            assert abs(row["Base IVA"] - money.quantize(Decimal("7688") / Decimal("0.19"))) < 1
            assert abs(row["Diferencia"]) < 5
            return
    raise AssertionError("FELE-827 missing from sample")


def test_base_iva_always_iva_over_19pct(sample_excel):
    """D-046 — Base IVA is ALWAYS IVA/0.19 (when IVA != 0). The conditional
    'pegar a Valor Base' from D-045 was reverted."""
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        if row["IVA"] != money.ZERO:
            esperado = money.quantize(row["IVA"] / Decimal("0.19"))
            assert row["Base IVA"] == esperado, "Base IVA es IVA/0.19 cuantizado a centavos"


def test_diferencia_is_valor_base_minus_base_iva(sample_excel):
    """D-046 — for rows where IVA != 0, Diferencia is the literal subtraction.
    For IVA = 0 rows we keep the explicit zero to avoid surfacing the full Total
    as a misleading 'gap' on exempt/excluded documents."""
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        if row["IVA"] == 0:
            assert row["Diferencia"] == 0.0
        else:
            expected = row["Valor Base"] - row["Base IVA"]
            assert abs(row["Diferencia"] - expected) < 0.01


def test_diferencia_matches_inc_bolsas_for_d1(sample_excel):
    """D1 94DD-49995: Total includes INC Bolsas = 73 that's NOT in IVA. The
    Diferencia should land around 73 pesos — exact value, since Base IVA is
    now strictly IVA/0.19."""
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        if row["# de factura"] == "94DD-49995":
            assert 60 < row["Diferencia"] < 90
            return
    raise AssertionError("94DD-49995 missing from sample")


def test_diferencia_zero_when_iva_zero(sample_excel):
    """IVA=0 rows (DSE, Nómina) get Base IVA=0 and Diferencia=0 (D-045)."""
    loaded = excel.load_excel(sample_excel)
    iva_zero_rows = [r for r in loaded.rows if r["IVA"] == 0]
    assert iva_zero_rows, "sample should contain at least one IVA=0 row"
    for row in iva_zero_rows:
        assert row["Base IVA"] == 0.0
        assert row["Diferencia"] == 0.0


def test_factura_number_format(sample_excel):
    loaded = excel.load_excel(sample_excel)
    numbers = {row["# de factura"] for row in loaded.rows}
    # D-030: Prefijo-Folio with hyphen no spaces.
    assert "DSE-211" in numbers
    assert "DSE-210" in numbers


def test_cufe_lowercased_96_chars(sample_excel):
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        cufe = row["CUFE/CUDE"]
        assert isinstance(cufe, str) and len(cufe) == 96
        assert cufe == cufe.lower()


def test_dates_iso(sample_excel):
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        # Emisión: yyyy-mm-dd
        emi = row["Fecha Emisión"]
        assert emi is not None and emi[4] == "-" and len(emi) >= 10
        # Recepción: yyyy-mm-ddThh:mm:ss
        rec = row["Fecha Recepción"]
        assert rec is not None and "T" in rec


def test_valor_base_uses_originals(sample_excel):
    """At load time, Valor Base = Total - IVA (originals, before V2). D-029."""
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        assert abs(row["Valor Base"] - (row["Total"] - row["IVA"])) < 0.01


def test_whitespace_trimmed_in_razon_social(sample_excel):
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        name_e = row["Nombre Emisor"]
        name_r = row["Nombre Receptor"]
        assert name_e == name_e.strip()
        assert name_r == name_r.strip()
        # No double spaces.
        assert "  " not in name_e and "  " not in name_r


def test_celda_numerica_vacia_es_cero():
    """Ausencia legítima → 0 (el comportamiento de siempre)."""
    row = excel._normalize_row({"IVA": None, "Total": 1000}, fila=2)
    assert row["IVA"] == money.ZERO and row["Total"] == Decimal("1000.00")


def test_importe_ilegible_falla_en_vez_de_volverse_cero():
    """Un importe que no se puede leer NO puede guardarse como 0.

    Antes, `_to_number` devolvía None ante cualquier cosa rara y el parser lo
    colapsaba al mismo 0 que una celda vacía: la fila aprobaba V3 (IVA=0 se omite)
    y el total quedaba mal sin ninguna señal."""
    with pytest.raises(excel.ExcelParseError) as exc:
        excel._normalize_row({"IVA": "no aplica", "Total": 1000}, fila=7)
    assert "Fila 7" in str(exc.value) and "IVA" in str(exc.value)


def test_importe_en_texto_formato_colombiano():
    """'1.234,56' es 1234.56, no un error ni un 0."""
    row = excel._normalize_row({"IVA": "1.234,56", "Total": "$ 1.234.567"}, fila=2)
    assert row["IVA"] == Decimal("1234.56")
    assert row["Total"] == Decimal("1234567.00")


def test_importe_ambiguo_no_se_adivina():
    """'10.000' puede ser diez mil o diez: equivocarse son 3 ordenes de magnitud.

    Se prefiere parar y pedir que arreglen el Excel antes que guardar un importe
    que puede estar mil veces mal."""
    with pytest.raises(excel.ExcelParseError, match="ambiguo"):
        excel._normalize_row({"Total": "10.000"}, fila=4)


# ── #14 — el periodo se valida antes de usarse ──────────────────────────────

def test_periodo_solo_se_deriva_de_una_fecha_iso_valida():
    """`_parse_date` deja pasar el texto original cuando no reconoce el formato,
    así que cortar a ciegas fe[:7] producía periodos basura como 'Marzo 2' — y ese
    periodo decide contra qué carpeta de soportes se valida el lote."""
    assert excel.periodo_from_row({"Fecha Emisión": "2024-02-26"}) == "2024-02"
    for basura in ("Marzo 2026", "26/02/2024", "2024-13-01", "2024-00-05", "", None, 20240226):
        assert excel.periodo_from_row({"Fecha Emisión": basura}) is None, f"{basura!r}"


# ── #15 — el mes dominante es determinista ──────────────────────────────────

def test_mes_dominante_por_mayoria():
    assert excel._periodo_dominante(["2024-03", "2024-02", "2024-02"]) == "2024-02"
    assert excel._periodo_dominante([]) is None


def test_mes_dominante_en_empate_gana_el_mas_antiguo():
    empate = ["2024-03", "2024-02", "2024-03", "2024-02"]
    assert excel._periodo_dominante(empate) == "2024-02"
    assert excel._periodo_dominante(list(reversed(empate))) == "2024-02"


def test_mes_dominante_no_depende_del_hash_del_proceso():
    """El bug original: `max(set(p), key=p.count)` dependía del orden de iteración
    de un set de strings, que cambia ENTRE PROCESOS por el hash aleatorio de
    Python. Dentro de un mismo proceso la semilla es fija, así que repetir la
    llamada en bucle no probaría nada: hay que lanzar procesos con semillas
    distintas."""
    import subprocess
    import sys

    codigo = (
        "from contab_core.excel import _periodo_dominante;"
        "print(_periodo_dominante(['2024-03','2024-02','2024-03','2024-02']))"
    )
    resultados = set()
    for semilla in ("0", "1", "42", "12345", "99999"):
        env = {**os.environ, "PYTHONHASHSEED": semilla}
        r = subprocess.run([sys.executable, "-c", codigo], capture_output=True,
                           text=True, env=env, cwd=str(Path(__file__).resolve().parents[1]))
        assert r.returncode == 0, r.stderr
        resultados.add(r.stdout.strip())
    assert resultados == {"2024-02"}, f"el mes elegido varió entre procesos: {resultados}"
