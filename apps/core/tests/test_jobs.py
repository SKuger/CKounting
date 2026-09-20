"""Trabajos en segundo plano con progreso (D-076)."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from contab_core import jobs

SAMPLES = Path(__file__).resolve().parents[3] / "docs" / "samples" / "pdfs"
CORE_DIR = Path(__file__).resolve().parents[1]


def _esperar(job_id, timeout=10):
    limite = time.time() + timeout
    while time.time() < limite:
        st = jobs.status(job_id)
        if st["status"] != jobs.STATUS_RUNNING:
            return st
        time.sleep(0.02)
    raise AssertionError("el trabajo no terminó a tiempo")


def test_start_devuelve_al_instante_y_no_bloquea():
    """La clave del arreglo: arrancar un trabajo no espera a que termine."""
    arranque = time.time()
    desc = jobs.start("lento", lambda report: (time.sleep(0.4), "listo")[1])
    assert time.time() - arranque < 0.1, "start() no puede bloquear"
    assert desc["status"] == jobs.STATUS_RUNNING
    assert "result" not in desc

    st = _esperar(desc["job_id"])
    assert st["status"] == jobs.STATUS_DONE
    assert st["result"] == "listo"


def test_publica_progreso():
    def trabajo(report):
        for i in range(4):
            report(i, 4, f"paso {i}")
            time.sleep(0.05)
        return "fin"

    desc = jobs.start("con_progreso", trabajo)
    vistos = set()
    limite = time.time() + 5
    while time.time() < limite:
        st = jobs.status(desc["job_id"])
        if st["progress"]["total"]:
            vistos.add(st["progress"]["done"])
        if st["status"] != jobs.STATUS_RUNNING:
            break
        time.sleep(0.02)
    assert vistos, "debe haberse observado algún avance intermedio"
    assert jobs.status(desc["job_id"])["progress"]["percent"] is not None


def test_error_se_reporta_sin_matar_el_hilo():
    desc = jobs.start("falla", lambda report: (_ for _ in ()).throw(ValueError("algo salió mal")))
    st = _esperar(desc["job_id"])
    assert st["status"] == jobs.STATUS_ERROR
    assert "algo salió mal" in st["error"]


def test_cancelacion():
    """`report` lanza Cancelled, así que basta con llamarlo para ser cancelable."""
    def largo(report):
        for i in range(500):
            report(i, 500, "trabajando")
            time.sleep(0.01)
        return "no deberia llegar"

    desc = jobs.start("cancelable", largo)
    time.sleep(0.05)
    jobs.cancel(desc["job_id"])
    st = _esperar(desc["job_id"])
    assert st["status"] == jobs.STATUS_CANCELLED


def test_job_desconocido_da_mensaje_claro():
    with pytest.raises(ValueError, match="ya no existe"):
        jobs.status("noexiste")


# ── protocolo completo contra el sidecar real, por stdio ──────────────────────

@pytest.mark.skipif(not SAMPLES.is_dir(), reason="faltan los PDFs de muestra")
def test_sidecar_atiende_otras_peticiones_mientras_el_trabajo_corre(tmp_path, isolate_data_dir):
    """El síntoma original: el bucle serial se bloqueaba durante toda la
    extracción y las peticiones siguientes se encolaban hasta reventar."""
    soportes = tmp_path / "soportes"
    soportes.mkdir()
    muestras = sorted(SAMPLES.glob("*.pdf"))
    if not muestras:
        pytest.skip("sin PDFs de muestra")
    for m in muestras:
        shutil.copy(m, soportes / m.name)

    env = {
        **os.environ,
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "APPDATA": str(tmp_path / "data"),
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "contab_core.sidecar"],
        cwd=str(CORE_DIR), env=env, text=True, encoding="utf-8",
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    contador = [0]

    def call(method, params):
        contador[0] += 1
        proc.stdin.write(json.dumps({"id": str(contador[0]), "method": method, "params": params}) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    try:
        emp = call("create_empresa", {"nit": "900181831", "razon_social": "REAL"})["result"]
        call("set_pdfs_folder", {"db_path": emp["db_path"], "folder": str(soportes)})

        t0 = time.time()
        inicio = call("reindex_pdfs_async", {"db_path": emp["db_path"]})["result"]
        assert time.time() - t0 < 2, "arrancar el trabajo debe ser inmediato"
        assert inicio["status"] == jobs.STATUS_RUNNING

        atendidas = 0
        limite = time.time() + 60
        while time.time() < limite:
            st = call("job_status", {"job_id": inicio["job_id"]})["result"]
            if st["status"] != jobs.STATUS_RUNNING:
                break
            # Esto es lo que antes no era posible: el bucle sigue respondiendo.
            assert call("ping", {})["result"]["pong"] is True
            atendidas += 1
            time.sleep(0.05)

        assert st["status"] == jobs.STATUS_DONE, st.get("error")
        assert atendidas > 0, "el bucle debe atender peticiones durante el trabajo"
        assert st["result"]["stats"]["total_pdfs"] == len(muestras)
    finally:
        proc.stdin.close()
        proc.wait(timeout=15)
