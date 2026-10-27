"""Ingesta desde el portal de la DIAN (Fase 2).

El enlace de acceso de la DIAN es una llave a la cuenta de un cliente. La mitad de
estos tests no comprueban que algo funcione, sino que ese enlace **no se escape**:
ni al log, ni al mensaje de un error, ni al resultado de un trabajo.
"""
import zipfile
from datetime import date

import pytest

from contab_core import dian_portal as dp
from contab_core.dian_portal import DianPortalError

ENLACE = (
    "https://catalogo-vpfe.dian.gov.co/User/AuthToken"
    "?pk=10910094%7C98634425&rk=900921756&token=24bdb332-ea46-42ad-8e38-36bf51f33c29"
)
SECRETO = "24bdb332-ea46-42ad-8e38-36bf51f33c29"


# ── el rango del mes ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("periodo,esperado", [
    ("2026-01", ("2026-01-01", "2026-01-31")),
    ("2026-04", ("2026-04-01", "2026-04-30")),
    ("2024-02", ("2024-02-01", "2024-02-29")),   # bisiesto
    ("2026-02", ("2026-02-01", "2026-02-28")),
    ("2026-12", ("2026-12-01", "2026-12-31")),
])
def test_el_ultimo_dia_del_mes_se_calcula(periodo, esperado):
    """Un rango que se queda corto deja documentos fuera del mes, y eso es
    contabilidad que falta — no un detalle de formato."""
    assert dp.rango_del_mes(periodo, hoy=date(2027, 6, 1)) == esperado


def test_el_mes_en_curso_se_pide_hasta_hoy():
    """Carlos pidió octubre el 27 de octubre y la DIAN respondió 500 a un rango
    que terminaba el 31: el portal no acepta un día futuro."""
    assert dp.rango_del_mes("2026-10", hoy=date(2026, 10, 27)) == ("2026-10-01", "2026-10-27")
    assert dp.rango_del_mes("2026-09", hoy=date(2026, 10, 27)) == ("2026-09-01", "2026-09-30")


def test_un_mes_que_no_ha_empezado_es_error():
    with pytest.raises(DianPortalError, match="no empieza"):
        dp.rango_del_mes("2026-11", hoy=date(2026, 10, 27))


@pytest.mark.parametrize("malo", ["2026-13", "26-01", "2026-1", "", "marzo", "2026-00"])
def test_un_mes_invalido_es_error(malo):
    with pytest.raises(DianPortalError, match="AAAA-MM"):
        dp.rango_del_mes(malo)


# ── el enlace ────────────────────────────────────────────────────────────────

def test_el_enlace_valido_pasa():
    assert dp.validar_enlace(f"  {ENLACE}  ") == ENLACE


@pytest.mark.parametrize("malo", [
    "",
    "https://otro-sitio.com/User/AuthToken?token=x",
    "https://catalogo-vpfe.dian.gov.co/User/Login",
    "https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=1&rk=2",   # sin token
])
def test_un_enlace_que_no_es_el_de_la_dian_se_rechaza(malo):
    with pytest.raises(DianPortalError):
        dp.validar_enlace(malo)


def test_el_error_del_enlace_no_repite_el_enlace():
    """Si el mensaje incluyera lo que llegó, el enlace acabaría en el log y en la
    captura de pantalla que el usuario manda para pedir ayuda."""
    try:
        dp.validar_enlace(ENLACE.replace("catalogo-vpfe.dian.gov.co", "falso.example"))
    except DianPortalError as exc:
        assert SECRETO not in str(exc)
        assert "token=" not in str(exc)
    else:
        pytest.fail("debía fallar")


def test_enmascarar_tapa_el_enlace_en_cualquier_texto():
    texto = f"la corrida falló al abrir {ENLACE} después de 3 intentos"
    salida = dp.enmascarar(texto)
    assert SECRETO not in salida
    assert "«enlace omitido»" in salida
    assert "la corrida falló al abrir" in salida and "después de 3 intentos" in salida


def test_enmascarar_no_toca_un_texto_sin_enlaces():
    assert dp.enmascarar("todo bien") == "todo bien"


def test_preparar_descarga_valida_todo_junto():
    plan = dp.preparar_descarga("2026-07", ENLACE, "recibidos")
    assert plan["desde"] == "2026-07-01" and plan["hasta"] == "2026-07-31"
    assert plan["grupo"] == "recibidos" and plan["etiqueta"] == "2026-07"


def test_un_grupo_inventado_se_rechaza():
    with pytest.raises(DianPortalError, match="Grupo desconocido"):
        dp.preparar_descarga("2026-07", ENLACE, "pendientes")


# ── el ZIP ───────────────────────────────────────────────────────────────────

def _zip_con(tmp_path, nombres):
    z = tmp_path / "bajado.zip"
    with zipfile.ZipFile(z, "w") as f:
        for n in nombres:
            f.writestr(n, b"contenido")
    return z


