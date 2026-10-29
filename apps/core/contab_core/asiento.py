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

    Factura de venta — el receptor es el cliente:
    Débito   clientes                                     total
    Crédito  cuenta del ingreso (la que dice la regla)    subtotal
    Crédito  IVA generado                                 IVA        (si aplica)

La nota crédito llega en negativo, pero se asienta en las mismas cuentas y al
lado contrario, con valores positivos (el contador, 2026-10-29).

La nómina no se causa: el reporte no trae lo que hace falta para hacerlo bien.

## Las cuentas que Contab no puede saber

El pasivo con el proveedor, el IVA descontable, la cuenta por cobrar a clientes
y el IVA generado son del PUC de cada empresa. **No se ponen por defecto**:
contabilizar un mes entero contra una cuenta que no es la suya se descubre tarde
y se deshace a mano. Si faltan, el asiento sale marcado diciendo cuál.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from . import causacion as causacion_module
from . import documentos as documentos_module
from . import pdf_impuestos
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
# La parte de un documento que no lleva IVA, cuando la otra sí: va a su propia
# cuenta (lo pidió el contador el 2026-10-28, con las facturas de D1).
ROL_NO_GRAVADO = "no_gravado"
ROLES = (ROL_GASTO, ROL_INGRESO, ROL_IVA, ROL_RETENCION, ROL_CARTERA, ROL_NO_GRAVADO)

# Lo más común es una vigencia que empieza después del mes que se causa.
_SIN_PERFIL = ("No hay perfil fiscal vigente para este mes: se puso el IVA que reporta la "
               "DIAN. Revisa el perfil de la empresa; si su vigencia empieza después de este "
               "mes, adelántala.")


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
    # None = el tercero del asiento. Otro NIT cuando la cartera es de otro: la
    # factura la emite uno y se le debe a otro (el contador, 2026-10-28).
    tercero_nit: str | None = None


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


def _centavos(v: Decimal) -> Decimal:
    """Los valores del documento van como los trae, con centavos: así los
    registra el contador (9 de 16 líneas de IVA de sus compras de septiembre)."""
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _plata(v: Decimal) -> str:
    """2388.3 → «2.388,30»; 500000 → «500.000». Como se lee en Colombia."""
    q = _centavos(v)
    entero = int(abs(q))
    centavos = int((abs(q) - entero) * 100)
    texto = f"{entero:,}".replace(",", ".") + (f",{centavos:02d}" if centavos else "")
    return ("-" if q < 0 else "") + texto


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


NINGUNA = "ninguna"
CENTAVO = Decimal("0.01")


def _tarifa_txt(t: Decimal) -> str:
    """19.00 → «19»; 2.5 → «2.5». Es la llave de `iva:<tarifa>` en la config."""
    return format(t.normalize(), "f") if t != t.to_integral() else str(int(t))


@dataclass
class Desglose:
    """El IVA de un documento por tarifa, y lo que no es IVA (el impuesto al consumo).

    Solo lo trae el XML. El reporte de la DIAN da un IVA total sin tarifa, y
    con eso no se puede partir: el asiento sale con una sola línea de IVA y la
    tarifa se deduce de dividir IVA entre base.
    """
    ivas: list[tuple[str, Decimal, Decimal]]   # (tarifa, base, valor), solo las que tienen IVA
    base_gravada: Decimal
    otros: Decimal                             # INC y demás: no es IVA descontable

    @property
    def iva(self) -> Decimal:
        return sum((v for _t, _b, v in self.ivas), CERO)


def desglose_de(documento: dict[str, Any]) -> Desglose | None:
    por_tarifa: dict[str, list[Decimal]] = {}
    otros = CERO
    for imp in documento.get("impuestos") or []:
        if imp.get("es_retencion"):
            continue
        tipo = str(imp.get("tipo") or "").strip()
        valor = _d(imp.get("valor"))
        if tipo == "01":
            if imp.get("tarifa") in (None, ""):
                return None
            acc = por_tarifa.setdefault(_tarifa_txt(_d(imp["tarifa"])), [CERO, CERO])
            acc[0] += _d(imp.get("base"))
            acc[1] += valor
        elif tipo == "00":
            return None       # un total sin desglose: no se sabe qué es
        else:
            otros += valor
    if not por_tarifa and otros == CERO:
        return None
    ivas = [(t, _centavos(b), _centavos(v)) for t, (b, v) in sorted(
        por_tarifa.items(), key=lambda kv: -_d(kv[0])) if v != CERO]
    return Desglose(ivas=ivas, base_gravada=sum((b for _t, b, _v in ivas), CERO),
                    otros=_centavos(otros))


def config_iva(conn) -> dict[str, Any]:
    """Qué código de Siigo lleva cada tarifa, y qué tarifa tiene cada código."""
    cfg = siigo_module.config(conn)
    return {
        "por_tarifa": {k[4:]: (v or "").strip() for k, v in cfg.items()
                       if k.startswith("iva:") and (v or "").strip()},
        "tarifa_de": {i["codigo"]: _tarifa_txt(_d(i["tarifa"]))
                      for i in siigo_module.ivas_disponibles(conn) if i.get("tarifa")},
    }


def _codigo_de_tarifa(cfg: dict[str, Any], propuesta, tarifa: str, unica: bool) -> str | None:
    """El código de la regla si es de esa tarifa (bienes o servicios lo decide
    él); si no, el que la empresa tiene para la tarifa."""
    elegido = (propuesta.iva_codigo or "").strip()
    if elegido:
        suya = cfg["tarifa_de"].get(elegido)
        if suya == tarifa or (suya is None and unica):
            return elegido
    return cfg["por_tarifa"].get(tarifa) or None


