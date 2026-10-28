"""El archivo de importación de comprobantes de Siigo — D-128.

Es lo que el contador sube cada mes. La estructura, verificada sobre su archivo
real, está en `docs/siigo-import-structure.md`; aquí se arma a partir de los
asientos **aprobados** (D-125), una fila por línea, un comprobante por documento.

Lo que Contab no puede deducir y vive en `siigo_config`, por empresa:

- `tipo:<naturaleza>`: el número del tipo de comprobante de Siigo para compras,
  notas crédito de compra, ventas, notas crédito de venta y documentos soporte.
- `ultimo:<tipo>`: el último consecutivo usado de ese tipo. Lo lleva el
  contador, Siigo lo exige, y repetir uno es pisar un comprobante.
- `iva:<tarifa>`: el código de impuesto de Siigo para cada tarifa de IVA.
- `vencimiento_dias`: la fecha de vencimiento es la de elaboración más estos días
  (30 en todo el mes de muestra).

El consecutivo que se le da a un asiento al exportar **se guarda en el asiento**
y no cambia: exportar dos veces el mismo mes produce el mismo archivo.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import xlsxwriter

from . import money
from .asiento import ROL_CARTERA, ROL_IVA, ROL_RETENCION

COLUMNAS: list[str] = [
    "Tipo de comprobante", "Consecutivo comprobante", "Fecha de elaboración",
    "Sigla moneda", "Tasa de cambio", "Código cuenta contable", "Identificación tercero",
    "Sucursal", "Código producto", "Código de bodega", "Acción", "Cantidad producto",
    "Prefijo", "Consecutivo", "No. cuota", "Fecha vencimiento", "Código impuesto",
    "Código grupo activo fijo", "Código activo fijo", "Descripción",
    "Código centro/subcentro de costos", "Débito", "Crédito", "Observaciones",
    "Base gravable libro compras/ventas", "Base exenta libro compras/ventas", "Mes de cierre",
]

# Las clases de comprobante que Contab arma. La nota crédito se distingue por el
# tipo del documento, no por la naturaleza: una NC de compra es una compra al revés.
CLASES = ("compra", "nc_compra", "venta", "nc_venta", "doc_soporte")
ETIQUETAS = {
    "compra": "Factura de compra", "nc_compra": "Nota crédito de compra",
    "venta": "Factura de venta", "nc_venta": "Nota crédito de venta",
    "doc_soporte": "Documento soporte",
}
VENCIMIENTO_DIAS = 30

_NUMERO_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9]*?)?[\s\-_]*(\d+)\s*$")


def clase_de(asiento: dict[str, Any]) -> str:
    nat = asiento.get("naturaleza") or "compra"
    if nat == "doc_soporte":
        return "doc_soporte"
    es_nc = (asiento.get("tipo_doc") or "") == "nota_credito"
    if nat == "venta":
        return "nc_venta" if es_nc else "venta"
    return "nc_compra" if es_nc else "compra"


def partir_numero(numero: str | None) -> tuple[str, str]:
    """'FE1-123456' → ('FE1', '123456'); 'DSE 242' → ('DSE', '242'); '845' → ('', '845')."""
    m = _NUMERO_RE.match(numero or "")
    if not m:
        return "", (numero or "").strip()
    return (m.group(1) or "").upper(), m.group(2)


# ─────────────────────────────── configuración ────────────────────────────────

def config(conn) -> dict[str, str]:
    return {r["clave"]: r["valor"] for r in conn.execute("SELECT clave, valor FROM siigo_config")}


def guardar_config(conn, valores: dict[str, Any]) -> dict[str, str]:
    """Guarda las claves que vengan; una vacía borra la clave."""
    for clave, valor in valores.items():
        clave = str(clave).strip()
        if not clave:
            continue
        texto = str(valor).strip() if valor is not None else ""
        if texto:
            conn.execute(
                "INSERT INTO siigo_config(clave, valor) VALUES (?, ?)"
                " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (clave, texto))
        else:
            conn.execute("DELETE FROM siigo_config WHERE clave = ?", (clave,))
    conn.commit()
    return config(conn)


def _tarifa_iva(linea: dict[str, Any]) -> str | None:
    """19, 5… a partir del IVA y su base. Es lo que decide el código de impuesto."""
    base = money.to_money(linea.get("base") or 0)
    valor = money.to_money(linea.get("debito") or 0) or money.to_money(linea.get("credito") or 0)
    if not base:
        return None
    pct = (abs(valor) / abs(base) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return str(pct)


# ───────────────────────────────── el archivo ─────────────────────────────────

def export_siigo(conn, periodo: str, output_dir: str | Path) -> dict[str, Any]:
    """Escribe `siigo-<periodo>.xlsx` con los asientos aprobados del mes.

    Asigna consecutivo a los que no lo tengan, siguiendo `ultimo:<tipo>`, y lo
    deja escrito en el asiento. Lo que falte para que Siigo lo acepte —un tipo
    de comprobante sin número, un código de impuesto sin definir— no detiene la
    exportación: la celda sale vacía y el faltante se devuelve con nombre.
    """
    from . import asiento as asiento_module  # local: evita el import circular

    cfg = config(conn)
    aprobados = [a for a in asiento_module.listar(conn, periodo) if a["aprobado"]]
    aprobados.sort(key=lambda a: (clase_de(a), a["fecha"] or "", a["id"]))
    faltan: set[str] = set()
    codigos_concepto = {
        r["id"]: (r["codigo_siigo"] or "").strip()
        for r in conn.execute("SELECT id, codigo_siigo FROM retencion_concepto")}
    dias = int(cfg.get("vencimiento_dias") or VENCIMIENTO_DIAS)

    # Consecutivos: primero a los que ya lo tienen (no se tocan), luego a los
    # nuevos, en orden de fecha, partiendo del último conocido de cada tipo.
    siguiente: dict[str, int] = {}
    for a in aprobados:
        clase = clase_de(a)
        tipo = (cfg.get(f"tipo:{clase}") or "").strip()
        if not tipo:
            faltan.add(f"tipo:{clase}")
            continue
        if a.get("siigo_consecutivo"):
            continue
        if tipo not in siguiente:
            siguiente[tipo] = max(int(cfg.get(f"ultimo:{tipo}") or 0), _ultimo_del_tipo(conn, cfg, tipo))
        siguiente[tipo] += 1
        a["siigo_consecutivo"] = siguiente[tipo]
        conn.execute("UPDATE asiento_propuesto SET siigo_consecutivo = ? WHERE id = ?",
                     (siguiente[tipo], a["id"]))
    for tipo, ultimo in siguiente.items():
        guardar_config(conn, {f"ultimo:{tipo}": ultimo})
    conn.commit()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"siigo-{periodo}.xlsx"
    wb = xlsxwriter.Workbook(str(out))
    ws = wb.add_worksheet("Comprobantes")
    negrita = wb.add_format({"bold": True})
    fecha_fmt = wb.add_format({"num_format": "yyyy-mm-dd"})
    for c, h in enumerate(COLUMNAS):
        ws.write(0, c, h, negrita)

    fila, lineas, comprobantes = 1, 0, 0
    total_debito = total_credito = money.ZERO
    for a in aprobados:
        clase = clase_de(a)
        tipo = (cfg.get(f"tipo:{clase}") or "").strip()
        prefijo, consecutivo_doc = partir_numero(a.get("numero"))
        numero_texto = f"{prefijo}-{consecutivo_doc}" if prefijo else consecutivo_doc
        fecha = _fecha(a.get("fecha"))
        comprobantes += 1
        for ln in a["lineas"]:
            debito = money.to_money(ln["debito"] or 0)
            credito = money.to_money(ln["credito"] or 0)
            # Una nota crédito va en negativo en Contab (D-045); en Siigo va en
            # positivo con el débito y el crédito intercambiados.
            if debito < 0 or credito < 0:
                debito, credito = -credito, -debito
            rol = ln.get("rol")
            codigo_imp = ""
            base = money.ZERO
            if rol == ROL_IVA:
                tarifa = _tarifa_iva(ln)
                codigo_imp = (cfg.get(f"iva:{tarifa}") or "").strip() if tarifa else ""
                if tarifa and not codigo_imp:
                    faltan.add(f"iva:{tarifa}")
                base = abs(money.to_money(ln.get("base") or 0))
            elif rol == ROL_RETENCION:
                codigo_imp = codigos_concepto.get(ln.get("concepto_id") or 0, "")
                if not codigo_imp:
                    faltan.add(f"concepto:{ln.get('concepto_id') or '?'}")
                base = abs(money.to_money(ln.get("base") or 0))
            es_cartera = rol == ROL_CARTERA
            valores: list[Any] = [
                int(tipo) if tipo.isdigit() else tipo, a.get("siigo_consecutivo"), fecha,
                "COP", "", _cuenta(ln.get("cuenta_puc")), _nit(a.get("tercero_nit")),
                "", "", "", "", "",
                prefijo if es_cartera else "", (int(consecutivo_doc) if es_cartera and consecutivo_doc.isdigit() else (consecutivo_doc if es_cartera else "")),
                1 if es_cartera else "", (fecha + timedelta(days=dias)) if (es_cartera and fecha) else "",
                codigo_imp, "", "", numero_texto or (ln.get("descripcion") or ""), "",
                debito, credito, numero_texto or (ln.get("descripcion") or ""),
                base, "", "",
            ]
            for c, v in enumerate(valores):
                if isinstance(v, date):
                    ws.write_datetime(fila, c, _a_datetime(v), fecha_fmt)
                elif isinstance(v, Decimal):
                    ws.write_number(fila, c, float(v))
                else:
                    ws.write(fila, c, "" if v is None else v)
            total_debito += debito
            total_credito += credito
            fila += 1
            lineas += 1
    wb.close()
    return {
        "path": str(out), "comprobantes": comprobantes, "lineas": lineas,
        "total_debito": str(total_debito), "total_credito": str(total_credito),
        "cuadra": total_debito == total_credito,
        "faltan": sorted(faltan),
    }


def _ultimo_del_tipo(conn, cfg: dict[str, str], tipo: str) -> int:
    """El mayor consecutivo ya asignado a asientos de ese tipo en esta base."""
    clases = [c for c in CLASES if (cfg.get(f"tipo:{c}") or "").strip() == tipo]
    mayor = 0
    for fila in conn.execute(
            "SELECT naturaleza, tipo_doc, siigo_consecutivo FROM asiento_propuesto"
            " WHERE siigo_consecutivo IS NOT NULL").fetchall():
        if clase_de(dict(fila)) in clases:
            mayor = max(mayor, int(fila["siigo_consecutivo"]))
    return mayor


def _fecha(texto: str | None) -> date | None:
    try:
        return date.fromisoformat((texto or "")[:10])
    except ValueError:
        return None


def _a_datetime(d: date):
    from datetime import datetime
    return datetime(d.year, d.month, d.day)


def _cuenta(valor: str | None) -> Any:
    v = (valor or "").strip()
    return int(v) if v.isdigit() else v


def _nit(valor: str | None) -> Any:
    v = (valor or "").strip().split("-")[0]
    return int(v) if v.isdigit() else v