def test_saca_el_excel_de_adentro_del_zip(tmp_path):
    """El portal no entrega el .xlsx suelto: viene dentro de un ZIP."""
    z = _zip_con(tmp_path, ["293a6c04-f112.xlsx"])
    salida = dp.extraer_excel(z, tmp_path / "mes.xlsx")
    assert salida.is_file() and salida.read_bytes() == b"contenido"


def test_un_zip_sin_excel_lo_dice_con_lo_que_trae(tmp_path):
    z = _zip_con(tmp_path, ["leeme.txt", "otro.pdf"])
    with pytest.raises(DianPortalError, match="no trae ningún Excel"):
        dp.extraer_excel(z, tmp_path / "mes.xlsx")


def test_si_algun_dia_entregan_el_excel_directo_tambien_sirve(tmp_path):
    suelto = tmp_path / "listado.xlsx"
    suelto.write_bytes(b"excel")
    assert dp.extraer_excel(suelto, tmp_path / "mes.xlsx").read_bytes() == b"excel"


def test_un_archivo_que_no_es_ni_zip_ni_excel_es_error(tmp_path):
    raro = tmp_path / "cosa.bin"
    raro.write_bytes(b"\x00\x01")
    with pytest.raises(DianPortalError, match="no es un ZIP ni un Excel"):
        dp.extraer_excel(raro, tmp_path / "mes.xlsx")


def test_un_archivo_que_no_existe_lo_dice_por_su_nombre(tmp_path):
    with pytest.raises(DianPortalError, match="No encuentro"):
        dp.extraer_excel(tmp_path / "no-esta.zip", tmp_path / "mes.xlsx")


# ── la bitácora ──────────────────────────────────────────────────────────────

@pytest.fixture()
def conn(tmp_path):
    from contab_core import storage
    db = tmp_path / "empresa.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL Seguros")
    c = storage.connect(db)
    storage.ensure_schema(c)
    yield c
    c.close()


def test_una_corrida_queda_anotada(conn):
    dp.registrar_ingesta(conn, periodo="2026-07", documentos=412, archivo="/tmp/x.xlsx")
    corridas = dp.listar_ingestas(conn)
    assert len(corridas) == 1
    assert corridas[0]["periodo"] == "2026-07" and corridas[0]["documentos"] == 412
    assert corridas[0]["estado"] == "ok" and corridas[0]["corrio_at"]


def test_el_error_se_guarda_enmascarado(conn):
    """El punto entero de la bitácora es poder leerla después. Si el enlace se
    guardara ahí, la llave de la cuenta del cliente quedaría en la base."""
    dp.registrar_ingesta(
        conn, periodo="2026-07", estado="error",
        error=f"no pude abrir {ENLACE} después de 3 intentos",
    )
    guardado = dp.listar_ingestas(conn)[0]["error"]
    assert SECRETO not in guardado
    assert "«enlace omitido»" in guardado and "después de 3 intentos" in guardado


def test_las_corridas_salen_de_la_mas_reciente(conn):
    for p in ("2026-05", "2026-06", "2026-07"):
        dp.registrar_ingesta(conn, periodo=p)
    assert dp.listar_ingestas(conn)[0]["periodo"] == "2026-07"


def test_se_pueden_filtrar_por_mes(conn):
    dp.registrar_ingesta(conn, periodo="2026-06")
    dp.registrar_ingesta(conn, periodo="2026-07")
    assert len(dp.listar_ingestas(conn, periodo="2026-07")) == 1


def test_un_camino_inventado_se_rechaza(conn):
    with pytest.raises(DianPortalError, match="Camino desconocido"):
        dp.registrar_ingesta(conn, periodo="2026-07", camino="telepatía")


def test_el_plan_de_descarga_cae_en_la_carpeta_del_mes(tmp_path):
    """Carlos, 0.11.0: «Traer de la DIAN» moría con `'periodo'` en toda empresa
    que ya tuviera carpeta. El plan traía `etiqueta` y el sidecar pedía
    `periodo` para crear la carpeta del mes (D-110). Esta prueba pasa por el
    handler real, que es el único sitio donde se juntan las dos cosas."""
    from contab_core import sidecar, storage
    db = tmp_path / "e.db"
    storage.init_empresa_db(db, nit="900921756", dv="6", razon_social="ALAGUNA")
    raiz = tmp_path / "ALAGUNA"
    raiz.mkdir()
    c = storage.connect(db)
    storage.ensure_schema(c)
    c.execute("UPDATE empresa_info SET default_folder = ?", (str(raiz),))
    c.commit()
    c.close()

    plan = sidecar._h_preparar_descarga_dian(
        {"db_path": str(db), "periodo": "2026-10", "enlace": ENLACE})
    assert plan["periodo"] == "2026-10"
    assert plan["carpeta"] == str(raiz / "2026-10")
    assert (raiz / "2026-10").is_dir(), "el mes nace con su carpeta hecha"
    assert plan["nit_receptor"] == "900921756"
