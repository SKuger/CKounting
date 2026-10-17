"""Guarda en la base lo que el XML dice — tareas 3.1 y 3.2 del plan.

`xml_ubl` solo lee y no sabe que existe una base de datos; aquí está todo lo que
toca SQLite. Separarlos deja el parser probable sin montar nada y evita que una
mejora de la lectura arrastre cambios de esquema.

**El caché tiene el mismo contrato que el de los PDF** (D-067): una entrada se
vuelve a leer cuando cambia `(mtime, tamaño)` o cuando sube `PARSER_VERSION`. Sin
lo segundo, mejorar el parser no llega nunca a los documentos ya leídos — y el
contador vería para siempre la lectura que hizo la versión vieja.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import xml_ubl
from .log import warn

EXTENSIONES = (".xml",)


@dataclass
class Resumen:
    leidos: int = 0
    desde_cache: int = 0
    fallidos: int = 0
    carpeta: str = ""
    errores: list[dict[str, str]] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "leidos": self.leidos, "desde_cache": self.desde_cache,
            "fallidos": self.fallidos, "carpeta": self.carpeta,
            "errores": self.errores[:50],
        }


def _borrar_documento(conn: sqlite3.Connection, cufe: str) -> None:
    """Las hijas se van con la madre: el ON DELETE CASCADE necesita la pragma."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM documento WHERE cufe = ?", (cufe,))


def guardar(conn: sqlite3.Connection, doc: xml_ubl.Documento, xml_path: str | Path) -> int:
    """Escribe el documento entero. Re-escribe si ese CUFE ya estaba.

    Se borra y se vuelve a insertar en vez de actualizar campo por campo: un
    documento releído con un parser mejor puede tener MENOS líneas que antes —si
    la versión vieja las duplicaba—, y un `UPDATE` dejaría las sobrantes.
    """
    if not doc.cufe:
        raise ValueError("Un documento sin CUFE no se puede guardar: es su llave.")
    _borrar_documento(conn, doc.cufe)
    cur = conn.execute(
        "INSERT INTO documento(cufe, tipo, numero, fecha_emision, hora_emision, moneda,"
        " emisor_nit, emisor_nombre, receptor_nit, receptor_nombre,"
        " subtotal, total_impuestos, total, xml_path, parser_version)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc.cufe, doc.tipo, doc.numero, doc.fecha_emision, doc.hora_emision, doc.moneda,
         doc.emisor_nit, doc.emisor_nombre, doc.receptor_nit, doc.receptor_nombre,
         _t(doc.subtotal), _t(doc.total_impuestos), _t(doc.total),
         str(xml_path), xml_ubl.PARSER_VERSION),
    )
    doc_id = int(cur.lastrowid)

    for linea in doc.lineas:
        cur = conn.execute(
            "INSERT INTO documento_linea(documento_id, numero, descripcion, cantidad,"
            " valor_unitario, total) VALUES (?,?,?,?,?,?)",
            (doc_id, linea.numero, linea.descripcion, _t(linea.cantidad),
             _t(linea.valor_unitario), _t(linea.total)),
        )
        linea_id = int(cur.lastrowid)
        for imp in linea.impuestos:
            _insertar_impuesto(conn, doc_id, linea_id, imp)

    for imp in doc.impuestos:
        _insertar_impuesto(conn, doc_id, None, imp)

    for ref in doc.referencias:
        conn.execute(
            "INSERT INTO documento_referencia(documento_id, cufe_referido, numero_referido,"
            " fecha_referida, codigo_motivo, motivo) VALUES (?,?,?,?,?,?)",
            (doc_id, ref.cufe, ref.numero, ref.fecha, ref.codigo_motivo, ref.motivo),
        )
    return doc_id


def _t(x) -> str | None:
    return None if x is None else str(x)


def _insertar_impuesto(conn, doc_id: int, linea_id: int | None,
                       imp: xml_ubl.Impuesto) -> None:
    conn.execute(
        "INSERT INTO documento_impuesto(documento_id, linea_id, tipo, nombre, base,"
        " tarifa, valor, es_retencion) VALUES (?,?,?,?,?,?,?,?)",
        (doc_id, linea_id, imp.tipo, imp.nombre, _t(imp.base), _t(imp.tarifa),
         _t(imp.valor), 1 if imp.es_retencion else 0),
    )


