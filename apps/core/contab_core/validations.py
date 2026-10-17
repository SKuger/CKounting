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


def _iva_declarado(documento: dict[str, Any] | None) -> dict[str, Any] | None:
    """El renglón de IVA del XML, si lo hay. Tipo 01 y sin ser retención."""
    if not documento:
        return None
    for imp in documento.get("impuestos") or []:
        if str(imp.get("tipo")) == "01" and not imp.get("es_retencion"):
            return imp
    return None


def evaluate_v3(row: dict[str, Any], tolerance: Decimal = V3_TOLERANCE_PESOS,
                documento: dict[str, Any] | None = None) -> str | None:
    """R-V3: tarifa de IVA.

    **Con XML se contrasta; sin XML se infiere** (tarea 3.3). Inferir la tarifa
    desde base e IVA obliga a adivinar entre 19% y 5%, y da por buena cualquier
    combinación que cuadre con una de las dos: una factura con IVA del 8% mal
    liquidado pasaba si el total casualmente encajaba. Cuando el XML declara la
    tarifa, ya no hay nada que adivinar. La inferencia de D-093 se conserva para
    las filas sin XML, que siguen siendo la mayoría.

    Returns None on pass, or a failure string. row must already have V2 applied."""
    iva = money.to_money(row.get("IVA") or 0)
    total = money.to_money(row.get("Total") or 0)

    declarado = _iva_declarado(documento)
    if declarado is not None and declarado.get("tarifa") is not None:
        tarifa = Decimal(str(declarado["tarifa"]))
        base = (Decimal(str(declarado["base"])) if declarado.get("base") is not None
                else money.quantize(total - iva))
        esperado = money.quantize(base * tarifa / Decimal("100"))
        if abs(esperado - iva) <= tolerance:
            return None
        return (
            f"El IVA no corresponde a la tarifa que declara el XML "
            f"({tarifa:.2f}%): esperado {esperado:.2f} sobre base {base:.2f}, "
            f"y el reporte trae {iva:.2f}"
        )
    if documento and declarado is None and iva != money.ZERO:
        return (
            f"El reporte trae IVA {iva:.2f}, pero el XML del documento "
            f"no declara ningún IVA"
        )

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


# ── Validaciones que solo el XML permite (tarea 3.4) ──────────────────────────
# Cada una responde a algo que el Excel de la DIAN no puede contestar, porque sus
# 32 columnas no traen ni la referencia de una nota ni la fecha real de emisión
# separada de la de recepción.
CODIGO_DUPLICADO = "V4"
CODIGO_NOTA_SIN_ORIGEN = "V5"
CODIGO_REZAGADO = "V6"
CODIGO_RUT_CANCELADO = "V7"

# El art. 496 ET da tres periodos para descontar el IVA, así que un documento
# emitido antes del mes que se está cerrando no es un error: es un dato que el
# contador tiene que ver para decidir. Pasados los tres, ya no es descontable.
PERIODOS_DE_GRACIA = 3

# Lo que el RUT puede decir y significa «este tercero ya no está activo». Se
# compara en mayúsculas y sin tildes para no depender de cómo lo escriba el RUT.
ESTADOS_RUT_MUERTOS = ("CANCELADO", "SUSPENDIDO", "INACTIVO")


def _meses_entre(periodo_a: str, periodo_b: str) -> int | None:
    """Cuántos meses hay de `periodo_a` a `periodo_b`, ambos 'AAAA-MM'."""
    try:
        aa, am = (int(x) for x in periodo_a.split("-")[:2])
        ba, bm = (int(x) for x in periodo_b.split("-")[:2])
    except (ValueError, AttributeError):
        return None
    return (ba - aa) * 12 + (bm - am)


