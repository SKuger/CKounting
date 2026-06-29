"""Runtime paths for the DIAN sidecar.

Packaged in the desktop app, the cwd is read-only (Program Files / app resources), so all writable
dirs (uploads, results, errors, browser_profile) must live under a writable workdir — the shell sets
DIAN_WORKDIR=%APPDATA%\\Contab\\dian. In dev (no env var) we fall back to the cwd, so behaviour is
unchanged. `static/` ships read-only inside the bundle, resolved relative to the executable.
"""
import os
import sys

WORKDIR = os.environ.get("DIAN_WORKDIR") or os.getcwd()

UPLOADS_DIR = os.path.join(WORKDIR, "uploads")
RESULTS_DIR = os.path.join(WORKDIR, "results")
ERRORS_DIR = os.path.join(WORKDIR, "errors")
BROWSER_PROFILE_DIR = os.path.join(WORKDIR, "browser_profile")


def _base_dir() -> str:
    # PyInstaller: bundled datas live under sys._MEIPASS (the _internal dir in onedir / the temp
    # extract dir in onefile). Dev: this file's own dir.
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


STATIC_DIR = os.path.join(_base_dir(), "static")

for _d in (UPLOADS_DIR, RESULTS_DIR, ERRORS_DIR, BROWSER_PROFILE_DIR):
    os.makedirs(_d, exist_ok=True)
