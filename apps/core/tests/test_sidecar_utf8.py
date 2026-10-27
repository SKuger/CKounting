"""El canal stdio del sidecar es UTF-8 aunque el sistema diga otra cosa.

Carlos vio «CASTA�EDA» en la ficha de un tercero. La DIAN mandaba bien la Ñ y
SQLite la guardaba bien; se perdía en el tubo: en Windows, Python abría stdout
con cp1252 y Node lo leía como UTF-8. Esta prueba arranca el sidecar de verdad
con la codificación «equivocada» impuesta por entorno y exige que la Ñ llegue.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1]


def _sidecar(tmp_path: Path, **env_extra):
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path), "APPDATA": str(tmp_path), **env_extra}
    return subprocess.Popen(
        [sys.executable, "-m", "contab_core.sidecar"],
        cwd=str(CORE_DIR), env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def test_la_tilde_sobrevive_al_tubo_aunque_el_sistema_hable_cp1252(tmp_path: Path):
    # La petición va en ASCII puro a propósito: si la Ñ viajara en la petición, el
    # error sería simétrico (mal leída, mal escrita) y la prueba no lo vería. El
    # texto con tilde lo pone Python, como pasa con un nombre que viene de la DIAN.
    proc = _sidecar(tmp_path, PYTHONIOENCODING="cp1252")
    try:
        req = {"id": "1", "method": "create_empresa",
               "params": {"nit": "900181831-5", "razon_social": "PRUEBA"}}
        proc.stdin.write((json.dumps(req) + "\n").encode("ascii"))
        proc.stdin.flush()
        crudo = proc.stdout.readline()
    finally:
        proc.stdin.close()
        proc.wait(timeout=15)
    assert b"\xef\xbf\xbd" not in crudo, "salió el carácter de reemplazo «�»"
    resp = json.loads(crudo.decode("utf-8"))
    assert "DV inválido" in resp["error"]["message"], resp
