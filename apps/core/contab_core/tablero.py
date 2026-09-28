"""Tablero multiempresa (Fase 1.5): en qué va cada empresa este mes.

La unidad de trabajo del contador no es una empresa, es **«mis N empresas este
mes»**, y hasta ahora no había una sola pantalla que lo respondiera: había que
entrar una por una.

**Por qué no hay tabla de caché.** El plan preveía guardar el estado en
`contab.db` y que cada operación lo escribiera. Se descartó al implementarlo: todo
lo que el tablero muestra ya vive en la .db de cada empresa —los lotes, las filas,
la carpeta del mes, el índice de CUFE, la última corrida de validaciones—, así que
una copia en el catálogo central solo puede hacer una cosa nueva: **quedar
desactualizada y mentir**. Y una tabla con columnas que nada escribe hasta la Fase
4 es exactamente el esquema muerto que D-085 sacó del repo. Se lee en vivo: son
unas pocas consultas con índice por empresa. Cuando la Fase 4 tenga algo que
guardar que no viva en ningún otro lado (cuándo se causó, cuándo se envió a Siigo),
esa tabla nacerá con algo que escribir.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from . import log, program_db, storage


def _periodo_actual() -> str:
    hoy = date.today()
    return f"{hoy.year:04d}-{hoy.month:02d}"


def estado_empresa(db_path: str | Path, periodo: str) -> dict[str, Any]:
    """Estado de una empresa en un mes. No lanza: un .db ilegible se reporta."""
    estado: dict[str, Any] = {
        "periodo": periodo,
        "mes_creado": False,
        "pdfs_folder": None,
        "soportes_carpeta_existe": True,
        "cargas": 0,
        "filas": 0,
        "soportes": 0,
        "soportes_con_cufe": 0,
        "validado_at": None,
        "no_conformes": None,
        "perfil_fiscal": False,
        "terceros": 0,
        "terceros_sin_rut": 0,
        "error": None,
    }
    conn = None
    try:
        conn = storage.connect(db_path)
        storage.ensure_schema(conn)

        fila = conn.execute(
            "SELECT pdfs_folder FROM periodo_folder WHERE periodo = ?", (periodo,)
        ).fetchone()
        if fila is not None:
            estado["mes_creado"] = True
            estado["pdfs_folder"] = fila["pdfs_folder"]

        agg = conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(total_rows), 0) AS f FROM excel_load "
            "WHERE periodo = ? AND deleted_at IS NULL",
            (periodo,),
        ).fetchone()
        estado["cargas"] = agg["c"]
        estado["filas"] = agg["f"]
        if agg["c"]:
            estado["mes_creado"] = True

        if estado["pdfs_folder"]:
            estado["soportes_carpeta_existe"] = Path(estado["pdfs_folder"]).is_dir()
            sop = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN EXISTS (
                             SELECT 1 FROM pdf_cufe_value v WHERE v.pdf_index_id = i.id
                           ) THEN 1 ELSE 0 END) AS con_cufe
                FROM pdf_cufe_index i WHERE i.folder_path = ?
                """,
                (estado["pdfs_folder"],),
            ).fetchone()
            estado["soportes"] = sop["total"] or 0
            estado["soportes_con_cufe"] = sop["con_cufe"] or 0

        corrida = conn.execute(
            """
            SELECT r.finished_at, r.failing_rows FROM validation_run r
            JOIN excel_load l ON l.id = r.load_id
            WHERE l.periodo = ? AND l.deleted_at IS NULL AND r.finished_at IS NOT NULL
            ORDER BY r.finished_at DESC LIMIT 1
            """,
            (periodo,),
        ).fetchone()
        if corrida is not None:
            estado["validado_at"] = corrida["finished_at"]
            estado["no_conformes"] = corrida["failing_rows"]

        estado["perfil_fiscal"] = conn.execute(
            "SELECT COUNT(*) FROM empresa_perfil_fiscal WHERE vigencia_desde <= ?",
            (date.today().isoformat(),),
        ).fetchone()[0] > 0

        estado["terceros"] = conn.execute("SELECT COUNT(*) FROM tercero").fetchone()[0]
        estado["terceros_sin_rut"] = conn.execute(
            "SELECT COUNT(*) FROM tercero WHERE consultado_at IS NULL"
        ).fetchone()[0]
    except Exception as exc:
        # Una empresa que no se puede leer no puede dejar al contador sin tablero:
        # se muestra la fila con su motivo y las demás siguen.
        log.exception("no se pudo leer el estado de %s", db_path)
        estado["error"] = str(exc)
    finally:
        if conn is not None:
            conn.close()
    return estado


def tablero(periodo: str | None = None, *, include_archived: bool = False) -> dict[str, Any]:
    """Todas las empresas del catálogo con su estado en un mes."""
    p = periodo or _periodo_actual()
    empresas = []
    for reg in program_db.list_registry(include_archived=include_archived):
        fila = {
            "db_path": reg["db_path"],
            "nit": reg["nit"],
            "dv": reg.get("dv"),
            "razon_social": reg["razon_social"],
            "archived": reg.get("archived", False),
            "last_opened_at": reg.get("last_opened_at"),
        }
        fila.update(estado_empresa(reg["db_path"], p))
        empresas.append(fila)

    resumen = {
        "empresas": len(empresas),
        "con_excel": sum(1 for e in empresas if e["cargas"]),
        "validadas": sum(1 for e in empresas if e["validado_at"]),
        "con_perfil": sum(1 for e in empresas if e["perfil_fiscal"]),
        "no_conformes": sum(e["no_conformes"] or 0 for e in empresas),
        "ilegibles": sum(1 for e in empresas if e["error"]),
    }
    return {"periodo": p, "resumen": resumen, "empresas": empresas}