def _lo_que_me_retienen(catalogo, codigos: str | None, subtotal: Decimal, iva: Decimal,
                        contexto: str) -> tuple[list[Linea], list[str]]:
    """En una venta, las retenciones que el cliente le practica a la empresa.

    Van al débito (son un anticipo de impuestos, cuentas 1355) y la cartera
    queda por el neto. La tarifa sale del catálogo de Siigo: retefuente sobre
    la base, ReteIVA sobre el IVA, y ReteICA **en por mil** sobre la base —así
    la trae el catálogo y así salen sus ventas, 2 por mil en 78 de 86 (D-131)—.
    Con centavos, como en su archivo.

    Un código puede llevar la tarifa del cliente cuando no es la del catálogo:
    «05:1.8» es ReteICA al 1,8 por mil. Pasa con el ICA de otros municipios.
    """
    if codigos is None:
        return [], ["No se sabe qué le retiene este cliente: la cartera quedó por el total. "
                    "Elíjalo al aprobar y se recordará."]
    if codigos.strip().lower() == NINGUNA:
        return [], []
    lineas, avisos = [], []
    for item in [c.strip() for c in codigos.split(",") if c.strip()]:
        codigo, _, propia = item.partition(":")
        fila = catalogo.get((codigo, contexto))
        if not fila:
            avisos.append(f"El código {codigo} no está en el catálogo de Siigo para {contexto}.")
            continue
        tarifa = _d(propia) if propia else _d(fila.get("tarifa"))
        tipo = fila.get("tipo")
        if tipo == "reteiva":
            base, valor = iva, iva * tarifa / 100
        elif tipo == "reteica":
            base, valor = subtotal, subtotal * tarifa / 1000
        elif tipo == "retefuente":
            base, valor = subtotal, subtotal * tarifa / 100
        else:
            continue
        if not base:
            continue
        lineas.append(Linea(fila.get("cuenta"), f"{fila.get('nombre') or codigo} (le retiene el cliente)",
                            debito=valor.quantize(CENTAVO, rounding=ROUND_HALF_UP),
                            rol=ROL_RETENCION, base=base, codigo_siigo=codigo))
    return lineas, avisos


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
    partes = desglose_de(documento)
    if partes is not None and partes.otros != CERO:
        # El ReteIVA es sobre el IVA; el impuesto al consumo no entra.
        visto = {**documento, "total_impuestos": str(partes.iva) if partes.iva else None}
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

    ctx = _contexto(conn, periodo)
    cuentas, perfil = ctx["cuentas"], ctx["perfil"]

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
            "SELECT id, aprobado, editado, estado FROM asiento_propuesto"
            " WHERE periodo = ? AND cufe = ?", (periodo, cufe)).fetchone()
        res.total += 1
        # Lo aprobado y lo que él guardó a mano no se rehace: sería borrarle el trabajo.
        if ya and (ya["aprobado"] or ya["editado"]):
            # Lo aprobado en una versión vieja no tenía número ni tipo: sin el
            # número, el archivo de Siigo salía sin la factura en la cartera.
            conn.execute(
                "UPDATE asiento_propuesto SET numero = COALESCE(numero, ?),"
                " tipo_doc = COALESCE(tipo_doc, ?) WHERE id = ?",
                (documento.get("numero"), documento.get("tipo"), ya["id"]))
            if ya["aprobado"] or ya["estado"] == ESTADO_COMPLETO:
                res.completos += 1
            else:
                res.revisar += 1
            continue

        propuesta = causacion_module.proponer(conn, documento)
        lineas, avisos, estado = _armar(conn, ctx, documento, propuesta, tercero_decidido=None)
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


TARIFAS_IVA = (Decimal("19"), Decimal("5"))


def _deducir_tarifa(subtotal: Decimal, iva: Decimal) -> list[tuple[Decimal, Decimal, Decimal]] | None:
    """Sin XML ni PDF legible: si el IVA es el 19 % exacto de una parte del
    subtotal, esa parte es la gravada y el resto no lleva IVA. Así salió la
    compra de 125.700 con IVA de 2.388,30 que el contador registró con base
    12.570. El 5 % no se intenta: con centavos casi cualquier IVA lo «es»."""
    t = Decimal("19")
    base = _centavos(abs(iva) * 100 / t)
    if base != base.to_integral() or base >= abs(subtotal):
        return None
    if _centavos(base * t / 100) != abs(iva):
        return None
    return [(t, base, abs(iva))]


def _con_tarifas(conn, ctx, documento) -> tuple[dict[str, Any], str | None]:
    """El documento con su IVA por tarifa, cuando el reporte no lo trae.

    Primero el XML (ya lo trae); si no, la tabla de impuestos del PDF, verificada
    contra el reporte; si no, una tarifa parcial deducida. Si el IVA es el 19 o
    el 5 % del subtotal entero no hay nada que buscar."""
    if desglose_de(documento) is not None:
        return documento, None
    if (documento.get("naturaleza") or "compra") == documentos_module.NATURALEZA_DOC_SOPORTE:
        return documento, None
    subtotal, iva = _d(documento.get("subtotal")), _d(documento.get("total_impuestos"))
    if iva == CERO or subtotal == CERO:
        return documento, None
    tasa = abs(iva) / abs(subtotal) * 100
    if any(abs(tasa - t) < Decimal("0.05") for t in TARIFAS_IVA):
        return documento, None
    cache = ctx.setdefault("pdf_tarifas", {})
    if documento["cufe"] not in cache:
        cache[documento["cufe"]] = pdf_impuestos.desglose_del_pdf(
            conn, documento["cufe"], subtotal=subtotal, iva=iva, clave=ctx.get("nit"))
    filas, de_donde = cache[documento["cufe"]], "del PDF de la factura"
    if not filas:
        filas, de_donde = _deducir_tarifa(subtotal, iva), "de dividir el IVA entre el 19 %"
    if not filas:
        return documento, (
            f"El IVA ({_plata(iva)}) no es el 19 % ni el 5 % del subtotal y no se pudo leer "
            "la tarifa: puede traer varias tarifas o una parte sin IVA. Repártelo en las líneas.")
    signo = -1 if iva < CERO else 1
    impuestos = [{"tipo": "01", "nombre": "IVA", "base": str(b * signo), "tarifa": str(t),
                  "valor": str(v * signo), "es_retencion": False} for t, b, v in filas]
    tarifas = ", ".join(f"{_tarifa_txt(t)} %" for t, _b, v in filas if v)
    return ({**documento, "impuestos": impuestos},
            f"Las tarifas de IVA ({tarifas}) salieron {de_donde}; revísalas.")


