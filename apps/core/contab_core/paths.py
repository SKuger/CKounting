"""OS-aware paths for Contab data (D-021)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP_NAME = "Contab"


def data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / APP_NAME


def empresas_dir() -> Path:
    p = data_dir() / "empresas"
    p.mkdir(parents=True, exist_ok=True)
    return p


def papelera_dir() -> Path:
    """Donde van las empresas borradas antes de desaparecer de verdad (D-078).

    Borrar una empresa es borrar la contabilidad completa de un cliente, con
    obligación legal de conservación. No puede depender de un clic bien dado."""
    p = data_dir() / "papelera"
    p.mkdir(parents=True, exist_ok=True)
    return p


def descargas_dir(nit: str) -> Path:
    """Donde caen los archivos que Contab baja de la DIAN, por empresa.

    Es una carpeta que administra Contab, no una que el contador elija: el ZIP y el
    Excel del portal son un paso intermedio, no documentos suyos. Pedirle que
    configurara una carpeta para esto era pedirle trabajo por un archivo que no va
    a volver a abrir — y encima el campo que se le pedía (`default_folder`) no tiene
    dónde configurarse desde que el mes pasó a ser el contenedor (D-062).
    """
    destino = data_dir() / "descargas" / (nit or "sin-nit")
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def program_db_path() -> Path:
    """The program-level DB (contab.db): user, settings, empresa registry.
    Complements D-003 (per-empresa DBs stay isolated); this only holds
    cross-empresa/app-level data."""
    base = data_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base / "contab.db"


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def empresa_slug(nit: str, razon_social: str) -> str:
    """<nit>_<razon-social-slug> for human-recognisable filenames.

    El NIT se reduce a dígitos: llega desde el meta.json de un backup, que es un
    archivo que el usuario recibe de fuera. Interpolarlo crudo permitía que un
    `nit` con '..' o separadores escribiera el .db fuera de la carpeta de empresas."""
    digits = "".join(c for c in str(nit or "") if c.isdigit())
    if not digits:
        raise ValueError(f"NIT inválido para nombre de archivo: {nit!r}")
    slug = _SLUG_RE.sub("-", razon_social.lower()).strip("-") or "empresa"
    return f"{digits}_{slug}"


def empresa_db_path(nit: str, razon_social: str) -> Path:
    return empresas_dir() / f"{empresa_slug(nit, razon_social)}.db"


def scan_empresa_dbs() -> list[Path]:
    return sorted(p for p in empresas_dir().glob("*.db") if p.is_file())
