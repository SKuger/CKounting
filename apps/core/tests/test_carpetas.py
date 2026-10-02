"""La forma del disco: una carpeta por empresa, dentro una por mes, y dentro el
Excel y `soportes`.

Lo que más importa aquí no es que cree carpetas: es que mover documentos de un
cliente no pierda ninguno y se pueda deshacer.
"""
from pathlib import Path

import pytest

from contab_core import carpetas, storage
from contab_core.sidecar import HANDLERS


@pytest.fixture
def empresa(tmp_path: Path) -> Path:
    db_path = tmp_path / "empresa.db"
    storage.init_empresa_db(db_path, nit="900181831", dv="7", razon_social="REAL")
    return db_path


def test_el_mes_nace_con_su_carpeta(empresa: Path, tmp_path: Path):
    raiz = tmp_path / "REAL Seguros"
    HANDLERS["carpeta_empresa"]({"db_path": str(empresa), "carpeta": str(raiz)})
    res = HANDLERS["create_periodo"]({"db_path": str(empresa), "periodo": "2026-09"})

    assert (raiz / "2026-09" / "soportes").is_dir()
    assert res["pdfs_folder"] == str(raiz / "2026-09" / "soportes")
    assert storage.periodo_folders(empresa)["2026-09"] == str(raiz / "2026-09" / "soportes")


def test_sin_carpeta_de_empresa_lo_dice_en_vez_de_inventarse_una(empresa: Path):
    res = HANDLERS["create_periodo"]({"db_path": str(empresa), "periodo": "2026-09"})
    assert res["falta_carpeta_empresa"] is True
    assert "pdfs_folder" not in res


def test_la_mudanza_lleva_cada_cosa_a_su_sitio(empresa: Path, tmp_path: Path):
    vieja = tmp_path / "Escritorio" / "septiembre"
    vieja.mkdir(parents=True)
    (vieja / "factura1.pdf").write_bytes(b"%PDF-1.4 uno")
    (vieja / "factura2.pdf").write_bytes(b"%PDF-1.4 dos")
    (vieja / "listado.xlsx").write_bytes(b"PK excel")
    storage.set_periodo_folder(empresa, "2026-09", str(vieja))

    raiz = tmp_path / "REAL Seguros"
    plan = HANDLERS["plan_mudanza"]({"db_path": str(empresa), "carpeta": str(raiz)})
    assert plan["total"] == 3, "el plan se ve antes de mover nada"
    assert plan["movidos"] == 0
    assert (vieja / "factura1.pdf").exists(), "un plan no mueve"

    res = HANDLERS["mudar_carpetas"]({"db_path": str(empresa), "carpeta": str(raiz)})
    assert res["movidos"] == 3 and res["fallidos"] == 0
    assert (raiz / "2026-09" / "soportes" / "factura1.pdf").read_bytes() == b"%PDF-1.4 uno"
    assert (raiz / "2026-09" / "soportes" / "factura2.pdf").exists()
    assert (raiz / "2026-09" / "listado.xlsx").exists(), "el Excel va al mes, no a soportes"
    assert not (vieja / "factura1.pdf").exists()
    assert storage.periodo_folders(empresa)["2026-09"] == str(raiz / "2026-09" / "soportes")


def test_la_mudanza_deja_manifiesto(empresa: Path, tmp_path: Path):
    vieja = tmp_path / "vieja"
    vieja.mkdir()
    (vieja / "x.pdf").write_bytes(b"%PDF")
    storage.set_periodo_folder(empresa, "2026-09", str(vieja))
    raiz = tmp_path / "raiz"

    res = HANDLERS["mudar_carpetas"]({"db_path": str(empresa), "carpeta": str(raiz)})
    manifiesto = Path(res["manifiesto"])
    assert manifiesto.name == carpetas.MANIFIESTO
    texto = manifiesto.read_text(encoding="utf-8-sig")
    assert "x.pdf" in texto and str(vieja) in texto, "dice de dónde salió cada archivo"


def test_no_pisa_un_archivo_que_ya_estaba(empresa: Path, tmp_path: Path):
    vieja = tmp_path / "vieja"
    vieja.mkdir()
    (vieja / "factura.pdf").write_bytes(b"el del cliente")
    storage.set_periodo_folder(empresa, "2026-09", str(vieja))

    raiz = tmp_path / "raiz"
    destino = carpetas.carpeta_soportes(raiz, "2026-09")
    destino.mkdir(parents=True)
    (destino / "factura.pdf").write_bytes(b"el que ya estaba")

    HANDLERS["mudar_carpetas"]({"db_path": str(empresa), "carpeta": str(raiz)})
    assert (destino / "factura.pdf").read_bytes() == b"el que ya estaba"
    assert (destino / "factura_1.pdf").read_bytes() == b"el del cliente"


def test_un_mes_con_ruta_rota_se_re_apunta_sin_romperse(empresa: Path, tmp_path: Path):
    """Tres meses del usuario apuntan a un escritorio que ya no existe."""
    storage.set_periodo_folder(empresa, "2026-07", str(tmp_path / "se-fue" / "julio"))
    raiz = tmp_path / "raiz"

    res = HANDLERS["mudar_carpetas"]({"db_path": str(empresa), "carpeta": str(raiz)})
    assert res["fallidos"] == 0
    assert storage.periodo_folders(empresa)["2026-07"] == str(raiz / "2026-07" / "soportes")
    assert (raiz / "2026-07" / "soportes").is_dir()