def _contexto(conn, periodo: str) -> dict[str, Any]:
    """Lo que no cambia de un documento a otro del mes: se lee una vez."""
    return {
        "cuentas": _cuentas_de(dict(conn.execute("SELECT * FROM empresa_info").fetchone() or {})),
        "perfil": perfil_module.perfil_vigente(conn, fecha=f"{periodo}-01"),
        "catalogo": siigo_module.catalogo(conn),
        "codigos_concepto": _codigos_concepto(conn),
        "iva": config_iva(conn),
        "nit": (dict(conn.execute("SELECT nit FROM empresa_info").fetchone() or {}).get("nit") or ""),
    }


def _armar(conn, ctx, documento, propuesta, *, tercero_decidido: bool | None):
    """Las líneas, los avisos y el estado de un documento con esta propuesta."""
    perfil, cuentas, catalogo = ctx["perfil"], ctx["cuentas"], ctx["catalogo"]
    documento, aviso_tarifa = _con_tarifas(conn, ctx, documento)
    calculo = _calcular_retenciones(
        conn, perfil=perfil, documento=documento, propuesta=propuesta,
        tercero_decidido=(_ya_lo_decidio(propuesta) if tercero_decidido is None
                          else tercero_decidido))
    lineas, avisos = _lineas_de(
        documento, propuesta, calculo, cuentas=cuentas,
        responsable_iva=bool(perfil.get("responsable_iva")) if perfil else None,
        catalogo=catalogo, codigo_iva=_codigo_iva(
            conn, propuesta, _d(documento.get("total_impuestos")), _d(documento.get("subtotal"))),
        codigos_concepto=ctx["codigos_concepto"], iva_cfg=ctx["iva"])
    avisos = [*avisos, *calculo.avisos]
    if documento.get("origen") == documentos_module.ORIGEN_EXCEL:
        avisos.append(
            "Sin el XML de este documento: se propuso con el total y el IVA "
            "del reporte de la DIAN, sin el detalle por línea ni por tarifa.")
    if aviso_tarifa:
        avisos.append(aviso_tarifa)
    if not propuesta.seguro:
        avisos.insert(0, propuesta.por_que)

    es_venta = documento.get("naturaleza") == documentos_module.NATURALEZA_VENTA
    contrapartida = cuentas["cuenta_clientes" if es_venta else "cuenta_proveedores"]
    # Con el catálogo cargado, una venta de un cliente del que no se sabe qué
    # retiene no se aprueba en lote: la cartera saldría por el total.
    no_se_sabe = bool(es_venta and catalogo and propuesta.retenciones_cliente is None)
    sin_cuenta = any(not ln.cuenta_puc for ln in lineas)
    sin_iva = any(ln.rol == ROL_NO_GRAVADO for ln in lineas)
    # Los valores repartidos se sugieren, pero los aprueba él (el contador,
    # 2026-10-29): un asiento repartido no entra en el lote.
    repartido = bool(propuesta.reparto)
    iva_sin_perfil = perfil is None and any(ln.rol == ROL_IVA for ln in lineas)
    estado = (ESTADO_COMPLETO
              if (propuesta.seguro and not calculo.revisar and contrapartida
                  and not no_se_sabe and not sin_cuenta and not sin_iva and not repartido
                  and not iva_sin_perfil)
              else ESTADO_REVISAR)
    return lineas, avisos, estado


def _codigos_concepto(conn) -> dict[int, str]:
    return {r["id"]: (r["codigo_siigo"] or "").strip()
            for r in conn.execute("SELECT id, codigo_siigo FROM retencion_concepto")}


def _repartir(monto: Decimal, reparto) -> list[tuple[str, Decimal]]:
    """El monto por las partes del reparto, al centavo; la última se lleva el
    redondeo para que la suma dé exacta."""
    salida, puesto = [], CERO
    for i, (cuenta, parte) in enumerate(reparto):
        valor = monto - puesto if i == len(reparto) - 1 else _centavos(monto * parte)
        salida.append((cuenta, valor))
        puesto += valor
    return salida


def _es_principal(ln: Linea) -> bool:
    """¿Es una línea del gasto o del ingreso, de las que se reparten?

    Las que él agrega a mano no tienen rol; el impuesto al consumo va a la
    cuenta del gasto pero no es parte del reparto."""
    if ln.rol not in (ROL_GASTO, ROL_INGRESO, None):
        return False
    descripcion = ln.descripcion or ""
    return not (descripcion.startswith("Impuesto al consumo") or "mayor valor" in descripcion)


