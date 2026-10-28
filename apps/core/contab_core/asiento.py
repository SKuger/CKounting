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

## Lo que la empresa emite también se causa (D-127)

    Documento soporte a no obligados — una compra sin IVA, el receptor es el proveedor:
    Débito   cuenta del gasto                             total
    Crédito  retenciones                                  lo retenido
    Crédito  proveedores                                  el resto

    Factura de venta (y su nota crédito, en negativo) — el receptor es el cliente:
    Débito   clientes                                     total
    Crédito  cuenta del ingreso (la que dice la regla)    subtotal
    Crédito  IVA generado                                 IVA        (si aplica)

La nómina no se causa: el reporte no trae lo que hace falta para hacerlo bien.

## Las cuentas que Contab no puede saber

El pasivo con el proveedor, el IVA descontable, la cuenta por cobrar a clientes
y el IVA generado son del PUC de cada empresa. **No se ponen por defecto**:
contabilizar un mes entero contra una cuenta que no es la suya se descubre tarde
y se deshace a mano. Si faltan, el asiento sale marcado diciendo cuál.
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
from . import siigo as siigo_module
from . import terceros as terceros_module

ESTADO_COMPLETO = "completo"
ESTADO_REVISAR = "revisar"
CERO = Decimal("0")


# Qué es cada línea. El archivo de Siigo (D-128) necesita saberlo para poner el
# código de impuesto y la base gravable en las de IVA y retención, y el número
# de la factura con su vencimiento en la de cartera.
ROL_GASTO, ROL_INGRESO, ROL_IVA, ROL_RETENCION, ROL_CARTERA = (
    "gasto", "ingreso", "iva", "retencion", "cartera")


@dataclass
class Linea:
    cuenta_puc: str | None
    descripcion: str
    debito: Decimal = CERO
    credito: Decimal = CERO
    rol: str | None = None
    base: Decimal | None = None
    concepto_id: int | None = None
    codigo_siigo: str | None = None


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
            # Cuántos se propusieron sin XML: salen igual, pero sin detalle.
            "sin_xml": self.sin_xml, "avisos": self.avisos[:20],
            # Lo que la pantalla del mes enseña: «412 documentos · 380 con regla
            # conocida [aprobar todos] · 32 nuevos [decidir]».
            "porcentaje_completo": (
                round(self.completos * 100 / self.total) if self.total else 0),
        }


def _ya_lo_decidio(propuesta) -> bool:
    """¿Existe ya una regla que diga qué hacer con la retención de este proveedor?

    Si la hay, una persona ya miró. Seguir pidiendo revisión por no conocer sus
    responsabilidades haría que aprobar la primera factura no sirviera de nada.
    """
    return bool(propuesta.seguro
                and (propuesta.concepto_retencion_id or propuesta.sin_retencion))


