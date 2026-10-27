"""stdio JSON-lines IPC loop. One request per line on stdin → one response per line on stdout.

Protocol:
  request:  {"id": "...", "method": "...", "params": {...}}
  response: {"id": "...", "result": <any>}                     on success
            {"id": "...", "error": {"code": "...", "message": "..."}}  on failure
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import asiento as asiento_module
from . import backup as backup_module
from . import carpetas as carpetas_module
from . import causacion as causacion_module
from . import cita_personas as citas_module
from . import dian_inconsistencias as dian_inc_module
from . import dian_portal as dian_portal_module
from . import documentos as documentos_module
from . import excel as excel_module
from . import export as export_module
from . import jobs as jobs_module
from . import log
from . import nit as nit_module
from . import paths as paths_module
from . import pdf_cufe as pdf_cufe_module
from . import perfil_fiscal as perfil_module
from . import program_db as program_db_module
from . import puc as puc_module
from . import rename_soportes as rename_module
from . import storage as storage_module
from . import tablero as tablero_module
from . import tarifas as tarifas_module
from . import terceros as terceros_module
from . import validations as validations_module

# ---------- handlers ----------

def _h_ping(_params: dict) -> dict:
    return {"pong": True}


def _h_check_dependencies(_params: dict) -> dict:
    """Estado de los binarios externos que Contab necesita (D-080).

    Permite avisar ANTES de procesar un mes entero, en vez de que el usuario vea
    todas las filas como 'sin soporte' sin saber que falta una instalación."""
    poppler = pdf_cufe_module.comprobar_pdftotext()
    return {
        "ok": poppler["disponible"],
        "pdftotext": poppler,
    }


def _h_list_empresas(params: dict) -> list[dict]:
    include_archived = bool(params.get("include_archived", False))
    out: list[dict] = []
    for db_path in paths_module.scan_empresa_dbs():
        info = None
        try:
            info = storage_module.read_empresa_info(db_path)
        except Exception:
            log.exception("no se pudo leer la empresa %s al listar", db_path)
        archived = bool(info["archived"]) if info else False
        if archived and not include_archived:
            continue
        out.append({
            "db_path": str(db_path),
            "filename": db_path.name,
            "nit": info["nit"] if info else None,
            "razon_social": info["razon_social"] if info else None,
            "archived": archived,
        })
    return out


def _h_validate_nit(params: dict) -> dict:
    nit_input = params.get("nit", "")
    dv = params.get("dv")
    if dv is not None and str(dv).strip():
        return {"valid": nit_module.is_valid_nit_with_dv(f"{nit_input}-{dv}")}
    digits = nit_module.normalize(nit_input)
    if not digits:
        return {"valid": False, "computed_dv": None}
    computed = nit_module.compute_dv(digits)
    return {"valid": True, "computed_dv": computed}


def _h_create_empresa(params: dict) -> dict:
    nit_raw = str(params.get("nit", "")).strip()
    razon_social = str(params.get("razon_social", "")).strip()
    if not nit_raw or not razon_social:
        raise ValueError("nit y razon_social son requeridos")
    digits = nit_module.normalize(nit_raw)
    if "-" in nit_raw:
        body, dv_in = nit_raw.rsplit("-", 1)
        body = nit_module.normalize(body)
        dv = nit_module.normalize(dv_in)
    else:
        body, dv = digits, None
    computed_dv = nit_module.compute_dv(body)
    if dv is not None and dv and dv != computed_dv:
        raise ValueError(f"DV inválido: ingresado {dv}, esperado {computed_dv}")
    dv = dv or computed_dv

    db_path = paths_module.empresa_db_path(body, razon_social)

    # D-079: crear sobre una empresa que ya existe NO puede devolver éxito.
    # `init_empresa_db` es idempotente, así que antes se adoptaba el .db existente
    # y se respondía con la razón social ENVIADA aunque la BD conservara la otra:
    # el usuario creía haber creado una empresa nueva y estaba editando otra.
    if db_path.exists():
        existente = storage_module.read_empresa_info(db_path) or {}
        raise ValueError(
            f"Ya existe una empresa con ese NIT y esa razón social: "
            f"{existente.get('nit', body)} · {existente.get('razon_social', razon_social)}. "
            "Ábrela desde la lista de empresas en vez de crearla de nuevo."
        )

    # El mismo NIT con otra razón social generaría un archivo distinto y dos
    # contabilidades paralelas para el mismo contribuyente: hay que avisar.
    for otra in paths_module.scan_empresa_dbs():
        try:
            info_otra = storage_module.read_empresa_info(otra)
        except Exception:
            log.warn("empresa ilegible al comprobar NIT duplicado: %s", otra)
            continue
        if info_otra and nit_module.normalize(info_otra.get("nit") or "") == body:
            raise ValueError(
                f"El NIT {body} ya está registrado como «{info_otra.get('razon_social')}». "
                "Si cambió de nombre, edita la razón social de esa empresa; no crees otra."
            )

    storage_module.init_empresa_db(db_path, body, dv, razon_social)
    try:
        program_db_module.register_empresa(db_path, body, dv, razon_social)
    except Exception:
        # El catálogo central es best-effort: la empresa ya quedó creada y
        # sync_registry la recogerá al arrancar. Pero que quede rastro.
        log.exception("no se pudo registrar %s en el catálogo central", db_path)
    return {"db_path": str(db_path), "nit": body, "dv": dv, "razon_social": razon_social}


def _h_open_empresa(params: dict) -> dict:
    db_path = Path(params["db_path"])
    info = storage_module.read_empresa_info(db_path)
    if info is None:
        raise ValueError("empresa.db no inicializada")
    return {"db_path": str(db_path), **info}


def _h_set_default_folder(params: dict) -> dict:
    db_path = Path(params["db_path"])
    folder = params.get("folder")
    if folder is not None and not isinstance(folder, str):
        raise ValueError("folder debe ser string o null")
    storage_module.set_default_folder(db_path, folder)
    info = storage_module.read_empresa_info(db_path)
    return {"db_path": str(db_path), **(info or {})}


def _h_set_pdfs_folder(params: dict) -> dict:
    db_path = Path(params["db_path"])
    folder = params.get("folder")
    if folder is not None and not isinstance(folder, str):
        raise ValueError("folder debe ser string o null")
    storage_module.set_pdfs_folder(db_path, folder)
    info = storage_module.read_empresa_info(db_path)
    return {"db_path": str(db_path), **(info or {})}


def _h_update_empresa(params: dict) -> dict:
    """E2 (D-041): solo razon_social es editable post-creación."""
    db_path = Path(params["db_path"])
    razon_social = params.get("razon_social")
    if not isinstance(razon_social, str):
        raise ValueError("razon_social requerida (string)")
    storage_module.update_razon_social(db_path, razon_social)
    info = storage_module.read_empresa_info(db_path)
    return {"db_path": str(db_path), **(info or {})}


def _h_archive_empresa(params: dict) -> dict:
    db_path = Path(params["db_path"])
    storage_module.set_archived(db_path, True)
    info = storage_module.read_empresa_info(db_path)
    return {"db_path": str(db_path), **(info or {})}


def _h_unarchive_empresa(params: dict) -> dict:
    db_path = Path(params["db_path"])
    storage_module.set_archived(db_path, False)
    info = storage_module.read_empresa_info(db_path)
    return {"db_path": str(db_path), **(info or {})}


def _h_backup_empresa(params: dict) -> dict:
    db_path = Path(params["db_path"])
    dest_folder = params.get("dest_folder")
    if not isinstance(dest_folder, str) or not dest_folder.strip():
        raise ValueError("dest_folder requerido (string)")
    result = backup_module.backup_empresa(db_path, dest_folder)
    return result.to_dict()


def _h_restore_empresa(params: dict) -> dict:
    zip_path = params.get("zip_path")
    if not isinstance(zip_path, str) or not zip_path.strip():
        raise ValueError("zip_path requerido (string)")
    result = backup_module.restore_empresa(zip_path)
    return result.to_dict()


def _h_delete_empresa(params: dict) -> dict:
    """D-042: hard delete. Requiere confirm_nit que coincida con el de la BD."""
    db_path = Path(params["db_path"])
    confirm_nit = params.get("confirm_nit")
    if not isinstance(confirm_nit, str):
        raise ValueError("confirm_nit requerido (string)")
    return backup_module.delete_empresa_file(db_path, confirm_nit)


def _h_papelera_list(_params: dict) -> list[dict]:
    """Qué empresas borradas siguen recuperables y cuántos días les quedan (D-078)."""
    return backup_module.listar_papelera()


def _h_papelera_restore(params: dict) -> dict:
    archivo = params.get("archivo")
    if not isinstance(archivo, str) or not archivo.strip():
        raise ValueError("archivo requerido (string)")
    return backup_module.restaurar_de_papelera(archivo)


def _h_list_pdfs_folder_files(params: dict) -> dict:
    """List PDFs in the empresa's pdfs_folder, joined against the index cache.
    Returns extraction status + CUFE count per file."""
    from datetime import datetime

    db_path = Path(params["db_path"])
    info = storage_module.read_empresa_info(db_path)
    if info is None:
        raise ValueError("empresa.db no inicializada")
    folder = (info.get("pdfs_folder") or "").strip()
    if not folder:
        return {"folder": None, "files": [], "indexed_cufe_count": 0, "error": None}

    folder_path = Path(folder)
    if not folder_path.is_dir():
        return {
            "folder": str(folder_path),
            "files": [],
            "indexed_cufe_count": 0,
            "error": f"La carpeta no existe o no es accesible: {folder_path}",
        }

    conn = storage_module.connect(db_path)
    try:
        indexed_rows = pdf_cufe_module.list_indexed_pdfs(conn, folder_path)
        indexed_by_path = {row["pdf_path"]: row for row in indexed_rows}
        indexed_cufes = pdf_cufe_module.get_indexed_cufes(conn, folder_path)
    finally:
        conn.close()

    files: list[dict] = []
    try:
        children = sorted(folder_path.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        return {
            "folder": str(folder_path),
            "files": [],
            "indexed_cufe_count": 0,
            "error": str(exc),
        }

    for p in children:
        if not p.is_file() or p.suffix.lower() != ".pdf":
            continue
        if p.name.startswith("~"):
            continue
        st = p.stat()
        full = str(p.resolve())
        cached = indexed_by_path.get(full)
        files.append({
            "name": p.name,
            "path": full,
            "size_bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            "extraction_status": cached["extraction_status"] if cached else None,
            "cufe_count": cached["cufe_count"] if cached else 0,
            "cufes": cached["cufes"] if cached else [],
            "is_stale": cached is not None and (
                cached["pdf_mtime"] != int(st.st_mtime) or
                cached["pdf_size_bytes"] != st.st_size
            ),
        })

    return {
        "folder": str(folder_path),
        "files": files,
        "indexed_cufe_count": len(indexed_cufes),
        "error": None,
    }


def _h_reindex_pdfs(params: dict, progress=None) -> dict:
    """Force a fresh incremental indexing of the empresa's pdfs_folder."""
    db_path = Path(params["db_path"])
    info = storage_module.read_empresa_info(db_path)
    if info is None:
        raise ValueError("empresa.db no inicializada")
    folder = (info.get("pdfs_folder") or "").strip()
    if not folder:
        return {"folder": None, "stats": None, "error": "Carpeta de PDFs no configurada"}

    conn = storage_module.connect(db_path)
    try:
        # index_folder hace COMMIT por archivo: no envolverlo en una transacción.
        stats = pdf_cufe_module.index_folder(conn, folder, progress=progress)
    finally:
        conn.close()
    return {"folder": stats.folder, "stats": stats.to_dict(), "error": None}


