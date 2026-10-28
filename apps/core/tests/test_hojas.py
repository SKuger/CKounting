"""Leer `.ods` sin dependencia nueva: el contador guarda en LibreOffice.

Lo delicado son las repeticiones: una celda o fila vacía «repetida» hasta el
borde de la hoja no puede expandirse a un millón de filas, y una con valor sí
tiene que expandirse.
"""
import zipfile
from datetime import datetime
from pathlib import Path

from contab_core import hojas

_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
 <office:body><office:spreadsheet>
  <table:table table:name="Hoja historicos">
   <table:table-row>
    <table:table-cell office:value-type="string"><text:p>Tipo de comprobante</text:p></table:table-cell>
    <table:table-cell office:value-type="string"><text:p>Código cuenta contable</text:p></table:table-cell>
    <table:table-cell office:value-type="string"><text:p>Fecha de elaboración</text:p></table:table-cell>
    <table:table-cell office:value-type="string"><text:p>Débito</text:p></table:table-cell>
    <table:table-cell table:number-columns-repeated="16380"/>
   </table:table-row>
   <table:table-row table:number-rows-repeated="2">
    <table:table-cell office:value-type="float" office:value="11"/>
    <table:table-cell office:value-type="float" office:value="22050501"/>
    <table:table-cell office:value-type="date" office:date-value="2026-09-03"/>
    <table:table-cell office:value-type="float" office:value="18496.5"/>
   </table:table-row>
   <table:table-row table:number-rows-repeated="1048570"><table:table-cell table:number-columns-repeated="16384"/></table:table-row>
  </table:table>
 </office:spreadsheet></office:body>
</office:document-content>"""


def _ods(ruta: Path):
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml", _CONTENT)


def test_un_ods_se_lee_con_sus_tipos_y_sin_el_relleno(tmp_path):
    ruta = tmp_path / "CARGA.ods"
    _ods(ruta)
    [h] = hojas.leer_hojas(ruta)
    assert h.titulo == "Hoja historicos"
    assert len(h.filas) == 3, "la cabecera y la fila repetida dos veces; el relleno no"
    assert h.filas[0] == ["Tipo de comprobante", "Código cuenta contable", "Fecha de elaboración", "Débito"]
    assert h.filas[1] == [11, 22050501, datetime(2026, 9, 3), 18496.5]
    assert h.filas[2] == h.filas[1]


def test_el_archivo_de_carga_en_ods_siembra_igual(tmp_path):
    from contab_core import siigo
    ruta = tmp_path / "CARGA.ods"
    _ods(ruta)
    filas = siigo._filas_siigo(ruta)
    assert len(filas) == 2 and filas[0]["Código cuenta contable"] == 22050501
