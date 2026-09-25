"""Cola de personas del vigía de citas DIAN (D-104), en contab.db.

El contador agrega aquí a quienes necesitan cita; el sidecar DIAN (apps/dian-rut/citas.py) toma
la primera pendiente, la lleva por el portal y la marca `en_curso` cuando llega hasta donde sabe
llegar. El contador termina la reserva y la marca `agendada` (o la devuelve a `pendiente`).
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from . import program_db

ESTADOS = ("pendiente", "en_curso", "agendada")
_CAMPOS = ("id", "cedula", "nombre", "correo", "celular", "autoriza_tratamiento", "estado",
           "detalle", "agendada_at", "created_at", "updated_at")


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = program_db._conn()
    try:
        yield conn
    finally:
        conn.close()


def _fila(r) -> dict:
    d = {k: r[k] for k in _CAMPOS}
    d["autoriza_tratamiento"] = bool(d["autoriza_tratamiento"])
    return d


def _limpio(v) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError("los datos de la persona deben ser texto")
    v = v.strip()
    return v or None


def list_personas() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(f"SELECT {', '.join(_CAMPOS)} FROM cita_persona ORDER BY id").fetchall()
    return [_fila(r) for r in rows]


def save_persona(datos: dict) -> dict:
    """Crea o actualiza (si trae `id`) una persona. La cédula es obligatoria y única."""
    cedula = re.sub(r"[.\s-]", "", _limpio(datos.get("cedula")) or "")
    if not re.fullmatch(r"\d{5,12}", cedula):
        raise ValueError("La cédula debe tener solo números (entre 5 y 12 dígitos).")
    correo = _limpio(datos.get("correo"))
    if correo and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        raise ValueError("El correo no parece válido.")
    valores = (cedula, _limpio(datos.get("nombre")), correo, _limpio(datos.get("celular")),
               1 if datos.get("autoriza_tratamiento") else 0)
    with _db() as conn:
        try:
            if datos.get("id"):
                cur = conn.execute(
                    "UPDATE cita_persona SET cedula=?, nombre=?, correo=?, celular=?, autoriza_tratamiento=?,"
                    " updated_at=datetime('now') WHERE id=?", (*valores, int(datos["id"])))
                if not cur.rowcount:
                    raise ValueError("Esa persona ya no existe.")
                pid = int(datos["id"])
            else:
                pid = conn.execute(
                    "INSERT INTO cita_persona(cedula, nombre, correo, celular, autoriza_tratamiento)"
                    " VALUES (?, ?, ?, ?, ?)", valores).lastrowid
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Ya hay una persona con la cédula {cedula}.") from e
        r = conn.execute(f"SELECT {', '.join(_CAMPOS)} FROM cita_persona WHERE id=?", (pid,)).fetchone()
    return _fila(r)


def delete_persona(pid: int) -> bool:
    with _db() as conn:
        return conn.execute("DELETE FROM cita_persona WHERE id=?", (int(pid),)).rowcount > 0


def set_estado(pid: int, estado: str, detalle: str | None = None) -> dict:
    """Lo usa el contador desde Contab: marcar `agendada` o devolver a `pendiente`."""
    if estado not in ESTADOS:
        raise ValueError(f"estado inválido: {estado}")
    with _db() as conn:
        cur = conn.execute(
            "UPDATE cita_persona SET estado=?, detalle=COALESCE(?, detalle),"
            " agendada_at=CASE WHEN ?='agendada' THEN datetime('now') ELSE NULL END,"
            " updated_at=datetime('now') WHERE id=?", (estado, detalle, estado, int(pid)))
        if not cur.rowcount:
            raise ValueError("Esa persona ya no existe.")
        r = conn.execute(f"SELECT {', '.join(_CAMPOS)} FROM cita_persona WHERE id=?", (int(pid),)).fetchone()
    return _fila(r)