def _h_list_load_soportes(params: dict, progress=None) -> dict:
    """Soportes del MES de este load (carpeta del periodo): un item por PDF con su
    estado de extracción y el CUFE encontrado, para ver CUÁLES soportes no se
    leyeron y re-verificarlos sin re-subir el Excel (D-068).

    `reindex=True` re-verifica (re-extrae lo pendiente / lo de un extractor viejo);
    `force=True` además limpia el caché de la carpeta y re-extrae todo. Sin
    `reindex` es solo lectura (para pintar el panel sin re-escanear)."""
    db_path = Path(params["db_path"])
    load_id = int(params["load_id"])
    reindex = bool(params.get("reindex", False))
    force = bool(params.get("force", False))
    empty = {"total": 0, "with_cufe": 0, "without_cufe": 0}

    conn = storage_module.connect(db_path)
    try:
        periodo = _load_periodo(conn, load_id)
        folder = (storage_module.periodo_pdfs_folder(conn, periodo) or "").strip()
        if not folder:
            return {"folder": None, "periodo": periodo, "files": [], "counts": empty,
                    "reindexed": False, "error": "Este mes no tiene carpeta de soportes configurada."}
        folder_path = Path(folder)
        if not folder_path.is_dir():
            return {"folder": str(folder_path), "periodo": periodo, "files": [], "counts": empty,
                    "reindexed": False, "error": f"La carpeta de soportes no existe: {folder_path}"}

        if reindex:
            if force:
                with storage_module.transaction(conn):
                    conn.execute("DELETE FROM pdf_cufe_index WHERE folder_path = ?",
                                 (str(folder_path.resolve()),))
            pdf_cufe_module.index_folder(conn, folder_path, progress=progress)

        indexed_by_path = {r["pdf_path"]: r for r in pdf_cufe_module.list_indexed_pdfs(conn, folder_path)}
    finally:
        conn.close()

    try:
        children = sorted(folder_path.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        return {"folder": str(folder_path), "periodo": periodo, "files": [], "counts": empty,
                "reindexed": reindex, "error": str(exc)}

    files: list[dict] = []
    with_cufe = 0
    for p in children:
        if not p.is_file() or p.suffix.lower() != ".pdf" or p.name.startswith("~"):
            continue
        cached = indexed_by_path.get(str(p.resolve()))
        cufes = (cached["cufes"] if cached else []) or []
        if cufes:
            with_cufe += 1
        files.append({
            "name": p.name,
            "path": str(p.resolve()),
            "has_cufe": bool(cufes),
            "extraction_status": cached["extraction_status"] if cached else None,
            "cufe": cufes[0]["value"] if cufes else None,
            "label": cufes[0]["label"] if cufes else None,
        })

    total = len(files)
    return {
        "folder": str(folder_path), "periodo": periodo, "files": files,
        "counts": {"total": total, "with_cufe": with_cufe, "without_cufe": total - with_cufe},
        "reindexed": reindex, "error": None,
    }


def _h_import_excel(params: dict) -> dict:
    db_path = Path(params["db_path"])
    source_path = Path(params["source_path"])
    periodo = params.get("periodo")
    if not isinstance(periodo, str) or not periodo.strip():
        raise ValueError("Debes indicar el mes (periodo 'AAAA-MM') al cargar el Excel.")
    periodo = storage_module._norm_periodo(periodo)
    storage_module.create_periodo(db_path, periodo)  # el Excel se carga DENTRO del mes
    loaded = excel_module.load_excel(source_path)
    conn = storage_module.connect(db_path)
    try:
        load_id = excel_module.persist_load(conn, str(source_path), loaded, periodo)
    finally:
        conn.close()
    return {
        "load_id": load_id,
        "sheet_name": loaded.sheet_name,
        "total_rows": len(loaded.rows),
        "periodo": periodo,
        "columns": excel_module.DIAN_COLUMNS + excel_module.DERIVED_COLUMNS,
    }


def _h_preparar_descarga_dian(params: dict) -> dict:
    """Valida el enlace y el mes, y devuelve lo que el sidecar DIAN necesita.

    El enlace **no se guarda**: entra, se valida y vuelve a salir hacia el
    navegador. Lo que sí queda en la respuesta es el rango calculado.
    """
    plan = dian_portal_module.preparar_descarga(
        params.get("periodo") or "", params.get("enlace") or "", params.get("grupo")
    )
    # La carpeta la decide Contab: el ZIP del portal es un intermedio, no un
    # documento del contador, y no hay por qué hacerle configurar nada.
    info = storage_module.read_empresa_info(Path(params["db_path"])) or {}
    # El listado del portal cae en el mes del contador, no en una carpeta interna
    # que él no ve. Si la empresa aún no tiene carpeta, sigue el sitio de antes.
    raiz = (info.get("default_folder") or "").strip()
    if raiz:
        plan["carpeta"] = carpetas_module.preparar_mes(raiz, plan["periodo"])["mes"]
    else:
        plan["carpeta"] = str(paths_module.descargas_dir(str(info.get("nit") or "")))
    plan["nit_receptor"] = info.get("nit")
    return plan


def _h_importar_descarga_dian(params: dict) -> dict:
    """Abre el ZIP que bajó el portal e importa su Excel al mes de la empresa.

    Se llama DESPUÉS de que el contador aprueba el resumen de la descarga: bajar y
    contabilizar son dos actos distintos, y el segundo no ocurre solo (D-097).
    """
    db_path = Path(params["db_path"])
    periodo = storage_module._norm_periodo(params.get("periodo") or "")
    descargado = Path(params["archivo"])

    destino = descargado.with_name(f"dian-{periodo}.xlsx")
    excel_path = dian_portal_module.extraer_excel(descargado, destino)
    resultado = _h_import_excel(
        {"db_path": str(db_path), "source_path": str(excel_path), "periodo": periodo}
    )
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        dian_portal_module.registrar_ingesta(
            conn, periodo=periodo, camino="portal", estado="ok",
            documentos=resultado.get("total_rows"), archivo=str(excel_path),
            empresa_dian=params.get("empresa_dian"),
        )
    finally:
        conn.close()
    return {**resultado, "archivo": str(excel_path)}


def _h_indexar_xml(params: dict, progress=None) -> dict:
    """Lee los XML de la carpeta de soportes de un mes (Fase 3.1).

    La carpeta es la misma de los PDF: el portal entrega los dos juntos en el ZIP
    de cada documento, así que separarlos obligaría al contador a decidir dónde va
    cada archivo de la misma descarga.
    """
    db_path = Path(params["db_path"])
    carpeta = params.get("carpeta")
    periodo = params.get("periodo")
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        if not carpeta:
            if not periodo:
                raise ValueError("Hace falta la carpeta o el mes.")
            carpeta = storage_module.periodo_pdfs_folder(conn, periodo)
            if not carpeta:
                raise ValueError(f"El mes {periodo} no tiene carpeta de soportes.")
        avisa = (lambda m: progress(0, 0, m)) if progress is not None else None
        return documentos_module.indexar_carpeta(conn, carpeta, progreso=avisa).como_dict()
    finally:
        conn.close()


def _h_documento_xml(params: dict) -> dict:
    """El documento de un CUFE, con líneas, impuestos y referencias (Fase 3.5)."""
    db_path = Path(params["db_path"])
    cufe = str(params.get("cufe") or "").strip().lower()
    if not cufe:
        raise ValueError("Hace falta el CUFE.")
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        doc = documentos_module.documento_por_cufe(conn, cufe)
        return {"cufe": cufe, "documento": doc}
    finally:
        conn.close()


def _h_documentos_del_mes(params: dict) -> dict:
    """Cuántas filas del mes tienen XML, para saber si vale la pena mirarlo."""
    db_path = Path(params["db_path"])
    periodo = storage_module._norm_periodo(params.get("periodo") or "")
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        docs = documentos_module.documentos_del_periodo(conn, periodo)
        total = conn.execute(
            "SELECT COUNT(DISTINCT cufe_cude) FROM excel_row"
            " WHERE periodo = ? AND cufe_cude IS NOT NULL", (periodo,)
        ).fetchone()[0]
        return {"periodo": periodo, "con_xml": len(docs), "total": total,
                "cufes": [d["cufe"] for d in docs]}
    finally:
        conn.close()


TIPO_EVENTO_RADIAN = "Application response"


def _h_documentos_sin_soporte(params: dict) -> dict:
    """Los documentos del mes a los que les falta el PDF, listos para ir a buscarlos.

    El NIT con el que se consulta es el de la **propia empresa**: el portal acepta
    el del emisor o el del receptor, y la empresa siempre es uno de los dos.
    """
    db_path = Path(params["db_path"])
    periodo = storage_module._norm_periodo(params.get("periodo") or "")
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        info = storage_module.read_empresa_info(db_path) or {}
        nit = str(info.get("nit") or "")

        carpeta = conn.execute(
            "SELECT pdfs_folder FROM periodo_folder WHERE periodo = ?", (periodo,)
        ).fetchone()
        carpeta = carpeta["pdfs_folder"] if carpeta else None
        ya_estan = (
            pdf_cufe_module.get_indexed_cufes(conn, carpeta) if carpeta else set()
        )

        # Los «Application response» son eventos RADIAN (acuse, aceptación), no
        # documentos: van con Total e IVA en cero y no tienen soporte que buscar.
        # En el septiembre real del usuario eran 9 de 41 filas, así que incluirlos
        # era mandar al bot a buscar una cuarta parte de cosas que no existen.
        filas = conn.execute(
            "SELECT DISTINCT cufe_cude FROM excel_row "
            "WHERE periodo = ? AND cufe_cude IS NOT NULL "
            "AND COALESCE(tipo_doc, '') <> ?",
            (periodo, TIPO_EVENTO_RADIAN),
        ).fetchall()
        faltan = [
            {"cufe": r["cufe_cude"], "nit": nit}
            for r in filas
            if r["cufe_cude"] not in ya_estan
        ]
        # Si este mes no tiene carpeta, se dicen los que sí: «no se puede» a secas
        # parece un fallo del programa, y aquí lo que falta es un dato del usuario.
        con_carpeta = [
            r["periodo"] for r in conn.execute(
                "SELECT periodo FROM periodo_folder WHERE pdfs_folder IS NOT NULL "
                "ORDER BY periodo DESC"
            ).fetchall()
        ]
        return {
            "periodo": periodo, "carpeta": carpeta, "nit": nit,
            "total": len(filas), "faltan": faltan, "meses_con_carpeta": con_carpeta,
        }
    finally:
        conn.close()


def _h_reindexar_soportes_con_nit(params: dict) -> dict:
    """Re-lee la carpeta del mes pasando el NIT como contraseña.

    Los PDF que entrega el portal vienen cifrados con él; sin esto quedarían
    marcados como protegidos y la validación diría que no hay soporte.
    """
    db_path = Path(params["db_path"])
    carpeta = params["carpeta"]
    info = storage_module.read_empresa_info(db_path) or {}
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        stats = pdf_cufe_module.index_folder(
            conn, carpeta, password=str(info.get("nit") or "") or None
        )
        return stats.to_dict()
    finally:
        conn.close()


def _h_registrar_ingesta(params: dict) -> dict:
    """Anota una corrida que NO terminó en importación (una que falló, o el camino
    manual). El mensaje se guarda enmascarado: podría arrastrar el enlace."""
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return dian_portal_module.registrar_ingesta(
            conn,
            periodo=params.get("periodo") or "",
            camino=params.get("camino") or "portal",
            estado=params.get("estado") or "error",
            documentos=params.get("documentos"),
            archivo=params.get("archivo"),
            error=params.get("error"),
            empresa_dian=params.get("empresa_dian"),
        )
    finally:
        conn.close()


def _h_listar_ingestas(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return {"ingestas": dian_portal_module.listar_ingestas(
            conn, periodo=params.get("periodo"), limite=int(params.get("limite", 20)))}
    finally:
        conn.close()


def _h_resumen_periodos(params: dict) -> dict:
    """Totales por mes, agregados en SQL (D-091).

    Antes esto era imposible sin cargar todas las filas a memoria: la fila entera
    vivía como blob JSON y no había nada que agrupar."""
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return {"periodos": excel_module.resumen_por_periodo(conn)}
    finally:
        conn.close()


def _h_resumen_emisores(params: dict) -> dict:
    """Mayores emisores, del mes indicado o de toda la empresa (D-091)."""
    db_path = Path(params["db_path"])
    periodo = params.get("periodo")
    limite = int(params.get("limite", 50))
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return {"emisores": excel_module.resumen_por_emisor(conn, periodo, limite)}
    finally:
        conn.close()


def _h_list_loads(params: dict) -> list[dict]:
    db_path = Path(params["db_path"])
    periodo = params.get("periodo")
    include_deleted = bool(params.get("include_deleted", False))
    conn = storage_module.connect(db_path)
    try:
        sql = (
            "SELECT id, source_name, loaded_at, total_rows, sheet_name, periodo, deleted_at "
            "FROM excel_load WHERE 1=1"
        )
        args: list = []
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        if periodo:
            sql += " AND periodo = ?"
            args.append(periodo)
        sql += " ORDER BY id DESC"
        out = []
        for r in conn.execute(sql, args).fetchall():
            out.append({
                "id": r["id"],
                "source_name": r["source_name"],
                "loaded_at": r["loaded_at"],
                "total_rows": r["total_rows"],
                "sheet_name": r["sheet_name"],
                "periodo": r["periodo"],
                "deleted": r["deleted_at"] is not None,
            })
        return out
    finally:
        conn.close()


def _h_list_folder_files(params: dict) -> dict:
    """List .xlsx files inside the empresa's default_folder. Each entry is
    flagged with `imported=true` if there is an excel_load whose source_path
    matches the file path verbatim."""
    from datetime import datetime

    db_path = Path(params["db_path"])
    info = storage_module.read_empresa_info(db_path)
    if info is None:
        raise ValueError("empresa.db no inicializada")
    folder = (info.get("default_folder") or "").strip()
    if not folder:
        return {"folder": None, "files": [], "error": None}

    folder_path = Path(folder)
    if not folder_path.is_dir():
        return {
            "folder": str(folder_path),
            "files": [],
            "error": f"La carpeta no existe o no es accesible: {folder_path}",
        }

    conn = storage_module.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, source_path FROM excel_load ORDER BY id DESC"
        ).fetchall()
    finally:
        conn.close()
    imported_by_path: dict[str, int] = {}
    for r in rows:
        sp = r["source_path"]
        if sp and sp not in imported_by_path:
            imported_by_path[sp] = r["id"]

    files: list[dict] = []
    try:
        children = sorted(folder_path.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        return {"folder": str(folder_path), "files": [], "error": str(exc)}

    for p in children:
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".xlsx", ".xls"):
            continue
        if p.name.startswith("~"):
            continue
        st = p.stat()
        mtime_iso = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        full = str(p)
        files.append({
            "name": p.name,
            "path": full,
            "size_bytes": st.st_size,
            "mtime": mtime_iso,
            "imported": full in imported_by_path,
            "imported_as_load_id": imported_by_path.get(full),
        })

    return {"folder": str(folder_path), "files": files, "error": None}


def _h_get_load_rows(params: dict) -> dict:
    db_path = Path(params["db_path"])
    load_id = int(params["load_id"])
    offset = int(params.get("offset", 0))
    limit = int(params.get("limit", 1000))
    conn = storage_module.connect(db_path)
    try:
        rows = excel_module.fetch_load_rows(conn, load_id)
        v3_overrides = sorted(storage_module.list_overrides(conn, load_id, "V3"))
    finally:
        conn.close()
    total = len(rows)
    page = rows[offset:offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "columns": excel_module.DIAN_COLUMNS + excel_module.DERIVED_COLUMNS,
        "rows": page,
        "v3_overrides": v3_overrides,
    }


def _h_toggle_validation_override(params: dict) -> dict:
    """D-046 — turn the manual override on/off for one (load, row, code).
    On success returns the up-to-date list of overrides for that load."""
    db_path = Path(params["db_path"])
    load_id = int(params["load_id"])
    row_index = int(params["row_index"])
    code = str(params.get("code", "V3"))
    active = bool(params.get("active", True))
    conn = storage_module.connect(db_path)
    try:
        with storage_module.transaction(conn):
            storage_module.toggle_override(conn, load_id, row_index, code, active)
        return {
            "load_id": load_id,
            "row_index": row_index,
            "code": code,
            "active": active,
            "v3_overrides": sorted(storage_module.list_overrides(conn, load_id, "V3")),
        }
    finally:
        conn.close()


def _load_periodo(conn, load_id: int) -> str | None:
    r = conn.execute("SELECT periodo FROM excel_load WHERE id = ?", (int(load_id),)).fetchone()
    return r["periodo"] if r else None


def _index_folder_cufes(conn, folder: str | None, progress=None) -> tuple[set[str] | None, dict | None]:
    """Index a PDFs folder and return (cufes_set, stats).
    Returns (None, None) if no folder. Caller manages the connection."""
    folder = (folder or "").strip()
    if not folder:
        return None, None
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return set(), {"folder": str(folder_path), "missing": True}
    stats = pdf_cufe_module.index_folder(conn, folder_path, progress=progress)
    cufes = pdf_cufe_module.get_indexed_cufes(conn, folder_path)
    return cufes, stats.to_dict()


def _resolve_load_cufes(conn, load_id: int, progress=None) -> tuple[set[str] | None, dict | None]:
    """0.1.4 — index the soportes folder OF THIS LOAD'S PERIODO (per-month),
    falling back to the empresa-wide folder if the month has none configured."""
    periodo = _load_periodo(conn, load_id)
    folder = storage_module.periodo_pdfs_folder(conn, periodo)
    return _index_folder_cufes(conn, folder, progress=progress)


def _capa_xml(conn, load_id: int) -> tuple[dict, str | None, dict]:
    """La capa que el XML añade a las filas: documentos, mes y estados del RUT.

    Si no hay XML leído, vuelve vacía — y entonces las validaciones se comportan
    exactamente como antes de la Fase 3 (D-039, D-064: el XML se PEGA al Excel,
    no lo reemplaza).
    """
    fila = conn.execute("SELECT periodo FROM excel_load WHERE id = ?", (load_id,)).fetchone()
    periodo = fila["periodo"] if fila else None
    docs: dict[str, dict] = {}
    for cufe in documentos_module.cufes_con_documento(conn):
        doc = documentos_module.documento_por_cufe(conn, cufe)
        if doc:
            docs[cufe] = doc
    estados = {
        r["nit"]: r["estado_rut"]
        for r in conn.execute(
            "SELECT nit, estado_rut FROM tercero WHERE estado_rut IS NOT NULL"
        ).fetchall()
    }
    return docs, periodo, estados


def _h_run_validations(params: dict, progress=None) -> dict:
    db_path = Path(params["db_path"])
    load_id = int(params["load_id"])
    run_v3 = bool(params.get("run_v3", True))

    info = storage_module.read_empresa_info(db_path) or {}
    self_nit = info.get("nit")

    conn = storage_module.connect(db_path)
    try:
        indexed_cufes, index_stats = _resolve_load_cufes(conn, load_id, progress=progress)
        if progress is not None:
            progress(0, 0, "Aplicando validaciones")
        rows = excel_module.fetch_load_rows(conn, load_id)
        v3_overrides = storage_module.list_overrides(conn, load_id, "V3")
        overrides_by_row = {i: {"V3"} for i in v3_overrides}
        docs_xml, periodo_lote, estados_rut = _capa_xml(conn, load_id)
        tagged = validations_module.evaluate_rows(
            rows,
            run_v3=run_v3,
            indexed_cufes=indexed_cufes,
            overrides_by_row=overrides_by_row,
            self_nit=self_nit,
            documentos_por_cufe=docs_xml,
            periodo=periodo_lote,
            estados_rut=estados_rut,
        )
        failing = sum(1 for r in tagged if r)
        notes = None
        if index_stats and index_stats.get("missing"):
            notes = f"Carpeta de soportes no existe: {index_stats.get('folder')}"
        elif index_stats:
            no_cufe = index_stats.get("no_cufe", []) or []
            if no_cufe:
                notes = f"{len(no_cufe)} PDF(s) sin CUFE extraído"
        failures = [
            {
                "row_index": i,
                "reason": "; ".join(msg for _code, msg in row),
                "codes": [code for code, _msg in row],
            }
            for i, row in enumerate(tagged) if row
        ]
        with storage_module.transaction(conn):
            cur = conn.execute(
                "INSERT INTO validation_run(load_id, finished_at, total_rows, failing_rows, notes) "
                "VALUES (?, datetime('now'), ?, ?, ?)",
                (load_id, len(rows), failing, notes),
            )
            run_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO validation_failure(run_id, row_index, cufe_cude, reason) "
                "VALUES (?, ?, ?, ?)",
                [(run_id, f["row_index"], rows[f["row_index"]].get("CUFE/CUDE"), f["reason"]) for f in failures],
            )
        return {
            "run_id": run_id,
            "total_rows": len(rows),
            "failing_rows": failing,
            "v1_active": indexed_cufes is not None,
            "indexed_cufe_count": len(indexed_cufes) if indexed_cufes is not None else 0,
            "index_stats": index_stats,
            "notes": notes,
            "failures": failures,
            "v3_overrides": sorted(v3_overrides),
        }
    finally:
        conn.close()


