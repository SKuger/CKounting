from contab_core import excel


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
            assert abs(row["Valor Base"] - 40462) < 1
            assert abs(row["Base IVA"] - (7688 / 0.19)) < 1
            assert abs(row["Diferencia"]) < 5
            return
    raise AssertionError("FELE-827 missing from sample")


def test_base_iva_always_iva_over_19pct(sample_excel):
    """D-046 — Base IVA is ALWAYS IVA/0.19 (when IVA != 0). The conditional
    'pegar a Valor Base' from D-045 was reverted."""
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        if row["IVA"] != 0:
            assert abs(row["Base IVA"] - (row["IVA"] / 0.19)) < 0.01


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