def reparto_de(lineas: list[Linea], naturaleza: str | None) -> list[tuple[str, Decimal]]:
    """Cómo quedó repartido el gasto o el ingreso en este asiento, por cuenta.

    Una sola cuenta da []: no hay plantilla que guardar, y la que hubiera se borra."""
    es_venta = naturaleza == documentos_module.NATURALEZA_VENTA
    por_cuenta: dict[str, Decimal] = {}
    for ln in lineas:
        if not _es_principal(ln) or not ln.cuenta_puc:
            continue
        valor = (ln.credito - ln.debito) if es_venta else (ln.debito - ln.credito)
        if valor != CERO:
            por_cuenta[ln.cuenta_puc] = por_cuenta.get(ln.cuenta_puc, CERO) + valor
    total = sum(por_cuenta.values(), CERO)
    # Signos mezclados (un anticipo que resta, por ejemplo) no son un reparto.
    if len(por_cuenta) < 2 or total == CERO or any(v * total < 0 for v in por_cuenta.values()):
        return []
    filas = list(por_cuenta.items())
    partes = [(c, (v / total).quantize(Decimal("0.000001"))) for c, v in filas[:-1]]
    return [*partes, (filas[-1][0], Decimal(1) - sum((p for _c, p in partes), CERO))]


def _lineas_de(
    documento: dict[str, Any],
    propuesta: causacion_module.Propuesta,
    calculo: retenciones_module.Calculo,
    *,
    cuentas: dict[str, str],
    responsable_iva: bool | None,
    catalogo: dict | None = None,
    codigo_iva: str | None = None,
    codigos_concepto: dict[int, str] | None = None,
    iva_cfg: dict[str, Any] | None = None,
) -> tuple[list[Linea], list[str]]:
    """Las líneas del asiento. Con el catálogo de Siigo cargado, la cuenta del
    IVA y de cada retención sale de él según el contexto —venta, compra o su
    devolución—; sin catálogo, de las cuentas de la empresa y del concepto."""
    avisos: list[str] = []
    catalogo = catalogo or {}
    codigos_concepto = codigos_concepto or {}
    naturaleza = documento.get("naturaleza") or documentos_module.NATURALEZA_COMPRA
    contexto = siigo_module.contexto_de(naturaleza, documento.get("tipo"))
    subtotal = _centavos(_d(documento.get("subtotal")))
    iva = _centavos(_d(documento.get("total_impuestos")))
    total = _centavos(_d(documento.get("total")))
    nombre = documento.get("tercero_nombre") or documento.get("emisor_nombre")
    iva_cfg = iva_cfg or {"por_tarifa": {}, "tarifa_de": {}}

    # El IVA por tarifa, si el XML lo trae: una línea por tarifa con su código
    # y su cuenta, y la parte sin IVA aparte (D1: 19 %, 5 % y excluidos en la
    # misma factura). Sin desglose, una sola línea como antes.
    partes = desglose_de(documento) if naturaleza != documentos_module.NATURALEZA_DOC_SOPORTE else None
    otros = CERO
    if partes is not None:
        unica = len(partes.ivas) == 1
        tramos = [(t, b, v, _codigo_de_tarifa(iva_cfg, propuesta, t, unica)) for t, b, v in partes.ivas]
        iva, otros = partes.iva, partes.otros
        no_gravado = subtotal - partes.base_gravada if partes.ivas and responsable_iva else CERO
        if abs(no_gravado) < Decimal("1"):
            no_gravado = CERO
    else:
        tramos = [(None, subtotal, iva, codigo_iva)] if iva != CERO else []
        no_gravado = CERO

    def lineas_de_iva(lado: str, etiqueta: str, respaldo: str) -> list[Linea]:
        salida = []
        for t, b, v, codigo in tramos:
            cuenta = _cuenta_del_catalogo(catalogo, codigo, contexto) or respaldo or None
            if not cuenta:
                avisos.append(f"Falta la cuenta del {etiqueta}"
                              + (f" al {t} %" if t else "") + ": elíjala en la línea.")
            ln = Linea(cuenta, etiqueta + (f" {t}%" if t and len(tramos) > 1 else ""),
                       rol=ROL_IVA, base=b, codigo_siigo=codigo)
            setattr(ln, lado, v)
            salida.append(ln)
        return salida

    # Sin IVA en todo el documento, el gasto o el ingreso es base exenta en el
    # libro de compras y ventas de Siigo: es lo que lleva la declaración de IVA
    # (el contador, 2026-10-29). La línea lleva la marca y el exportador escribe
    # su valor. El documento soporte no: viene de un no obligado.
    todo_sin_iva = (responsable_iva and not tramos and iva == CERO
                    and naturaleza != documentos_module.NATURALEZA_DOC_SOPORTE)

    def principales(cuenta: str | None, etiqueta: str, lado: str, monto: Decimal,
                    rol: str) -> list[Linea]:
        """El gasto o el ingreso: en una línea, o repartido como la última vez."""
        partes = _repartir(monto, propuesta.reparto) if propuesta.reparto and monto != CERO \
            else [(cuenta, monto)]
        if len(partes) > 1:
            avisos.append(
                "Se repartió como la última vez: "
                + ", ".join(f"{_tarifa_txt((p * 100).quantize(Decimal('0.1')))} % a {c}" for c, p in propuesta.reparto)
                + ". Revisa los valores antes de aprobar.")
        salida = []
        for c, valor in partes:
            ln = Linea(c, etiqueta, rol=rol, base=valor if todo_sin_iva else None)
            setattr(ln, lado, valor)
            salida.append(ln)
        return salida

    def la_parte_sin_iva(lado: str) -> list[Linea]:
        if no_gravado == CERO:
            return []
        # Depende de la factura (el contador, 2026-10-29): la cuenta de la vez
        # anterior se propone, pero el asiento queda para que él la mire.
        if propuesta.cuenta_no_gravada:
            avisos.append(
                f"{_plata(no_gravado)} pesos de este documento no llevan IVA. Se propuso la cuenta "
                "de la última vez; revísala, porque depende de la factura.")
        else:
            avisos.append(
                f"{_plata(no_gravado)} pesos de este documento no llevan IVA y van a su propia "
                "cuenta: escríbela en la línea «Parte no gravada».")
        ln = Linea(propuesta.cuenta_no_gravada, "Parte no gravada", rol=ROL_NO_GRAVADO,
                   base=no_gravado)
        setattr(ln, lado, no_gravado)
        return [ln]

    if naturaleza == documentos_module.NATURALEZA_VENTA:
        # El cliente debe el total menos lo que retiene; el ingreso y el IVA
        # generado son el haber.
        cartera = Linea(cuentas["cuenta_clientes"] or None, "Clientes", debito=total, rol=ROL_CARTERA)
        lineas = [cartera]
        lineas.extend(principales(propuesta.cuenta_puc, nombre or "Venta", "credito",
                                  subtotal - no_gravado, ROL_INGRESO))
        lineas.extend(la_parte_sin_iva("credito"))
        # El IVA que reporta la DIAN va siempre (el contador, 2026-10-29): sin
        # él la venta no cuadra. Si el perfil no lo espera, se dice.
        if iva != CERO:
            lineas.extend(lineas_de_iva("credito", "IVA generado", cuentas["cuenta_iva_generado"]))
            if responsable_iva is None:
                avisos.append(_SIN_PERFIL)
            elif not responsable_iva:
                avisos.append(
                    "El perfil fiscal dice que la empresa no es responsable de IVA, pero esta "
                    "venta trae IVA: revisa el perfil o la factura.")
        if otros != CERO:
            avisos.append(f"Esta venta trae {otros} pesos de impuesto al consumo: elija su cuenta.")
            lineas.append(Linea(None, "Impuesto al consumo", credito=otros))
        if catalogo:
            retenidas, avisos_ret = _lo_que_me_retienen(
                catalogo, propuesta.retenciones_cliente, subtotal, iva, contexto)
            lineas.extend(retenidas)
            avisos.extend(avisos_ret)
            cartera.debito = total - sum((x.debito for x in retenidas), CERO)
    else:
        if naturaleza == documentos_module.NATURALEZA_DOC_SOPORTE:
            # Sin IVA: quien no está obligado a facturar no lo cobra. El gasto
            # es el total, y si el reporte trae IVA es para mirarlo.
            if iva != CERO:
                avisos.append(
                    f"Este documento soporte trae IVA por {iva} pesos; un no obligado "
                    "no lo cobra. Se causó el total como gasto.")
            subtotal, iva = (total if total != CERO else subtotal), CERO
            tramos = []
        lineas = principales(propuesta.cuenta_puc, nombre or "Compra", "debito",
                             subtotal - no_gravado, ROL_GASTO)
        lineas.extend(la_parte_sin_iva("debito"))
        if otros != CERO:
            # El impuesto al consumo no se descuenta: es mayor valor del gasto.
            lineas.append(Linea(propuesta.cuenta_puc, "Impuesto al consumo (mayor valor del gasto)",
                                debito=otros, rol=ROL_GASTO))

        if iva != CERO and responsable_iva is False:
            # Quien no es responsable no descuenta el IVA: es mayor valor del gasto.
            lineas.append(Linea(propuesta.cuenta_puc, "IVA (mayor valor del gasto)",
                                debito=iva, rol=ROL_GASTO))
        elif iva != CERO:
            lineas.extend(lineas_de_iva("debito", "IVA descontable", cuentas["cuenta_iva_descontable"]))
            if responsable_iva is None:
                avisos.append(_SIN_PERFIL)

        retenido = CERO
        for r in calculo.retenciones:
            codigo = codigos_concepto.get(r.concepto_id or 0) or None
            cuenta = _cuenta_del_catalogo(catalogo, codigo, contexto) or r.cuenta_puc
            lineas.append(Linea(cuenta, f"{r.concepto} ({r.tarifa}%)", credito=r.valor,
                                rol=ROL_RETENCION, base=r.base, concepto_id=r.concepto_id,
                                codigo_siigo=codigo))
            retenido += r.valor

        # El crédito al proveedor es el resto: así cuadra por construcción.
        base_credito = total if total > CERO else subtotal + iva + otros
        por_pagar = _centavos(base_credito - retenido)
        lineas.append(Linea(cuentas["cuenta_proveedores"] or None, "Proveedores",
                            credito=por_pagar, rol=ROL_CARTERA))

    _sin_negativos(lineas)
    descuadre = sum(x.debito for x in lineas) - sum(x.credito for x in lineas)
    if descuadre != CERO:
        # Puede pasar si el XML no trae total, o si falta la cuenta del IVA.
        avisos.append(
            f"El asiento no cuadra por {descuadre} pesos; revísalo antes de aprobar.")
    return lineas, avisos