def _h_get_latest_run_failures(params: dict) -> dict:
    """Return the failures of the most recent validation_run for this load_id.
    Useful to render the table inline without re-running validations."""
    db_path = Path(params["db_path"])
    load_id = int(params["load_id"])
    conn = storage_module.connect(db_path)
    try:
        run = conn.execute(
            "SELECT id, total_rows, failing_rows, started_at, finished_at, notes "
            "FROM validation_run WHERE load_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (load_id,),
        ).fetchone()
        if run is None:
            return {"run": None, "failures": []}
        failures = conn.execute(
            "SELECT row_index, reason FROM validation_failure "
            "WHERE run_id = ? ORDER BY row_index",
            (run["id"],),
        ).fetchall()
        return {
            "run": dict(run),
            "failures": [{"row_index": f["row_index"], "reason": f["reason"]} for f in failures],
        }
    finally:
        conn.close()


def _h_export_no_conformes(params: dict) -> dict:
    db_path = Path(params["db_path"])
    load_id = int(params["load_id"])
    output_path = Path(params["output_path"])
    run_v3 = bool(params.get("run_v3", True))

    info = storage_module.read_empresa_info(db_path) or {}
    self_nit = info.get("nit")

    conn = storage_module.connect(db_path)
    try:
        indexed_cufes, _stats = _resolve_load_cufes(conn, load_id)
        rows = excel_module.fetch_load_rows(conn, load_id)
        v3_overrides = storage_module.list_overrides(conn, load_id, "V3")
    finally:
        conn.close()
    overrides_by_row = {i: {"V3"} for i in v3_overrides}
    tagged = validations_module.evaluate_rows(
        rows, run_v3=run_v3, indexed_cufes=indexed_cufes,
        overrides_by_row=overrides_by_row, self_nit=self_nit,
    )
    reasons = validations_module.failures_to_strings(tagged)
    return export_module.export_no_conformes(rows, reasons, output_path)


