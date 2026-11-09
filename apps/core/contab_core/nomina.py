"""La nómina del mes como comprobante de Siigo (tipo 992) — D-134.

La fuente **no es la DIAN**: es el Excel de nómina que el contador liquida cada
quincena (hojas «1Q» y «2Q», una fila por empleado). Contab lo lee y arma un
comprobante por quincena con la misma forma que el que él sube hoy a Siigo,
verificada línea por línea contra los dos 992 de septiembre de REAL:

- **Por empleado**, con su cédula como tercero: los devengos al débito (salario,
  auxilio de transporte, rodamiento, otros pagos), las provisiones (cesantías,
  intereses, prima, vacaciones: gasto 5105 contra pasivo 2510), los aportes del
  empleador al débito (pensión 12 %, caja 4 %, ARL), y al crédito el neto a
  pagar, la retención y las otras deducciones.
- **Por aporte**, con la entidad como tercero: la salud del empleado, la
  pensión (empleado + empleador + fondo de solidaridad), la caja y la ARL, cada
  una en la cuenta de la entidad de ese empleado.

Las cuentas, las tarifas y la entidad de cada empleado viven en una
**plantilla** por empresa (`siigo_config`, claves `nom:`). No se escriben de
memoria: se **aprenden** del 992 que ya está en Siigo, comparando cada línea con
el Excel de nómina de esa misma quincena. Lo que no se pueda explicar se
devuelve con nombre.

Redondeo: al peso, por empleado y por concepto, como en su archivo — la ARL
de la quincena da 52.070 sumando empleados, no 52.069,5 sobre el total.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from .hojas import leer_hojas

CERO = Decimal("0")
QUINCENAS = ("1Q", "2Q")

# Las columnas del Excel de nómina, por su texto (no por posición: la plantilla
# del contador ha cambiado de columnas entre meses).
DEVENGOS = {
    "salario devengado": "salario",
    "vr. vacaciones": "vacaciones_disfrutadas", "vacaciones": "vacaciones_disfrutadas",
    "comisones": "comisiones", "comisiones": "comisiones",
    "vr. incapacidad": "incapacidad",
    "vr. recargo nocturno": "recargo_nocturno",
    "vr. extras diurnas": "extras", "vr. extras nocturnas": "extras",
    "vr. dominical diurno": "extras", "vr. dominical nocturno": "extras",
    "vr. extra dominical diurno": "extras", "vr. extra dominical nocturno": "extras",
    "auxilio de transporte": "aux_transporte",
    "auxilio de datos": "aux_datos",
    "auxilio de rodamiento": "rodamiento",
    "otros pagos no salariales": "otros_pagos",
}
DEDUCCIONES = {
    "salud": "salud", "pension": "pension", "fondo de solidaridad pensional": "fsp",
    "retencion en la fuente": "retencion", "cartera": "cartera", "prestamos": "prestamos",
    "otras deducciones": "otras_deducciones",
}
# Lo que entra en la base de las provisiones y los aportes: lo salarial.
SALARIALES = ("salario", "vacaciones_disfrutadas", "comisiones", "recargo_nocturno", "extras")

# Las que se calculan, con la tarifa que trae el archivo de septiembre de REAL.
# Son ley y quedan en la plantilla, editables: no se fijan en el código.
PROVISIONES = ("cesantias", "intereses", "prima", "vacaciones")
APORTES = ("pension_empleador", "caja", "arl")
TARIFAS_INICIALES = {
    "cesantias": "8.33", "intereses": "12", "prima": "8.33", "vacaciones": "4.17",
    "pension_empleador": "12", "caja": "4", "arl": "0.522",
}
ENTIDADES = ("salud", "pension", "caja", "arl")
# Las que elige cada empleado; la ARL la designa el empleador (el contador,
# 2026-11-04). El fondo de cesantías se guarda pero el 992 no lo usa: la
# provisión va contra el empleado hasta que se consigna.
ENTIDADES_DEL_EMPLEADO = ("salud", "pension", "cesantias", "caja")

# La ARL por clase de riesgo (D-142). Fija para todas las empresas, como pidió
# el contador; su tabla trae los valores redondeados (0,52 %…) y el 992 real de
# REAL confirma el 0,522 % de la clase I.
RIESGOS_ARL = {"I": Decimal("0.522"), "II": Decimal("1.044"), "III": Decimal("2.436"),
               "IV": Decimal("4.350"), "V": Decimal("6.960")}
# Lo que la ley descuenta al empleado, para revisar el Excel (no para calcular:
# el neto que se pagó sale de lo que el Excel descontó).
DESCUENTO_EMPLEADO = {"salud": Decimal("4"), "pension": Decimal("4")}

ETIQUETA = {
    "salario": "Salario", "vacaciones_disfrutadas": "Vacaciones disfrutadas",
    "comisiones": "Comisiones", "incapacidad": "Incapacidad", "recargo_nocturno": "Recargo nocturno",
    "extras": "Horas extra", "aux_transporte": "Auxilio de transporte", "aux_datos": "Auxilio de datos",
    "rodamiento": "Auxilio de rodamiento", "otros_pagos": "Otros pagos no salariales",
    "retencion": "Retención en la fuente", "cartera": "Cartera", "prestamos": "Préstamos",
    "otras_deducciones": "Otras deducciones", "neto": "Neto a pagar",
    "cesantias": "Cesantías", "intereses": "Intereses de cesantías", "prima": "Prima",
    "vacaciones": "Vacaciones", "pension_empleador": "Pensión empleador", "caja": "Caja de compensación",
    "arl": "ARL", "salud": "Salud", "pension": "Pensión", "fsp": "Fondo de solidaridad",
}


def _plano(v: Any) -> str:
    t = unicodedata.normalize("NFKD", str(v or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.replace("\n", " ").split()).strip().lower()


def _d(v: Any) -> Decimal:
    if isinstance(v, bool) or v in (None, ""):
        return CERO
    if isinstance(v, float):
        # 124547.49999999999 es 124.547,5 con ruido de coma flotante: sin
        # limpiarlo, el redondeo al peso cae hacia abajo y no hacia arriba.
        return Decimal(str(round(v, 6)))
    try:
        return Decimal(str(v))
    except Exception:
        return CERO


def _peso(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _nit(v: Any) -> str:
    t = str(v).strip()
    return t[:-2] if t.endswith(".0") else t


# ───────────────────────────── leer el Excel de nómina ────────────────────────

@dataclass
class Empleado:
    id: str
    nombre: str
    valores: dict[str, Decimal] = field(default_factory=dict)
    observaciones: str = ""

    def v(self, k: str) -> Decimal:
        return self.valores.get(k, CERO)


@dataclass
class Quincena:
    nombre: str
    empleados: list[Empleado]
    columnas_sin_leer: list[str] = field(default_factory=list)


def leer_nomina(ruta: str | Path) -> dict[str, Quincena]:
    """Las hojas «1Q» y «2Q» del Excel de nómina, por empleado y por concepto."""
    out: dict[str, Quincena] = {}
    for h in leer_hojas(ruta):
        nombre = h.titulo.strip().upper()
        if nombre not in QUINCENAS:
            continue
        cab = next((i for i, r in enumerate(h.filas)
                    if len(r) > 2 and _plano(r[1]) == "id" and "nombre" in _plano(r[2])), None)
        if cab is None:
            continue
        sub1 = h.filas[cab + 1] if cab + 1 < len(h.filas) else []
        sub2 = h.filas[cab + 2] if cab + 2 < len(h.filas) else []
        grupo, columnas, sin_leer = "", {}, []
        for c in range(3, max(len(h.filas[cab]), len(sub1), len(sub2))):
            g = _plano(h.filas[cab][c]) if c < len(h.filas[cab]) else ""
            if g:
                grupo = g
            t1 = _plano(sub1[c]) if c < len(sub1) else ""
            t2 = _plano(sub2[c]) if c < len(sub2) else ""
            if t2.startswith(("dias", "horas")) or t1.startswith(("dias", "horas")):
                continue          # días u horas: la columna del valor viene al lado
            texto = t2 if t2.startswith("vr.") or t2 == "vacaciones" else (t1 or g)
            if texto.startswith("vr.") and texto not in DEVENGOS and any(
                    p in texto for p in ("extra", "dominical", "recargo", "festivo")):
                texto = "vr. extras diurnas"
            if texto in ("neto pagado", "neto  pagado") or g.startswith("neto"):
                columnas[c] = "neto"
            elif "observacion" in g or "observacion" in texto:
                columnas[c] = "observaciones"
            elif grupo.startswith("deduccion") and texto in DEDUCCIONES:
                columnas[c] = DEDUCCIONES[texto]
            elif texto in DEVENGOS:
                columnas[c] = DEVENGOS[texto]
            elif texto and not texto.startswith(("total", "dias", "horas", "salario basico")) and texto != "aux tte":
                sin_leer.append(texto)
        empleados = []
        for r in h.filas[cab + 3:]:
            if len(r) < 3 or not isinstance(r[1], (int, float)) or isinstance(r[1], bool):
                continue
            e = Empleado(id=_nit(r[1]), nombre=str(r[2] or "").strip())
            for c, k in columnas.items():
                if c >= len(r):
                    continue
                if k == "observaciones":
                    e.observaciones = str(r[c] or "").strip()
                else:
                    # Al peso, como lo lleva a Siigo: el auxilio de transporte de
                    # la quincena viene con medio peso (124.547,5) y él lo
                    # redondea por empleado; el neto, igual.
                    e.valores[k] = e.valores.get(k, CERO) + _peso(_d(r[c]))
            empleados.append(e)
        out[nombre] = Quincena(nombre, empleados, sin_leer)
    return out


# ─────────────────────────────── la plantilla ─────────────────────────────────
# Claves en siigo_config:
#   nom:debito:<concepto>        cuenta del gasto (devengos, provisiones, aportes)
#   nom:credito:<concepto>       cuenta del pasivo (provisiones, neto, retención, deducciones)
#   nom:tarifa:<concepto>        % (provisiones y aportes)
#   nom:entidad:<id>:<aporte>    «cuenta|nit» de la entidad de ese empleado
#   nom:entidad:*:<aporte>       la de un empleado nuevo (la más común)
#   nom:empleado:<id>:<concepto> cuenta propia de ese empleado (otros pagos, deducciones)

def plantilla(cfg: dict[str, str]) -> dict[str, str]:
    p = {k: v for k, v in cfg.items() if k.startswith("nom:")}
    for k, v in TARIFAS_INICIALES.items():
        p.setdefault(f"nom:tarifa:{k}", v)
    return p


@dataclass
class LineaNomina:
    cuenta: str | None
    tercero: str
    descripcion: str
    debito: Decimal = CERO
    credito: Decimal = CERO


def _ajustar_redondeo(lineas: list[LineaNomina], diferencia: Decimal) -> Decimal:
    """Cuadra la quincena moviendo un peso en el neto de algunos empleados.

    Cada valor va al peso, y con el medio peso del auxilio de transporte la
    quincena queda descuadrada por uno o dos pesos. Así no se puede aprobar, y
    sin aprobar no va en el archivo de Siigo (2026-11-09, ALAGUNA). En Siigo el
    contador lo absorbe en el neto. Solo hasta un peso por empleado: más que eso
    no es redondeo y se deja descuadrada, con su aviso.
    """
    netos = sorted((x for x in lineas if x.descripcion == ETIQUETA["neto"] and x.credito),
                   key=lambda x: x.credito, reverse=True)
    pesos = int(abs(diferencia))
    if diferencia != diferencia.to_integral() or not pesos or pesos > len(netos):
        return CERO
    paso = Decimal(1) if diferencia > 0 else Decimal(-1)
    for x in netos[:pesos]:
        x.credito += paso
    return paso * pesos


def _cuenta_empleado(p: dict[str, str], lado: str, concepto: str, e: Empleado) -> str | None:
    return (p.get(f"nom:empleado:{e.id}:{concepto}") or p.get(f"nom:{lado}:{concepto}") or "").strip() or None


def _entidad(p: dict[str, str], aporte: str, e: Empleado) -> tuple[str | None, str]:
    crudo = p.get(f"nom:entidad:{e.id}:{aporte}") or p.get(f"nom:entidad:*:{aporte}") or ""
    cuenta, _, nit = crudo.partition("|")
    return (cuenta.strip() or None), nit.strip()


def armar(quincena: Quincena, p: dict[str, str]) -> tuple[list[LineaNomina], list[str]]:
    """Las líneas del comprobante de una quincena y lo que falta para que salga bien."""
    lineas: list[LineaNomina] = []
    faltan: set[str] = set()
    tarifa = {k: _d(p.get(f"nom:tarifa:{k}")) / 100 for k in (*PROVISIONES, *APORTES)}

    def linea(cuenta, tercero, concepto, debito=CERO, credito=CERO, falta_clave=None):
        if not debito and not credito:
            return
        if not cuenta and falta_clave:
            faltan.add(falta_clave)
        lineas.append(LineaNomina(cuenta, tercero, ETIQUETA.get(concepto, concepto), debito, credito))

    for e in quincena.empleados:
        base = sum((e.v(k) for k in SALARIALES), CERO)
        for k in ("salario", "vacaciones_disfrutadas", "comisiones", "incapacidad", "recargo_nocturno",
                  "extras", "aux_transporte", "aux_datos", "rodamiento", "otros_pagos"):
            linea(_cuenta_empleado(p, "debito", k, e), e.id, k, debito=e.v(k), falta_clave=f"nom:debito:{k}")

        ces = _peso(base * tarifa["cesantias"])
        calculadas = {"cesantias": ces, "intereses": _peso(ces * tarifa["intereses"]),
                      "prima": _peso(base * tarifa["prima"]), "vacaciones": _peso(base * tarifa["vacaciones"])}
        for k, v in calculadas.items():
            linea(_cuenta_empleado(p, "debito", k, e), e.id, k, debito=v, falta_clave=f"nom:debito:{k}")
            linea(_cuenta_empleado(p, "credito", k, e), e.id, k, credito=v, falta_clave=f"nom:credito:{k}")

        aporte = {k: _peso(base * tarifa[k]) for k in APORTES}
        riesgo = (p.get(f"nom:riesgo:{e.id}") or "").strip().upper()
        if riesgo in RIESGOS_ARL:
            aporte["arl"] = _peso(base * RIESGOS_ARL[riesgo] / 100)
        for k, v in aporte.items():
            linea(_cuenta_empleado(p, "debito", k, e), e.id, k, debito=v, falta_clave=f"nom:debito:{k}")

        # A las entidades: salud del empleado; pensión del empleado, del
        # empleador y fondo de solidaridad; caja y ARL del empleador.
        for nombre, partes in (("salud", (("salud", e.v("salud")),)),
                               ("pension", (("pension", e.v("pension")),
                                            ("pension_empleador", aporte["pension_empleador"]),
                                            ("fsp", e.v("fsp")))),
                               ("caja", (("caja", aporte["caja"]),)),
                               ("arl", (("arl", aporte["arl"]),))):
            cuenta, nit = _entidad(p, nombre, e)
            for concepto, v in partes:
                linea(cuenta, nit or e.id, concepto, credito=v, falta_clave=f"nom:entidad:*:{nombre}")
            if cuenta and not nit and any(v for _, v in partes):
                faltan.add(f"nom:entidad:{e.id}:{nombre}")

        for k in ("retencion", "cartera", "prestamos", "otras_deducciones"):
            linea(_cuenta_empleado(p, "credito", k, e), e.id, k, credito=e.v(k), falta_clave=f"nom:credito:{k}")
        linea(_cuenta_empleado(p, "credito", "neto", e), e.id, "neto", credito=e.v("neto"),
              falta_clave="nom:credito:neto")

    return lineas, sorted(faltan)


def revisar(quincena: Quincena, p: dict[str, str], smmlv: Decimal | None) -> list[str]:
    """Lo que el Excel trae distinto de la ley, para que él lo mire (D-142).

    No cambia ningún valor: el comprobante lleva lo que se liquidó y se pagó.
    Los umbrales son mensuales y la hoja es de una quincena: se comparan contra
    la mitad.
    """
    avisos: list[str] = []
    for e in quincena.empleados:
        base = sum((e.v(k) for k in SALARIALES), CERO)
        if not base:
            continue
        quien = e.nombre or e.id
        for k, pct in DESCUENTO_EMPLEADO.items():
            esperado = _peso(base * pct / 100)
            if abs(e.v(k) - esperado) > 1:
                avisos.append(f"{quien}: la {ETIQUETA.get(k, k).lower()} del Excel es {e.v(k)}, "
                              f"y el {pct} % de la base es {esperado}.")
        if smmlv:
            if base >= smmlv * 2 and not e.v("fsp"):
                avisos.append(f"{quien} gana 4 o más salarios mínimos y no tiene fondo de solidaridad pensional.")
            if base >= smmlv * 5:
                avisos.append(f"{quien} gana 10 o más salarios mínimos: el empleador no está exonerado "
                              "de salud, SENA e ICBF. Contab todavía no los causa.")
        if not (p.get(f"nom:riesgo:{e.id}") or "").strip():
            avisos.append(f"{quien}: falta la clase de riesgo de la ARL; se usó la tarifa general.")
    return avisos


# ─────────────────────── los empleados y sus entidades (D-142) ─────────────────

def _entidad_dict(crudo: str | None) -> dict[str, str]:
    cuenta, _, nit = (crudo or "").partition("|")
    return {"cuenta": cuenta.strip(), "nit": nit.strip()}


def empleados(conn) -> dict[str, Any]:
    """Cada empleado con su EPS, fondos y caja, la ARL de la empresa y el salario mínimo."""
    from . import siigo as siigo_module

    p = plantilla(siigo_module.config(conn))
    ids = set()
    for k in p:
        partes = k.split(":")
        if (partes[1] in ("nombre", "riesgo") and len(partes) == 3) or (
                partes[1] == "entidad" and partes[2] != "*"):
            ids.add(partes[2])
    lista = []
    for i in sorted(ids, key=lambda x: (p.get(f"nom:nombre:{x}") or x).lower()):
        lista.append({
            "id": i, "nombre": p.get(f"nom:nombre:{i}") or "",
            "riesgo": (p.get(f"nom:riesgo:{i}") or "").strip().upper(),
            **{ent: _entidad_dict(p.get(f"nom:entidad:{i}:{ent}")) for ent in ENTIDADES_DEL_EMPLEADO},
        })
    return {
        "empleados": lista,
        "arl": _entidad_dict(p.get("nom:entidad:*:arl")),
        "por_defecto": {ent: _entidad_dict(p.get(f"nom:entidad:*:{ent}")) for ent in ENTIDADES_DEL_EMPLEADO},
        "smmlv": {k.split(":")[2]: v for k, v in p.items() if k.startswith("nom:smmlv:")},
        "riesgos": {k: str(v) for k, v in RIESGOS_ARL.items()},
    }


def _texto_entidad(v: dict[str, Any] | None) -> str:
    v = v or {}
    cuenta, nit = str(v.get("cuenta") or "").strip(), str(v.get("nit") or "").strip().split("-")[0]
    return f"{cuenta}|{nit}" if cuenta or nit else ""


def guardar_empleado(conn, data: dict[str, Any]) -> dict[str, Any]:
    from . import siigo as siigo_module

    i = _nit(data.get("id") or "").split("-")[0].replace(".", "")
    if not i.isdigit():
        raise ValueError("La cédula del empleado tiene que ser un número.")
    riesgo = str(data.get("riesgo") or "").strip().upper()
    if riesgo and riesgo not in RIESGOS_ARL:
        raise ValueError(f"La clase de riesgo es I, II, III, IV o V; llegó «{riesgo}».")
    valores = {f"nom:nombre:{i}": str(data.get("nombre") or "").strip(), f"nom:riesgo:{i}": riesgo}
    for ent in ENTIDADES_DEL_EMPLEADO:
        valores[f"nom:entidad:{i}:{ent}"] = _texto_entidad(data.get(ent))
    siigo_module.guardar_config(conn, valores)
    return next(e for e in empleados(conn)["empleados"] if e["id"] == i)


def guardar_empresa(conn, data: dict[str, Any]) -> dict[str, Any]:
    """La ARL de la empresa (una sola: la designa el empleador) y el salario mínimo."""
    from . import siigo as siigo_module

    valores: dict[str, Any] = {}
    if "arl" in data:
        valores["nom:entidad:*:arl"] = _texto_entidad(data["arl"])
        # Una ARL por empleado venía de aprenderla del 992; ahora manda la de la empresa.
        for k in [k for k in siigo_module.config(conn) if k.startswith("nom:entidad:") and k.endswith(":arl")
                  and not k.startswith("nom:entidad:*:")]:
            valores[k] = ""
    for anio, v in (data.get("smmlv") or {}).items():
        if not str(anio).isdigit() or len(str(anio)) != 4:
            raise ValueError(f"«{anio}» no es un año.")
        texto = str(v or "").replace(".", "").replace(",", "").strip()
        if texto and not texto.isdigit():
            raise ValueError("El salario mínimo va en pesos, sin decimales.")
        valores[f"nom:smmlv:{anio}"] = texto
    siigo_module.guardar_config(conn, valores)
    return empleados(conn)


# ───────────────────── aprender la plantilla del 992 que ya existe ─────────────

def aprender(conn, ruta_nomina: str | Path, ruta_carga: str | Path, *,
             dry_run: bool = False, periodo: str | None = None) -> dict[str, Any]:
    """Deduce la plantilla comparando el Excel de nómina con el 992 de Siigo.

    Cada quincena se empareja con el 992 cuyo «neto a pagar» suma lo mismo.
    Por empleado: la línea con su cédula y su valor dice la cuenta de cada
    concepto. Por aporte: la línea de la entidad con el valor de ese empleado
    dice la cuenta y el NIT de su EPS, su fondo, su caja y su ARL. Las tarifas
    de provisiones y aportes también se leen de ahí.

    Con `periodo`, cada quincena se busca primero entre los 992 de ese mes: con
    el movimiento del año entero, el neto de septiembre coincidía con el de
    febrero por dos pesos y se aprendía del comprobante equivocado (2026-11-09).
    """
    from . import siigo as siigo_module

    nomina = leer_nomina(ruta_nomina)
    if not nomina:
        raise ValueError("El Excel no tiene hojas «1Q» ni «2Q» con la liquidación por empleado.")
    comprobantes: dict[Any, list[dict[str, Any]]] = {}
    tipo_nomina = (siigo_module.config(conn).get("tipo:nomina") or "992").strip()
    for f in siigo_module._filas_siigo(ruta_carga):
        if _nit(f.get("Tipo de comprobante") or "") == tipo_nomina:
            comprobantes.setdefault(f.get("Consecutivo comprobante"), []).append(f)
    if not comprobantes:
        raise ValueError(f"El archivo de carga no trae comprobantes de nómina (tipo {tipo_nomina}).")

    def monto(f):
        return _d(f.get("Débito")) or _d(f.get("Crédito"))

    aprendido: dict[str, str] = {}
    votos_entidad: dict[str, dict[str, int]] = {}
    emparejadas: list[str] = []
    del_mes = {k: v for k, v in comprobantes.items()
               if periodo and str(v[0].get("Fecha de elaboración") or "")[:7] == periodo}
    candidatos = del_mes or comprobantes
    tarifas_vistas: dict[str, set[Decimal]] = {}
    for q in nomina.values():
        neto = sum((e.v("neto") for e in q.empleados), CERO)
        mejor = min(candidatos.items(), key=lambda kv: abs(
            sum((_d(f.get("Crédito")) for f in kv[1] if str(f.get("Código cuenta contable") or "").startswith("2505")), CERO) - neto))
        lineas = mejor[1]
        emparejadas.append(f"{q.nombre} ↔ {tipo_nomina}-{_nit(mejor[0])}")
        ids = {e.id for e in q.empleados}

        for e in q.empleados:
            propias = [f for f in lineas if _nit(f.get("Identificación tercero") or "") == e.id]
            for lado, conceptos in (("debito", ("salario", "vacaciones_disfrutadas", "comisiones", "incapacidad",
                                                "recargo_nocturno", "extras", "aux_transporte", "aux_datos",
                                                "rodamiento", "otros_pagos")),
                                    ("credito", ("retencion", "cartera", "prestamos", "otras_deducciones", "neto"))):
                for k in conceptos:
                    v = e.v(k)
                    if not v:
                        continue
                    f = next((f for f in propias if abs(_d(f.get("Débito" if lado == "debito" else "Crédito")) - v) <= 1
                              and not str(f.get("Código cuenta contable") or "").startswith(("51053", "2510"))), None)
                    if f is None:
                        continue
                    cuenta = _nit(f["Código cuenta contable"])
                    general = f"nom:{lado}:{k}"
                    if general not in aprendido:
                        aprendido[general] = cuenta
                    elif aprendido[general] != cuenta:
                        aprendido[f"nom:empleado:{e.id}:{k}"] = cuenta
                    propias.remove(f)

            base = sum((e.v(k) for k in SALARIALES), CERO)
            if base:
                # Provisiones y aportes del empleador: débito con su cédula, y la
                # tarifa es la que da ese valor sobre su base. Cesantías y prima
                # pesan lo mismo (8,33 %): en su PUC la subcuenta de cesantías va
                # primero, en el gasto (5105 30 < 5105 36) y en el pasivo.
                pares: dict[str, list[str]] = {}
                valores: dict[str, Decimal] = {}
                for f in propias:
                    if not _d(f.get("Débito")):
                        continue
                    pct = _d(f["Débito"]) / base * 100
                    c = _nit(f["Código cuenta contable"])
                    for k in ("cesantias", "intereses", "vacaciones", *APORTES):
                        t = Decimal(TARIFAS_INICIALES[k])
                        objetivo = t * Decimal("8.33") / 100 if k == "intereses" else t
                        if abs(pct - objetivo) < Decimal("0.01"):
                            pares.setdefault(k, [])
                            if c not in pares[k]:
                                pares[k].append(c)
                            valores.setdefault(k, _d(f["Débito"]))
                            if k in ("cesantias", "vacaciones"):
                                # La tarifa que de verdad usa la empresa: 8,333 % y
                                # no 8,33 %. Con la de la ley redondeada, el pasivo
                                # no se encontraba y la nómina no cuadraba con Siigo.
                                tarifas_vistas.setdefault(k, set()).add(pct.quantize(Decimal("0.001")))
                            break
                if "cesantias" in valores and "intereses" in valores:
                    tarifas_vistas.setdefault("intereses", set()).add(
                        (valores["intereses"] / valores["cesantias"] * 100).quantize(Decimal("0.01")))
                ces_prima = sorted(pares.pop("cesantias", []))
                for k, c in zip(("cesantias", "prima"), ces_prima, strict=False):
                    aprendido.setdefault(f"nom:debito:{k}", c)
                for k, cs in pares.items():
                    aprendido.setdefault(f"nom:debito:{k}", cs[0])

                # El pasivo de cada provisión es el crédito a 2510 por el mismo
                # valor que su gasto, con la cédula del empleado.
                def pasivos(valor: Decimal, propias=propias) -> list[str]:
                    return sorted({_nit(f["Código cuenta contable"]) for f in propias
                                   if str(f.get("Código cuenta contable") or "").startswith("2510")
                                   and abs(_d(f.get("Crédito")) - valor) <= 1})
                if "cesantias" in valores:
                    for k, c in zip(("cesantias", "prima"), pasivos(valores["cesantias"]), strict=False):
                        aprendido.setdefault(f"nom:credito:{k}", c)
                for k in ("intereses", "vacaciones"):
                    if k in valores:
                        cs = pasivos(valores[k])
                        if cs:
                            aprendido.setdefault(f"nom:credito:{k}", cs[0])

            # Entidades: líneas cuyo tercero no es empleado, con el valor de él.
            ajenas = [f for f in lineas if _nit(f.get("Identificación tercero") or "") not in ids
                      and _d(f.get("Crédito"))]
            esperado = {"salud": e.v("salud"),
                        "pension": e.v("pension"),
                        "caja": _peso(base * Decimal("0.04")),
                        "arl": _peso(base * Decimal("0.00522"))}
            for aporte, v in esperado.items():
                if not v:
                    continue
                for f in ajenas:
                    c = _nit(f.get("Código cuenta contable") or "")
                    if abs(_d(f["Crédito"]) - v) > 1:
                        continue
                    familia = {"salud": "237005", "pension": "237045", "caja": "237010", "arl": "237006"}[aporte]
                    if not c.startswith(familia):
                        continue
                    valor = f"{c}|{_nit(f['Identificación tercero'])}"
                    aprendido[f"nom:entidad:{e.id}:{aporte}"] = valor
                    votos = votos_entidad.setdefault(aporte, {})
                    votos[valor] = votos.get(valor, 0) + 1
                    break

    for aporte, votos in votos_entidad.items():
        aprendido[f"nom:entidad:*:{aporte}"] = max(votos.items(), key=lambda kv: kv[1])[0]
    # Solo si todos los empleados dan la misma: una sola que no cuadre es un
    # caso suyo, no la tarifa de la empresa.
    for k, vistas in tarifas_vistas.items():
        if len(vistas) == 1:
            t = format(next(iter(vistas)).normalize(), "f")
            aprendido[f"nom:tarifa:{k}"] = t
            if k == "cesantias":
                aprendido["nom:tarifa:prima"] = t

    # Lo que la plantilla todavía no sabe, para decirlo con nombre.
    p = plantilla({**siigo_module.config(conn), **aprendido})
    diferencias = []
    for q in nomina.values():
        _lineas, faltan = armar(q, p)
        diferencias.extend(f for f in faltan if f not in diferencias)

    if not dry_run:
        siigo_module.guardar_config(conn, aprendido)
    return {
        "quincenas": emparejadas, "aprendido": len(aprendido),
        "cuentas": {k: v for k, v in sorted(aprendido.items()) if not k.startswith("nom:entidad:")
                    and not k.startswith("nom:empleado:")},
        "entidades": sorted({v for k, v in aprendido.items() if k.startswith("nom:entidad:*")}),
        "faltan": diferencias, "dry_run": dry_run,
    }


# ─────────────────────── la nómina del mes, para aprobar y exportar ───────────

def _fecha_de(periodo: str, quincena: str) -> str:
    import calendar
    anio, mes = int(periodo[:4]), int(periodo[5:7])
    dia = 15 if quincena == "1Q" else calendar.monthrange(anio, mes)[1]
    return date(anio, mes, dia).isoformat()


def generar(conn, periodo: str, ruta_nomina: str | Path) -> dict[str, Any]:
    """Arma los comprobantes de las dos quincenas del mes. Lo aprobado no se rehace."""
    from . import siigo as siigo_module

    p = plantilla(siigo_module.config(conn))
    nomina = leer_nomina(ruta_nomina)
    if not nomina:
        raise ValueError("El Excel no tiene hojas «1Q» ni «2Q» con la liquidación por empleado.")
    resumen = []
    for q in nomina.values():
        ya = conn.execute("SELECT id, aprobado FROM nomina_comprobante WHERE periodo = ? AND quincena = ?",
                          (periodo, q.nombre)).fetchone()
        if ya and ya["aprobado"]:
            resumen.append({"quincena": q.nombre, "aprobado": True})
            continue
        lineas, faltan = armar(q, p)
        # El nombre de cada empleado, para reconocerlo en la pantalla de empleados.
        siigo_module.guardar_config(conn, {f"nom:nombre:{e.id}": e.nombre for e in q.empleados
                                           if e.nombre and not p.get(f"nom:nombre:{e.id}")})
        debito = sum((x.debito for x in lineas), CERO)
        credito = sum((x.credito for x in lineas), CERO)
        avisos = [f"Falta {f}" for f in faltan]
        ajuste = _ajustar_redondeo(lineas, debito - credito)
        if ajuste:
            credito += ajuste
            avisos.append(
                f"Se ajustó el neto en {ajuste} pesos por el redondeo al peso (el medio peso del "
                "auxilio de transporte), como se hace en Siigo.")
        smmlv = _d(p.get(f"nom:smmlv:{periodo[:4]}")) or None
        if smmlv is None:
            avisos.append(f"Falta el salario mínimo de {periodo[:4]} (en Empleados): sin él no se "
                          "revisan el fondo de solidaridad ni la exoneración.")
        avisos.extend(revisar(q, p, smmlv))
        if debito != credito:
            avisos.append(f"La quincena no cuadra por {debito - credito} pesos: revise el neto del Excel.")
        if q.columnas_sin_leer:
            avisos.append("Columnas del Excel que no se leyeron: " + ", ".join(q.columnas_sin_leer))
        import json
        if ya:
            conn.execute("DELETE FROM nomina_comprobante WHERE id = ?", (ya["id"],))
        cur = conn.execute(
            "INSERT INTO nomina_comprobante(periodo, quincena, fecha, empleados, avisos, fuente)"
            " VALUES (?,?,?,?,?,?)",
            (periodo, q.nombre, _fecha_de(periodo, q.nombre), len(q.empleados),
             json.dumps(avisos, ensure_ascii=False) if avisos else None, Path(ruta_nomina).name))
        cid = int(cur.lastrowid)
        for orden, x in enumerate(lineas):
            conn.execute(
                "INSERT INTO nomina_linea(comprobante_id, orden, cuenta, tercero, descripcion, debito, credito)"
                " VALUES (?,?,?,?,?,?,?)",
                (cid, orden, x.cuenta, x.tercero, x.descripcion, str(x.debito), str(x.credito)))
        resumen.append({"quincena": q.nombre, "aprobado": False, "lineas": len(lineas),
                        "debito": str(debito), "credito": str(credito), "cuadra": debito == credito,
                        "avisos": avisos})
    conn.commit()
    return {"periodo": periodo, "quincenas": resumen}


def listar(conn, periodo: str) -> list[dict[str, Any]]:
    import json
    out = []
    for fila in conn.execute(
            "SELECT * FROM nomina_comprobante WHERE periodo = ? ORDER BY quincena", (periodo,)).fetchall():
        c = dict(fila)
        c["avisos"] = json.loads(c["avisos"]) if c["avisos"] else []
        c["lineas"] = [dict(r) for r in conn.execute(
            "SELECT * FROM nomina_linea WHERE comprobante_id = ? ORDER BY orden", (c["id"],))]
        c["debito"] = str(sum((_d(x["debito"]) for x in c["lineas"]), CERO))
        c["credito"] = str(sum((_d(x["credito"]) for x in c["lineas"]), CERO))
        por_cuenta: dict[str, list[Decimal]] = {}
        for x in c["lineas"]:
            t = por_cuenta.setdefault(x["cuenta"] or "falta", [CERO, CERO])
            t[0] += _d(x["debito"])
            t[1] += _d(x["credito"])
        c["por_cuenta"] = [{"cuenta": k, "debito": str(v[0]), "credito": str(v[1])}
                           for k, v in sorted(por_cuenta.items())]
        out.append(c)
    return out


def aprobar(conn, comprobante_id: int, aprobado: bool = True) -> None:
    fila = conn.execute("SELECT * FROM nomina_comprobante WHERE id = ?", (int(comprobante_id),)).fetchone()
    if fila is None:
        raise ValueError(f"El comprobante de nómina {comprobante_id} no existe.")
    if aprobado and conn.execute(
            "SELECT 1 FROM nomina_linea WHERE comprobante_id = ? AND cuenta IS NULL", (fila["id"],)).fetchone():
        raise ValueError("Hay líneas sin cuenta: complete la plantilla de nómina y vuelva a armarla.")
    conn.execute("UPDATE nomina_comprobante SET aprobado = ?, aprobado_at = CASE WHEN ? THEN datetime('now') END"
                 " WHERE id = ?", (1 if aprobado else 0, 1 if aprobado else 0, fila["id"]))
    conn.commit()