def evaluate_xml(
    documento: dict[str, Any] | None,
    *,
    periodo: str | None = None,
    cufes_repetidos: set[str] | None = None,
    estados_rut: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Las validaciones de 3.4. Sin XML no devuelve nada — y eso es correcto:
    una fila sin documento no es una fila con un problema."""
    if not documento:
        return []
    out: list[tuple[str, str]] = []
    cufe = (documento.get("cufe") or "").strip().lower()

    if cufes_repetidos and cufe in cufes_repetidos:
        out.append((CODIGO_DUPLICADO,
                    f"El documento {documento.get('numero') or cufe[:12]} aparece "
                    f"más de una vez en el mes con el mismo CUFE"))

    if documento.get("tipo") == "nota_credito":
        tiene_origen = any((r.get("cufe_referido") or r.get("numero_referido"))
                           for r in documento.get("referencias") or [])
        if not tiene_origen:
            out.append((CODIGO_NOTA_SIN_ORIGEN,
                        f"La nota crédito {documento.get('numero') or ''} no dice a qué "
                        f"factura corresponde: no se puede imputar".strip()))

    fecha = documento.get("fecha_emision") or ""
    if periodo and len(fecha) >= 7:
        meses = _meses_entre(fecha[:7], periodo)
        if meses is not None and meses > 0:
            dentro = meses < PERIODOS_DE_GRACIA
            out.append((CODIGO_REZAGADO,
                        f"Emitido en {fecha[:7]} y llega en {periodo} "
                        f"({meses} {'mes' if meses == 1 else 'meses'} después): "
                        + ("todavía descontable, art. 496 ET" if dentro
                           else "fuera de los 3 periodos del art. 496 ET")))

    nit = (documento.get("emisor_nit") or "").strip()
    estado = (estados_rut or {}).get(nit, "")
    if estado and estado.strip().upper() in ESTADOS_RUT_MUERTOS:
        out.append((CODIGO_RUT_CANCELADO,
                    f"El emisor {nit} figura con RUT {estado.strip().upper()} "
                    f"en la última consulta"))
    return out


def cufes_repetidos_de(documentos_por_fila: list[dict[str, Any] | None]) -> set[str]:
    """Los CUFE que aparecen más de una vez. Se calcula una vez por corrida."""
    vistos: dict[str, int] = {}
    for d in documentos_por_fila:
        if not d:
            continue
        c = (d.get("cufe") or "").strip().lower()
        if c:
            vistos[c] = vistos.get(c, 0) + 1
    return {c for c, n in vistos.items() if n > 1}


def evaluate_row(
    row: dict[str, Any],
    *,
    run_v3: bool,
    indexed_cufes: set[str] | None = None,
    overridden_codes: set[str] | None = None,
    self_nit: str | None = None,
    documento: dict[str, Any] | None = None,
    periodo: str | None = None,
    cufes_repetidos: set[str] | None = None,
    estados_rut: dict[str, str] | None = None,
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
        v3 = evaluate_v3(transformed, documento=documento)
        if v3:
            out.append(("V3", v3))
    # Sin XML esto no añade nada, que es como se comportaba antes de la Fase 3.
    for codigo, mensaje in evaluate_xml(
        documento, periodo=periodo, cufes_repetidos=cufes_repetidos,
        estados_rut=estados_rut,
    ):
        if codigo not in overrides:
            out.append((codigo, mensaje))
    return out


def evaluate_rows(
    rows: list[dict[str, Any]],
    *,
    run_v3: bool = True,
    indexed_cufes: set[str] | None = None,
    overrides_by_row: dict[int, set[str]] | None = None,
    self_nit: str | None = None,
    documentos_por_cufe: dict[str, dict[str, Any]] | None = None,
    periodo: str | None = None,
    estados_rut: dict[str, str] | None = None,
) -> list[list[tuple[str, str]]]:
    """Returns a list[list[(code, message)]] aligned with `rows`. Use
    `failures_to_strings(...)` to get the legacy flat string view.

    `documentos_por_cufe` es la capa del XML. Si va vacía, el resultado es
    idéntico al de antes de la Fase 3 — y la suite vieja en verde es la prueba.
    """
    overrides_by_row = overrides_by_row or {}
    docs = documentos_por_cufe or {}
    por_fila = [docs.get(_cufe_de(r)) for r in rows]
    repetidos = cufes_repetidos_de(por_fila) if docs else set()
    return [
        evaluate_row(
            r,
            run_v3=run_v3,
            indexed_cufes=indexed_cufes,
            overridden_codes=overrides_by_row.get(i),
            self_nit=self_nit,
            documento=por_fila[i],
            periodo=periodo,
            cufes_repetidos=repetidos,
            estados_rut=estados_rut,
        )
        for i, r in enumerate(rows)
    ]


def _cufe_de(row: dict[str, Any]) -> str:
    for clave in ("CUFE/CUDE", "CUFE", "cufe_cude"):
        valor = row.get(clave)
        if valor:
            return str(valor).strip().lower()
    return ""


def failures_to_strings(tagged: list[list[tuple[str, str]]]) -> list[list[str]]:
    """Adapter: drop the codes, keep only the messages — for legacy callers
    (export module + existing tests)."""
    return [[msg for _code, msg in row] for row in tagged]
