"""Excel exports (D-014, D-027, D-028, D-029, D-047)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import xlsxwriter

from . import money
from .excel import DERIVED_COLUMNS, DIAN_COLUMNS
from .validations import apply_v2_inversion

RAZON_FALLA_COL = "razon_falla"
REASON_SEPARATOR = "; "  # D-028
EXPORT_COLUMNS: list[str] = DIAN_COLUMNS + DERIVED_COLUMNS + [RAZON_FALLA_COL]

# D-047: reporte de faltantes por soporte (V1 fail). Solo 5 columnas, en este orden.
MISSING_SUPPORTS_COLUMNS: list[str] = [
    "NIT Emisor",
    "Nombre Emisor",
    "# de factura",
    "Fecha Emisión",
    "Total",
]


def _coerce_cell(value: Any) -> Any:
    """xlsxwriter writes numbers as numbers and strings as strings, but None breaks.

    Borde de salida de los importes (D-075): xlsxwriter no entiende Decimal, así
    que aquí —y solo aquí— se convierte a float. El valor ya viene cuantizado a
    centavos, de modo que la celda queda con el importe exacto que se calculó."""
    if value is None:
        return ""
    return money.to_json(value)


def export_no_conformes(
    rows: list[dict[str, Any]],
    reasons_per_row: list[list[str]],
    output_path: str | Path,
) -> dict[str, Any]:
    """Write a .xlsx containing only non-conformant rows (any failure) with full columns.

    Applies V2 inversion in-memory to NC rows before writing (D-029).
    Returns {path, rows_written}."""
    if len(rows) != len(reasons_per_row):
        raise ValueError("rows and reasons_per_row must have the same length")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = xlsxwriter.Workbook(str(output_path))
    sheet = workbook.add_worksheet("No conformes")
    header_format = workbook.add_format({"bold": True, "bg_color": "#EFEFEF"})
    nc_format = workbook.add_format({"font_color": "#B00020"})

    for col_idx, header in enumerate(EXPORT_COLUMNS):
        sheet.write(0, col_idx, header, header_format)

    written = 0
    for row, reasons in zip(rows, reasons_per_row, strict=False):
        if not reasons:
            continue
        transformed = apply_v2_inversion(row)
        is_nc = transformed is not row  # apply_v2_inversion returns a copy iff NC
        fmt = nc_format if is_nc else None
        excel_row = written + 1
        for col_idx, header in enumerate(EXPORT_COLUMNS):
            if header == RAZON_FALLA_COL:
                value = REASON_SEPARATOR.join(reasons)
            else:
                value = _coerce_cell(transformed.get(header))
            if fmt is not None:
                sheet.write(excel_row, col_idx, value, fmt)
            else:
                sheet.write(excel_row, col_idx, value)
        written += 1

    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(written, 0), len(EXPORT_COLUMNS) - 1)
    workbook.close()

    return {"path": str(output_path), "rows_written": written}


def export_missing_supports(
    rows: list[dict[str, Any]],
    missing_row_indexes: set[int],
    output_path: str | Path,
) -> dict[str, Any]:
    """D-047 — write a .xlsx with the rows that failed V1 (no PDF support found).
    Output keeps exactly 5 columns: NIT Emisor / Nombre Emisor / # de factura /
    Fecha Emisión / Total. V2 sign inversion is applied to NCs (Total negative)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = xlsxwriter.Workbook(str(output_path))
    sheet = workbook.add_worksheet("Faltantes de soporte")
    header_format = workbook.add_format({"bold": True, "bg_color": "#EFEFEF"})
    nc_format = workbook.add_format({"font_color": "#B00020"})
    number_format = workbook.add_format({"num_format": "#,##0"})
    nc_number_format = workbook.add_format({"font_color": "#B00020", "num_format": "#,##0"})

    for col_idx, header in enumerate(MISSING_SUPPORTS_COLUMNS):
        sheet.write(0, col_idx, header, header_format)

    written = 0
    for i, row in enumerate(rows):
        if i not in missing_row_indexes:
            continue
        transformed = apply_v2_inversion(row)
        is_nc = transformed is not row
        excel_row = written + 1
        for col_idx, header in enumerate(MISSING_SUPPORTS_COLUMNS):
            value = transformed.get(header)
            if value is None:
                value = ""
            if header == "Total" and money.is_money(value):
                sheet.write_number(
                    excel_row, col_idx, money.to_json(value),
                    nc_number_format if is_nc else number_format,
                )
            else:
                fmt = nc_format if is_nc else None
                if fmt is not None:
                    sheet.write(excel_row, col_idx, value, fmt)
                else:
                    sheet.write(excel_row, col_idx, value)
        written += 1

    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(written, 0), len(MISSING_SUPPORTS_COLUMNS) - 1)
    sheet.set_column(0, 0, 14)   # NIT
    sheet.set_column(1, 1, 36)   # Nombre Emisor
    sheet.set_column(2, 2, 16)   # # de factura
    sheet.set_column(3, 3, 14)   # Fecha Emisión
    sheet.set_column(4, 4, 16)   # Total
    workbook.close()

    return {"path": str(output_path), "rows_written": written}


