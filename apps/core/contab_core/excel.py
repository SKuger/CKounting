"""DIAN Excel loader. Implements the coercion + derived-columns logic
locked in D-012, D-014, D-024, D-027, D-030. See docs/excel-structure.md."""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from . import money

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

# Columnas que llevan IMPORTES (D-075): se manejan en Decimal de punta a punta.
# Son todas las de DIAN_COLUMNS que no son texto ni fecha, más las derivadas.
MONEY_COLUMNS: frozenset[str] = frozenset({
    "IVA", "ICA", "IC", "INC", "Timbre", "INC Bolsas",
    "IN Carbono", "IN Combustibles", "IC Datos", "ICL",
    "INPP", "IBUA", "ICUI",
    "Rete IVA", "Rete Renta", "Rete ICA",
    "Total",
    "Valor Base", "Base IVA", "Diferencia",
})

IVA_RATE_GENERAL = Decimal("0.19")
IVA_TOLERANCE_PESOS = Decimal("5")


def compute_iva_columns(
    iva: Decimal,
    total: Decimal,
    *,
    rate: Decimal = IVA_RATE_GENERAL,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return the trio (Valor Base, Base IVA, Diferencia) — D-046 (revisa D-045).

      Valor Base = Total − IVA              (siempre)
      Base IVA   = IVA / 0.19               (siempre, salvo IVA = 0 → 0)
      Diferencia = Valor Base − Base IVA    (literal; 0 cuando la tarifa es 19% exacta)

    Los tres salen cuantizados a centavos: `IVA / 0.19` es periódico y antes se
    guardaba y exportaba crudo (40463.15789473684) en la columna que ve el contador.
    """
    iva = money.to_money(iva)
    total = money.to_money(total)
    valor_base = money.quantize(total - iva)
    if iva == money.ZERO:
        return valor_base, money.ZERO, money.ZERO
    base_iva = money.quantize(iva / rate)
    return valor_base, base_iva, money.quantize(valor_base - base_iva)

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

# Importes escritos como texto. Solo se aceptan formas SIN ambigüedad (ver _to_number).
_CO_DECIMAL_RE = re.compile(r"[+-]?\d{1,3}(?:\.\d{3})*,\d+|[+-]?\d+,\d+")  # 1.234,56 · 1234,56
_THOUSANDS_RE = re.compile(r"[+-]?\d{1,3}(?:\.\d{3}){2,}")                  # 1.234.567
_AMBIGUOUS_RE = re.compile(r"[+-]?\d{1,3}\.\d{3}")                          # 10.000 → ¿miles o decimal?
_PLAIN_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")                               # 1234 · 1234.56


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


def _to_number(value: Any) -> Decimal | None:
    """None = celda VACÍA (ausencia legítima → 0). Un valor presente pero
    ininterpretable levanta ValueError: nunca debe colapsarse al mismo 0.

    Devuelve Decimal cuantizado a centavos (D-075)."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"valor booleano en columna numérica: {value!r}")
    if isinstance(value, (int, float, Decimal)):
        return money.to_money(value)
    s = str(value).strip()
    if not s:
        return None
    # Importe en texto. openpyxl entrega números como números, así que esto es el
    # camino raro — y en dinero NO se adivina: solo se aceptan formas sin ambigüedad.
    cleaned = s.replace("$", "").replace("\xa0", "").replace(" ", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):  # contabilidad: (123) = -123
        cleaned = "-" + cleaned[1:-1]

    if "," in cleaned:
        # La coma marca el decimal (es-CO) → el punto solo puede ser de miles.
        if _CO_DECIMAL_RE.fullmatch(cleaned):
            return money.to_money(cleaned.replace(".", "").replace(",", "."))
        raise ValueError(f"formato numérico no reconocido: {value!r}")
    if _THOUSANDS_RE.fullmatch(cleaned):
        # Dos o más grupos ("1.234.567") solo pueden ser miles.
        return money.to_money(cleaned.replace(".", ""))
    if _AMBIGUOUS_RE.fullmatch(cleaned):
        # "10.000" puede ser diez mil (es-CO) o diez con tres decimales (en-US).
        # Equivocarse son tres órdenes de magnitud en un importe: mejor parar.
        raise ValueError(
            f"{value!r} es ambiguo: no se sabe si el punto separa miles o decimales. "
            "Corrige la columna en el Excel (dale formato de número) y vuelve a subirlo"
        )
    if _PLAIN_RE.fullmatch(cleaned):
        return money.to_money(cleaned)
    raise ValueError(f"no se pudo interpretar como número: {value!r}")


def is_nota_credito(tipo: Any) -> bool:
    if not isinstance(tipo, str):
        return False
    return tipo.lower().lstrip().startswith(NC_TIPO_PREFIX)


def _normalize_row(raw: dict[str, Any], fila: int = 0) -> dict[str, Any]:
    """Apply column-specific coercion. The result is what we persist.
    `fila` es el número de fila del Excel (1-based, contando el encabezado) y solo
    se usa para que el error diga dónde está el problema."""
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
            try:
                n = _to_number(v)
            except ValueError as exc:
                # Vacío → 0 es legítimo. Ilegible → error: un importe mal leído que
                # se guarda como 0 pasa V3 en silencio (IVA=0 se omite) y descuadra
                # el reporte sin que nadie lo note.
                raise ExcelParseError(
                    f"Fila {fila}: la columna «{col}» trae un valor que no es un número "
                    f"({v!r}). Revisa el archivo: {exc}"
                ) from None
            out[col] = n if n is not None else money.ZERO
    return out


def _derive_columns(row: dict[str, Any]) -> dict[str, Any]:
    """# de factura / Valor Base / Base IVA / Diferencia — calculated from raw
    (non-V2) values (D-024, D-029, D-045). V2 inversion is applied only at
    evaluation / export time."""
    iva = _to_number(row.get("IVA")) or money.ZERO
    total = _to_number(row.get("Total")) or money.ZERO
    prefijo = row.get("Prefijo") or ""
    folio = row.get("Folio") or ""
    numero = f"{prefijo}-{folio}" if (prefijo or folio) else ""  # D-030
    valor_base, base_iva, diferencia = compute_iva_columns(iva, total)
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
            raise ExcelParseError("Hoja vacía") from None

        headers = [str(h).strip() if h is not None else "" for h in header_row]
        missing = [c for c in DIAN_COLUMNS if c not in headers]
        if missing:
            raise ExcelParseError(
                f"Faltan columnas requeridas del reporte DIAN: {missing[:5]}"
                + (" (y más)" if len(missing) > 5 else "")
            )

        col_index = {h: i for i, h in enumerate(headers)}
        rows: list[dict[str, Any]] = []
        for fila, data in enumerate(iterator, start=2):  # 1 es el encabezado
            if data is None or all(c is None for c in data):
                continue
            raw = {
                col: (data[col_index[col]] if col_index[col] < len(data) else None)
                for col in DIAN_COLUMNS
            }
            normalized = _normalize_row(raw, fila=fila)
            normalized.update(_derive_columns(normalized))
            rows.append(normalized)

        return LoadedExcel(sheet_name=sheet_name, columns=headers, rows=rows)
    finally:
        wb.close()


PERIODO_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")


def _periodo_dominante(periodos: list[str]) -> str | None:
    """El mes más frecuente del lote; en empate gana el más antiguo.

    `max(set(p), key=p.count)` dependía del orden de iteración de un set de
    strings, que varía entre procesos por el hash aleatorio de Python: el mismo
    Excel podía quedar en meses distintos en dos cargas. Además era O(n²)."""
    if not periodos:
        return None
    conteo = Counter(periodos)
    return min(conteo, key=lambda p: (-conteo[p], p))


def resumen_por_periodo(conn, *, incluir_borrados: bool = False) -> list[dict[str, Any]]:
    """Totales por mes, agregados EN SQL (D-091).

    Esto es lo que las columnas consultables desbloquean: antes había que cargar
    todas las filas de todos los lotes a memoria en Python para sumar un mes.
    Los importes están en centavos (INTEGER), así que `SUM` es exacto.
    """
    filtro = "" if incluir_borrados else "AND l.deleted_at IS NULL"
    filas = conn.execute(
        f"""
        SELECT r.periodo             AS periodo,
               COUNT(*)              AS documentos,
               SUM(r.total_centavos) AS total_centavos,
               SUM(r.iva_centavos)   AS iva_centavos,
               COUNT(DISTINCT r.nit_emisor) AS emisores
        FROM excel_row r
        JOIN excel_load l ON l.id = r.load_id
        WHERE r.periodo IS NOT NULL {filtro}
        GROUP BY r.periodo
        ORDER BY r.periodo DESC
        """
    ).fetchall()
    return [
        {
            "periodo": f["periodo"],
            "documentos": f["documentos"],
            "total": money.de_centavos(f["total_centavos"]) or money.ZERO,
            "iva": money.de_centavos(f["iva_centavos"]) or money.ZERO,
            "emisores": f["emisores"],
        }
        for f in filas
    ]


def resumen_por_emisor(conn, periodo: str | None = None, limite: int = 50) -> list[dict[str, Any]]:
    """Los mayores emisores del periodo, agregados en SQL (D-091)."""
    where = "WHERE r.nit_emisor IS NOT NULL AND l.deleted_at IS NULL"
    params: list[Any] = []
    if periodo:
        where += " AND r.periodo = ?"
        params.append(periodo)
    filas = conn.execute(
        f"""
        SELECT r.nit_emisor          AS nit,
               COUNT(*)              AS documentos,
               SUM(r.total_centavos) AS total_centavos
        FROM excel_row r
        JOIN excel_load l ON l.id = r.load_id
        {where}
        GROUP BY r.nit_emisor
        ORDER BY SUM(r.total_centavos) DESC
        LIMIT ?
        """,
        (*params, int(limite)),
    ).fetchall()
    return [
        {
            "nit": f["nit"],
            "documentos": f["documentos"],
            "total": money.de_centavos(f["total_centavos"]) or money.ZERO,
        }
        for f in filas
    ]


def periodo_from_row(row: dict[str, Any]) -> str | None:
    """'YYYY-MM' derivado de 'Fecha Emisión' (ISO). None si no se puede.

    Se VALIDA la forma antes de devolverlo. `_parse_date` deja pasar el texto
    original cuando no reconoce el formato, así que cortar a ciegas los 7 primeros
    caracteres producía periodos basura como 'Marzo 2' — y ese periodo decide
    contra qué carpeta de soportes se valida el lote."""
    fe = row.get("Fecha Emisión")
    if not isinstance(fe, str) or len(fe) < 7:
        return None
    candidato = fe[:7]
    return candidato if PERIODO_RE.fullmatch(candidato) else None


def persist_load(conn, source_path: str, loaded: LoadedExcel, periodo: str | None = None) -> int:
    """Insert load + rows. Returns load_id.
    0.1.4: cada fila recibe su 'periodo' (mes) derivado de 'Fecha Emisión' (o el
    'periodo' forzado); el lote guarda el mes dominante."""
    from .storage import transaction

    src = Path(source_path)
    row_periodos = [periodo or periodo_from_row(row) for row in loaded.rows]
    non_null = [p for p in row_periodos if p]
    load_periodo = periodo or _periodo_dominante(non_null)
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO excel_load(source_path, source_name, total_rows, sheet_name, periodo) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(src), src.name, len(loaded.rows), loaded.sheet_name, load_periodo),
        )
        load_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO excel_row(load_id, row_index, cufe_cude, grupo, tipo_doc, data_json,"
            " periodo, total_centavos, iva_centavos, nit_emisor, fecha_emision) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    load_id,
                    i,
                    row.get("CUFE/CUDE"),
                    row.get("Grupo"),
                    row.get("Tipo de documento"),
                    _dump_row_json(row),
                    row_periodos[i],
                    # D-091: proyección consultable. `data_json` sigue siendo la
                    # fuente de verdad de la fila completa.
                    money.a_centavos(row.get("Total")),
                    money.a_centavos(row.get("IVA")),
                    row.get("NIT Emisor"),
                    row.get("Fecha Emisión"),
                )
                for i, row in enumerate(loaded.rows)
            ],
        )
    return load_id


def _dump_row_json(row: dict[str, Any]) -> str:
    """Serializa una fila a `data_json`. Los importes van como STRING exacto
    ("12952.83"), no como número JSON: un float en el archivo reintroduce por la
    puerta de atrás la representación binaria que estamos evitando (D-075)."""
    return json.dumps(
        {k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items()},
        ensure_ascii=False,
        default=str,
    )


def _revive_money(row: dict[str, Any]) -> dict[str, Any]:
    """Devuelve los importes de `data_json` a Decimal.

    Soporta cargas VIEJAS, donde quedaron como números JSON (float): `to_money`
    los pasa por `repr()`, así que 12952.83 vuelve como Decimal('12952.83') y no
    como el binario largo."""
    for col in MONEY_COLUMNS:
        if col in row and row[col] is not None:
            try:
                row[col] = money.to_money(row[col])
            except ValueError:
                row[col] = money.ZERO
    return row


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
        row = _revive_money(json.loads(r["data_json"]))
        row.update(_derive_columns(row))
        out.append(row)
    return out