def _sin_negativos(lineas: list[Linea]) -> None:
    """Un valor negativo pasa a la columna contraria, en positivo.

    La nota crédito llega en negativo (D-045), pero en el asiento va en la misma
    cuenta y al otro lado (el contador, 2026-10-29)."""
    for ln in lineas:
        if ln.debito < CERO or ln.credito < CERO:
            ln.debito, ln.credito = -ln.credito, -ln.debito
            if ln.base is not None:
                ln.base = abs(ln.base)


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
            " debito, credito, rol, base, concepto_id, codigo_siigo, tercero_nit)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (asiento_id, orden, ln.cuenta_puc, ln.descripcion, str(ln.debito), str(ln.credito),
             ln.rol, str(ln.base) if ln.base is not None else None, ln.concepto_id, ln.codigo_siigo,
             ln.tercero_nit))


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

# Lo que él puede corregir antes de dar el visto bueno. Se guarda con el asiento
# (`correccion`) para que aprobarlo después —uno a uno o en bloque— aprenda lo
# mismo que si lo hubiera aprobado en el momento.
CAMPOS_CORRECCION = ("cuenta_puc", "patron", "concepto_retencion_id", "sin_retencion",
                     "aprender_regla", "iva_codigo", "retenciones_cliente")


def _uno(conn, asiento_id: int) -> dict[str, Any]:
    fila = conn.execute(
        "SELECT * FROM asiento_propuesto WHERE id = ?", (int(asiento_id),)).fetchone()
    if fila is None:
        raise ValueError(f"El asiento {asiento_id} no existe.")
    return dict(fila)


