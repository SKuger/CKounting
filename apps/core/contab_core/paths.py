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


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def empresa_slug(nit: str, razon_social: str) -> str:
    """<nit>_<razon-social-slug> for human-recognisable filenames."""
    slug = _SLUG_RE.sub("-", razon_social.lower()).strip("-") or "empresa"
    return f"{nit}_{slug}"


def empresa_db_path(nit: str, razon_social: str) -> Path:
    return empresas_dir() / f"{empresa_slug(nit, razon_social)}.db"


def scan_empresa_dbs() -> list[Path]:
    return sorted(p for p in empresas_dir().glob("*.db") if p.is_file())