def _d(v: Any) -> Decimal:
    if v in (None, ""):
        return CERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _pesos(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _cuenta_del_catalogo(catalogo, codigo: str | None, contexto: str) -> str | None:
    fila = catalogo.get(((codigo or "").strip(), contexto)) if codigo else None
    return (fila or {}).get("cuenta") or None


def _codigo_iva(conn, propuesta, iva: Decimal, base: Decimal) -> str | None:
    """El código de IVA de esta línea: el de la regla, o el de la tarifa."""
    if propuesta.iva_codigo:
        return propuesta.iva_codigo
    if not base:
        return None
    tarifa = (abs(iva) / abs(base) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (siigo_module.config(conn).get(f"iva:{tarifa}") or "").strip() or None


def _cuentas_de(info: dict[str, Any]) -> dict[str, str]:
    return {k: (info.get(k) or "").strip() for k in (
        "cuenta_proveedores", "cuenta_iva_descontable",
        "cuenta_clientes", "cuenta_iva_generado")}


def _calcular_retenciones(conn, *, perfil, documento, propuesta, tercero_decidido):
    """Las retenciones del documento, o ninguna si es una venta.

    En una venta la que retiene es la otra parte, al pagar; aquí no hay nada que
    calcular. En un documento soporte sí: es una compra a alguien que no factura,
    y lo que la factura «declara» del emisor es de la propia empresa, así que se
    mira solo el catálogo del receptor.
    """
    naturaleza = documento.get("naturaleza") or documentos_module.NATURALEZA_COMPRA
    if naturaleza == documentos_module.NATURALEZA_VENTA:
        return retenciones_module.Calculo()
    tercero = terceros_module.obtener(conn, documento.get("tercero_nit") or "")
    visto = documento
    if naturaleza == documentos_module.NATURALEZA_DOC_SOPORTE:
        visto = {**documento, "emisor_responsabilidades": None,
                 "subtotal": documento.get("total"), "total_impuestos": None}
    return retenciones_module.calcular(
        conn, perfil=perfil, documento=visto, tercero=tercero,
        concepto_id=propuesta.concepto_retencion_id,
        sin_retencion=propuesta.sin_retencion,
        tercero_decidido=tercero_decidido)


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

    cuentas = _cuentas_de(dict(conn.execute("SELECT * FROM empresa_info").fetchone() or {}))
    perfil = perfil_module.perfil_vigente(conn, fecha=f"{periodo}-01")
    catalogo = siigo_module.catalogo(conn)
    codigos_concepto = _codigos_concepto(conn)

    if not cuentas["cuenta_proveedores"]:
        res.avisos.append(
            "Falta decir a qué cuenta va el pasivo con el proveedor; sin ella el "
            "asiento no se puede cerrar.")
    if perfil is None:
        res.avisos.append(
            "Esta empresa no tiene perfil fiscal: no se calculan retenciones.")

    # Con XML si lo hay, y con lo que el Excel ya trae si no (D-104). Si solo se
    # miraran los que tienen XML, un mes sin XML no produciría ni una propuesta —
    # y los XML hay que bajarlos uno por uno del portal.
    docs = documentos_module.documentos_a_causar(conn, periodo)
    res.sin_xml = sum(1 for d in docs
                      if d.get("origen") == documentos_module.ORIGEN_EXCEL)

    for i, documento in enumerate(docs, 1):
        avisa(f"Proponiendo {i} de {len(docs)}…")
        cufe = documento["cufe"]
        ya = conn.execute(
            "SELECT id, aprobado FROM asiento_propuesto WHERE periodo = ? AND cufe = ?",
            (periodo, cufe)).fetchone()
        if ya and ya["aprobado"]:
            res.total += 1
            res.completos += 1
            continue

        res.total += 1

        propuesta = causacion_module.proponer(conn, documento)
        calculo = _calcular_retenciones(
            conn, perfil=perfil, documento=documento, propuesta=propuesta,
            tercero_decidido=_ya_lo_decidio(propuesta))

        lineas, avisos = _lineas_de(
            documento, propuesta, calculo, cuentas=cuentas,
            responsable_iva=bool(perfil and perfil.get("responsable_iva")),
            catalogo=catalogo, codigo_iva=_codigo_iva(
                conn, propuesta, _d(documento.get("total_impuestos")), _d(documento.get("subtotal"))),
            codigos_concepto=codigos_concepto)
        avisos = [*avisos, *calculo.avisos]
        if documento.get("origen") == documentos_module.ORIGEN_EXCEL:
            avisos.append(
                "Sin el XML de este documento: se propuso con el total y el IVA "
                "del reporte de la DIAN, sin el detalle por línea.")
        if not propuesta.seguro:
            avisos.insert(0, propuesta.por_que)

        contrapartida = cuentas["cuenta_clientes" if documento.get("naturaleza")
                                == documentos_module.NATURALEZA_VENTA
                                else "cuenta_proveedores"]
        estado = (ESTADO_COMPLETO
                  if propuesta.seguro and not calculo.revisar and contrapartida
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


def _codigos_concepto(conn) -> dict[int, str]:
    return {r["id"]: (r["codigo_siigo"] or "").strip()
            for r in conn.execute("SELECT id, codigo_siigo FROM retencion_concepto")}


def _lineas_de(
    documento: dict[str, Any],
    propuesta: causacion_module.Propuesta,
    calculo: retenciones_module.Calculo,
    *,
    cuentas: dict[str, str],
    responsable_iva: bool,
    catalogo: dict | None = None,
    codigo_iva: str | None = None,
    codigos_concepto: dict[int, str] | None = None,
) -> tuple[list[Linea], list[str]]:
    """Las líneas del asiento. Con el catálogo de Siigo cargado, la cuenta del
    IVA y de cada retención sale de él según el contexto —venta, compra o su
    devolución—; sin catálogo, de las cuentas de la empresa y del concepto."""
    avisos: list[str] = []
    catalogo = catalogo or {}
    codigos_concepto = codigos_concepto or {}
    naturaleza = documento.get("naturaleza") or documentos_module.NATURALEZA_COMPRA
    contexto = siigo_module.contexto_de(naturaleza, documento.get("tipo"))
    subtotal = _pesos(_d(documento.get("subtotal")))
    iva = _pesos(_d(documento.get("total_impuestos")))
    total = _pesos(_d(documento.get("total")))
    nombre = documento.get("tercero_nombre") or documento.get("emisor_nombre")

    if naturaleza == documentos_module.NATURALEZA_VENTA:
        # El cliente debe el total; el ingreso y el IVA generado son el haber.
        lineas = [Linea(cuentas["cuenta_clientes"] or None, "Clientes", debito=total, rol=ROL_CARTERA)]
        lineas.append(Linea(propuesta.cuenta_puc, nombre or "Venta", credito=subtotal, rol=ROL_INGRESO))
        if iva != CERO and responsable_iva:
            cuenta_iva = _cuenta_del_catalogo(catalogo, codigo_iva, contexto) or cuentas["cuenta_iva_generado"]
            if cuenta_iva:
                lineas.append(Linea(cuenta_iva, "IVA generado", credito=iva, rol=ROL_IVA,
                                    base=subtotal, codigo_siigo=codigo_iva))
            else:
                avisos.append(
                    "Falta la cuenta del IVA generado: el IVA de esta venta no "
                    "quedó en ninguna línea.")
    else:
        if naturaleza == documentos_module.NATURALEZA_DOC_SOPORTE:
            # Sin IVA: quien no está obligado a facturar no lo cobra. El gasto
            # es el total, y si el reporte trae IVA es para mirarlo.
            if iva != CERO:
                avisos.append(
                    f"Este documento soporte trae IVA por {iva} pesos; un no obligado "
                    "no lo cobra. Se causó el total como gasto.")
            subtotal, iva = (total if total != CERO else subtotal), CERO
        lineas = [Linea(propuesta.cuenta_puc, nombre or "Compra", debito=subtotal, rol=ROL_GASTO)]

        if iva > CERO and responsable_iva:
            cuenta_iva = _cuenta_del_catalogo(catalogo, codigo_iva, contexto) or cuentas["cuenta_iva_descontable"]
            if cuenta_iva:
                lineas.append(Linea(cuenta_iva, "IVA descontable", debito=iva, rol=ROL_IVA,
                                    base=subtotal, codigo_siigo=codigo_iva))
            else:
                avisos.append(
                    "Falta la cuenta del IVA descontable: el IVA de esta factura no "
                    "quedó en ninguna línea.")

        retenido = CERO
        for r in calculo.retenciones:
            codigo = codigos_concepto.get(r.concepto_id or 0) or None
            cuenta = _cuenta_del_catalogo(catalogo, codigo, contexto) or r.cuenta_puc
            lineas.append(Linea(cuenta, f"{r.concepto} ({r.tarifa}%)", credito=r.valor,
                                rol=ROL_RETENCION, base=r.base, concepto_id=r.concepto_id,
                                codigo_siigo=codigo))
            retenido += r.valor

        # El crédito al proveedor es el resto: así cuadra por construcción.
        base_credito = total if total > CERO else subtotal + iva
        por_pagar = _pesos(base_credito - retenido)
        lineas.append(Linea(cuentas["cuenta_proveedores"] or None, "Proveedores",
                            credito=por_pagar, rol=ROL_CARTERA))

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
        " avisos, regla_id, naturaleza, numero, tipo_doc) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (periodo, documento["cufe"],
         documento.get("tercero_nit") or documento.get("emisor_nit"),
         documento.get("fecha_emision"), estado,
         json.dumps(avisos, ensure_ascii=False) if avisos else None, regla_id,
         documento.get("naturaleza") or documentos_module.NATURALEZA_COMPRA,
         documento.get("numero"), documento.get("tipo")))
    _escribir_lineas(conn, int(cur.lastrowid), lineas)


def _escribir_lineas(conn, asiento_id: int, lineas: list[Linea]) -> None:
    for orden, ln in enumerate(lineas):
        conn.execute(
            "INSERT INTO asiento_linea(asiento_id, orden, cuenta_puc, descripcion,"
            " debito, credito, rol, base, concepto_id, codigo_siigo) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (asiento_id, orden, ln.cuenta_puc, ln.descripcion, str(ln.debito), str(ln.credito),
             ln.rol, str(ln.base) if ln.base is not None else None, ln.concepto_id, ln.codigo_siigo))


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