def _h_export_missing_supports(params: dict) -> dict:
    """D-047 + D-048 — export rows that failed V1 (no PDF support match).

    Output is the 5-column report (NIT Emisor, Nombre Emisor, # factura,
    Fecha Emisión, Total). V3 overrides DO NOT affect this report — V1 status
    is independent.

    Rows where NIT Emisor matches the empresa's own NIT are skipped (D-048):
    the company itself issued those documents, so no external support is
    expected.
    """
    db_path = Path(params["db_path"])
    load_id = int(params["load_id"])
    output_path = Path(params["output_path"])

    info = storage_module.read_empresa_info(db_path) or {}
    self_nit = info.get("nit")

    conn = storage_module.connect(db_path)
    try:
        indexed_cufes, _stats = _resolve_load_cufes(conn, load_id)
        if indexed_cufes is None:
            raise ValueError(
                "Configura la carpeta de PDFs (soportes) antes de generar este reporte"
            )
        rows = excel_module.fetch_load_rows(conn, load_id)
    finally:
        conn.close()

    missing: set[int] = set()
    for i, row in enumerate(rows):
        transformed = validations_module.apply_v2_inversion(row)
        v1 = validations_module.evaluate_v1(transformed, indexed_cufes, self_nit=self_nit)
        if v1 is not None:  # any V1 failure → row is "sin soporte"
            missing.add(i)

    return export_module.export_missing_supports(rows, missing, output_path)


