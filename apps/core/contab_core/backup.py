"""E2 — Backup / restore de una empresa.

Backup (D-043): un único `.contab.zip` con
  empresa.db           ← .db con WAL checkpointed
  excels/<original>    ← los Excels importados (source_path) que aún existen en disco
  pdfs/<original>      ← los PDFs presentes en pdfs_folder al momento del backup
  meta.json            ← NIT, razón social, rutas originales, timestamp, versión

Restore:
  - Recupera la BD a <empresas_dir>/<slug>.db. Si existe, renombra a
    <slug>_restored[_N].db (D-E2-3 — política autom-rename por defecto).
  - Extrae los archivos a <empresas_dir>/<slug>_restored_files/{excels,pdfs}/.
  - Actualiza `default_folder` y `pdfs_folder` de la BD restaurada para que
    apunten a las carpetas restauradas.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import paths as paths_module
from . import program_db as program_db_module
from . import storage

BACKUP_VERSION = 1
ZIP_DB_NAME = "empresa.db"
ZIP_META_NAME = "meta.json"
ZIP_EXCELS_PREFIX = "excels/"
ZIP_PDFS_PREFIX = "pdfs/"

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    """Strip path separators and unsafe chars; used for backup output names."""
    cleaned = _SAFE_NAME_RE.sub("-", name).strip("-_.")
    return cleaned or "empresa"


@dataclass
class BackupResult:
    path: str
    size_bytes: int
    excels_included: int
    pdfs_included: int

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "excels_included": self.excels_included,
            "pdfs_included": self.pdfs_included,
        }


@dataclass
class RestoreResult:
    db_path: str
    excels_folder: str | None
    pdfs_folder: str | None
    excels_restored: int
    pdfs_restored: int
    conflict_action: str | None
    meta: dict

    def to_dict(self) -> dict:
        return {
            "db_path": self.db_path,
            "excels_folder": self.excels_folder,
            "pdfs_folder": self.pdfs_folder,
            "excels_restored": self.excels_restored,
            "pdfs_restored": self.pdfs_restored,
            "conflict_action": self.conflict_action,
            "meta": self.meta,
        }


def _list_excels_to_backup(db_path: Path) -> list[Path]:
    conn = storage.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT source_path FROM excel_load WHERE source_path IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    out: list[Path] = []
    seen: set[str] = set()
    for r in rows:
        sp = r["source_path"]
        if not sp or sp in seen:
            continue
        seen.add(sp)
        p = Path(sp)
        if p.is_file():
            out.append(p)
    return out


def _list_pdfs_to_backup(pdfs_folder: str | None) -> list[Path]:
    if not pdfs_folder:
        return []
    folder = Path(pdfs_folder)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def backup_empresa(db_path: str | Path, dest_folder: str | Path) -> BackupResult:
    db_path = Path(db_path)
    dest_folder = Path(dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)

    info = storage.read_empresa_info(db_path)
    if info is None:
        raise ValueError("empresa.db no inicializada")

    # Make sure WAL pages are persisted into the main file before copying.
    storage.wal_checkpoint(db_path)

    excels = _list_excels_to_backup(db_path)
    pdfs = _list_pdfs_to_backup(info.get("pdfs_folder"))

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = _safe_filename(f"{info['nit']}_{info['razon_social']}")
    output_path = dest_folder / f"{base}_{timestamp}.contab.zip"

    meta = {
        "backup_version": BACKUP_VERSION,
        "nit": info["nit"],
        "dv": info.get("dv"),
        "razon_social": info["razon_social"],
        "archived": info.get("archived", False),
        "default_folder": info.get("default_folder"),
        "pdfs_folder": info.get("pdfs_folder"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_db": str(db_path),
        "excel_files": [p.name for p in excels],
        "pdf_files": [p.name for p in pdfs],
    }

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(db_path, arcname=ZIP_DB_NAME)
            z.writestr(ZIP_META_NAME, json.dumps(meta, ensure_ascii=False, indent=2))
            seen_names_excel: set[str] = set()
            for p in excels:
                arcname = ZIP_EXCELS_PREFIX + _disambiguate(p.name, seen_names_excel)
                z.write(p, arcname=arcname)
            seen_names_pdf: set[str] = set()
            for p in pdfs:
                arcname = ZIP_PDFS_PREFIX + _disambiguate(p.name, seen_names_pdf)
                z.write(p, arcname=arcname)
        tmp_path.replace(output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return BackupResult(
        path=str(output_path),
        size_bytes=output_path.stat().st_size,
        excels_included=len(excels),
        pdfs_included=len(pdfs),
    )


def _disambiguate(name: str, seen: set[str]) -> str:
    """Append _2, _3, ... if a filename would collide inside the zip."""
    if name not in seen:
        seen.add(name)
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 2
    while True:
        candidate = f"{stem}_{i}{suffix}"
        if candidate not in seen:
            seen.add(candidate)
            return candidate
        i += 1


def _assert_dentro_de(base: Path, candidate: Path) -> Path:
    """Defensa en profundidad: el destino de un restore debe quedar DENTRO de la
    carpeta de empresas. El slug ya sanea el NIT (paths.empresa_slug), pero el
    meta.json viene de un archivo externo y esto no debe depender de una sola capa."""
    base_r = base.resolve()
    cand_r = (base_r / candidate.name).resolve() if candidate.name else base_r
    if cand_r.parent != base_r:
        raise ValueError("Backup inválido: la ruta de destino se sale de la carpeta de empresas.")
    return cand_r


def _unique_db_path(empresas_dir: Path, slug: str) -> tuple[Path, str | None]:
    """Return a (path, conflict_action) tuple. Tries the natural slug first; if
    occupied, appends _restored[_N]."""
    natural = _assert_dentro_de(empresas_dir, empresas_dir / f"{slug}.db")
    if not natural.exists():
        return natural, None
    suffix = "_restored"
    i = 1
    while True:
        suffix_id = "" if i == 1 else f"_{i}"
        candidate = empresas_dir / f"{slug}{suffix}{suffix_id}.db"
        if not candidate.exists():
            return candidate, f"existía '{slug}.db', renombrado a '{candidate.name}'"
        i += 1


def restore_empresa(
    zip_path: str | Path,
    empresas_dir: str | Path | None = None,
) -> RestoreResult:
    zip_path = Path(zip_path)
    if empresas_dir is None:
        empresas_dir = paths_module.empresas_dir()
    empresas_dir = Path(empresas_dir)
    empresas_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as z:
        try:
            meta_raw = z.read(ZIP_META_NAME)
        except KeyError:
            raise ValueError("Backup inválido: falta meta.json") from None
        meta = json.loads(meta_raw)

        nit = meta.get("nit")
        razon = meta.get("razon_social")
        if not nit or not razon:
            raise ValueError("meta.json incompleto (nit/razon_social)")

        slug = paths_module.empresa_slug(nit, razon)
        target_db, conflict_action = _unique_db_path(empresas_dir, slug)

        # Restored sidecar files: place under <empresas_dir>/<target-stem>_files/
        files_dir = empresas_dir / f"{target_db.stem}_files"
        excels_dir = files_dir / "excels"
        pdfs_dir = files_dir / "pdfs"

        # Extract DB.
        with z.open(ZIP_DB_NAME) as src, open(target_db, "wb") as dst:
            shutil.copyfileobj(src, dst)

        excels_restored = 0
        pdfs_restored = 0
        for name in z.namelist():
            if name in (ZIP_DB_NAME, ZIP_META_NAME):
                continue
            if name.startswith(ZIP_EXCELS_PREFIX):
                excels_dir.mkdir(parents=True, exist_ok=True)
                target = excels_dir / Path(name).name
                with z.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                excels_restored += 1
            elif name.startswith(ZIP_PDFS_PREFIX):
                pdfs_dir.mkdir(parents=True, exist_ok=True)
                target = pdfs_dir / Path(name).name
                with z.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pdfs_restored += 1

    # Reapply schema on the restored DB (runs migrations and ensures consistency).
    conn = storage.connect(target_db)
    try:
        storage.ensure_schema(conn)
    finally:
        conn.close()

    # Repoint folders. The original paths probably don't exist on this machine.
    storage.set_default_folder(target_db, str(excels_dir) if excels_restored else None)
    storage.set_pdfs_folder(target_db, str(pdfs_dir) if pdfs_restored else None)

    # Alta en el catálogo central (D-077): sin esto la empresa restaurada no
    # aparecía hasta el siguiente arranque, cuando sync_registry la descubría.
    try:
        program_db_module.register_empresa(
            target_db, nit=nit, dv=meta.get("dv"), razon_social=razon
        )
    except Exception:
        pass

    return RestoreResult(
        db_path=str(target_db),
        excels_folder=str(excels_dir) if excels_restored else None,
        pdfs_folder=str(pdfs_dir) if pdfs_restored else None,
        excels_restored=excels_restored,
        pdfs_restored=pdfs_restored,
        conflict_action=conflict_action,
        meta=meta,
    )


PAPELERA_RETENCION_DIAS = 30


def _sello() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def purgar_papelera(dias: int = PAPELERA_RETENCION_DIAS) -> int:
    """Borra definitivamente lo que lleve más de `dias` en la papelera."""
    limite = time.time() - dias * 86400
    borrados = 0
    for f in paths_module.papelera_dir().glob("*.db"):
        try:
            if f.stat().st_mtime < limite:
                f.unlink()
                borrados += 1
        except OSError:
            continue
    return borrados


def listar_papelera() -> list[dict]:
    """Qué hay en la papelera y desde cuándo, para poder recuperarlo."""
    out: list[dict] = []
    for f in sorted(paths_module.papelera_dir().glob("*.db"), reverse=True):
        try:
            st = f.stat()
        except OSError:
            continue
        info = None
        try:
            info = storage.read_empresa_info(f)
        except Exception:
            pass
        borrado = datetime.fromtimestamp(st.st_mtime)
        out.append({
            "archivo": f.name,
            "ruta": str(f),
            "nit": (info or {}).get("nit"),
            "razon_social": (info or {}).get("razon_social"),
            "borrado_el": borrado.isoformat(timespec="seconds"),
            "dias_restantes": max(
                0, PAPELERA_RETENCION_DIAS - int((time.time() - st.st_mtime) // 86400)
            ),
            "bytes": st.st_size,
        })
    return out


def restaurar_de_papelera(archivo: str) -> dict:
    """Devuelve una empresa de la papelera a la carpeta de empresas."""
    origen = paths_module.papelera_dir() / Path(archivo).name
    if not origen.is_file():
        raise ValueError(f"No está en la papelera: {archivo}")
    info = storage.read_empresa_info(origen)
    if info is None:
        raise ValueError("El archivo de la papelera no es una empresa válida.")
    slug = paths_module.empresa_slug(info["nit"], info["razon_social"])
    destino, conflicto = _unique_db_path(paths_module.empresas_dir(), slug)
    shutil.move(str(origen), str(destino))
    try:
        program_db_module.register_empresa(
            destino, nit=info["nit"], dv=info.get("dv"), razon_social=info["razon_social"]
        )
    except Exception:
        pass  # el catálogo se reconcilia solo en el próximo arranque
    return {
        "db_path": str(destino),
        "nit": info["nit"],
        "razon_social": info["razon_social"],
        "conflict_action": conflicto,
    }


def delete_empresa_file(db_path: str | Path, confirm_nit: str) -> dict:
    """Borra una empresa moviéndola a la PAPELERA (D-078), no con `unlink`.

    Antes era un borrado duro e irreversible con solo el NIT como confirmación.
    Ahora el .db se mueve a `<data_dir>/papelera/` y se conserva 30 días, así que
    un clic equivocado se deshace con `restaurar_de_papelera`. Los archivos
    -wal/-shm sí se descartan: son estado transitorio, y el checkpoint previo
    vuelca su contenido al .db.

    Caller must close all connections first."""
    db_path = Path(db_path)
    info = storage.read_empresa_info(db_path)
    if info is None:
        raise ValueError("empresa.db no inicializada")
    if confirm_nit.strip() != info["nit"]:
        raise ValueError(
            f"NIT de confirmación no coincide (recibido {confirm_nit!r}, esperado {info['nit']!r})"
        )

    # Volcar el WAL al .db para que lo que se mueve esté completo.
    try:
        storage.wal_checkpoint(db_path)
    except Exception:
        pass

    destino = paths_module.papelera_dir() / f"{_sello()}_{db_path.name}"
    i = 1
    while destino.exists():
        destino = paths_module.papelera_dir() / f"{_sello()}_{i}_{db_path.name}"
        i += 1
    shutil.move(str(db_path), str(destino))

    descartados = []
    for sibling in (db_path.with_suffix(".db-wal"), db_path.with_suffix(".db-shm")):
        if sibling.exists():
            sibling.unlink()
            descartados.append(sibling.name)

    # El catálogo central deja de anunciar una empresa que ya no está (D-077).
    try:
        program_db_module.unregister_empresa(db_path)
    except Exception:
        pass

    purgados = purgar_papelera()
    return {
        "deleted": [db_path.name, *descartados],
        "nit": info["nit"],
        "razon_social": info["razon_social"],
        "papelera": str(destino),
        "dias_retencion": PAPELERA_RETENCION_DIAS,
        "purgados_de_papelera": purgados,
    }