# ─────────────────────── aprobar, que es donde se aprende ──────────────────────
# Lo pidió así el contador el 2026-10-22:
#
# > «Para el primer registro de una factura de un proveedor me muestras en
# > pantalla cómo sería el registro, yo lo valido y en caso de un cambio lo pueda
# > realizar yo; y como por lo general el concepto que factura el proveedor es el
# > mismo, las siguientes facturas se registrarían de esa forma.»
#
# Así que aprobar no es marcar una casilla: es **enseñarle a Contab** lo que
# acaba de decidir, para no volvérselo a preguntar.

def aprobar(
    conn,
    asiento_id: int,
    *,
    cuenta_puc: str | None = None,
    patron: str | None = None,
    concepto_retencion_id: int | None = None,
    cuenta_proveedores: str | None = None,
    cuenta_iva_descontable: str | None = None,
    cuenta_clientes: str | None = None,
    cuenta_iva_generado: str | None = None,
    sin_retencion: bool = False,
    aprender_regla: bool = True,
    iva_codigo: str | None = None,
) -> dict[str, Any]:
    """Da por bueno un asiento, con las correcciones que él haya hecho.

    Lo que corrija se guarda **para esta empresa**: las cuentas viven en su
    propia base (D-003), así que «las cuentas pueden variar por cada empresa»
    sale gratis — no hay una tabla común que pudiera mezclarlas.
    """
    fila = conn.execute(
        "SELECT * FROM asiento_propuesto WHERE id = ?", (int(asiento_id),)).fetchone()
    if fila is None:
        raise ValueError(f"El asiento {asiento_id} no existe.")
    a = dict(fila)

    # Las cuentas de la empresa, si las acaba de escribir en esta pantalla.
    nuevas = {"cuenta_proveedores": cuenta_proveedores,
              "cuenta_iva_descontable": cuenta_iva_descontable,
              "cuenta_clientes": cuenta_clientes,
              "cuenta_iva_generado": cuenta_iva_generado}
    if any(nuevas.values()):
        actual = dict(conn.execute("SELECT * FROM empresa_info").fetchone() or {})
        conn.execute(
            "UPDATE empresa_info SET cuenta_proveedores = ?, cuenta_iva_descontable = ?,"
            " cuenta_clientes = ?, cuenta_iva_generado = ?",
            tuple((nuevas[k] or actual.get(k) or "").strip() or None for k in nuevas))

    es_venta = (a.get("naturaleza") or "compra") == documentos_module.NATURALEZA_VENTA
    # La regla, para que la próxima factura de este tercero salga sola.
    if aprender_regla and cuenta_puc and a.get("tercero_nit"):
        causacion_module.aprender(
            conn, cuenta_puc=cuenta_puc, tercero_nit=a["tercero_nit"],
            patron=(patron or "").strip() or None,
            concepto_retencion_id=None if es_venta else concepto_retencion_id,
            # «A este proveedor no se le retiene», dicho por él. Va a la regla
            # para que las siguientes facturas no vuelvan a preguntarlo.
            sin_retencion=sin_retencion and not es_venta,
            naturaleza=a.get("naturaleza") or documentos_module.NATURALEZA_COMPRA,
            iva_codigo=iva_codigo)

    # Se rehace el asiento con lo corregido y se marca aprobado.
    # El documento puede venir del XML o del Excel: `aprobar` tiene que mirar en
    # los dos sitios. Buscándolo solo por XML, en un mes sin XML la corrección
    # del contador no se aplicaba a ninguna línea — y él la veía ignorada.
    documento = next(
        (d for d in documentos_module.documentos_a_causar(conn, a["periodo"])
         if d["cufe"] == a["cufe"]), None)
    if documento is not None:
        info = dict(conn.execute("SELECT * FROM empresa_info").fetchone() or {})
        perfil = perfil_module.perfil_vigente(conn, fecha=f"{a['periodo']}-01")
        propuesta = causacion_module.proponer(conn, documento)
        if cuenta_puc:
            propuesta.cuenta_puc = cuenta_puc
            propuesta.seguro = True
        if concepto_retencion_id:
            propuesta.concepto_retencion_id = concepto_retencion_id
            propuesta.sin_retencion = False
        elif sin_retencion:
            propuesta.sin_retencion = True
        if (iva_codigo or "").strip():
            propuesta.iva_codigo = iva_codigo.strip()
        calculo = _calcular_retenciones(
            conn, perfil=perfil, documento=documento, propuesta=propuesta,
            tercero_decidido=True)   # la está aprobando una persona
        lineas, avisos = _lineas_de(
            documento, propuesta, calculo, cuentas=_cuentas_de(info),
            responsable_iva=bool(perfil and perfil.get("responsable_iva")),
            catalogo=siigo_module.catalogo(conn),
            codigo_iva=_codigo_iva(conn, propuesta, _d(documento.get("total_impuestos")),
                                   _d(documento.get("subtotal"))),
            codigos_concepto=_codigos_concepto(conn))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM asiento_linea WHERE asiento_id = ?", (a["id"],))
        _escribir_lineas(conn, a["id"], lineas)
        conn.execute(
            "UPDATE asiento_propuesto SET avisos = ? WHERE id = ?",
            (json.dumps(avisos, ensure_ascii=False) if avisos else None, a["id"]))

    conn.execute(
        "UPDATE asiento_propuesto SET aprobado = 1, estado = ?,"
        " aprobado_at = datetime('now') WHERE id = ?", (ESTADO_COMPLETO, a["id"]))
    conn.commit()
    return listar_uno(conn, a["id"])


