"""El IVA por tarifa, leído del PDF de la factura cuando no hay XML (D-135).

El reporte de la DIAN da un IVA total sin tarifa. Una factura como las de D1
mezcla 19 %, 5 % y excluidos, y con el total solo no se pueden separar. Pero el
PDF —el mismo que ya se indexa para el CUFE— suele imprimir la tabla:

    [DISCRIMINACIÓN DE IMPUESTOS]
    IVA 5%:  44.657,14  2.232,86
    IVA 0%:  20.900,00      0,00
    IVA 19%: 14.487,39  2.752,60

Lo que se lee aquí es una PROPUESTA y se verifica antes de usarla: la suma del
IVA tiene que dar el IVA del reporte y las bases no pueden pasar del subtotal.
Si no cuadra, no se usa y el asiento sale con una sola línea de IVA.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import pdf_cufe

_MONTO = r"\$?\s*-?\d[\d.,]*"
_FILA = re.compile(
    rf"\bIVA\s*(\d{{1,2}}(?:[.,]\d{{1,2}})?)\s*%\s*:?\s*({_MONTO})\s+({_MONTO})", re.IGNORECASE)
TOLERANCIA = Decimal("1")


def _monto(texto: str) -> Decimal | None:
    """«14.487,39» y «14,487.39» son lo mismo: el último separador es el decimal
    si lleva uno o dos dígitos detrás; si no, es de miles."""
    t = texto.replace("$", "").replace(" ", "").strip()
    if not t:
        return None
    ultimo = max(t.rfind("."), t.rfind(","))
    if ultimo >= 0 and len(t) - ultimo - 1 in (1, 2):
        entero, decimal = t[:ultimo], t[ultimo + 1:]
    else:
        entero, decimal = t, ""
    entero = entero.replace(".", "").replace(",", "")
    try:
        return Decimal(f"{entero}.{decimal}" if decimal else entero)
    except InvalidOperation:
        return None


def desglose_del_texto(texto: str) -> list[tuple[Decimal, Decimal, Decimal]]:
    """(tarifa, base, IVA) por cada fila «IVA n%: base valor» del texto.

    Una tarifa repetida (la tabla y un resumen al pie) se cuenta una vez."""
    vistas: dict[Decimal, tuple[Decimal, Decimal, Decimal]] = {}
    for m in _FILA.finditer(texto or ""):
        tarifa = _monto(m.group(1))
        base, valor = _monto(m.group(2)), _monto(m.group(3))
        if tarifa is None or base is None or valor is None:
            continue
        vistas.setdefault(tarifa, (tarifa, base, valor))
    return list(vistas.values())


def verificar(filas, *, subtotal: Decimal, iva: Decimal) -> bool:
    """¿Lo leído cuadra con lo que dice el reporte de la DIAN?"""
    if not filas:
        return False
    suma_iva = sum((v for _t, _b, v in filas), Decimal("0"))
    suma_base = sum((b for _t, b, _v in filas), Decimal("0"))
    if abs(suma_iva - abs(iva)) > TOLERANCIA:
        return False
    if suma_base > abs(subtotal) + TOLERANCIA:
        return False
    # Cada fila tiene que ser su tarifa: base × tarifa ≈ IVA de la fila.
    return all(abs(b * t / 100 - v) <= TOLERANCIA for t, b, v in filas)


def pdf_de(conn, cufe: str) -> Path | None:
    fila = conn.execute(
        "SELECT i.pdf_path FROM pdf_cufe_value v JOIN pdf_cufe_index i ON i.id = v.pdf_index_id"
        " WHERE lower(v.cufe_cude) = lower(?) ORDER BY i.indexed_at DESC LIMIT 1",
        (cufe,)).fetchone()
    if fila is None:
        return None
    ruta = Path(fila[0])
    return ruta if ruta.exists() else None


def desglose_del_pdf(conn, cufe: str, *, subtotal: Decimal, iva: Decimal,
                     clave: str | None = None) -> list[tuple[Decimal, Decimal, Decimal]] | None:
    """El desglose del PDF de este CUFE, solo si cuadra con el reporte."""
    ruta = pdf_de(conn, cufe)
    if ruta is None:
        return None
    try:
        texto = pdf_cufe._pdftotext(ruta, layout=True)
    except pdf_cufe.PdfProtegido:
        if not clave:
            return None
        try:
            texto = pdf_cufe._pdftotext(ruta, layout=True, password=clave)
        except Exception:
            return None
    except Exception:
        return None
    filas = desglose_del_texto(texto)
    return filas if verificar(filas, subtotal=subtotal, iva=iva) else None
