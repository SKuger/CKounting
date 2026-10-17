"""Catálogo de terceros de la empresa (Fase 1.3).

El **tercero** es la contraparte: si la fila del reporte DIAN es `Recibido`, el
tercero es el emisor —el proveedor—; si es `Emitido`, es el receptor —el cliente—.
Esa regla está en `docs/glosario.md` y es la que decide de qué columnas del Excel
sale cada tercero.

Hasta ahora los terceros existían solo implícitos, repetidos en cada fila. Aquí
pasan a ser una tabla, porque la Fase 4 necesita colgarles algo que la fila no
tiene: qué responsabilidades tienen ante la DIAN, qué actividad económica y en qué
municipio —de eso dependen las retenciones— y qué regla de causación se les aplicó
la vez pasada.

Vive **dentro de la .db de cada empresa** (D-100). El mismo proveedor se consulta
una vez por empresa, que es el costo que se aceptó a cambio de no abrirle una
excepción a D-003.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from . import nit as nit_module
from .storage import transaction

ORIGENES = ("excel", "rut", "manual")


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "").strip())


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _fila(row) -> dict[str, Any]:
    d = dict(row)
    crudo = d.get("responsabilidades")
    if crudo:
        try:
            d["responsabilidades"] = json.loads(crudo)
        except (TypeError, ValueError):
            # Un JSON ilegible no puede tumbar el listado entero del catálogo.
            d["responsabilidades"] = []
    else:
        d["responsabilidades"] = []
    return d


def tercero_de_la_fila(data: dict[str, Any], grupo: str | None) -> tuple[str, str] | None:
    """(NIT, nombre) de la contraparte de una fila del Excel DIAN, o None.

    `Recibido` → el emisor; `Emitido` → el receptor. Un grupo que no sea ninguno
    de los dos se omite en vez de adivinarse: si la DIAN añade un valor nuevo,
    preferimos un tercero que falta a un tercero inventado del lado equivocado.
    """
    g = _norm(grupo).lower()
    if g == "recibido":
        crudo_nit, crudo_nombre = data.get("NIT Emisor"), data.get("Nombre Emisor")
    elif g == "emitido":
        crudo_nit, crudo_nombre = data.get("NIT Receptor"), data.get("Nombre Receptor")
    else:
        return None

    nit = nit_module.normalize(_norm(crudo_nit))
    if not nit:
        return None
    return nit, _norm(crudo_nombre)


def sembrar_desde_excel(conn) -> dict[str, Any]:
    """Crea o completa los terceros a partir de las filas ya importadas.

    Es idempotente: al segundo pase no duplica nada. Un tercero que ya existe
    solo recibe la razón social si no tenía —lo que vino del RUT o escribió el
    contador manda sobre lo que trae el Excel, que llega con espacios de más y
    sin tildes consistentes.
    """
    vistos: dict[str, str] = {}
    for r in conn.execute("SELECT data_json, grupo FROM excel_row").fetchall():
        try:
            data = json.loads(r["data_json"])
        except (TypeError, ValueError):
            continue
        par = tercero_de_la_fila(data, r["grupo"])
        if par is None:
            continue
        nit, nombre = par
        # Gana el primer nombre no vacío: el resto de filas del mismo tercero
        # traen el mismo texto con espaciados distintos.
        if nombre and not vistos.get(nit):
            vistos[nit] = nombre
        vistos.setdefault(nit, "")

    if not vistos:
        return {"encontrados": 0, "nuevos": 0, "completados": 0}

    existentes = {
        r["nit"]: r["razon_social"]
        for r in conn.execute("SELECT nit, razon_social FROM tercero").fetchall()
    }
    nuevos = [(n, v) for n, v in vistos.items() if n not in existentes]
    completados = [
        (n, v) for n, v in vistos.items()
        if n in existentes and v and not _norm(existentes[n])
    ]

    with transaction(conn):
        if nuevos:
            conn.executemany(
                "INSERT INTO tercero(nit, dv, razon_social, origen) VALUES (?, ?, ?, 'excel')",
                [(n, nit_module.compute_dv(n), v) for n, v in nuevos],
            )
        if completados:
            conn.executemany(
                "UPDATE tercero SET razon_social = ?, updated_at = ? WHERE nit = ?",
                [(v, _ahora(), n) for n, v in completados],
            )

    return {"encontrados": len(vistos), "nuevos": len(nuevos), "completados": len(completados)}


def listar(conn, *, buscar: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
    q = "SELECT * FROM tercero"
    params: list[Any] = []
    termino = _norm(buscar)
    if termino:
        q += " WHERE nit LIKE ? OR razon_social LIKE ?"
        params += [f"%{termino}%", f"%{termino}%"]
    q += " ORDER BY razon_social COLLATE NOCASE, nit LIMIT ? OFFSET ?"
    params += [int(limit), int(offset)]
    return [_fila(r) for r in conn.execute(q, params).fetchall()]


def contar(conn) -> dict[str, int]:
    """Cuántos terceros hay y cuántos tienen el RUT consultado — la diferencia es
    el trabajo que le falta al catálogo antes de poder calcular retenciones."""
    total = conn.execute("SELECT COUNT(*) FROM tercero").fetchone()[0]
    con_rut = conn.execute(
        "SELECT COUNT(*) FROM tercero WHERE consultado_at IS NOT NULL"
    ).fetchone()[0]
    return {"total": total, "con_rut": con_rut, "sin_rut": total - con_rut}


def obtener(conn, nit: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM tercero WHERE nit = ?", (nit_module.normalize(_norm(nit)),)
    ).fetchone()
    return _fila(row) if row else None


def guardar(conn, data: dict[str, Any]) -> dict[str, Any]:
    """Alta o edición manual de un tercero. El NIT identifica la fila."""
    nit = nit_module.normalize(_norm(data.get("nit")))
    if not nit:
        raise ValueError("El tercero necesita un NIT")

    responsabilidades = data.get("responsabilidades")
    if isinstance(responsabilidades, str):
        responsabilidades = [r for r in re.split(r"[,\s]+", responsabilidades) if r]
    resp_json = json.dumps(responsabilidades) if responsabilidades else None

    ciiu = _norm(data.get("ciiu")) or None
    if ciiu and not re.fullmatch(r"\d{4}", ciiu):
        raise ValueError(f"El código CIIU son 4 dígitos (llegó «{ciiu}»)")

    with transaction(conn):
        conn.execute(
            """
            INSERT INTO tercero(nit, dv, razon_social, tipo, responsabilidades, ciiu,
                                municipio, estado_rut, origen, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?)
            ON CONFLICT(nit) DO UPDATE SET
              dv = excluded.dv,
              razon_social = excluded.razon_social,
              tipo = excluded.tipo,
              responsabilidades = excluded.responsabilidades,
              ciiu = excluded.ciiu,
              municipio = excluded.municipio,
              estado_rut = excluded.estado_rut,
              notas = excluded.notas,
              updated_at = ?
            """,
            (
                nit,
                _norm(data.get("dv")) or nit_module.compute_dv(nit),
                _norm(data.get("razon_social")),
                _norm(data.get("tipo")) or None,
                resp_json,
                ciiu,
                _norm(data.get("municipio")) or None,
                _norm(data.get("estado_rut")) or None,
                _norm(data.get("notas")) or None,
                _ahora(),
            ),
        )
    return obtener(conn, nit)


# ── Lo que hay que saber de un tercero para retenerle bien ────────────────────
# La consulta pública de la DIAN devuelve razón social y tipo, y nada más: las
# responsabilidades y el estado del RUT están en el **certificado de RUT**, que
# es un PDF que el contribuyente descarga autenticado. No hay de dónde rasparlas,
# así que se escriben a mano — y por eso tienen que ser fáciles de escribir bien.
#
# Esta lista NO es el catálogo completo de responsabilidades del RUT (casilla 53,
# que pasa de cincuenta): son **las que cambian el cálculo de una retención**. Si
# un tercero tiene otra, se escribe igual y se guarda; esto solo evita que las
# importantes dependan de teclearlas sin una errata.
CODIGOS_RESPONSABILIDAD: dict[str, str] = {
    "O-13": "Gran contribuyente",
    "O-15": "Autorretenedor",
    "O-23": "Agente de retención de IVA",
    "O-47": "Régimen simple de tributación",
    "O-48": "Responsable de IVA",
    "O-49": "No responsable de IVA",
}

# El estado del RUT decide si al tercero se le puede seguir comprando. Lo lee la
# validación V7, que sin este campo lleno no se dispara nunca.
ESTADOS_RUT: tuple[str, ...] = ("ACTIVO", "CANCELADO", "SUSPENDIDO", "INACTIVO")


def tiene_responsabilidad(tercero: dict[str, Any] | None, codigo: str) -> bool:
    """¿El tercero declara esta responsabilidad? Tolera el formato que sea."""
    if not tercero:
        return False
    crudas = tercero.get("responsabilidades") or []
    if isinstance(crudas, str):
        crudas = [x for x in re.split(r"[,\s]+", crudas) if x]
    objetivo = codigo.strip().upper().replace(" ", "")
    return any(str(x).strip().upper().replace(" ", "") == objetivo for x in crudas)


def actualizar_desde_rut(conn, nit: str, datos: dict[str, Any]) -> dict[str, Any] | None:
    """Vuelca en el tercero lo que devolvió la consulta del RUT y sella la fecha.

    Solo pisa los campos que la consulta trajo con contenido: una consulta que no
    encontró la razón social no puede borrar la que ya estaba.
    """
    nit_n = nit_module.normalize(_norm(nit))
    if not obtener(conn, nit_n):
        with transaction(conn):
            conn.execute(
                "INSERT INTO tercero(nit, dv, origen) VALUES (?, ?, 'rut')",
                (nit_n, nit_module.compute_dv(nit_n)),
            )

    campos: list[str] = []
    valores: list[Any] = []
    for columna, clave in (
        ("razon_social", "razon_social"),
        ("tipo", "tipo"),
        ("ciiu", "ciiu"),
        ("municipio", "municipio"),
        ("estado_rut", "estado_rut"),
    ):
        valor = _norm(datos.get(clave))
        if valor:
            campos.append(f"{columna} = ?")
            valores.append(valor)

    responsabilidades = datos.get("responsabilidades")
    if responsabilidades:
        campos.append("responsabilidades = ?")
        valores.append(json.dumps(responsabilidades))

    campos += ["consultado_at = ?", "origen = 'rut'", "updated_at = ?"]
    ahora = _ahora()
    valores += [ahora, ahora, nit_n]

    with transaction(conn):
        conn.execute(f"UPDATE tercero SET {', '.join(campos)} WHERE nit = ?", valores)
    return obtener(conn, nit_n)


def pendientes_de_rut(conn, *, solo_faltantes: bool = True) -> list[dict[str, Any]]:
    """Los terceros a los que hay que consultarles el RUT."""
    q = "SELECT nit, dv, razon_social FROM tercero"
    if solo_faltantes:
        q += " WHERE consultado_at IS NULL"
    q += " ORDER BY razon_social COLLATE NOCASE, nit"
    return [dict(r) for r in conn.execute(q).fetchall()]
