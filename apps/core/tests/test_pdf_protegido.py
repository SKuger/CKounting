"""PDFs protegidos con contraseña (Fase 2.6).

El portal de la DIAN entrega los soportes **cifrados con el NIT**. Antes de esto,
`extract_cufes` los devolvía como `status='no_text', error=None`: decía «este PDF
no tiene texto» —falso— y no reportaba nada. Con eso, V1 marcaría cada soporte
bajado del portal como «Sin soporte» y el contador saldría a pedirle al cliente
documentos que ya están en el disco.

El PDF cifrado se genera aquí a partir de una muestra del repo (datos falsos), en
vez de guardar uno real: un soporte de verdad trae datos de un tercero.
"""
import shutil

import pytest

from contab_core import pdf_cufe

CLAVE = "900181831"          # el NIT, que es como cifra el portal


@pytest.fixture()
def pdf_claro(tmp_path):
    """Una muestra del repo, sin cifrar, con su CUFE conocido."""
    from .conftest import SAMPLES_DIR
    origen = SAMPLES_DIR / "pdfs" / "dseDSE210.pdf"
    destino = tmp_path / "claro.pdf"
    shutil.copyfile(origen, destino)
    return destino


@pytest.fixture()
def pdf_cifrado(tmp_path, pdf_claro):
    pypdf = pytest.importorskip("pypdf", reason="pypdf es dependencia de pruebas")
    lector = pypdf.PdfReader(str(pdf_claro))
    escritor = pypdf.PdfWriter()
    for pagina in lector.pages:
        escritor.add_page(pagina)
    escritor.encrypt(CLAVE)
    destino = tmp_path / "cifrado.pdf"
    with destino.open("wb") as f:
        escritor.write(f)
    return destino


def test_la_muestra_sin_cifrar_sigue_leyendose(pdf_claro):
    """Red de seguridad: el cambio no puede romper el caso normal."""
    r = pdf_cufe.extract_cufes(pdf_claro)
    assert r.status == pdf_cufe.EXTRACTION_STATUS_OK
    assert r.cufes


def test_un_pdf_cifrado_sin_contrasena_no_dice_que_no_tiene_texto(pdf_cifrado):
    """El defecto que esto arregla: decía «sin texto» y no reportaba error."""
    r = pdf_cufe.extract_cufes(pdf_cifrado)
    assert r.status == pdf_cufe.EXTRACTION_STATUS_PROTEGIDO
    assert r.status != pdf_cufe.EXTRACTION_STATUS_NO_TEXT
    assert r.error and "contraseña" in r.error.lower()


def test_con_la_contrasena_correcta_saca_el_mismo_cufe(pdf_claro, pdf_cifrado):
    esperado = pdf_cufe.extract_cufes(pdf_claro)
    obtenido = pdf_cufe.extract_cufes(pdf_cifrado, password=CLAVE)
    assert obtenido.status == pdf_cufe.EXTRACTION_STATUS_OK
    assert [c.value for c in obtenido.cufes] == [c.value for c in esperado.cufes]


def test_con_la_contrasena_equivocada_lo_dice(pdf_cifrado):
    r = pdf_cufe.extract_cufes(pdf_cifrado, password="123456789")
    assert r.status == pdf_cufe.EXTRACTION_STATUS_PROTEGIDO


def test_la_contrasena_no_estorba_en_un_pdf_sin_cifrar(pdf_claro):
    """Pasarla siempre tiene que ser inofensivo: el indexador no sabe de antemano
    cuáles están cifrados."""
    r = pdf_cufe.extract_cufes(pdf_claro, password=CLAVE)
    assert r.status == pdf_cufe.EXTRACTION_STATUS_OK and r.cufes


def test_el_indexador_acepta_la_contrasena_de_la_carpeta(tmp_path, pdf_cifrado):
    """Los soportes bajados del portal se cifran todos con el mismo NIT."""
    from contab_core import storage
    carpeta = tmp_path / "soportes"
    carpeta.mkdir()
    shutil.copyfile(pdf_cifrado, carpeta / "soporte.pdf")

    db = tmp_path / "empresa.db"
    storage.init_empresa_db(db, "900181831", "4", "REAL Seguros")
    conn = storage.connect(db)
    try:
        storage.ensure_schema(conn)
        sin_clave = pdf_cufe.index_folder(conn, carpeta)
        assert sin_clave.no_cufe, "sin la clave no debería sacar el CUFE"

        con_clave = pdf_cufe.index_folder(conn, carpeta, password=CLAVE)
        assert pdf_cufe.get_indexed_cufes(conn, carpeta), "con la clave sí"
        assert not con_clave.no_cufe
    finally:
        conn.close()