def _documento_de(conn, a: dict[str, Any]) -> dict[str, Any] | None:
    # El documento puede venir del XML o del Excel: hay que mirar en los dos
    # sitios. Buscándolo solo por XML, en un mes sin XML la corrección del
    # contador no se aplicaba a ninguna línea — y él la veía ignorada.
    return next((d for d in documentos_module.documentos_a_causar(conn, a["periodo"])
                 if d["cufe"] == a["cufe"]), None)


def _propuesta_corregida(conn, documento, c: dict[str, Any]):
    propuesta = causacion_module.proponer(conn, documento)
    if c.get("cuenta_puc"):
        propuesta.cuenta_puc = str(c["cuenta_puc"]).strip()
        propuesta.seguro = True
    if c.get("concepto_retencion_id"):
        propuesta.concepto_retencion_id = int(c["concepto_retencion_id"])
        propuesta.sin_retencion = False
    elif c.get("sin_retencion"):
        propuesta.sin_retencion = True
    if (c.get("iva_codigo") or "").strip():
        propuesta.iva_codigo = c["iva_codigo"].strip()
    if (c.get("retenciones_cliente") or "").strip():
        propuesta.retenciones_cliente = c["retenciones_cliente"].strip()
    return propuesta


def _guardar_cuentas_empresa(conn, nuevas: dict[str, str | None]) -> None:
    if any(nuevas.values()):
        actual = dict(conn.execute("SELECT * FROM empresa_info").fetchone() or {})
        conn.execute(
            "UPDATE empresa_info SET cuenta_proveedores = ?, cuenta_iva_descontable = ?,"
            " cuenta_clientes = ?, cuenta_iva_generado = ?",
            tuple((nuevas.get(k) or actual.get(k) or "").strip() or None for k in (
                "cuenta_proveedores", "cuenta_iva_descontable",
                "cuenta_clientes", "cuenta_iva_generado")))


def _linea_dict(ln: Linea) -> dict[str, Any]:
    return {"cuenta_puc": ln.cuenta_puc, "descripcion": ln.descripcion,
            "debito": str(ln.debito), "credito": str(ln.credito), "rol": ln.rol,
            "base": str(ln.base) if ln.base is not None else None,
            "concepto_id": ln.concepto_id, "codigo_siigo": ln.codigo_siigo,
            "tercero_nit": ln.tercero_nit}


def previsualizar(conn, asiento_id: int, **correccion) -> dict[str, Any]:
    """Cómo quedaría el asiento con esta cuenta, retención o IVA. No guarda nada:
    es lo que la bandeja pone en el editor cuando él cambia un desplegable."""
    a = _uno(conn, asiento_id)
    documento = _documento_de(conn, a)
    if documento is None:
        raise ValueError("No se encontró el documento de este asiento en el mes.")
    ctx = _contexto(conn, a["periodo"])
    for k in ("cuenta_proveedores", "cuenta_iva_descontable", "cuenta_clientes", "cuenta_iva_generado"):
        if (correccion.get(k) or "").strip():
            ctx["cuentas"][k] = correccion[k].strip()
    propuesta = _propuesta_corregida(conn, documento, correccion)
    lineas, avisos, estado = _armar(conn, ctx, documento, propuesta, tercero_decidido=True)
    return {"lineas": [_linea_dict(x) for x in lineas], "avisos": avisos, "estado": estado}


_NIT = re.compile(r"^\d{5,15}$")


def _leer_lineas(lineas: list[dict[str, Any]]) -> list[Linea]:
    """Las líneas que él escribió, validadas. Lo que no se puede guardar se
    rechaza con su motivo; lo que solo impide aprobar (falta una cuenta, no
    cuadra) se guarda y deja el asiento por revisar."""
    salida: list[Linea] = []
    for n, x in enumerate(lineas, 1):
        cuenta = re.sub(r"\s", "", str(x.get("cuenta_puc") or "")) or None
        if cuenta and not cuenta.isdigit():
            raise ValueError(f"Línea {n}: la cuenta «{cuenta}» no es un número del PUC.")
        try:
            debito = _d(str(x.get("debito") or "0").replace(",", ""))
            credito = _d(str(x.get("credito") or "0").replace(",", ""))
        except Exception as exc:
            raise ValueError(f"Línea {n}: el valor no es un número.") from exc
        if debito and credito:
            raise ValueError(f"Línea {n}: una línea va al débito o al crédito, no a los dos.")
        if not debito and not credito and not cuenta:
            continue          # una fila vacía que agregó y no llenó
        tercero = str(x.get("tercero_nit") or "").strip().split("-")[0].replace(".", "") or None
        if tercero and not _NIT.match(tercero):
            raise ValueError(f"Línea {n}: «{x.get('tercero_nit')}» no es un NIT o cédula.")
        rol = x.get("rol") if x.get("rol") in ROLES else None
        base = x.get("base")
        salida.append(Linea(
            cuenta, str(x.get("descripcion") or "").strip(), debito=debito, credito=credito,
            rol=rol, base=_d(base) if base not in (None, "") else None,
            concepto_id=int(x["concepto_id"]) if x.get("concepto_id") else None,
            codigo_siigo=(str(x.get("codigo_siigo") or "").strip() or None),
            tercero_nit=tercero))
    if not salida:
        raise ValueError("Un asiento sin líneas no se puede guardar.")
    _sin_negativos(salida)
    return salida