def aprobar_lote(conn, periodo: str) -> dict[str, Any]:
    """Aprueba de un golpe lo que ya estaba completo. Lo marcado NO se toca."""
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM asiento_propuesto WHERE periodo = ? AND estado = ?"
        " AND aprobado = 0", (periodo, ESTADO_COMPLETO)).fetchall()]
    for i in ids:
        conn.execute(
            "UPDATE asiento_propuesto SET aprobado = 1, aprobado_at = datetime('now')"
            " WHERE id = ?", (i,))
    conn.commit()
    return {"aprobados": len(ids), **resumen(conn, periodo)}


def desaprobar(conn, asiento_id: int) -> dict[str, Any]:
    """Volver atrás. Aprobar por error no puede ser irreversible."""
    conn.execute(
        "UPDATE asiento_propuesto SET aprobado = 0, aprobado_at = NULL WHERE id = ?",
        (int(asiento_id),))
    conn.commit()
    return listar_uno(conn, asiento_id)


def listar_uno(conn, asiento_id: int) -> dict[str, Any]:
    fila = conn.execute(
        "SELECT * FROM asiento_propuesto WHERE id = ?", (int(asiento_id),)).fetchone()
    if fila is None:
        raise ValueError(f"El asiento {asiento_id} no existe.")
    a = dict(fila)
    a["avisos"] = json.loads(a["avisos"]) if a["avisos"] else []
    a["lineas"] = [dict(r) for r in conn.execute(
        "SELECT * FROM asiento_linea WHERE asiento_id = ? ORDER BY orden",
        (a["id"],)).fetchall()]
    return a
