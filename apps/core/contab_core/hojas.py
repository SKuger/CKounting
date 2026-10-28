"""Leer una hoja de cálculo, sea `.xlsx` o `.ods`, como filas de valores.

El contador guarda en LibreOffice: su archivo de carga de Siigo llegó como
`.ods`. Pedirle que lo pase a `.xlsx` cada vez es una instrucción más que
olvidar, y openpyxl no lee `.ods`. Un `.ods` es un ZIP con `content.xml`: se
lee con la biblioteca estándar, sin dependencia nueva.

Lo único delicado del `.ods` son las repeticiones: una fila o una celda vacía
puede venir marcada «repetida un millón de veces» hasta el final de la hoja.
Se expanden solo si no están vacías.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

_NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
_T = f"{{{_NS['table']}}}"
_O = f"{{{_NS['office']}}}"
_X = f"{{{_NS['text']}}}"
# Una celda repetida más de esto y vacía es relleno hasta el borde de la hoja.
_TOPE_REPETICION = 1000


@dataclass
class Hoja:
    titulo: str
    filas: list[list[Any]]


def leer_hojas(ruta: str | Path) -> list[Hoja]:
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".ods":
        return _leer_ods(ruta)
    return _leer_xlsx(ruta)


def _leer_xlsx(ruta: Path) -> list[Hoja]:
    from openpyxl import load_workbook
    wb = load_workbook(ruta, data_only=True, read_only=True)
    try:
        return [Hoja(ws.title, [list(r) for r in ws.iter_rows(values_only=True)])
                for ws in wb.worksheets]
    finally:
        wb.close()


def _valor(celda: ET.Element) -> Any:
    tipo = celda.get(_O + "value-type")
    if tipo in ("float", "percentage", "currency"):
        crudo = celda.get(_O + "value")
        try:
            f = float(crudo)
        except (TypeError, ValueError):
            return crudo
        return int(f) if f.is_integer() and abs(f) < 1e15 else f
    if tipo == "date":
        crudo = celda.get(_O + "date-value") or ""
        try:
            return datetime.fromisoformat(crudo)
        except ValueError:
            return crudo
    if tipo == "boolean":
        return celda.get(_O + "boolean-value") == "true"
    partes = ["".join(p.itertext()) for p in celda.findall(_X + "p")]
    texto = "\n".join(partes)
    return texto if texto else None


def _leer_ods(ruta: Path) -> list[Hoja]:
    with zipfile.ZipFile(ruta) as z, z.open("content.xml") as f:
        raiz = ET.parse(f).getroot()
    hojas: list[Hoja] = []
    for tabla in raiz.iter(_T + "table"):
        filas: list[list[Any]] = []
        for fila in tabla.iter(_T + "table-row"):
            valores: list[Any] = []
            for celda in fila:
                if celda.tag not in (_T + "table-cell", _T + "covered-table-cell"):
                    continue
                v = _valor(celda)
                n = int(celda.get(_T + "number-columns-repeated") or 1)
                if v is None and n > _TOPE_REPETICION:
                    continue
                valores.extend([v] * n)
            while valores and valores[-1] is None:
                valores.pop()
            n_filas = int(fila.get(_T + "number-rows-repeated") or 1)
            if not valores:
                if n_filas <= _TOPE_REPETICION:
                    filas.extend([[] for _ in range(n_filas)])
                continue
            filas.extend([list(valores) for _ in range(n_filas)])
        while filas and not filas[-1]:
            filas.pop()
        hojas.append(Hoja(tabla.get(_T + "name") or "", filas))
    return hojas
