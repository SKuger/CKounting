"""E1 validations (D-023):
  V1 - CUFE present in PDF folder. Stubbed in E1 → emits "pendiente E4" warning (D-017).
  V2 - Nota Crédito sign inversion. Applied in memory only (D-029).
  V3 - IVA rate consistency: 19% then 5% fallback, tolerance ±5 pesos.

Pending: D-E1-13 (behavior when IVA=0 in V3). Default = skip.
"""
from __future__ import annotations

from copy import copy
from decimal import Decimal
from typing import Any

from . import money
from .excel import DIAN_COLUMNS, compute_iva_columns, is_nota_credito  # noqa: F401

# Importes en Decimal (D-075): la tolerancia y las tarifas también, para que la
# comparación no pase nunca por float.
V3_TOLERANCE_PESOS = Decimal("5")
IVA_RATE_GENERAL = Decimal("0.19")
IVA_RATE_REDUCED = Decimal("0.05")

V1_STUB_MESSAGE = "Validación CUFE-en-carpeta pendiente — disponible en E4"
V1_NO_SUPPORT_MESSAGE = "Sin soporte PDF (CUFE no encontrado en la carpeta de soportes)"
V1_NO_CUFE_MESSAGE = "La fila no trae CUFE/CUDE — no se puede validar contra PDFs"


def _normalize_nit(value: Any) -> str:
    """Drop dots / dashes / whitespace and keep just digits. Lets us compare
    '900181831', ' 900181831 ', '900.181.831', '900181831-4' as equal NIT bodies."""
    if value is None:
        return ""
    s = str(value)
    return "".join(c for c in s if c.isdigit())


def apply_v2_inversion(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the row with IVA and Total multiplied by -1 if it's an NC.
    Derived columns (Valor Base, Base IVA, Diferencia) are recomputed from the
    inverted values (D-045)."""
    if not is_nota_credito(row.get("Tipo de documento")):
        return row
    inverted = copy(row)
    iva = money.to_money(row.get("IVA") or 0) * -1
    total = money.to_money(row.get("Total") or 0) * -1
    inverted["IVA"] = iva
    inverted["Total"] = total
    valor_base, base_iva, diferencia = compute_iva_columns(iva, total)
    inverted["Valor Base"] = valor_base
    inverted["Base IVA"] = base_iva
    inverted["Diferencia"] = diferencia
    return inverted


def _v3_check_rate(valor_base: Decimal, iva: Decimal, rate: Decimal, tolerance: Decimal) -> bool:
    """True if the IVA implied by the base matches the reported IVA within tolerance.

    Se compara en ESPACIO DE IVA (base * tarifa vs IVA), no en espacio de base
    (base vs IVA / tarifa). Dividir por la tarifa amplifica el redondeo del IVA por
    1/tarifa, así que una tolerancia de ±5 pesos sobre la base equivalía a ±0,95
    pesos de IVA al 19% y a solo ±0,25 al 5%: casi toda factura del 5% con el IVA
    redondeado al peso fallaba V3 sin motivo. Multiplicar no amplifica nada y la
    tolerancia significa exactamente lo que dice."""
    return abs(iva - (valor_base * rate)) <= tolerance


def evaluate_v3(row: dict[str, Any], tolerance: Decimal = V3_TOLERANCE_PESOS) -> str | None:
    """R-V3: tarifa de IVA.
    Returns None on pass, or a failure string. row must already have V2 applied."""
    iva = money.to_money(row.get("IVA") or 0)
    total = money.to_money(row.get("Total") or 0)
    if iva == money.ZERO:
        # D-E1-13 default: skip excluded/exempt rows.
        return None
    valor_base = money.quantize(total - iva)
    if _v3_check_rate(valor_base, iva, IVA_RATE_GENERAL, tolerance):
        return None
    if _v3_check_rate(valor_base, iva, IVA_RATE_REDUCED, tolerance):
        return None
    return (
        f"IVA no corresponde a tarifa 19% ni 5% "
        f"(Valor Base={valor_base:.2f}, IVA={iva:.2f})"
    )


def evaluate_v1_stub(row: dict[str, Any]) -> str | None:
    """E1 stub fallback when no PDF folder is configured."""
    return V1_STUB_MESSAGE


def is_self_emitted(row: dict[str, Any], self_nit: str | None) -> bool:
    """D-048 — `True` if the row's NIT Emisor matches the empresa's own NIT.
    Those rows were issued by the empresa itself, so V1 does not apply
    (no external 'soporte' is expected for our own documents)."""
    if not self_nit:
        return False
    a = _normalize_nit(self_nit)
    if not a:
        return False
    return a == _normalize_nit(row.get("NIT Emisor"))


def evaluate_v1(
    row: dict[str, Any],
    indexed_cufes: set[str],
    *,
    self_nit: str | None = None,
) -> str | None:
    """V1: row's CUFE/CUDE must exist in the set of CUFEs indexed from the
    PDFs folder. Empty CUFE on the row is reported separately.

    D-048 — when `self_nit` is provided and the row's NIT Emisor matches it,
    V1 is skipped silently: la empresa misma emitió el documento."""
    if is_self_emitted(row, self_nit):
        return None
    raw = row.get("CUFE/CUDE")
    cufe = raw.strip().lower() if isinstance(raw, str) else ""
    if not cufe:
        return V1_NO_CUFE_MESSAGE
    if cufe in indexed_cufes:
        return None
    return V1_NO_SUPPORT_MESSAGE


def evaluate_row(
    row: dict[str, Any],
    *,
    run_v3: bool,
    indexed_cufes: set[str] | None = None,
    overridden_codes: set[str] | None = None,
    self_nit: str | None = None,
) -> list[tuple[str, str]]:
    """Run the E1 validation pipeline against one row.

    Returns a list of `(code, message)` tuples. `code` is the validation ID
    (`'V1'`, `'V3'`). The list is empty when the row is conformant.

    Order: V2 (transform in memory) → V1 → V3.

    `overridden_codes` lists validation codes the user manually approved for
    THIS row (D-046). Their messages are skipped.

    `self_nit` is the empresa's NIT. Rows where `NIT Emisor == self_nit` are
    skipped by V1 (D-048).
    """
    transformed = apply_v2_inversion(row)
    overrides = overridden_codes or set()
    out: list[tuple[str, str]] = []
    if indexed_cufes is not None and "V1" not in overrides:
        v1 = evaluate_v1(transformed, indexed_cufes, self_nit=self_nit)
        if v1:
            out.append(("V1", v1))
    if run_v3 and "V3" not in overrides:
        v3 = evaluate_v3(transformed)
        if v3:
            out.append(("V3", v3))
    return out


def evaluate_rows(
    rows: list[dict[str, Any]],
    *,
    run_v3: bool = True,
    indexed_cufes: set[str] | None = None,
    overrides_by_row: dict[int, set[str]] | None = None,
    self_nit: str | None = None,
) -> list[list[tuple[str, str]]]:
    """Returns a list[list[(code, message)]] aligned with `rows`. Use
    `failures_to_strings(...)` to get the legacy flat string view."""
    overrides_by_row = overrides_by_row or {}
    return [
        evaluate_row(
            r,
            run_v3=run_v3,
            indexed_cufes=indexed_cufes,
            overridden_codes=overrides_by_row.get(i),
            self_nit=self_nit,
        )
        for i, r in enumerate(rows)
    ]


def failures_to_strings(tagged: list[list[tuple[str, str]]]) -> list[list[str]]:
    """Adapter: drop the codes, keep only the messages — for legacy callers
    (export module + existing tests)."""
    return [[msg for _code, msg in row] for row in tagged]
