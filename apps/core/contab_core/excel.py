"""DIAN Excel loader. Implements the coercion + derived-columns logic
locked in D-012, D-014, D-024, D-027, D-030. See docs/excel-structure.md."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

# The 32 expected DIAN columns, in original order.
DIAN_COLUMNS: list[str] = [
    "Tipo de documento", "CUFE/CUDE", "Folio", "Prefijo", "Divisa",
    "Forma de Pago", "Medio de Pago", "Fecha Emisión", "Fecha Recepción",
    "NIT Emisor", "Nombre Emisor", "NIT Receptor", "Nombre Receptor",
    "IVA", "ICA", "IC", "INC", "Timbre", "INC Bolsas",
    "IN Carbono", "IN Combustibles", "IC Datos", "ICL",
    "INPP", "IBUA", "ICUI",
    "Rete IVA", "Rete Renta", "Rete ICA",
    "Total", "Estado", "Grupo",
]

DERIVED_COLUMNS: list[str] = ["# de factura", "Valor Base", "Base IVA", "Diferencia"]

IVA_RATE_GENERAL = 0.19
IVA_TOLERANCE_PESOS = 5.0


def compute_iva_columns(
    iva: float,
    total: float,
    *,
    rate: float = IVA_RATE_GENERAL,
) -> tuple[float, float, float]:
    """Return the trio (Valor Base, Base IVA, Diferencia) — D-046 (revisa D-045).

      Valor Base = Total − IVA              (siempre)
      Base IVA   = IVA / 0.19               (siempre, salvo IVA = 0 → 0)
      Diferencia = Valor Base − Base IVA    (literal; 0 cuando la tarifa es 19% exacta)
    """
    valor_base = total - iva
    if iva == 0:
        return valor_base, 0.0, 0.0
    base_iva = iva / rate
    return valor_base, base_iva, valor_base - base_iva

# Order applied to the export (D-014, D-027).
EXPORT_ORDER: list[str] = DIAN_COLUMNS + DERIVED_COLUMNS + ["razon_falla"]

NC_TIPO_PREFIX = "nota de cr"  # matches "Nota de crédito electrónica" case-insensitively.

# UBL Payment Means decoding (D-018, glosario).
FORMA_PAGO_LABELS: dict[str, str] = {"1": "Contado", "2": "Crédito"}
MEDIO_PAGO_LABELS: dict[str, str] = {
    "10": "Efectivo", "30": "Crédito documentario", "42": "Consignación bancaria",
    "47": "Transferencia bancaria", "48": "Tarjeta de crédito", "49": "Tarjeta débito",
    "71": "Bonos", "ZZZ": "Mutuamente definido",
}

_WS_RE = re.compile(r"\s+")
_DATE_RE = re.compile(r"^\s*(\d{1,2})-(\d{1,2})-(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*$")


class ExcelParseError(Exception):
    pass


@dataclass(frozen=True)
class LoadedExcel:
    sheet_name: str
    columns: list[str]          # exact headers as they appeared
    rows: list[dict[str, Any]]  # each row keyed by header, including derived columns


def _trim_ws(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = _WS_RE.sub(" ", value).strip()
        return cleaned
    return value


def _to_string_id(value: Any) -> str | None:
    """Coerce NIT / Folio numerics to string preserving digits as written.
    Excel stores these as numbers, so we never get leading zeros back from openpyxl
    for the numeric case — best we can do is preserve what's there. Shared-string
    values (already strings) are kept verbatim."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _parse_date(value: Any) -> str | None:
    """Return ISO-8601 (yyyy-mm-dd[Thh:mm:ss]) or None if unparseable."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _DATE_RE.match(s)
    if not m:
        return s
    d, mo, y, hh, mm, ss = m.groups()
    iso = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    if hh is not None:
        iso += f"T{int(hh):02d}:{int(mm):02d}:{int(ss or 0):02d}"
    return iso


def _to_number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_nota_credito(tipo: Any) -> bool:
    if not isinstance(tipo, str):
        return False
    return tipo.lower().lstrip().startswith(NC_TIPO_PREFIX)


def _normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply column-specific coercion. The result is what we persist."""
    out: dict[str, Any] = {}
    for col in DIAN_COLUMNS:
        v = raw.get(col)
        if col in ("Tipo de documento", "Prefijo", "Divisa", "Nombre Emisor",
                   "Nombre Receptor", "Estado", "Grupo"):
            out[col] = _trim_ws(v) if v is not None else None
        elif col in ("Folio", "NIT Emisor", "NIT Receptor"):
            out[col] = _to_string_id(v)
        elif col == "CUFE/CUDE":
            out[col] = v.strip().lower() if isinstance(v, str) else (_to_string_id(v) or None)
        elif col in ("Forma de Pago", "Medio de Pago"):
            # Keep as string for UBL code lookup; mixed (ZZZ) supported.
            out[col] = _to_string_id(v)
        elif col in ("Fecha Emisión", "Fecha Recepción"):
            out[col] = _parse_date(v)
        else:
            # numeric column (impuestos / retenciones / Total)
            n = _to_number(v)
            out[col] = n if n is not None else 0
    return out


