"""Colombian NIT check-digit (módulo 11 DIAN). Glosario."""
from __future__ import annotations

# Official DIAN weighting factors. Applied right-to-left: the rightmost digit
# gets factor 3, the next 7, then 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71.
_FACTORS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]


def normalize(nit_input: str) -> str:
    """Strip dots, dashes, spaces — keep digits only."""
    return "".join(c for c in (nit_input or "") if c.isdigit())


def compute_dv(nit_body: str) -> str:
    """Compute the check digit for a NIT body (digits only, no DV)."""
    digits = normalize(nit_body)
    if not digits:
        raise ValueError("NIT vacío")
    if len(digits) > len(_FACTORS):
        raise ValueError(f"NIT demasiado largo ({len(digits)} dígitos, máx {len(_FACTORS)})")
    weighted = sum(int(d) * _FACTORS[i] for i, d in enumerate(reversed(digits)))
    remainder = weighted % 11
    if remainder == 0 or remainder == 1:
        return str(remainder)
    return str(11 - remainder)


def is_valid_nit_with_dv(nit_with_dv: str) -> bool:
    """Validate a NIT supplied as '<body>-<dv>' or '<body><dv>'."""
    raw = (nit_with_dv or "").strip()
    if "-" in raw:
        body, dv = raw.rsplit("-", 1)
    else:
        digits = normalize(raw)
        if len(digits) < 2:
            return False
        body, dv = digits[:-1], digits[-1]
    try:
        return compute_dv(body) == normalize(dv)
    except ValueError:
        return False