# ── Los asientos aprobados, para llevarlos a Siigo ────────────────────────────
# Sin esto la bandeja era un callejón sin salida: el contador aprobaba y tenía
# que teclear en Siigo mirando la pantalla. Una fila por línea de asiento, que
# es la forma que entiende el importador de Siigo y cualquier otro.
ASIENTO_COLUMNS: list[str] = [
    "Fecha", "NIT proveedor", "Cuenta PUC", "Descripción", "Débito", "Crédito", "CUFE",
]


def export_asientos(conn, periodo: str, output_dir: str | Path) -> dict[str, Any]:
    """Escribe `asientos-<periodo>.xlsx` con los asientos APROBADOS del mes.

    Solo los aprobados: lo que está «por decidir» no es un asiento todavía, es una
    propuesta, y mezclarlos en el mismo archivo es cómo acaba contabilizado algo
    que nadie aprobó.
    """
    from . import asiento as asiento_module  # local: evita el import circular

    aprobados = [a for a in asiento_module.listar(conn, periodo) if a["aprobado"]]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"asientos-{periodo}.xlsx"

    wb = xlsxwriter.Workbook(str(out))
    ws = wb.add_worksheet("Asientos")
    negrita = wb.add_format({"bold": True})
    pesos = wb.add_format({"num_format": "#,##0"})
    for c, h in enumerate(ASIENTO_COLUMNS):
        ws.write(0, c, h, negrita)

    fila = 1
    total_debito = money.ZERO
    total_credito = money.ZERO
    lineas = 0
    for a in aprobados:
        for ln in a["lineas"]:
            debito = money.to_money(ln["debito"] or 0)
            credito = money.to_money(ln["credito"] or 0)
            valores = [a["fecha"], a["tercero_nit"], ln["cuenta_puc"],
                       ln["descripcion"], debito, credito, a["cufe"]]
            for c, v in enumerate(valores):
                ws.write(fila, c, _coerce_cell(v), pesos if c in (4, 5) else None)
            total_debito += debito
            total_credito += credito
            fila += 1
            lineas += 1
        fila += 1   # un renglón en blanco entre asientos, para leerlo

    ws.write(fila, 3, "TOTAL", negrita)
    ws.write(fila, 4, _coerce_cell(total_debito), pesos)
    ws.write(fila, 5, _coerce_cell(total_credito), pesos)
    ws.set_column(0, 0, 12)
    ws.set_column(1, 2, 14)
    ws.set_column(3, 3, 36)
    ws.set_column(4, 5, 14)
    ws.set_column(6, 6, 24)
    wb.close()

    return {
        "path": str(out), "asientos": len(aprobados), "lineas": lineas,
        "total_debito": str(total_debito), "total_credito": str(total_credito),
        # Que cuadre el archivo entero es la comprobación más barata que existe
        # antes de llevarlo a Siigo.
        "cuadra": total_debito == total_credito,
    }
