"""La propuesta de asiento de todo un mes — tarea 4.4.

Junta lo de las tres tareas anteriores: la **cuenta** que dice la regla (4.3),
las **retenciones** que calcula el motor (4.2) con las tarifas del contador
(4.1), y el **documento** que trae el XML (Fase 3).

Es una **propuesta**: nada sale hacia Siigo hasta que él apruebe (4.5). Por eso
cada asiento nace con un estado —`completo` o `revisar`— y con los motivos
escritos en su idioma, no con un código de error.

## El asiento de una factura de compra

    Débito   cuenta del gasto (la que dice la regla)      subtotal
    Débito   IVA descontable                              IVA        (si aplica)
    Crédito  retención en la fuente                       lo retenido
    Crédito  ReteIVA                                      lo retenido
    Crédito  proveedores                                  el resto

El crédito a proveedores es **lo que queda**, no un dato aparte: así el asiento
cuadra por construcción y no por una suma que pueda salir mal.

## Las dos cuentas que Contab no puede saber

El pasivo con el proveedor y el IVA descontable son del PUC de cada empresa.
**No se ponen por defecto**: contabilizar un mes entero contra una cuenta que no
es la suya se descubre tarde y se deshace a mano. Si faltan, el asiento sale
marcado diciendo cuál.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from . import causacion as causacion_module
from . import documentos as documentos_module
from . import perfil_fiscal as perfil_module
from . import retenciones as retenciones_module
from . import terceros as terceros_module

ESTADO_COMPLETO = "completo"
ESTADO_REVISAR = "revisar"
CERO = Decimal("0")


@dataclass
class Linea:
    cuenta_puc: str | None
    descripcion: str
    debito: Decimal = CERO
    credito: Decimal = CERO


@dataclass
class Resumen:
    periodo: str = ""
    total: int = 0
    completos: int = 0
    revisar: int = 0
    sin_xml: int = 0
    avisos: list[str] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "periodo": self.periodo, "total": self.total,
            "completos": self.completos, "revisar": self.revisar,
            "sin_xml": self.sin_xml, "avisos": self.avisos[:20],
            # Lo que la pantalla del mes enseña: «412 documentos · 380 con regla
            # conocida [aprobar todos] · 32 nuevos [decidir]».
            "porcentaje_completo": (
                round(self.completos * 100 / self.total) if self.total else 0),
        }


def _d(v: Any) -> Decimal:
    if v in (None, ""):
        return CERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _pesos(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def generar(
    conn,
    periodo: str,
    *,
    progreso: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Rehace la propuesta del mes entero. Idempotente: se puede volver a correr.

    Lo ya **aprobado no se toca**: volver a generar después de que el contador
    aprobó media mañana de trabajo le borraría esa mañana.
    """
    avisa = progreso or (lambda _m: None)
    res = Resumen(periodo=periodo)

    info = dict(conn.execute("SELECT * FROM empresa_info").fetchone() or {})
    cuenta_proveedores = (info.get("cuenta_proveedores") or "").strip()
    cuenta_iva = (info.get("cuenta_iva_descontable") or "").strip()
    perfil = perfil_module.perfil_vigente(conn, fecha=f"{periodo}-01")

    if not cuenta_proveedores:
        res.avisos.append(
            "Falta decir a qué cuenta va el pasivo con el proveedor; sin ella el "
            "asiento no se puede cerrar.")
    if perfil is None:
        res.avisos.append(
            "Esta empresa no tiene perfil fiscal: no se calculan retenciones.")

    docs = documentos_module.documentos_del_periodo(conn, periodo)
    filas_del_mes = conn.execute(
        "SELECT COUNT(DISTINCT cufe_cude) FROM excel_row WHERE periodo = ?"
        " AND cufe_cude IS NOT NULL", (periodo,)).fetchone()[0]
    res.sin_xml = max(filas_del_mes - len(docs), 0)

    for i, cabecera in enumerate(docs, 1):
        avisa(f"Proponiendo {i} de {len(docs)}…")
        cufe = cabecera["cufe"]
        ya = conn.execute(
            "SELECT id, aprobado FROM asiento_propuesto WHERE periodo = ? AND cufe = ?",
            (periodo, cufe)).fetchone()
        if ya and ya["aprobado"]:
            res.total += 1
            res.completos += 1
            continue

        documento = documentos_module.documento_por_cufe(conn, cufe)
        if documento is None:
            continue
        res.total += 1

        propuesta = causacion_module.proponer(conn, documento)
        tercero = terceros_module.obtener(conn, documento.get("emisor_nit") or "")
        calculo = retenciones_module.calcular(
            conn, perfil=perfil, documento=documento, tercero=tercero,
            concepto_id=propuesta.concepto_retencion_id)

        lineas, avisos = _lineas_de(
            documento, propuesta, calculo,
            cuenta_proveedores=cuenta_proveedores, cuenta_iva=cuenta_iva,
            responsable_iva=bool(perfil and perfil.get("responsable_iva")))
        avisos = [*avisos, *calculo.avisos]
        if not propuesta.seguro:
            avisos.insert(0, propuesta.por_que)

        estado = (ESTADO_COMPLETO
                  if propuesta.seguro and not calculo.revisar and cuenta_proveedores
                  else ESTADO_REVISAR)
        if estado == ESTADO_COMPLETO:
            res.completos += 1
            if propuesta.regla_id:
                causacion_module.marcar_usada(conn, propuesta.regla_id)
        else:
            res.revisar += 1

        _escribir(conn, periodo, documento, estado, avisos, propuesta.regla_id,
                  lineas, asiento_id=(ya["id"] if ya else None))

    conn.commit()
    return res.como_dict()


