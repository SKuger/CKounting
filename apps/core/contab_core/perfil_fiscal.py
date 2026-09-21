"""Perfil fiscal de la empresa y sus municipios de ICA (Fase 1.1).

Qué es la empresa ante la DIAN: régimen, responsabilidad de IVA, si es agente de
retención o autorretenedora, gran contribuyente, actividad CIIU, y en qué
municipios declara ICA y a qué tarifa.

**Todo va fechado.** El perfil no es una fila sino una lista de versiones con
`vigencia_desde`, y se consulta la vigente a una fecha. La razón no es prolijidad:
a una empresa la nombran autorretenedora en agosto, y la causación de marzo tiene
que seguir calculándose con lo que la empresa era en marzo. Un perfil sin fecha
obliga a rehacer el pasado cada vez que cambia el presente.

Sin perfil guardado, `perfil_vigente` devuelve None y quien consuma esto debe
tratar la empresa como "sin configurar", nunca inventar un valor por defecto: una
retención calculada sobre un supuesto es peor que una retención no calculada.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .storage import transaction

REGIMENES = ("ordinario", "simple")
PERIODICIDADES_IVA = ("bimestral", "cuatrimestral")

# Las banderas del perfil, en el orden en que se muestran y se guardan.
BANDERAS = (
    "responsable_iva",
    "agente_retefuente",
    "agente_reteiva",
    "agente_reteica",
    "autorretenedor_renta",
    "gran_contribuyente",
)

_FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PerfilFiscalError(ValueError):
    """Error de validación del perfil, con mensaje en español para la UI."""


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "").strip())


def _fecha(v: Any, campo: str) -> str:
    f = _norm(v)
    if not _FECHA_RE.match(f):
        raise PerfilFiscalError(f"{campo} debe venir como AAAA-MM-DD (llegó «{f}»)")
    try:
        date.fromisoformat(f)
    except ValueError as exc:
        raise PerfilFiscalError(f"{campo} no es una fecha real: «{f}»") from exc
    return f


def _bandera(v: Any) -> int:
    return 1 if v in (1, True, "1", "true", "True", "si", "sí", "Sí", "Si") else 0


def tarifa_a_decimal(v: Any) -> Decimal:
    """Lee una tarifa por mil como Decimal. Acepta coma o punto decimal.

    Va por Decimal y no por float por lo mismo que los importes (D-075): una
    tarifa del 6,9 por mil en binario no es 6,9, y esa diferencia termina en una
    retención que no cuadra con la que calculó el cliente.
    """
    s = _norm(v).replace(",", ".")
    if not s:
        raise PerfilFiscalError("la tarifa de ICA no puede quedar vacía")
    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise PerfilFiscalError(f"la tarifa de ICA no es un número: «{v}»") from exc
    if d < 0:
        raise PerfilFiscalError("la tarifa de ICA no puede ser negativa")
    return d


def _fila_perfil(row) -> dict[str, Any]:
    d = dict(row)
    for b in BANDERAS:
        d[b] = bool(d.get(b, 0))
    return d


def perfil_vigente(conn, *, fecha: str | None = None) -> dict[str, Any] | None:
    """El perfil en vigor a `fecha` (por defecto hoy), o None si no hay ninguno.

    "En vigor" = el de mayor `vigencia_desde` que no sea posterior a la fecha. Un
    perfil con vigencia futura existe pero todavía no manda.
    """
    f = _fecha(fecha, "fecha") if fecha else date.today().isoformat()
    row = conn.execute(
        "SELECT * FROM empresa_perfil_fiscal WHERE vigencia_desde <= ? "
        "ORDER BY vigencia_desde DESC LIMIT 1",
        (f,),
    ).fetchone()
    return _fila_perfil(row) if row else None


def listar_perfiles(conn) -> list[dict[str, Any]]:
    """Todas las versiones del perfil, de la más reciente a la más antigua."""
    return [
        _fila_perfil(r)
        for r in conn.execute(
            "SELECT * FROM empresa_perfil_fiscal ORDER BY vigencia_desde DESC"
        ).fetchall()
    ]


def guardar_perfil(conn, data: dict[str, Any]) -> dict[str, Any]:
    """Crea o reemplaza la versión del perfil que empieza en `vigencia_desde`.

    Guardar dos veces la misma fecha actualiza esa versión; no crea una segunda.
    """
    vigencia = _fecha(data.get("vigencia_desde"), "vigencia_desde")

    regimen = _norm(data.get("regimen")).lower() or "ordinario"
    if regimen not in REGIMENES:
        raise PerfilFiscalError(f"régimen desconocido: «{regimen}» (esperado: {', '.join(REGIMENES)})")

    banderas = {b: _bandera(data.get(b)) for b in BANDERAS}

    periodicidad = _norm(data.get("periodicidad_iva")).lower() or None
    if periodicidad and periodicidad not in PERIODICIDADES_IVA:
        raise PerfilFiscalError(
            f"periodicidad de IVA desconocida: «{periodicidad}» "
            f"(esperado: {', '.join(PERIODICIDADES_IVA)})"
        )
    if banderas["responsable_iva"] and not periodicidad:
        raise PerfilFiscalError(
            "una empresa responsable de IVA declara bimestral o cuatrimestralmente; "
            "falta la periodicidad"
        )
    if not banderas["responsable_iva"]:
        periodicidad = None

    ciiu = _norm(data.get("ciiu")) or None
    if ciiu and not re.fullmatch(r"\d{4}", ciiu):
        raise PerfilFiscalError(f"el código CIIU son 4 dígitos (llegó «{ciiu}»)")

    with transaction(conn):
        conn.execute(
            """
            INSERT INTO empresa_perfil_fiscal
              (vigencia_desde, regimen, responsable_iva, periodicidad_iva,
               agente_retefuente, agente_reteiva, agente_reteica,
               autorretenedor_renta, gran_contribuyente, ciiu, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vigencia_desde) DO UPDATE SET
              regimen = excluded.regimen,
              responsable_iva = excluded.responsable_iva,
              periodicidad_iva = excluded.periodicidad_iva,
              agente_retefuente = excluded.agente_retefuente,
              agente_reteiva = excluded.agente_reteiva,
              agente_reteica = excluded.agente_reteica,
              autorretenedor_renta = excluded.autorretenedor_renta,
              gran_contribuyente = excluded.gran_contribuyente,
              ciiu = excluded.ciiu,
              notas = excluded.notas
            """,
            (
                vigencia,
                regimen,
                banderas["responsable_iva"],
                periodicidad,
                banderas["agente_retefuente"],
                banderas["agente_reteiva"],
                banderas["agente_reteica"],
                banderas["autorretenedor_renta"],
                banderas["gran_contribuyente"],
                ciiu,
                _norm(data.get("notas")) or None,
            ),
        )
    row = conn.execute(
        "SELECT * FROM empresa_perfil_fiscal WHERE vigencia_desde = ?", (vigencia,)
    ).fetchone()
    return _fila_perfil(row)


def eliminar_perfil(conn, vigencia_desde: str) -> None:
    """Borra una versión del perfil. La última que quede no se protege: una
    empresa puede quedarse legítimamente sin perfil configurado."""
    v = _fecha(vigencia_desde, "vigencia_desde")
    with transaction(conn):
        conn.execute("DELETE FROM empresa_perfil_fiscal WHERE vigencia_desde = ?", (v,))


def listar_municipios_ica(conn, *, fecha: str | None = None) -> list[dict[str, Any]]:
    """Municipios de ICA. Con `fecha`, solo los vigentes a esa fecha — y de cada
    (municipio, actividad) únicamente la versión que manda ese día."""
    if fecha is None:
        rows = conn.execute(
            "SELECT * FROM empresa_municipio_ica ORDER BY municipio, actividad, vigencia_desde DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    f = _fecha(fecha, "fecha")
    rows = conn.execute(
        """
        SELECT m.* FROM empresa_municipio_ica m
        WHERE m.vigencia_desde <= ?
          AND m.vigencia_desde = (
            SELECT MAX(m2.vigencia_desde) FROM empresa_municipio_ica m2
            WHERE m2.municipio = m.municipio
              AND IFNULL(m2.actividad, '') = IFNULL(m.actividad, '')
              AND m2.vigencia_desde <= ?
          )
        ORDER BY m.municipio, m.actividad
        """,
        (f, f),
    ).fetchall()
    return [dict(r) for r in rows]


def guardar_municipio_ica(conn, data: dict[str, Any]) -> dict[str, Any]:
    """Crea o actualiza la tarifa de un (municipio, actividad) desde una fecha."""
    municipio = _norm(data.get("municipio"))
    if not municipio:
        raise PerfilFiscalError("el municipio no puede quedar vacío")
    actividad = _norm(data.get("actividad")) or None
    vigencia = _fecha(data.get("vigencia_desde"), "vigencia_desde")
    tarifa = tarifa_a_decimal(data.get("tarifa_por_mil"))

    codigo_dane = _norm(data.get("codigo_dane")) or None
    if codigo_dane and not re.fullmatch(r"\d{5}", codigo_dane):
        raise PerfilFiscalError(f"el código DANE del municipio son 5 dígitos (llegó «{codigo_dane}»)")

    with transaction(conn):
        conn.execute(
            """
            INSERT INTO empresa_municipio_ica
              (municipio, codigo_dane, actividad, tarifa_por_mil, vigencia_desde)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(municipio, actividad, vigencia_desde) DO UPDATE SET
              codigo_dane = excluded.codigo_dane,
              tarifa_por_mil = excluded.tarifa_por_mil
            """,
            (municipio, codigo_dane, actividad, str(tarifa), vigencia),
        )
    row = conn.execute(
        "SELECT * FROM empresa_municipio_ica WHERE municipio = ? "
        "AND IFNULL(actividad, '') = IFNULL(?, '') AND vigencia_desde = ?",
        (municipio, actividad, vigencia),
    ).fetchone()
    return dict(row)


def eliminar_municipio_ica(conn, municipio_id: int) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM empresa_municipio_ica WHERE id = ?", (int(municipio_id),))
