from contab_core.nit import compute_dv, is_valid_nit_with_dv, normalize


def test_normalize_strips_punctuation():
    assert normalize(" 900.181.831 - 4 ") == "9001818314"


def test_real_seguros_dv_is_4():
    # Real Seguros (sample company) - NIT 900181831, DV is 4.
    assert compute_dv("900181831") == "4"
    assert is_valid_nit_with_dv("900181831-4")


def test_known_dian_dvs():
    # Spot-check NITs in the sample PDFs.
    assert compute_dv("890900608") == "9"   # Almacenes Éxito
    assert compute_dv("830122566") == "1"   # Movistar
    assert compute_dv("900276962") == "1"   # D1


def test_invalid_dv_rejected():
    assert not is_valid_nit_with_dv("900181831-5")