def indexar_carpeta(
    conn: sqlite3.Connection,
    carpeta: str | Path,
    progreso: Callable[[str], None] | None = None,
) -> Resumen:
    """Lee los XML de una carpeta, saltándose los que no cambiaron."""
    carpeta = Path(carpeta)
    res = Resumen(carpeta=str(carpeta))
    avisa = progreso or (lambda _m: None)
    if not carpeta.is_dir():
        # Que la carpeta no exista no es «no hay documentos» (D-080).
        raise FileNotFoundError(f"La carpeta de soportes no existe: {carpeta}")

    archivos = sorted(x for x in carpeta.iterdir()
                      if x.is_file() and x.suffix.lower() in EXTENSIONES)
    for i, ruta in enumerate(archivos, 1):
        st = ruta.stat()
        mtime, size = int(st.st_mtime), st.st_size
        ya = conn.execute(
            "SELECT estado FROM xml_index WHERE folder_path = ? AND xml_path = ?"
            " AND xml_mtime = ? AND xml_size_bytes = ? AND parser_version = ?",
            (str(carpeta), str(ruta), mtime, size, xml_ubl.PARSER_VERSION),
        ).fetchone()
        if ya is not None:
            res.desde_cache += 1
            continue

        avisa(f"Leyendo XML {i} de {len(archivos)}…")
        lectura = xml_ubl.leer(ruta)
        if lectura.documento is not None and lectura.documento.cufe:
            try:
                guardar(conn, lectura.documento, ruta)
            except Exception as exc:
                lectura = xml_ubl.Lectura(
                    None, xml_ubl.ESTADO_ERROR,
                    f"No se pudo guardar: {exc.__class__.__name__}: {exc}")
                warn(f"xml: no se pudo guardar {ruta}: {exc}")

        conn.execute(
            "INSERT INTO xml_index(folder_path, xml_path, xml_mtime, xml_size_bytes,"
            " estado, error, parser_version) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(folder_path, xml_path) DO UPDATE SET"
            " xml_mtime = excluded.xml_mtime, xml_size_bytes = excluded.xml_size_bytes,"
            " estado = excluded.estado, error = excluded.error,"
            " parser_version = excluded.parser_version, indexed_at = datetime('now')",
            (str(carpeta), str(ruta), mtime, size, lectura.estado, lectura.error,
             xml_ubl.PARSER_VERSION),
        )
        if lectura.estado == xml_ubl.ESTADO_OK:
            res.leidos += 1
        else:
            res.fallidos += 1
            res.errores.append({"archivo": ruta.name, "estado": lectura.estado,
                                "error": lectura.error or ""})
    conn.commit()
    return res


# ───────────────────────────────── lectura ─────────────────────────────────────

def cufes_con_documento(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT cufe FROM documento")}


def documento_por_cufe(conn: sqlite3.Connection, cufe: str) -> dict[str, Any] | None:
    """El documento con sus líneas, impuestos y referencias, o None."""
    fila = conn.execute(
        "SELECT * FROM documento WHERE cufe = ?", ((cufe or "").strip().lower(),)
    ).fetchone()
    if fila is None:
        return None
    doc = dict(fila)
    doc_id = doc["id"]

    lineas = [dict(r) for r in conn.execute(
        "SELECT * FROM documento_linea WHERE documento_id = ? ORDER BY numero", (doc_id,))]
    por_linea: dict[int, list[dict]] = {}
    sueltos: list[dict] = []
    for r in conn.execute(
            "SELECT * FROM documento_impuesto WHERE documento_id = ? ORDER BY id", (doc_id,)):
        imp = dict(r)
        imp["es_retencion"] = bool(imp["es_retencion"])
        if imp["linea_id"] is None:
            sueltos.append(imp)
        else:
            por_linea.setdefault(imp["linea_id"], []).append(imp)
    for ln in lineas:
        ln["impuestos"] = por_linea.get(ln["id"], [])

    doc["lineas"] = lineas
    doc["impuestos"] = sueltos
    doc["referencias"] = [dict(r) for r in conn.execute(
        "SELECT * FROM documento_referencia WHERE documento_id = ? ORDER BY id", (doc_id,))]
    return doc


def documentos_del_periodo(conn: sqlite3.Connection, periodo: str) -> list[dict[str, Any]]:
    """Los documentos cuyo CUFE aparece en las filas del Excel de ese mes.

    Se cruza por CUFE y no por fecha del XML a propósito: el mes al que pertenece
    una fila lo decide el Excel de la DIAN, y un documento emitido en otro periodo
    puede aparecer en este —son los *rezagados* que caza 3.4—.
    """
    return [dict(r) for r in conn.execute(
        "SELECT d.* FROM documento d"
        " JOIN (SELECT DISTINCT cufe_cude AS c FROM excel_row WHERE periodo = ?) e"
        "   ON e.c = d.cufe"
        " ORDER BY d.fecha_emision, d.numero", (periodo,))]
