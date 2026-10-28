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
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import xlsxwriter

from . import money
from .hojas import Hoja, leer_hojas

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
    "doc_soporte": "Documento soporte", "nomina": "Comprobante de nómina",
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
            codigo_imp = (ln.get("codigo_siigo") or "").strip()
            base = money.ZERO
            if rol == "iva":
                tarifa = _tarifa_iva(ln)
                if not codigo_imp and tarifa:
                    codigo_imp = (cfg.get(f"iva:{tarifa}") or "").strip()
                if tarifa and not codigo_imp:
                    faltan.add(f"iva:{tarifa}")
                base = abs(money.to_money(ln.get("base") or 0))
            elif rol == "retencion":
                codigo_imp = codigo_imp or codigos_concepto.get(ln.get("concepto_id") or 0, "")
                if not codigo_imp:
                    faltan.add(f"concepto:{ln.get('concepto_id') or '?'}")
                base = abs(money.to_money(ln.get("base") or 0))
            es_cartera = rol == "cartera"
            valores: list[Any] = [
                int(tipo) if tipo.isdigit() else tipo, a.get("siigo_consecutivo"), fecha,
                "COP", "", _cuenta(ln.get("cuenta_puc")), _nit(ln.get("tercero_nit") or a.get("tercero_nit")),
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

    # La nómina aprobada del mes (D-134): un comprobante por quincena, con el
    # tipo de nómina de la empresa y cada línea con su propio tercero.
    from . import nomina as nomina_module
    tipo_nom = (cfg.get("tipo:nomina") or "").strip()
    for nc in [n for n in nomina_module.listar(conn, periodo) if n["aprobado"]]:
        if not tipo_nom:
            faltan.add("tipo:nomina")
        if not nc.get("siigo_consecutivo") and tipo_nom:
            ultimo = max(int(config(conn).get(f"ultimo:{tipo_nom}") or 0),
                         int(conn.execute("SELECT COALESCE(MAX(siigo_consecutivo), 0) FROM nomina_comprobante")
                             .fetchone()[0]))
            nc["siigo_consecutivo"] = ultimo + 1
            conn.execute("UPDATE nomina_comprobante SET siigo_consecutivo = ? WHERE id = ?",
                         (ultimo + 1, nc["id"]))
            guardar_config(conn, {f"ultimo:{tipo_nom}": ultimo + 1})
        fecha = _fecha(nc["fecha"])
        texto = f"NOMINA {'PRIM' if nc['quincena'] == '1Q' else 'SEG'} QUINCENA {periodo}"
        comprobantes += 1
        for ln in nc["lineas"]:
            debito = money.to_money(ln["debito"] or 0)
            credito = money.to_money(ln["credito"] or 0)
            valores = [
                int(tipo_nom) if tipo_nom.isdigit() else tipo_nom, nc.get("siigo_consecutivo"), fecha,
                "COP", "", _cuenta(ln.get("cuenta")), _nit(ln.get("tercero")),
                "", "", "", "", "", "", "", "", "", "", "", "",
                f"{texto} · {ln.get('descripcion') or ''}", "", debito, credito, texto,
                money.ZERO, "", "",
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
    conn.commit()
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


# ─────────────────────────── el catálogo, desde su Excel ──────────────────────
# El contador manda UNA empresa y carga las otras él mismo. El archivo es el que
# se le pidió el 2026-10-28: hoja «Impuestos» (Código, Nombre, Tipo, Tarifa,
# Cuenta) y hoja «Comprobantes» (Clase, Tipo en Siigo, Último consecutivo). Se
# lee por nombre de columna, sin importar el orden ni las mayúsculas, para que
# un export de Siigo con cabeceras parecidas también entre.


@dataclass
class CatalogoCargado:
    source_name: str
    impuestos: list[dict[str, Any]] = field(default_factory=list)
    comprobantes: list[dict[str, Any]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


_TIPOS_IMPUESTO = {
    "iva": "iva", "retefuente": "retefuente", "retencion": "retefuente",
    "retención": "retefuente", "reteiva": "reteiva", "reteica": "reteica",
    "autorretencion": "autorretencion", "autorretención": "autorretencion",
}
# «Nota crédito proveedores» es la de compra; «para clientes», la de venta.
_CLASES_POR_TEXTO = (
    ("doc_soporte", ("soporte",)),
    ("nc_compra", ("nota credito", "proveedor")),
    ("nc_compra", ("nota credito", "compra")),
    ("nc_venta", ("nota credito", "cliente")),
    ("nc_venta", ("nota credito", "venta")),
    ("compra", ("factura", "compra")),
    ("venta", ("factura", "venta")),
    ("nomina", ("nomina",)),
)
CONTEXTOS = ("venta", "compra", "dev_venta", "dev_compra")


def contexto_de(naturaleza: str | None, tipo_doc: str | None) -> str:
    """En qué columna del catálogo se busca la cuenta de una línea."""
    es_nc = (tipo_doc or "") == "nota_credito"
    if (naturaleza or "compra") == "venta":
        return "dev_venta" if es_nc else "venta"
    return "dev_compra" if es_nc else "compra"


def _contexto_de_fila(cuenta: str, descripcion: str) -> str | None:
    """El catálogo del contador trae el mismo código cuatro veces, una por
    contexto, sin decir cuál es cuál: lo dicen la cuenta y la descripción.
    1355 son retenciones que le practican (ventas); 2365/2367/2368 las que
    practica (compras); 2408 05/20 es IVA generado y 2408 1x/06 descontable.
    «Dev» en la descripción marca la devolución."""
    c = (cuenta or "").strip()
    d = _plano(descripcion)
    dev = "dev" in d or "devol" in d
    if c.startswith("1355") or c[:6] in ("240805", "240820"):
        lado = "venta"
    elif c[:4] in ("2365", "2367", "2368") or c[:5] == "24081" or c[:6] == "240806":
        lado = "compra"
    elif c[:4] in ("2464", "2495"):
        lado = "venta" if "venta" in d else "compra"
    else:
        return None
    return f"dev_{lado}" if dev else lado


def _plano(v: Any) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(v or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).strip().lower()


def _hoja(hojas: list[Hoja], *nombres: str) -> Hoja | None:
    """La hoja cuyo título O cuya cabecera contenga alguna de las palabras: el
    contador la llamó «Hoja1», y lo que la identifica es la columna «Código»."""
    for h in hojas:
        if any(n in _plano(h.titulo) for n in nombres):
            return h
    for h in hojas:
        for r in h.filas[:5]:
            cab = " ".join(_plano(v) for v in r if v is not None)
            if any(n in cab for n in nombres):
                return h
    return None


def _filas_con_cabecera(hoja: Hoja) -> list[dict[str, Any]]:
    filas = hoja.filas
    i = next((k for k, r in enumerate(filas)
              if sum(1 for v in r if isinstance(v, str) and v.strip()) >= 2), None)
    if i is None:
        return []
    cab = [_plano(v) for v in filas[i]]
    out = []
    for r in filas[i + 1:]:
        if not any(v is not None and str(v).strip() for v in r):
            continue
        out.append({cab[c]: r[c] for c in range(min(len(cab), len(r))) if cab[c]})
    return out


def _col(fila: dict[str, Any], *claves: str) -> Any:
    for k, v in fila.items():
        if any(c in k for c in claves):
            return v
    return None


def _codigo(v: Any) -> str:
    """'2' y 2.0 se guardan como '02': Siigo los imprime con dos dígitos."""
    t = str(v).strip() if v is not None else ""
    if t.endswith(".0"):
        t = t[:-2]
    return t.zfill(2) if t.isdigit() and len(t) < 2 else t


def _tarifa(v: Any) -> str | None:
    if v in (None, ""):
        return None
    try:
        d = Decimal(str(v).replace("%", "").replace(",", ".").strip())
    except Exception:
        return None
    if d < 1 and d > 0:
        d = d * 100     # celda con formato de porcentaje: 0.19 es 19 %
    return str(d.normalize())


def cargar_catalogo(ruta: str | Path) -> CatalogoCargado:
    ruta = Path(ruta)
    hojas = leer_hojas(ruta)
    out = CatalogoCargado(source_name=ruta.name)

    ws = _hoja(hojas, "impuesto", "codigo")
    if ws is None:
        out.avisos.append("No hay hoja «Impuestos»: no se leen códigos de impuesto.")
    else:
        for f in _filas_con_cabecera(ws):
            codigo = _codigo(_col(f, "codigo", "código"))
            if not codigo:
                continue
            tipo_txt = _plano(_col(f, "tipo")).replace(" ", "")
            tipo = _TIPOS_IMPUESTO.get(tipo_txt, "otro" if tipo_txt else "")
            cuenta = str(_col(f, "cuenta") or "").strip().replace(".0", "")
            descripcion = str(_col(f, "descripcion", "descripción") or "").strip()
            out.impuestos.append({
                "codigo": codigo, "nombre": str(_col(f, "nombre") or "").strip(),
                "tipo": tipo, "tarifa": _tarifa(_col(f, "tarifa")), "cuenta": cuenta,
                "descripcion": descripcion,
                "contexto": _contexto_de_fila(cuenta, descripcion),
            })
            if not tipo:
                out.avisos.append(f"El código {codigo} no dice de qué tipo es (IVA, Retefuente…); no se puede cruzar.")
            elif out.impuestos[-1]["contexto"] is None and cuenta:
                out.avisos.append(f"No sé si la cuenta {cuenta} del código {codigo} es de compra o de venta; se guarda sin contexto.")

    ws = _hoja(hojas, "comprobante", "clase")
    if ws is None:
        out.avisos.append("No hay hoja «Comprobantes»: no se leen tipos ni consecutivos.")
    else:
        for f in _filas_con_cabecera(ws):
            texto = _plano(_col(f, "clase", "nombre", "descripcion")).replace("é", "e")
            clase = next((c for c, palabras in _CLASES_POR_TEXTO
                          if all(p in texto for p in palabras)), None)
            tipo = _col(f, "tipo")
            if clase is None or tipo in (None, ""):
                # El catálogo trae los catorce tipos de la empresa; Contab arma
                # cinco. Los demás (egresos, nómina, depreciación…) no son un aviso.
                continue
            ultimo = _col(f, "ultimo", "último", "consecutivo")
            out.comprobantes.append({
                "clase": clase, "tipo": str(tipo).replace(".0", "").strip(),
                "ultimo": str(ultimo).replace(".0", "").strip() if ultimo not in (None, "") else "",
            })
    return out


def aplicar_catalogo(conn, cargado: CatalogoCargado, *, dry_run: bool = False) -> dict[str, Any]:
    """Cruza el catálogo con lo que la empresa ya tiene y, si no es ensayo, escribe.

    El catálogo entero va a `siigo_impuesto` (código × contexto → cuenta). Un
    código de retención se cruza con un concepto **por la cuenta de compra**
    primero y, si no, por tipo y tarifa. Lo que no cruza se devuelve con nombre:
    un código sin concepto no es un error, es un concepto que no está cargado.
    """
    conceptos = [dict(r) for r in conn.execute(
        "SELECT id, concepto, sobre, tarifa, cuenta_puc, codigo_siigo FROM retencion_concepto"
        " WHERE archivado = 0")]
    cruzados, sin_cruce, ivas = [], [], {}
    cuentas_de_todos = {i["cuenta"] for i in cargado.impuestos if i["cuenta"]}
    vistos: set[str] = set()
    for imp in cargado.impuestos:
        if imp["tipo"] == "iva":
            if imp["tarifa"] and imp["contexto"] in (None, "compra", "venta"):
                # Si hay dos códigos para la misma tarifa (bienes y servicios),
                # el de servicios queda por defecto: la regla del proveedor lo
                # afina. Se dice en la vista previa.
                clave = f"iva:{imp['tarifa']}"
                if clave not in ivas or "servicio" in _plano(imp["nombre"]):
                    ivas[clave] = imp["codigo"]
            continue
        if imp["codigo"] in vistos:
            continue
        vistos.add(imp["codigo"])
        if imp["tipo"] not in ("retefuente", "reteiva"):
            sin_cruce.append({**imp, "motivo": "Contab no aplica este tipo de impuesto"})
            continue
        sobre = "iva" if imp["tipo"] == "reteiva" else "base"
        cuentas_compra = {i["cuenta"] for i in cargado.impuestos
                          if i["codigo"] == imp["codigo"] and i["contexto"] == "compra"}
        c = next((c for c in conceptos if (c["cuenta_puc"] or "") in cuentas_compra), None)
        if c is None and imp["tarifa"]:
            candidatos = [c for c in conceptos if c["sobre"] == sobre and c["tarifa"]
                          and Decimal(str(c["tarifa"])) == Decimal(imp["tarifa"])
                          and (c["cuenta_puc"] or "") not in cuentas_de_todos]
            c = candidatos[0] if len(candidatos) == 1 else None
        if c is None:
            sin_cruce.append({**imp, "motivo": "ningún concepto de retención con esa cuenta ni esa tarifa"})
            continue
        cruzados.append({**imp, "concepto_id": c["id"], "concepto": c["concepto"]})

    config_nueva: dict[str, str] = dict(ivas)
    for cp in cargado.comprobantes:
        config_nueva[f"tipo:{cp['clase']}"] = cp["tipo"]
        if cp["ultimo"]:
            config_nueva[f"ultimo:{cp['tipo']}"] = cp["ultimo"]

    if not dry_run:
        if cargado.impuestos:
            conn.execute("DELETE FROM siigo_impuesto")
            for imp in cargado.impuestos:
                if not imp["contexto"]:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO siigo_impuesto(codigo, contexto, nombre, tipo, tarifa,"
                    " cuenta, descripcion) VALUES (?,?,?,?,?,?,?)",
                    (imp["codigo"], imp["contexto"], imp["nombre"], imp["tipo"], imp["tarifa"],
                     imp["cuenta"], imp["descripcion"]))
        for x in cruzados:
            conn.execute("UPDATE retencion_concepto SET codigo_siigo = ?, updated_at = datetime('now')"
                         " WHERE id = ?", (x["codigo"], x["concepto_id"]))
        guardar_config(conn, config_nueva)
        conn.commit()
    return {
        "source_name": cargado.source_name,
        "conceptos_cruzados": cruzados, "sin_cruce": sin_cruce,
        "config": config_nueva, "avisos": cargado.avisos, "dry_run": dry_run,
        "impuestos": len(cargado.impuestos),
    }


# ─────────────────────── el catálogo, para quien arma el asiento ──────────────

def catalogo(conn) -> dict[tuple[str, str], dict[str, Any]]:
    """(código, contexto) → fila del catálogo. Vacío si no se ha cargado."""
    try:
        filas = conn.execute("SELECT * FROM siigo_impuesto").fetchall()
    except Exception:
        return {}
    return {(r["codigo"], r["contexto"]): dict(r) for r in filas}


def retenciones_de_venta(conn) -> list[dict[str, Any]]:
    """Las retenciones que un cliente puede practicarle, para elegir al aprobar."""
    return [{"codigo": c, "nombre": f["nombre"], "tipo": f["tipo"], "tarifa": f["tarifa"]}
            for (c, ctx), f in sorted(catalogo(conn).items(), key=lambda kv: (kv[1]["tipo"] or "", kv[0][0]))
            if ctx == "venta" and f["tipo"] in ("retefuente", "reteiva", "reteica")]


def ivas_disponibles(conn) -> list[dict[str, Any]]:
    """Los códigos de IVA del catálogo, uno por código, para elegir al aprobar."""
    vistos: dict[str, dict[str, Any]] = {}
    for (codigo, _contexto), fila in sorted(catalogo(conn).items()):
        if fila["tipo"] == "iva" and codigo not in vistos:
            vistos[codigo] = {"codigo": codigo, "nombre": fila["nombre"], "tarifa": fila["tarifa"]}
    return list(vistos.values())


# ─────────────────── sembrar reglas desde los históricos de Siigo ─────────────
# El archivo de carga del contador trae una hoja de históricos: tres años de
# comprobantes exportados de Siigo. Cada factura de compra dice a qué cuenta fue
# el gasto de ese proveedor; cada venta, a qué cuenta fue el ingreso. Es la
# decisión que la bandeja le pediría una vez por tercero, ya tomada. Sembrarla
# hace que el primer mes de una empresa salga casi todo «listo» (D-130).
#
# Lo que NO hace: pisar una regla que ya existe —manual o aprendida al aprobar—,
# ni elegir cuando el tercero fue a cuentas distintas sin una que domine. Eso
# se devuelve con nombre, para que lo decida él en la bandeja.

VENTANA_HISTORICO = 10        # los últimos N comprobantes de cada tercero
DOMINIO_MINIMO = Decimal("0.7")
ORIGEN_HISTORICO = "historico"
_NO_GASTO = ("2408", "2365", "2367", "2368", "2205", "1355", "1305", "2335")


def _filas_siigo(ruta: str | Path) -> list[dict[str, Any]]:
    """Todas las filas de todas las hojas que tengan la cabecera del modelo."""
    out: list[dict[str, Any]] = []
    for h in leer_hojas(ruta):
        if not h.filas:
            continue
        cab = h.filas[0]
        if "tipo de comprobante" not in [_plano(v) for v in cab]:
            continue
        nombres = [str(v).strip() if v is not None else "" for v in cab]
        for r in h.filas[1:]:
            if r and r[0] is not None:
                out.append({nombres[i]: r[i] for i in range(min(len(nombres), len(r))) if nombres[i]})
    return out


def _clase_por_tipo(cfg: dict[str, str]) -> dict[str, str]:
    return {v.strip(): k.split(":", 1)[1] for k, v in cfg.items()
            if k.startswith("tipo:") and v.strip()}


def sembrar_reglas(conn, ruta: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Crea una regla por tercero a partir de los comprobantes históricos.

    De cada tercero se miran sus últimos `VENTANA_HISTORICO` comprobantes de
    compra, documento soporte o venta. Si todos fueron a la misma cuenta —o
    una pesa al menos el 70 %— se crea la regla con esa cuenta, el código de
    IVA que traían y el concepto de retención cuyo código de Siigo aparece. Si
    no, se devuelve como ambiguo. Las notas crédito no siembran: sus cuentas
    son las de devolución.
    """
    cfg = config(conn)
    clase_por_tipo = _clase_por_tipo(cfg)
    cat = catalogo(conn)

    def _tarifa_vista(ln: dict[str, Any], codigo: str) -> str:
        """La tarifa que de verdad aplicó el cliente, si no es la del catálogo.
        Retefuente y ReteIVA en %, ReteICA en por mil, como el catálogo."""
        fila = cat.get((codigo, "venta")) or {}
        base = Decimal(str(ln.get("Base gravable libro compras/ventas") or 0))
        valor = Decimal(str(ln.get("Débito") or 0)) or Decimal(str(ln.get("Crédito") or 0))
        if not base or not fila.get("tarifa"):
            return ""
        escala = 1000 if fila.get("tipo") == "reteica" else 100
        vista = (valor / base * escala).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if vista == Decimal(fila["tarifa"]).quantize(Decimal("0.1")):
            return ""
        # «10», no «1E+1»: normalize() pasa a notación científica los enteros.
        return format(vista.normalize(), "f")

    if not clase_por_tipo:
        raise ValueError(
            "Primero cargue el catálogo de Siigo de esta empresa: sin los tipos de "
            "comprobante no se sabe cuáles son compras, cuáles ventas y cuáles soportes.")
    concepto_por_codigo = {
        (r["codigo_siigo"] or "").strip(): r["id"]
        for r in conn.execute("SELECT id, codigo_siigo FROM retencion_concepto WHERE archivado = 0")
        if (r["codigo_siigo"] or "").strip()}

    comprobantes: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for f in _filas_siigo(ruta):
        tipo = str(f.get("Tipo de comprobante") or "").strip().replace(".0", "")
        comprobantes.setdefault((tipo, f.get("Consecutivo comprobante")), []).append(f)

    por_tercero: dict[tuple[str, str], list[dict[str, Any]]] = {}
    ignorados = 0
    for (tipo, _cons), lineas in comprobantes.items():
        clase = clase_por_tipo.get(tipo)
        if clase not in ("compra", "doc_soporte", "venta"):
            ignorados += 1
            continue
        nit = str(lineas[0].get("Identificación tercero") or "").strip().replace(".0", "").split("-")[0]
        if not nit:
            continue
        cuenta = None
        mayor = Decimal("0")
        iva_codigo = None
        retencion_codigo = None
        le_retienen: dict[str, str] = {}
        for ln in lineas:
            c = str(ln.get("Código cuenta contable") or "").strip().replace(".0", "")
            deb = Decimal(str(ln.get("Débito") or 0))
            cre = Decimal(str(ln.get("Crédito") or 0))
            codigo = _codigo(ln.get("Código impuesto")) if ln.get("Código impuesto") not in (None, "") else ""
            if c.startswith("2408") and codigo:
                iva_codigo = codigo
            if c[:4] in ("2365", "2367") and codigo:
                retencion_codigo = codigo
            if c.startswith("1355") and codigo and codigo not in le_retienen:
                tarifa = _tarifa_vista(ln, codigo)
                # Una línea en cero no es una retención: el cliente no la practicó.
                if tarifa != "0":
                    le_retienen[codigo] = tarifa
            valor = cre if clase == "venta" else deb
            es_candidata = (c.startswith("4") if clase == "venta" else c[:4] not in _NO_GASTO)
            if es_candidata and valor > mayor:
                cuenta, mayor = c, valor
        if cuenta:
            por_tercero.setdefault((nit, clase), []).append({
                "fecha": str(lineas[0].get("Fecha de elaboración") or "")[:10],
                "cuenta": cuenta, "iva": iva_codigo, "retencion": retencion_codigo,
                "le_retienen": ",".join(
                    f"{c}:{t}" if t else c for c, t in sorted(le_retienen.items())) or "ninguna"})

    nuevas, ya_existian, ambiguos = [], 0, []
    for (nit, clase), vistos in sorted(por_tercero.items()):
        vistos = sorted(vistos, key=lambda v: v["fecha"])[-VENTANA_HISTORICO:]
        conteo: dict[str, int] = {}
        for v in vistos:
            conteo[v["cuenta"]] = conteo.get(v["cuenta"], 0) + 1
        cuenta, n = max(conteo.items(), key=lambda kv: (kv[1], kv[0]))
        if Decimal(n) / Decimal(len(vistos)) < DOMINIO_MINIMO:
            ambiguos.append({"tercero_nit": nit, "naturaleza": clase,
                             "cuentas": sorted(conteo, key=conteo.get, reverse=True)[:4]})
            continue
        existe = conn.execute(
            "SELECT 1 FROM regla_causacion WHERE tercero_nit = ? AND naturaleza = ?"
            " AND patron IS NULL AND archivada = 0", (nit, clase)).fetchone()
        if existe:
            ya_existian += 1
            continue
        de_esa = [v for v in vistos if v["cuenta"] == cuenta]
        iva = next((v["iva"] for v in reversed(de_esa) if v["iva"]), None)
        ret = next((v["retencion"] for v in reversed(de_esa) if v["retencion"]), None)
        conjuntos: dict[str, int] = {}
        for v in de_esa:
            conjuntos[v["le_retienen"]] = conjuntos.get(v["le_retienen"], 0) + 1
        le_retienen = max(conjuntos.items(), key=lambda kv: kv[1])[0] if clase == "venta" else None
        nuevas.append({
            "tercero_nit": nit, "naturaleza": clase, "cuenta_puc": cuenta,
            "iva_codigo": iva if clase != "doc_soporte" else None,
            "concepto_retencion_id": concepto_por_codigo.get(ret or "") if clase != "venta" else None,
            "retenciones_cliente": le_retienen,
            "comprobantes": len(vistos),
        })

    if not dry_run:
        for r in nuevas:
            conn.execute(
                "INSERT INTO regla_causacion(tercero_nit, patron, cuenta_puc, concepto_retencion_id,"
                " sin_retencion, naturaleza, iva_codigo, retenciones_cliente, origen)"
                " VALUES (?, NULL, ?, ?, 0, ?, ?, ?, ?)",
                (r["tercero_nit"], r["cuenta_puc"], r["concepto_retencion_id"], r["naturaleza"],
                 r["iva_codigo"], r["retenciones_cliente"], ORIGEN_HISTORICO))
        conn.commit()

    por_clase: dict[str, int] = {}
    for r in nuevas:
        por_clase[r["naturaleza"]] = por_clase.get(r["naturaleza"], 0) + 1
    return {
        "source_name": Path(ruta).name,
        "nuevas": len(nuevas), "por_clase": por_clase,
        "con_retencion": sum(1 for r in nuevas if r["concepto_retencion_id"]),
        "ya_existian": ya_existian, "ambiguos": ambiguos,
        "comprobantes_ignorados": ignorados, "dry_run": dry_run,
    }