# ---------- 0.1.4: MESES (periodos) — crear, soportes por mes, mover/borrar el Excel ----------

def _h_create_periodo(params: dict) -> dict:
    """Crea el mes y, si la empresa ya tiene carpeta, su sitio en el disco.

    Crear el mes y crear su carpeta son el mismo gesto: si se separan, el mes
    nace sin dónde guardar nada y alguien tiene que acordarse después.
    """
    db_path = Path(params["db_path"])
    periodo = params.get("periodo")
    if not isinstance(periodo, str):
        raise ValueError("periodo requerido (string 'AAAA-MM')")
    res = storage_module.create_periodo(db_path, periodo)

    info = storage_module.read_empresa_info(db_path) or {}
    raiz = (info.get("default_folder") or "").strip()
    if not raiz:
        # Sin carpeta de empresa no hay dónde crearla. No es un error: la UI la
        # pide en este momento, que es cuando se entiende para qué sirve.
        res["falta_carpeta_empresa"] = True
        return res
    rutas = carpetas_module.preparar_mes(raiz, res["periodo"])
    storage_module.set_periodo_folder(db_path, res["periodo"], rutas["soportes"])
    res.update(carpeta_mes=rutas["mes"], pdfs_folder=rutas["soportes"])
    return res


def _h_carpeta_empresa(params: dict) -> dict:
    """Fija la carpeta de la empresa y deja listos los meses que ya existan."""
    db_path = Path(params["db_path"])
    carpeta = params.get("carpeta")
    if not isinstance(carpeta, str) or not carpeta.strip():
        raise ValueError("carpeta requerida")
    storage_module.set_default_folder(db_path, carpeta.strip())
    for periodo in storage_module.periodo_folders(db_path):
        rutas = carpetas_module.preparar_mes(carpeta.strip(), periodo)
        storage_module.set_periodo_folder(db_path, periodo, rutas["soportes"])
    return {"carpeta": carpeta.strip()}


def _h_plan_mudanza(params: dict) -> dict:
    """Qué se movería al reorganizar. No toca nada."""
    db_path = Path(params["db_path"])
    info = storage_module.read_empresa_info(db_path) or {}
    raiz = (params.get("carpeta") or info.get("default_folder") or "").strip()
    if not raiz:
        raise ValueError("Esta empresa todavía no tiene carpeta.")
    return carpetas_module.mudar(db_path, raiz, dry_run=True)


def _h_mudar_carpetas(params: dict, progress=None) -> dict:
    """Mueve de verdad, deja manifiesto, y vuelve a indexar donde quedaron.

    Reindexar es parte de mudar, no un paso aparte: el índice de CUFEs guarda la
    ruta de cada PDF, así que al moverlos queda apuntando a sitios que ya no
    existen y la validación diría que faltan soportes que están ahí mismo. Pedirle
    al contador que se acuerde de re-verificar mes por mes es trasladarle un
    problema que creamos nosotros.
    """
    db_path = Path(params["db_path"])
    info = storage_module.read_empresa_info(db_path) or {}
    raiz = (params.get("carpeta") or info.get("default_folder") or "").strip()
    if not raiz:
        raise ValueError("Esta empresa todavía no tiene carpeta.")
    storage_module.set_default_folder(db_path, raiz)
    res = carpetas_module.mudar(db_path, raiz, dry_run=False)

    # El NIT es la contraseña de los PDF que entrega el portal (vienen cifrados).
    clave = str(info.get("nit") or "") or None
    reindexados: dict[str, Any] = {}
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        por_mes = storage_module.periodo_folders(db_path)
        for i, (periodo, carpeta) in enumerate(por_mes.items(), 1):
            if not carpeta or not Path(carpeta).is_dir():
                continue
            if progress is not None:
                progress(i, len(por_mes), f"Revisando los soportes de {periodo}…")
            try:
                stats = pdf_cufe_module.index_folder(conn, carpeta, password=clave)
                reindexados[periodo] = stats.to_dict()
            except Exception as exc:
                # Que falle un mes no puede tapar que la mudanza sí se hizo.
                log.warn(f"mudanza: no se pudo reindexar {periodo}: {exc}")
                reindexados[periodo] = {"error": f"{exc.__class__.__name__}: {exc}"}
    finally:
        conn.close()
    res["reindexados"] = reindexados
    return res


def _h_list_periodos(params: dict) -> list[dict]:
    db_path = Path(params["db_path"])
    include_deleted = bool(params.get("include_deleted", False))
    periodos = storage_module.list_periodos(db_path, include_deleted=include_deleted)
    conn = storage_module.connect(db_path)
    try:
        for p in periodos:
            folder = p.get("pdfs_folder")
            count = 0
            if folder and Path(folder).is_dir():
                try:
                    count = len(pdf_cufe_module.get_indexed_cufes(conn, Path(folder)))
                except Exception:
                    count = 0
            p["indexed_cufe_count"] = count
    finally:
        conn.close()
    return periodos


def _h_set_periodo_pdfs_folder(params: dict) -> dict:
    db_path = Path(params["db_path"])
    periodo = params.get("periodo")
    folder = params.get("folder")
    if not isinstance(periodo, str):
        raise ValueError("periodo requerido (string 'AAAA-MM')")
    if folder is not None and not isinstance(folder, str):
        raise ValueError("folder debe ser string o null")
    return storage_module.set_periodo_folder(db_path, periodo, folder)


def _h_delete_periodo(params: dict) -> dict:
    db_path = Path(params["db_path"])
    periodo = params.get("periodo")
    if not isinstance(periodo, str):
        raise ValueError("periodo requerido (string 'AAAA-MM')")
    return storage_module.delete_periodo(db_path, periodo)


def _h_set_load_periodo(params: dict) -> dict:
    db_path = Path(params["db_path"])
    load_id = int(params["load_id"])
    periodo = params.get("periodo")
    if not isinstance(periodo, str):
        raise ValueError("periodo requerido (string 'AAAA-MM')")
    return storage_module.set_load_periodo(db_path, load_id, periodo)


def _h_soft_delete_load(params: dict) -> dict:
    return storage_module.soft_delete_load(Path(params["db_path"]), int(params["load_id"]))


def _h_restore_load(params: dict) -> dict:
    return storage_module.restore_load(Path(params["db_path"]), int(params["load_id"]))


# ---------- 0.1.4: BD del programa (contab.db) — usuario, ajustes, registro ----------

def _h_program_get_user(_params: dict) -> dict:
    return {"user": program_db_module.get_user()}


def _h_program_save_user(params: dict) -> dict:
    name = params.get("name")
    email = params.get("email")
    if name is not None and not isinstance(name, str):
        raise ValueError("name debe ser string")
    if email is not None and not isinstance(email, str):
        raise ValueError("email debe ser string")
    return {"user": program_db_module.save_user(name=name, email=email)}


def _h_program_get_settings(_params: dict) -> dict:
    return {"settings": program_db_module.get_settings()}


def _h_program_save_settings(params: dict) -> dict:
    patch = params.get("patch")
    if not isinstance(patch, dict):
        raise ValueError("patch debe ser un objeto de ajustes")
    return {"settings": program_db_module.save_settings(patch)}


def _h_program_list_empresas(params: dict) -> list[dict]:
    include_archived = bool(params.get("include_archived", False))
    return program_db_module.list_registry(include_archived=include_archived)


def _h_citas_list(_params: dict) -> list[dict]:
    return citas_module.list_personas()


def _h_citas_save_persona(params: dict) -> dict:
    persona = params.get("persona")
    if not isinstance(persona, dict):
        raise ValueError("persona debe ser un objeto")
    return citas_module.save_persona(persona)


def _h_citas_delete_persona(params: dict) -> dict:
    return {"deleted": citas_module.delete_persona(_id_param(params))}


def _h_citas_set_estado(params: dict) -> dict:
    estado = params.get("estado")
    if not isinstance(estado, str):
        raise ValueError("estado requerido (string)")
    return citas_module.set_estado(_id_param(params), estado)


def _id_param(params: dict) -> int:
    pid = params.get("id")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ValueError("id requerido (entero positivo)")
    return pid


def _h_program_touch_empresa(params: dict) -> dict:
    db_path = params.get("db_path")
    if not isinstance(db_path, str) or not db_path.strip():
        raise ValueError("db_path requerido (string)")
    program_db_module.touch_empresa(db_path)
    return {"ok": True}


# ---------- Consulta de Inconsistencias DIAN (razón social por NIT+DV) ----------

def _h_consulta_inconsistencias(params: dict) -> dict:
    """Una consulta NIT+DV → razón social (scrape HTTP-plano de MUISCA)."""
    nit = str(params.get("nit", "")).strip()
    dv = str(params.get("dv", "")).strip()
    if not nit:
        raise ValueError("nit requerido")
    return dian_inc_module.consultar(nit, dv)