def _derive_columns(row: dict[str, Any]) -> dict[str, Any]:
    """# de factura / Valor Base / Base IVA / Diferencia — calculated from raw
    (non-V2) values (D-024, D-029, D-045). V2 inversion is applied only at
    evaluation / export time."""
    iva = _to_number(row.get("IVA")) or 0
    total = _to_number(row.get("Total")) or 0
    prefijo = row.get("Prefijo") or ""
    folio = row.get("Folio") or ""
    numero = f"{prefijo}-{folio}" if (prefijo or folio) else ""  # D-030
    valor_base, base_iva, diferencia = compute_iva_columns(float(iva), float(total))
    return {
        "# de factura": numero,
        "Valor Base": valor_base,
        "Base IVA": base_iva,
        "Diferencia": diferencia,
    }


def load_excel(path: str | Path) -> LoadedExcel:
    """Parse a DIAN report Excel. Returns the headers as they appeared
    plus normalized rows with derived columns appended.
    Raises ExcelParseError if structure is wrong."""
    path = Path(path)
    if not path.exists():
        raise ExcelParseError(f"Archivo no encontrado: {path}")

    wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    try:
        sheet = wb.worksheets[0]
        sheet_name = sheet.title
        iterator = sheet.iter_rows(values_only=True)
        try:
            header_row = next(iterator)
        except StopIteration:
            raise ExcelParseError("Hoja vacía")

        headers = [str(h).strip() if h is not None else "" for h in header_row]
        missing = [c for c in DIAN_COLUMNS if c not in headers]
        if missing:
            raise ExcelParseError(
                f"Faltan columnas requeridas del reporte DIAN: {missing[:5]}"
                + (" (y más)" if len(missing) > 5 else "")
            )

        col_index = {h: i for i, h in enumerate(headers)}
        rows: list[dict[str, Any]] = []
        for data in iterator:
            if data is None or all(c is None for c in data):
                continue
            raw = {
                col: (data[col_index[col]] if col_index[col] < len(data) else None)
                for col in DIAN_COLUMNS
            }
            normalized = _normalize_row(raw)
            normalized.update(_derive_columns(normalized))
            rows.append(normalized)

        return LoadedExcel(sheet_name=sheet_name, columns=headers, rows=rows)
    finally:
        wb.close()


def periodo_from_row(row: dict[str, Any]) -> str | None:
    """'YYYY-MM' derivado de 'Fecha Emisión' (ISO). None si no se puede."""
    fe = row.get("Fecha Emisión")
    if isinstance(fe, str) and len(fe) >= 7:
        return fe[:7]
    return None


def persist_load(conn, source_path: str, loaded: LoadedExcel, periodo: str | None = None) -> int:
    """Insert load + rows. Returns load_id.
    0.1.4: cada fila recibe su 'periodo' (mes) derivado de 'Fecha Emisión' (o el
    'periodo' forzado); el lote guarda el mes dominante."""
    from .storage import transaction

    src = Path(source_path)
    row_periodos = [periodo or periodo_from_row(row) for row in loaded.rows]
    non_null = [p for p in row_periodos if p]
    load_periodo = periodo or (max(set(non_null), key=non_null.count) if non_null else None)
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO excel_load(source_path, source_name, total_rows, sheet_name, periodo) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(src), src.name, len(loaded.rows), loaded.sheet_name, load_periodo),
        )
        load_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO excel_row(load_id, row_index, cufe_cude, grupo, tipo_doc, data_json, periodo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    load_id,
                    i,
                    row.get("CUFE/CUDE"),
                    row.get("Grupo"),
                    row.get("Tipo de documento"),
                    json.dumps(row, ensure_ascii=False, default=str),
                    row_periodos[i],
                )
                for i, row in enumerate(loaded.rows)
            ],
        )
    return load_id


def fetch_load_rows(conn, load_id: int) -> list[dict[str, Any]]:
    """Read rows back as dicts (data_json deserialized).
    Derived columns are recomputed on every read so the latest derivation logic
    always wins, even on cargas persisted with older schemas (D-045 retrofit).
    0.1.4: la tabla NO cambia — el periodo vive a nivel de lote (excel_load), no
    por fila; no hay papelera de filas."""
    cur = conn.execute(
        "SELECT row_index, data_json FROM excel_row WHERE load_id = ? ORDER BY row_index",
        (load_id,),
    )
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        row = json.loads(r["data_json"])
        row.update(_derive_columns(row))
        out.append(row)
    return out