def _lineas_de(
    documento: dict[str, Any],
    propuesta: causacion_module.Propuesta,
    calculo: retenciones_module.Calculo,
    *,
    cuenta_proveedores: str,
    cuenta_iva: str,
    responsable_iva: bool,
) -> tuple[list[Linea], list[str]]:
    avisos: list[str] = []
    subtotal = _pesos(_d(documento.get("subtotal")))
    iva = _pesos(_d(documento.get("total_impuestos")))
    total = _pesos(_d(documento.get("total")))

    lineas = [Linea(
        cuenta_puc=propuesta.cuenta_puc,
        descripcion=documento.get("emisor_nombre") or "Compra",
        debito=subtotal)]

    if iva > CERO and responsable_iva:
        if cuenta_iva:
            lineas.append(Linea(cuenta_iva, "IVA descontable", debito=iva))
        else:
            avisos.append(
                "Falta la cuenta del IVA descontable: el IVA de esta factura no "
                "quedó en ninguna línea.")

    retenido = CERO
    for r in calculo.retenciones:
        lineas.append(Linea(r.cuenta_puc, f"{r.concepto} ({r.tarifa}%)", credito=r.valor))
        retenido += r.valor

    # El crédito al proveedor es el resto: así cuadra por construcción.
    base_credito = total if total > CERO else subtotal + iva
    por_pagar = _pesos(base_credito - retenido)
    lineas.append(Linea(cuenta_proveedores or None, "Proveedores", credito=por_pagar))

    descuadre = sum(x.debito for x in lineas) - sum(x.credito for x in lineas)
    if descuadre != CERO:
        # Puede pasar si el XML no trae total, o si falta la cuenta del IVA.
        avisos.append(
            f"El asiento no cuadra por {descuadre} pesos; revísalo antes de aprobar.")
    return lineas, avisos


def _escribir(conn, periodo, documento, estado, avisos, regla_id, lineas,
              *, asiento_id: int | None) -> None:
    if asiento_id:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM asiento_propuesto WHERE id = ?", (asiento_id,))
    cur = conn.execute(
        "INSERT INTO asiento_propuesto(periodo, cufe, tercero_nit, fecha, estado,"
        " avisos, regla_id) VALUES (?,?,?,?,?,?,?)",
        (periodo, documento["cufe"], documento.get("emisor_nit"),
         documento.get("fecha_emision"), estado,
         json.dumps(avisos, ensure_ascii=False) if avisos else None, regla_id))
    aid = int(cur.lastrowid)
    for orden, ln in enumerate(lineas):
        conn.execute(
            "INSERT INTO asiento_linea(asiento_id, orden, cuenta_puc, descripcion,"
            " debito, credito) VALUES (?,?,?,?,?,?)",
            (aid, orden, ln.cuenta_puc, ln.descripcion, str(ln.debito), str(ln.credito)))


# ─────────────────────────────── lectura ───────────────────────────────────────

def listar(conn, periodo: str, *, estado: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM asiento_propuesto WHERE periodo = ?"
    args: list[Any] = [periodo]
    if estado:
        sql += " AND estado = ?"
        args.append(estado)
    sql += " ORDER BY fecha, id"
    salida = []
    for fila in conn.execute(sql, args).fetchall():
        a = dict(fila)
        a["avisos"] = json.loads(a["avisos"]) if a["avisos"] else []
        a["lineas"] = [dict(r) for r in conn.execute(
            "SELECT * FROM asiento_linea WHERE asiento_id = ? ORDER BY orden",
            (a["id"],)).fetchall()]
        salida.append(a)
    return salida


def resumen(conn, periodo: str) -> dict[str, Any]:
    fila = conn.execute(
        "SELECT COUNT(*) total,"
        " SUM(CASE WHEN estado = 'completo' THEN 1 ELSE 0 END) completos,"
        " SUM(CASE WHEN aprobado = 1 THEN 1 ELSE 0 END) aprobados"
        " FROM asiento_propuesto WHERE periodo = ?", (periodo,)).fetchone()
    total = fila["total"] or 0
    completos = fila["completos"] or 0
    return {
        "periodo": periodo, "total": total, "completos": completos,
        "revisar": total - completos, "aprobados": fila["aprobados"] or 0,
        "porcentaje_completo": round(completos * 100 / total) if total else 0,
    }