def _problemas(lineas: list[Linea]) -> list[str]:
    problemas = []
    sin = sum(1 for x in lineas if not x.cuenta_puc)
    if sin:
        problemas.append(f"{sin} línea{'s' if sin > 1 else ''} sin cuenta.")
    descuadre = sum((x.debito for x in lineas), CERO) - sum((x.credito for x in lineas), CERO)
    if descuadre != CERO:
        lado = "el débito" if descuadre > CERO else "el crédito"
        problemas.append(f"El asiento no cuadra por {_plata(abs(descuadre))} pesos: sobra en {lado}.")
    return problemas


def guardar(conn, asiento_id: int, lineas: list[dict[str, Any]],
            correccion: dict[str, Any] | None = None, **cuentas_empresa) -> dict[str, Any]:
    """Guarda las líneas como él las dejó, sin aprobar.

    Lo pidió el contador el 2026-10-28: «antes de aprobar un registro, un botón
    de guardar el movimiento». Guardado, el asiento ya no lo pisa volver a armar
    la propuesta; queda listo si cuadra y tiene todas sus cuentas.
    """
    a = _uno(conn, asiento_id)
    if a["aprobado"]:
        raise ValueError("Este asiento ya está aprobado: deshaga la aprobación para cambiarlo.")
    nuevas = _leer_lineas(lineas)
    _guardar_cuentas_empresa(conn, cuentas_empresa)
    problemas = _problemas(nuevas)
    c = {k: (correccion or {}).get(k) for k in CAMPOS_CORRECCION if (correccion or {}).get(k) not in (None, "")}
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM asiento_linea WHERE asiento_id = ?", (a["id"],))
    _escribir_lineas(conn, a["id"], nuevas)
    conn.execute(
        "UPDATE asiento_propuesto SET editado = 1, correccion = ?, estado = ?, avisos = ?"
        " WHERE id = ?",
        (json.dumps(c, ensure_ascii=False) if c else None,
         ESTADO_REVISAR if problemas else ESTADO_COMPLETO,
         json.dumps(problemas, ensure_ascii=False) if problemas else None, a["id"]))
    conn.commit()
    return listar_uno(conn, a["id"])