def _h_parse_nit_dv(params: dict) -> dict:
    """Lee un .xlsx con columnas NIT y DV → filas normalizadas."""
    source_path = params.get("source_path")
    if not isinstance(source_path, str) or not source_path.strip():
        raise ValueError("source_path requerido (string)")
    return dian_inc_module.parse_nit_dv(source_path)


def _h_export_inconsistencias(params: dict) -> dict:
    """Escribe el .xlsx de salida con NIT, DV y Razón Social."""
    rows = params.get("rows")
    output_path = params.get("output_path")
    if not isinstance(rows, list):
        raise ValueError("rows requerido (lista)")
    if not isinstance(output_path, str) or not output_path.strip():
        raise ValueError("output_path requerido (string)")
    return dian_inc_module.export_inconsistencias(rows, output_path)


# ---------- Renombrado de soportes (DD-MM_NIT_RAZON-SOCIAL_FACTURA) ----------

def _h_rename_soportes(params: dict) -> dict:
    """Renombra los PDFs del mes según el cruce CUFE↔fila del Excel.
    dry_run=True (por defecto) solo devuelve el plan; dry_run=False aplica."""
    db_path = Path(params["db_path"])
    load_id = int(params["load_id"])
    dry_run = bool(params.get("dry_run", True))
    conn = storage_module.connect(db_path)
    try:
        periodo = _load_periodo(conn, load_id)
        folder = storage_module.periodo_pdfs_folder(conn, periodo)
        if not folder or not Path(folder).is_dir():
            raise ValueError("La carpeta de soportes de este mes no está configurada o no existe.")
        with storage_module.transaction(conn):
            pdf_cufe_module.index_folder(conn, folder)
        rows = excel_module.fetch_load_rows(conn, load_id)
        pdfs = pdf_cufe_module.list_indexed_pdfs(conn, folder)
        result = rename_module.rename_soportes(rows, pdfs, folder, dry_run=dry_run)
        if not dry_run:
            # tras renombrar, refrescar el índice para que la app vea los nombres nuevos
            with storage_module.transaction(conn):
                pdf_cufe_module.index_folder(conn, folder)
        return result
    finally:
        conn.close()


def _digits(s: Any) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def _con(db_path):
    conn = storage_module.connect(Path(db_path))
    storage_module.ensure_schema(conn)
    return conn


def _h_reglas_list(params: dict) -> dict:
    conn = _con(params["db_path"])
    try:
        return {"reglas": causacion_module.listar(
            conn, incluir_archivadas=bool(params.get("incluir_archivadas")))}
    finally:
        conn.close()


def _h_regla_guardar(params: dict) -> dict:
    conn = _con(params["db_path"])
    try:
        return causacion_module.guardar(conn, params.get("regla") or {})
    finally:
        conn.close()


def _h_regla_archivar(params: dict) -> dict:
    conn = _con(params["db_path"])
    try:
        causacion_module.archivar(conn, int(params["id"]),
                                  bool(params.get("archivada", True)))
        return {"ok": True}
    finally:
        conn.close()


def _h_asiento_generar(params: dict, progress=None) -> dict:
    """Rehace la propuesta del mes. Trabajo largo: va en segundo plano (D-076)."""
    periodo = storage_module._norm_periodo(params.get("periodo") or "")
    conn = _con(params["db_path"])
    try:
        avisa = (lambda m: progress(0, 0, m)) if progress is not None else None
        return asiento_module.generar(conn, periodo, progreso=avisa)
    finally:
        conn.close()


def _h_asiento_list(params: dict) -> dict:
    periodo = storage_module._norm_periodo(params.get("periodo") or "")
    conn = _con(params["db_path"])
    try:
        return {
            "asientos": asiento_module.listar(conn, periodo,
                                              estado=params.get("estado") or None),
            "resumen": asiento_module.resumen(conn, periodo),
        }
    finally:
        conn.close()


def _h_asiento_aprobar(params: dict) -> dict:
    """Aprueba un asiento con las correcciones del contador, y aprende de ellas."""
    conn = _con(params["db_path"])
    try:
        return asiento_module.aprobar(
            conn, int(params["id"]),
            cuenta_puc=(params.get("cuenta_puc") or "").strip() or None,
            patron=(params.get("patron") or "").strip() or None,
            concepto_retencion_id=(int(params["concepto_retencion_id"])
                                   if params.get("concepto_retencion_id") else None),
            cuenta_proveedores=(params.get("cuenta_proveedores") or "").strip() or None,
            cuenta_iva_descontable=(params.get("cuenta_iva_descontable") or "").strip() or None,
            cuenta_clientes=(params.get("cuenta_clientes") or "").strip() or None,
            cuenta_iva_generado=(params.get("cuenta_iva_generado") or "").strip() or None,
            sin_retencion=bool(params.get("sin_retencion")),
            aprender_regla=bool(params.get("aprender_regla", True)),
        )
    finally:
        conn.close()


def _h_asiento_aprobar_lote(params: dict) -> dict:
    periodo = storage_module._norm_periodo(params.get("periodo") or "")
    conn = _con(params["db_path"])
    try:
        return asiento_module.aprobar_lote(conn, periodo)
    finally:
        conn.close()


def _h_asiento_desaprobar(params: dict) -> dict:
    conn = _con(params["db_path"])
    try:
        return asiento_module.desaprobar(conn, int(params["id"]))
    finally:
        conn.close()


def _h_asiento_exportar(params: dict) -> dict:
    """Los asientos aprobados del mes a un Excel, una fila por línea.

    Es lo que hace útil la bandeja ANTES de Siigo: sin esto, aprobar era un
    callejón sin salida y el contador tenía que teclear mirando la pantalla.
    """
    periodo = storage_module._norm_periodo(params.get("periodo") or "")
    carpeta = params.get("output_dir")
    if not carpeta:
        raise ValueError("Hace falta la carpeta donde guardar el archivo.")
    conn = _con(params["db_path"])
    try:
        return export_module.export_asientos(conn, periodo, Path(carpeta))
    finally:
        conn.close()


CUENTAS_EMPRESA = ("cuenta_proveedores", "cuenta_iva_descontable",
                   "cuenta_clientes", "cuenta_iva_generado")


def _h_cuentas_empresa(params: dict) -> dict:
    """Las cuentas que Contab no puede deducir: proveedores, IVA descontable,
    clientes e IVA generado (D-127). Son del PUC de cada empresa."""
    conn = _con(params["db_path"])
    try:
        if any(k in params for k in CUENTAS_EMPRESA):
            actual = dict(conn.execute("SELECT * FROM empresa_info").fetchone() or {})
            conn.execute(
                "UPDATE empresa_info SET " + ", ".join(f"{k} = ?" for k in CUENTAS_EMPRESA),
                tuple((params.get(k) if k in params else actual.get(k)) or None
                      for k in CUENTAS_EMPRESA))
            conn.commit()
        fila = conn.execute(
            "SELECT " + ", ".join(CUENTAS_EMPRESA) + " FROM empresa_info").fetchone()
        return dict(fila) if fila else {}
    finally:
        conn.close()


def _h_tarifas_import(params: dict) -> dict:
    """Sube el Excel de tarifas del contador (4.1). `dry_run` enseña sin escribir.

    No se valida contra el NIT como en el PUC: las tarifas son nacionales, el
    mismo archivo sirve para las cinco empresas que lleva.
    """
    db_path = Path(params["db_path"])
    source_path = Path(params["source_path"])
    dry_run = bool(params.get("dry_run", False))
    try:
        cargado = tarifas_module.cargar(source_path)
    except Exception as exc:
        raise ValueError(f"No se pudo leer el archivo: {exc}") from exc
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return tarifas_module.guardar(conn, cargado, dry_run=dry_run)
    finally:
        conn.close()


def _h_tarifas_list(params: dict) -> dict:
    db_path = Path(params["db_path"])
    anio = int(params.get("anio") or 0) or None
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        conceptos = tarifas_module.listar_conceptos(
            conn, incluir_archivados=bool(params.get("incluir_archivados")))
        if anio:
            # La base en pesos depende del año; se calcula al listar y no se
            # guarda, porque cambia sola cuando cambia la UVT.
            for c in conceptos:
                pesos = tarifas_module.base_minima_pesos(conn, c, anio)
                c["base_minima_pesos"] = str(pesos) if pesos is not None else None
        return {
            "conceptos": conceptos,
            "uvt": tarifas_module.listar_uvt(conn),
            "ultima_importacion": tarifas_module.ultima_importacion(conn),
            "anio": anio,
        }
    finally:
        conn.close()


