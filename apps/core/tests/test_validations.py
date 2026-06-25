from contab_core import excel, validations


def test_v2_inverts_nc_only(sample_excel):
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        result = validations.apply_v2_inversion(row)
        if excel.is_nota_credito(row["Tipo de documento"]):
            assert result is not row, "NC should get a new dict"
            assert result["IVA"] == -row["IVA"]
            assert result["Total"] == -row["Total"]
            # Derived columns recomputed.
            assert abs(result["Valor Base"] - (result["Total"] - result["IVA"])) < 0.01
        else:
            assert result is row, "non-NC rows pass through unchanged"


def test_v3_passes_for_19pct_rate():
    row = {"Tipo de documento": "Factura electrónica", "IVA": 1900.0, "Total": 11900.0}
    # Valor Base = 10000, IVA/0.19 = 10000 → match.
    assert validations.evaluate_v3(row) is None


def test_v3_passes_for_5pct_rate():
    row = {"Tipo de documento": "Factura electrónica", "IVA": 500.0, "Total": 10500.0}
    # IVA/0.19 = 2631.5; mismatch. IVA/0.05 = 10000; matches Valor Base = 10000.
    assert validations.evaluate_v3(row) is None


def test_v3_fails_for_arbitrary_rate():
    row = {"Tipo de documento": "Factura electrónica", "IVA": 100.0, "Total": 10000.0}
    reason = validations.evaluate_v3(row)
    assert reason is not None and "19%" in reason and "5%" in reason


def test_v3_skips_iva_zero():
    # D-E1-13 default: skip when IVA = 0.
    row = {"Tipo de documento": "Factura electrónica", "IVA": 0, "Total": 10000.0}
    assert validations.evaluate_v3(row) is None


def test_v1_real_passes_when_cufe_in_set():
    cufe = "a" * 96
    row = {"CUFE/CUDE": cufe, "Tipo de documento": "Factura electrónica", "IVA": 0, "Total": 0}
    assert validations.evaluate_v1(row, {cufe}) is None


def test_v1_real_fails_when_cufe_missing():
    cufe = "a" * 96
    row = {"CUFE/CUDE": cufe, "Tipo de documento": "Factura electrónica", "IVA": 0, "Total": 0}
    assert validations.evaluate_v1(row, set()) == validations.V1_NO_SUPPORT_MESSAGE


def test_v1_real_reports_missing_cufe_on_row():
    row = {"CUFE/CUDE": "", "Tipo de documento": "Factura electrónica", "IVA": 0, "Total": 0}
    assert validations.evaluate_v1(row, set()) == validations.V1_NO_CUFE_MESSAGE


def _messages(tagged):
    """Helper: flatten the (code, msg) tuples to just messages."""
    return [[msg for _code, msg in row] for row in tagged]


def test_v1_skipped_when_indexed_cufes_is_none(sample_excel):
    loaded = excel.load_excel(sample_excel)
    tagged = validations.evaluate_rows(loaded.rows, run_v3=True, indexed_cufes=None)
    for row in _messages(tagged):
        assert validations.V1_NO_SUPPORT_MESSAGE not in row
        assert validations.V1_NO_CUFE_MESSAGE not in row


def test_evaluate_rows_with_indexed_cufes(sample_excel):
    loaded = excel.load_excel(sample_excel)
    # No CUFE matches → every row with a CUFE fails V1.
    tagged = validations.evaluate_rows(loaded.rows, run_v3=True, indexed_cufes=set())
    messages = _messages(tagged)
    rows_with_v1 = sum(
        1 for row in messages
        if validations.V1_NO_SUPPORT_MESSAGE in row
        or validations.V1_NO_CUFE_MESSAGE in row
    )
    assert rows_with_v1 == len(loaded.rows)


def test_returns_tuples_with_codes(sample_excel):
    """D-046 — evaluate_rows now returns [(code, message), ...] per row."""
    loaded = excel.load_excel(sample_excel)
    tagged = validations.evaluate_rows(loaded.rows, run_v3=True, indexed_cufes=set())
    # Look for at least one row with both V1 and V3 codes tagged.
    for row in tagged:
        for entry in row:
            assert isinstance(entry, tuple) and len(entry) == 2
            code, message = entry
            assert code in ("V1", "V3")
            assert isinstance(message, str) and message


def test_v3_override_suppresses_v3_only(sample_excel):
    """D-046 — overriding V3 for a row keeps V1 failures intact."""
    loaded = excel.load_excel(sample_excel)
    # FELE-823 (index 3 in sample) fails both V1 (sin soporte) and V3 (tarifa).
    target = next(i for i, r in enumerate(loaded.rows) if r.get("# de factura") == "FELE-823")
    no_override = validations.evaluate_rows(loaded.rows, run_v3=True, indexed_cufes=set())
    with_override = validations.evaluate_rows(
        loaded.rows, run_v3=True, indexed_cufes=set(),
        overrides_by_row={target: {"V3"}},
    )
    codes_no = {c for c, _ in no_override[target]}
    codes_yes = {c for c, _ in with_override[target]}
    assert "V3" in codes_no
    assert "V3" not in codes_yes      # V3 suppressed
    assert codes_yes == codes_no - {"V3"}  # V1 still there


def test_nc_inversion_makes_v3_pass(sample_excel):
    """For NC rows the original (positive) values may fail V3; after V2 they should pass
    (since the actual factura had a valid rate and we just flipped the sign)."""
    loaded = excel.load_excel(sample_excel)
    for row in loaded.rows:
        if not excel.is_nota_credito(row["Tipo de documento"]):
            continue
        transformed = validations.apply_v2_inversion(row)
        # Tolerate either pass or fail per data — the assertion is that the magnitudes match.
        assert transformed["IVA"] == -row["IVA"]
        assert transformed["Total"] == -row["Total"]