def descartar(conn, asiento_id: int) -> dict[str, Any]:
    """Olvida lo guardado a mano y vuelve a la propuesta de las reglas."""
    a = _uno(conn, asiento_id)
    if a["aprobado"]:
        raise ValueError("Este asiento ya está aprobado: deshaga la aprobación primero.")
    documento = _documento_de(conn, a)
    if documento is None:
        raise ValueError("No se encontró el documento de este asiento en el mes.")
    ctx = _contexto(conn, a["periodo"])
    propuesta = causacion_module.proponer(conn, documento)
    lineas, avisos, estado = _armar(conn, ctx, documento, propuesta, tercero_decidido=None)
    _escribir(conn, a["periodo"], documento, estado, avisos, propuesta.regla_id,
              lineas, asiento_id=a["id"])
    conn.commit()
    nuevo = conn.execute("SELECT id FROM asiento_propuesto WHERE periodo = ? AND cufe = ?",
                         (a["periodo"], a["cufe"])).fetchone()
    return listar_uno(conn, nuevo["id"])


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
    retenciones_cliente: str | None = None,
    lineas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Da por bueno un asiento, con las correcciones que él haya hecho.

    Lo que corrija se guarda **para esta empresa**: las cuentas viven en su
    propia base (D-003), así que «las cuentas pueden variar por cada empresa»
    sale gratis — no hay una tabla común que pudiera mezclarlas.

    Con `lineas`, o si el asiento ya estaba guardado a mano, las líneas son las
    suyas y no se rehacen: solo se aprende la regla y se aprueba. Un asiento
    que no cuadra o con una línea sin cuenta no se aprueba.
    """
    a = _uno(conn, asiento_id)
    if a["aprobado"]:
        return listar_uno(conn, a["id"])
    dados = {"cuenta_puc": cuenta_puc, "patron": patron,
             "concepto_retencion_id": concepto_retencion_id, "sin_retencion": sin_retencion,
             "aprender_regla": aprender_regla, "iva_codigo": iva_codigo,
             "retenciones_cliente": retenciones_cliente}
    cuentas_empresa = {"cuenta_proveedores": cuenta_proveedores,
                       "cuenta_iva_descontable": cuenta_iva_descontable,
                       "cuenta_clientes": cuenta_clientes,
                       "cuenta_iva_generado": cuenta_iva_generado}
    if lineas is not None:
        a = guardar(conn, a["id"], lineas, dados, **cuentas_empresa)
    else:
        _guardar_cuentas_empresa(conn, cuentas_empresa)

    if a["editado"]:
        guardada = json.loads(a["correccion"]) if a.get("correccion") else {}
        # Lo que eligió al guardar, salvo que ahora diga otra cosa.
        c = dict(guardada)
        for k, v in dados.items():
            if k != "aprender_regla" and v not in (None, "", False):
                c[k] = v
        if "aprender_regla" not in c:
            c["aprender_regla"] = aprender_regla
        propias = [Linea(r["cuenta_puc"], r["descripcion"] or "", debito=_d(r["debito"]),
                         credito=_d(r["credito"]), rol=r["rol"])
                   for r in conn.execute("SELECT * FROM asiento_linea WHERE asiento_id = ?"
                                         " ORDER BY orden", (a["id"],))]
        problemas = _problemas(propias)
        if problemas:
            raise ValueError("No se puede aprobar: " + " ".join(problemas))
        principal = next((x for x in propias if x.rol in (ROL_GASTO, ROL_INGRESO)), None)
        sin_iva = next((x for x in propias if x.rol == ROL_NO_GRAVADO and x.cuenta_puc), None)
        _aprender(conn, a, cuenta_puc=c.get("cuenta_puc") or (principal.cuenta_puc if principal else None),
                  correccion=c, cuenta_no_gravada=sin_iva.cuenta_puc if sin_iva else None,
                  reparto=reparto_de(propias, a.get("naturaleza")))
    else:
        _aprender(conn, a, cuenta_puc=cuenta_puc, correccion=dados, cuenta_no_gravada=None,
                  reparto=None)
        # Se rehace el asiento con lo corregido.
        documento = _documento_de(conn, a)
        if documento is not None:
            ctx = _contexto(conn, a["periodo"])
            propuesta = _propuesta_corregida(conn, documento, dados)
            nuevas, avisos, _estado = _armar(conn, ctx, documento, propuesta, tercero_decidido=True)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM asiento_linea WHERE asiento_id = ?", (a["id"],))
            _escribir_lineas(conn, a["id"], nuevas)
            conn.execute(
                "UPDATE asiento_propuesto SET avisos = ? WHERE id = ?",
                (json.dumps(avisos, ensure_ascii=False) if avisos else None, a["id"]))

    conn.execute(
        "UPDATE asiento_propuesto SET aprobado = 1, estado = ?,"
        " aprobado_at = datetime('now') WHERE id = ?", (ESTADO_COMPLETO, a["id"]))
    conn.commit()
    return listar_uno(conn, a["id"])


def _aprender(conn, a, *, cuenta_puc, correccion, cuenta_no_gravada, reparto) -> None:
    """La regla, para que la próxima factura de este tercero salga sola."""
    if not (correccion.get("aprender_regla", True) and cuenta_puc and a.get("tercero_nit")):
        return
    es_venta = (a.get("naturaleza") or "compra") == documentos_module.NATURALEZA_VENTA
    concepto = correccion.get("concepto_retencion_id")
    sin_retencion = bool(correccion.get("sin_retencion"))
    if not concepto and not sin_retencion and not es_venta:
        # No eligió retención en esta pantalla: se conserva lo que ya se sabía
        # —la de las líneas, o la de la regla—. Sin esto, guardar un asiento
        # editado y aprobarlo le borraba el concepto a la regla del proveedor.
        fila = conn.execute(
            "SELECT concepto_id FROM asiento_linea WHERE asiento_id = ? AND rol = ?"
            " AND concepto_id IS NOT NULL LIMIT 1", (a["id"], ROL_RETENCION)).fetchone()
        regla = conn.execute(
            "SELECT concepto_retencion_id, sin_retencion FROM regla_causacion WHERE id = ?",
            (a.get("regla_id") or 0,)).fetchone()
        if fila:
            concepto = fila["concepto_id"]
        elif regla:
            concepto, sin_retencion = regla["concepto_retencion_id"], bool(regla["sin_retencion"])
    causacion_module.aprender(
        conn, cuenta_puc=cuenta_puc, tercero_nit=a["tercero_nit"],
        patron=(correccion.get("patron") or "").strip() or None,
        concepto_retencion_id=None if es_venta or not concepto else int(concepto),
        # «A este proveedor no se le retiene», dicho por él. Va a la regla
        # para que las siguientes facturas no vuelvan a preguntarlo.
        sin_retencion=sin_retencion and not es_venta,
        naturaleza=a.get("naturaleza") or documentos_module.NATURALEZA_COMPRA,
        iva_codigo=correccion.get("iva_codigo"),
        retenciones_cliente=((correccion.get("retenciones_cliente") or "").strip() or None)
        if es_venta else None,
        cuenta_no_gravada=cuenta_no_gravada, reparto=reparto)


def aprobar_lote(conn, periodo: str, ids: list[int] | None = None) -> dict[str, Any]:
    """Aprueba de un golpe los marcados, o todos los listos si no marcó ninguno.

    Solo entra lo que está listo: lo que falta decidir no se aprueba en bloque.
    Uno guardado a mano aprende su regla igual que si lo aprobara solo.
    """
    sql = ("SELECT id, estado, editado FROM asiento_propuesto WHERE periodo = ?"
           " AND aprobado = 0")
    args: list[Any] = [periodo]
    if ids is not None:
        sql += f" AND id IN ({','.join('?' * len(ids))})" if ids else " AND 0"
        args += [int(i) for i in ids]
    aprobados, omitidos = 0, 0
    for fila in conn.execute(sql, args).fetchall():
        if fila["estado"] != ESTADO_COMPLETO:
            omitidos += 1
            continue
        if fila["editado"]:
            try:
                aprobar(conn, fila["id"])
            except ValueError:
                omitidos += 1
                continue
        else:
            conn.execute(
                "UPDATE asiento_propuesto SET aprobado = 1, aprobado_at = datetime('now')"
                " WHERE id = ?", (fila["id"],))
        aprobados += 1
    conn.commit()
    return {"aprobados": aprobados, "omitidos": omitidos, **resumen(conn, periodo)}


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