def _h_tarifas_guardar_concepto(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return tarifas_module.guardar_concepto(conn, params.get("concepto") or {})
    finally:
        conn.close()


def _h_tarifas_guardar_uvt(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return tarifas_module.guardar_uvt(
            conn, int(params["anio"]), str(params["valor"]), str(params.get("norma") or ""))
    finally:
        conn.close()


def _h_tarifas_archivar_concepto(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        tarifas_module.archivar_concepto(
            conn, int(params["id"]), bool(params.get("archivado", True)))
        return {"ok": True}
    finally:
        conn.close()


def _h_puc_import(params: dict) -> dict:
    """Sube un dump de PUC (upsert por código = fusionar). Valida que el NIT del
    encabezado del Excel coincida con la empresa: si no, BLOQUEA (D-070).
    `dry_run=True` devuelve la vista previa sin escribir."""
    db_path = Path(params["db_path"])
    source_path = Path(params["source_path"])
    dry_run = bool(params.get("dry_run", False))

    info = storage_module.read_empresa_info(db_path)
    if info is None:
        raise ValueError("La empresa no está inicializada.")

    try:
        loaded = puc_module.load_puc(source_path)
    except puc_module.PucParseError:
        raise
    except Exception as exc:
        raise ValueError(
            "No pude leer el Excel de cuentas. Revisa que sea el archivo correcto "
            f"en formato .xlsx. Detalle: {exc}"
        ) from exc
    empresa_nit = _digits(info.get("nit"))
    if loaded.empresa_nit and empresa_nit and loaded.empresa_nit != empresa_nit:
        raise ValueError(
            f"El NIT del Excel ({loaded.empresa_nit}) no coincide con el de esta empresa "
            f"({empresa_nit} · {info.get('razon_social')}). No se subió nada. "
            "Verifica que estés subiendo el PUC de la empresa correcta."
        )

    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return puc_module.persist_puc(conn, loaded, dry_run=dry_run)
    finally:
        conn.close()


def _h_get_perfil_fiscal(params: dict) -> dict:
    db_path = Path(params["db_path"])
    fecha = params.get("fecha") or None
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return {
            "perfil": perfil_module.perfil_vigente(conn, fecha=fecha),
            "perfiles": perfil_module.listar_perfiles(conn),
            "municipios_ica": perfil_module.listar_municipios_ica(conn),
        }
    finally:
        conn.close()


def _h_save_perfil_fiscal(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return perfil_module.guardar_perfil(conn, params.get("perfil") or {})
    finally:
        conn.close()


def _h_delete_perfil_fiscal(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        perfil_module.eliminar_perfil(conn, params.get("vigencia_desde") or "")
        return {"ok": True}
    finally:
        conn.close()


def _h_save_municipio_ica(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return perfil_module.guardar_municipio_ica(conn, params.get("municipio") or {})
    finally:
        conn.close()


def _h_delete_municipio_ica(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        perfil_module.eliminar_municipio_ica(conn, params["municipio_id"])
        return {"ok": True}
    finally:
        conn.close()


def _h_terceros_list(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return {
            "terceros": terceros_module.listar(
                conn,
                buscar=params.get("buscar"),
                limit=int(params.get("limit", 500)),
                offset=int(params.get("offset", 0)),
            ),
            "counts": terceros_module.contar(conn),
        }
    finally:
        conn.close()


def _h_terceros_sembrar(params: dict) -> dict:
    """Deriva el catálogo de las filas del Excel ya importadas."""
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return terceros_module.sembrar_desde_excel(conn)
    finally:
        conn.close()


def _h_tercero_save(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return terceros_module.guardar(conn, params.get("tercero") or {})
    finally:
        conn.close()


def _h_catalogo_tercero(_params: dict) -> dict:
    """Los códigos y estados que la pantalla ofrece al editar un tercero.

    Se sirven desde aquí y no se copian en el `.vue` para que la lista que la
    pantalla muestra y la que el motor de retenciones lee sean **la misma**: dos
    copias es cómo empiezan a divergir.
    """
    return {
        "responsabilidades": [
            {"codigo": c, "etiqueta": e}
            for c, e in terceros_module.CODIGOS_RESPONSABILIDAD.items()
        ],
        "estados_rut": list(terceros_module.ESTADOS_RUT),
    }


def _h_tercero_consultar_rut(params: dict) -> dict:
    """Consulta el RUT de un tercero y vuelca lo que devuelva en el catálogo.

    Hoy la consulta pública devuelve razón social y tipo. Las responsabilidades,
    el CIIU y el municipio se escriben a mano hasta que una sesión contra el
    portal real confirme de dónde leerlos — el mismo criterio de la tarea 2.1:
    no se diseña contra una página que nadie ha visto.
    """
    db_path = Path(params["db_path"])
    nit_param = str(params["nit"])
    dv = str(params.get("dv") or "").strip() or nit_module.compute_dv(
        nit_module.normalize(nit_param)
    )
    consulta = dian_inc_module.consultar(nit_param, dv)
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        if not consulta.get("found"):
            return {"consulta": consulta, "tercero": terceros_module.obtener(conn, nit_param)}
        tercero = terceros_module.actualizar_desde_rut(conn, nit_param, consulta)
        return {"consulta": consulta, "tercero": tercero}
    finally:
        conn.close()


def _h_terceros_consultar_rut_todos(params: dict, progress=None) -> dict:
    """Consulta el RUT de todos los terceros pendientes, uno por uno.

    Es un trabajo largo —una consulta HTTP por tercero— así que va como trabajo en
    segundo plano (D-076): treinta y seis terceros son treinta y seis peticiones, y
    una petición síncrona reventaría por timeout mientras Python sigue trabajando.

    Va **de uno en uno y con pausa**: es un servicio público del Estado y no hay
    ninguna prisa que justifique golpearlo en paralelo. Un fallo de red en un NIT
    no aborta el resto; se cuenta y se sigue.
    """
    import time as _time

    db_path = Path(params["db_path"])
    solo_faltantes = bool(params.get("solo_faltantes", True))
    pausa = float(params.get("pausa", 0.7))

    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        pendientes = terceros_module.pendientes_de_rut(conn, solo_faltantes=solo_faltantes)
        total = len(pendientes)
        if progress:
            progress(0, total, f"{total} terceros por consultar")

        encontrados = fallidos = sin_resultado = 0
        for i, fila in enumerate(pendientes, 1):
            nit = fila["nit"]
            dv = fila.get("dv") or nit_module.compute_dv(nit)
            if progress:
                progress(i - 1, total, f"{fila.get('razon_social') or nit}…")
            try:
                consulta = dian_inc_module.consultar(nit, dv)
            except Exception:
                log.exception("falló la consulta del RUT de %s", nit)
                fallidos += 1
            else:
                if consulta.get("found"):
                    terceros_module.actualizar_desde_rut(conn, nit, consulta)
                    encontrados += 1
                elif consulta.get("error"):
                    fallidos += 1
                else:
                    sin_resultado += 1
            if i < total and pausa:
                _time.sleep(pausa)

        if progress:
            progress(total, total, "Listo")
        return {
            "total": total, "encontrados": encontrados,
            "sin_resultado": sin_resultado, "fallidos": fallidos,
            "counts": terceros_module.contar(conn),
        }
    finally:
        conn.close()


def _h_tablero(params: dict) -> dict:
    return tablero_module.tablero(
        params.get("periodo"), include_archived=bool(params.get("include_archived", False))
    )


def _h_puc_list(params: dict) -> dict:
    db_path = Path(params["db_path"])
    include_archived = bool(params.get("include_archived", True))
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return {
            "accounts": puc_module.list_accounts(conn, include_archived=include_archived),
            "counts": puc_module.counts(conn),
            "last_import": puc_module.last_import(conn),
        }
    finally:
        conn.close()


def _h_puc_save_account(params: dict) -> dict:
    db_path = Path(params["db_path"])
    account_id = params.get("account_id")
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return puc_module.save_account(conn, params.get("account") or {}, account_id=account_id)
    finally:
        conn.close()


def _h_puc_archive_account(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        puc_module.set_archived(conn, int(params["account_id"]), bool(params.get("archived", True)))
        return {"ok": True}
    finally:
        conn.close()


def _h_puc_delete_account(params: dict) -> dict:
    db_path = Path(params["db_path"])
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        puc_module.delete_account(conn, int(params["account_id"]))
        return {"ok": True}
    finally:
        conn.close()


def _h_puc_export(params: dict) -> dict:
    db_path = Path(params["db_path"])
    output_path = Path(params["output_path"])
    include_archived = bool(params.get("include_archived", False))
    conn = storage_module.connect(db_path)
    try:
        storage_module.ensure_schema(conn)
        return puc_module.export_puc(conn, output_path, include_archived=include_archived)
    finally:
        conn.close()


# ---------- trabajos en segundo plano (D-076) ----------

# Métodos cuya duración no tiene techo (extracción de PDFs, validación de un mes
# entero). Llamarlos con `"<método>_async"` arranca un trabajo y devuelve su
# `job_id` al instante; el progreso se consulta con `job_status`.
ASYNC_CAPABLE: dict[str, Callable[[dict, Any], Any]] = {
    "run_validations": _h_run_validations,
    "reindex_pdfs": lambda p, progress: _h_reindex_pdfs(p, progress=progress),
    "list_load_soportes": lambda p, progress: _h_list_load_soportes(p, progress=progress),
    "terceros_consultar_rut_todos": _h_terceros_consultar_rut_todos,
    # Los tres se pasaban de los 30 s en meses grandes: la pantalla decía error
    # mientras el sidecar seguía trabajando.
    "asiento_generar": lambda p, progress: _h_asiento_generar(p, progress=progress),
    "mudar_carpetas": lambda p, progress: _h_mudar_carpetas(p, progress=progress),
    "indexar_xml": lambda p, progress: _h_indexar_xml(p, progress=progress),
}


def _h_job_status(params: dict) -> dict:
    return jobs_module.status(str(params["job_id"]))


def _h_job_cancel(params: dict) -> dict:
    return jobs_module.cancel(str(params["job_id"]))


def _h_job_list(_params: dict) -> list[dict]:
    return jobs_module.listar()


def _start_async(method: str, params: dict) -> dict:
    fn = ASYNC_CAPABLE[method]
    return jobs_module.start(method, lambda report: fn(params, report))


HANDLERS: dict[str, Callable[[dict], Any]] = {
    "job_status": _h_job_status,
    "job_cancel": _h_job_cancel,
    "job_list": _h_job_list,
    "ping": _h_ping,
    "check_dependencies": _h_check_dependencies,
    "list_empresas": _h_list_empresas,
    "validate_nit": _h_validate_nit,
    "create_empresa": _h_create_empresa,
    "open_empresa": _h_open_empresa,
    "set_default_folder": _h_set_default_folder,
    "set_pdfs_folder": _h_set_pdfs_folder,
    "update_empresa": _h_update_empresa,
    "archive_empresa": _h_archive_empresa,
    "unarchive_empresa": _h_unarchive_empresa,
    "backup_empresa": _h_backup_empresa,
    "restore_empresa": _h_restore_empresa,
    "delete_empresa": _h_delete_empresa,
    "papelera_list": _h_papelera_list,
    "papelera_restore": _h_papelera_restore,
    "list_pdfs_folder_files": _h_list_pdfs_folder_files,
    "reindex_pdfs": _h_reindex_pdfs,
    "list_load_soportes": _h_list_load_soportes,
    "import_excel": _h_import_excel,
    "list_loads": _h_list_loads,
    "resumen_periodos": _h_resumen_periodos,
    "resumen_emisores": _h_resumen_emisores,
    "list_folder_files": _h_list_folder_files,
    "get_load_rows": _h_get_load_rows,
    "run_validations": _h_run_validations,
    "get_latest_run_failures": _h_get_latest_run_failures,
    "toggle_validation_override": _h_toggle_validation_override,
    "export_no_conformes": _h_export_no_conformes,
    "export_missing_supports": _h_export_missing_supports,
    # 0.1.4 — meses (periodos) + papelera del Excel
    "create_periodo": _h_create_periodo,
    "indexar_xml": lambda p, progress: _h_indexar_xml(p, progress=progress),
    "documento_xml": _h_documento_xml,
    "documentos_del_mes": _h_documentos_del_mes,
    "carpeta_empresa": _h_carpeta_empresa,
    "plan_mudanza": _h_plan_mudanza,
    "mudar_carpetas": _h_mudar_carpetas,
    "list_periodos": _h_list_periodos,
    "set_periodo_pdfs_folder": _h_set_periodo_pdfs_folder,
    "delete_periodo": _h_delete_periodo,
    "set_load_periodo": _h_set_load_periodo,
    "soft_delete_load": _h_soft_delete_load,
    "restore_load": _h_restore_load,
    # 0.1.4 — BD del programa (contab.db)
    "program_get_user": _h_program_get_user,
    "program_save_user": _h_program_save_user,
    "program_get_settings": _h_program_get_settings,
    "program_save_settings": _h_program_save_settings,
    "program_list_empresas": _h_program_list_empresas,
    "citas_list": _h_citas_list,
    "citas_save_persona": _h_citas_save_persona,
    "citas_delete_persona": _h_citas_delete_persona,
    "citas_set_estado": _h_citas_set_estado,
    "program_touch_empresa": _h_program_touch_empresa,
    # Consulta de Inconsistencias DIAN (razón social por NIT+DV)
    "consulta_inconsistencias": _h_consulta_inconsistencias,
    "parse_nit_dv": _h_parse_nit_dv,
    "export_inconsistencias": _h_export_inconsistencias,
    # Renombrado de soportes PDF (DD-MM_NIT_RAZON-SOCIAL_FACTURA)
    "rename_soportes": _h_rename_soportes,
    # Perfil fiscal de la empresa (Fase 1.1 del plan de automatización)
    "get_perfil_fiscal": _h_get_perfil_fiscal,
    "save_perfil_fiscal": _h_save_perfil_fiscal,
    "delete_perfil_fiscal": _h_delete_perfil_fiscal,
    "save_municipio_ica": _h_save_municipio_ica,
    "delete_municipio_ica": _h_delete_municipio_ica,
    # Ingesta desde el portal de la DIAN (Fase 2)
    "preparar_descarga_dian": _h_preparar_descarga_dian,
    "importar_descarga_dian": _h_importar_descarga_dian,
    "registrar_ingesta": _h_registrar_ingesta,
    "documentos_sin_soporte": _h_documentos_sin_soporte,
    "reindexar_soportes_con_nit": _h_reindexar_soportes_con_nit,
    "listar_ingestas": _h_listar_ingestas,
    # Catálogo de terceros por empresa (Fase 1.3, D-100)
    "terceros_list": _h_terceros_list,
    "terceros_sembrar": _h_terceros_sembrar,
    "tercero_save": _h_tercero_save,
    "catalogo_tercero": _h_catalogo_tercero,
    "tercero_consultar_rut": _h_tercero_consultar_rut,
    "terceros_consultar_rut_todos": _h_terceros_consultar_rut_todos,
    # Tablero multiempresa (Fase 1.5)
    "tablero": _h_tablero,
    # Plan Único de Cuentas (PUC) por empresa (D-070)
    "puc_import": _h_puc_import,
    "tarifas_import": _h_tarifas_import,
    "reglas_list": _h_reglas_list,
    "regla_guardar": _h_regla_guardar,
    "regla_archivar": _h_regla_archivar,
    "asiento_generar": lambda p, progress: _h_asiento_generar(p, progress=progress),
    "asiento_list": _h_asiento_list,
    "asiento_aprobar": _h_asiento_aprobar,
    "asiento_aprobar_lote": _h_asiento_aprobar_lote,
    "asiento_desaprobar": _h_asiento_desaprobar,
    "asiento_exportar": _h_asiento_exportar,
    "cuentas_empresa": _h_cuentas_empresa,
    "tarifas_list": _h_tarifas_list,
    "tarifas_guardar_concepto": _h_tarifas_guardar_concepto,
    "tarifas_guardar_uvt": _h_tarifas_guardar_uvt,
    "tarifas_archivar_concepto": _h_tarifas_archivar_concepto,
    "puc_list": _h_puc_list,
    "puc_save_account": _h_puc_save_account,
    "puc_archive_account": _h_puc_archive_account,
    "puc_delete_account": _h_puc_delete_account,
    "puc_export": _h_puc_export,
}


# ---------- IPC loop ----------

def _json_default(obj: Any) -> Any:
    """Único borde de salida de los importes (D-075).

    Un `Decimal` debe viajar a la UI como NÚMERO JSON, no como string: con el
    `default=str` anterior la tabla habría recibido "12952.83" y se le habría roto
    el orden y el formato. Los importes están cuantizados a centavos, así que el
    double más cercano los representa sin pérdida perceptible para mostrar.
    Todo lo demás (Path, datetime…) sigue cayendo a `str`."""
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def handle_request(request: dict) -> dict:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    try:
        if isinstance(method, str) and method.endswith("_async") and method[:-6] in ASYNC_CAPABLE:
            # Arranca el trabajo y responde al instante con su job_id: el bucle
            # queda libre para atender job_status mientras el hilo trabaja.
            result = _start_async(method[:-6], params)
            return {"id": request_id, "result": result}
        handler = HANDLERS.get(method)
        if handler is None:
            return {"id": request_id, "error": {"code": "unknown_method", "message": method or ""}}
        result = handler(params)
        return {"id": request_id, "result": result}
    except Exception as exc:
        # La traza va al log (stderr), no al payload: la UI recibe el mensaje para
        # el usuario, no rutas internas ni nombres de módulo (D-083).
        log.exception("%s falló", method)
        return {
            "id": request_id,
            "error": {"code": exc.__class__.__name__, "message": str(exc)},
        }


def main(argv: list[str] | None = None) -> int:
    # El canal con Nitro es UTF-8 en los dos sentidos. Sin esto, en Windows Python
    # abre stdin/stdout con la página de códigos del sistema (cp1252), y como las
    # respuestas van con ensure_ascii=False, toda Ñ o tilde salía en cp1252 y Node
    # —que lee UTF-8— la volvía «�»: así llegó «CASTA�EDA» a la ficha de un tercero.
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    # Registra en el catálogo central (contab.db) las empresas ya existentes en disco
    # (migración de instalaciones previas a 0.1.4). Best-effort: nunca bloquea el arranque.
    try:
        program_db_module.sync_registry()
    except Exception:
        # Nunca debe impedir el arranque, pero sí debe verse en el log.
        log.exception("sync_registry falló al arrancar")
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {"id": None, "error": {"code": "invalid_json", "message": str(exc)}}
        else:
            response = handle_request(req)
        sys.stdout.write(json.dumps(response, ensure_ascii=False, default=_json_default) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
