"""Ingesta del listado mensual desde el portal de la DIAN (Fase 2).

Este módulo tiene la lógica del dominio; **el navegador vive en el sidecar**
`apps/dian-rut/portal.py`, que es donde está Playwright. El reparto no es
caprichoso: acá se valida, se calcula el rango del mes y se abre el ZIP —cosas que
se pueden probar sin abrir un navegador ni tocar la DIAN—, y allá solo se conduce.

**El enlace de acceso nunca se guarda** (re-alcance de la 2.2, 2026-09-28). La DIAN
no autentica con usuario y clave: manda al correo un enlace de un solo uso. Ese
enlace vale como llave de la cuenta del cliente mientras viva, así que viaja por
parámetro, se usa y se descarta. No entra a la base, ni al log, ni al mensaje de un
error — de eso se encarga `enmascarar`.
"""
from __future__ import annotations

import calendar
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

PORTAL_HOST = "catalogo-vpfe.dian.gov.co"
GRUPOS = ("todos", "emitidos", "recibidos")

_RE_PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_RE_ENLACE = re.compile(
    rf"^https://{re.escape(PORTAL_HOST)}/User/AuthToken\?.*\btoken=", re.I
)
# Cualquier cosa con forma de enlace de acceso, para no dejarla salir en un texto.
_RE_FUGA = re.compile(
    rf"https?://{re.escape(PORTAL_HOST)}/User/AuthToken\?\S*", re.I
)


class DianPortalError(ValueError):
    """Error con mensaje en español para la UI. Nunca lleva el enlace dentro."""


def rango_del_mes(periodo: str) -> tuple[str, str]:
    """'AAAA-MM' → ('AAAA-MM-01', 'AAAA-MM-<último día>').

    El último día se calcula, no se asume: febrero de un año bisiesto y los meses
    de 30 días son justo donde un rango mal armado se come o se deja documentos.
    """
    p = (periodo or "").strip()
    if not _RE_PERIODO.match(p):
        raise DianPortalError(f"El mes debe venir como AAAA-MM (llegó «{p}»)")
    anio, mes = int(p[:4]), int(p[5:])
    ultimo = calendar.monthrange(anio, mes)[1]
    return f"{p}-01", f"{p}-{ultimo:02d}"


def validar_enlace(enlace: str) -> str:
    """Comprueba que sea un enlace de acceso de la DIAN y lo devuelve limpio.

    No se registra en ninguna parte; el mensaje de error jamás lo incluye.
    """
    limpio = (enlace or "").strip()
    if not limpio:
        raise DianPortalError("Falta el enlace de acceso que la DIAN envía al correo.")
    if not _RE_ENLACE.match(limpio):
        raise DianPortalError(
            "Ese no parece el enlace de acceso de la DIAN. Es el del correo, y "
            f"empieza por https://{PORTAL_HOST}/User/AuthToken?"
        )
    return limpio


def enmascarar(texto: str) -> str:
    """Tapa cualquier enlace de acceso que se haya colado en un texto.

    Se aplica a todo lo que salga hacia un log, un error o un resultado de trabajo.
    No es paranoia: en este proyecto un enlace de acceso real terminó pegado en una
    conversación, y los logs se copian a issues, respaldos y capturas.
    """
    return _RE_FUGA.sub(f"https://{PORTAL_HOST}/User/AuthToken?«enlace omitido»", texto or "")


def validar_grupo(grupo: str | None) -> str:
    g = (grupo or "todos").strip().lower()
    if g not in GRUPOS:
        raise DianPortalError(f"Grupo desconocido: «{g}» (esperado: {', '.join(GRUPOS)})")
    return g


def extraer_excel(zip_path: str | Path, destino: str | Path) -> Path:
    """Saca el Excel del ZIP que entrega el portal.

    El portal **no** entrega el `.xlsx` suelto: viene dentro de un ZIP, con el
    nombre del identificador de la solicitud. Si algún día entrega el Excel
    directo, se acepta también en vez de fallar.
    """
    zip_path, destino = Path(zip_path), Path(destino)
    if not zip_path.is_file():
        raise DianPortalError(f"No encuentro el archivo descargado: {zip_path.name}")

    if not zipfile.is_zipfile(zip_path):
        if zip_path.suffix.lower() in (".xlsx", ".xls"):
            shutil.copyfile(zip_path, destino)
            return destino
        raise DianPortalError(
            f"Lo que entregó la DIAN no es un ZIP ni un Excel ({zip_path.name})."
        )

    with zipfile.ZipFile(zip_path) as z:
        excels = [n for n in z.namelist() if n.lower().endswith((".xlsx", ".xls"))]
        if not excels:
            dentro = ", ".join(z.namelist()[:5]) or "nada"
            raise DianPortalError(
                f"El archivo de la DIAN no trae ningún Excel adentro (contiene: {dentro})."
            )
        if len(excels) > 1:
            # Nunca se ha visto más de uno; si pasa, se toma el primero y se avisa
            # en vez de elegir en silencio cuál es la contabilidad del mes.
            excels.sort()
        destino.parent.mkdir(parents=True, exist_ok=True)
        with z.open(excels[0]) as origen, destino.open("wb") as salida:
            shutil.copyfileobj(origen, salida)
    return destino


def preparar_descarga(periodo: str, enlace: str, grupo: str | None = None) -> dict[str, Any]:
    """Todo lo que el sidecar necesita para conducir el navegador, ya validado."""
    desde, hasta = rango_del_mes(periodo)
    return {
        "enlace": validar_enlace(enlace),
        "desde": desde,
        "hasta": hasta,
        "grupo": validar_grupo(grupo),
        "etiqueta": periodo,
    }


# ─────────────────────────── bitácora (Fase 2.5) ───────────────────────────
# Qué se intentó, cuándo y cómo salió. El portal falla de formas que no se
# repiten —mantenimiento, sesión vencida, bloqueo de seguridad—, y sin registro
# cada fallo se investiga desde cero.
#
# El «bajar varias empresas de un golpe» que pedía el plan se retiró el 2026-09-28:
# el acceso es un enlace de un solo uso POR EMPRESA, así que un lote sería pegar
# veinte enlaces — el mismo trabajo, con más código y más formas de fallar.

CAMINOS = ("portal", "manual")
ESTADOS = ("ok", "error")


def registrar_ingesta(
    conn,
    *,
    periodo: str,
    camino: str = "portal",
    estado: str = "ok",
    documentos: int | None = None,
    archivo: str | None = None,
    error: str | None = None,
    empresa_dian: str | None = None,
) -> dict[str, Any]:
    """Anota una corrida. El error se guarda **enmascarado**, siempre."""
    from .storage import transaction

    if camino not in CAMINOS:
        raise DianPortalError(f"Camino desconocido: «{camino}»")
    if estado not in ESTADOS:
        raise DianPortalError(f"Estado desconocido: «{estado}»")

    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO ingesta_run(periodo, camino, estado, documentos, archivo, error, "
            "empresa_dian) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (periodo, camino, estado, documentos, archivo,
             enmascarar(error) if error else None, empresa_dian),
        )
        fila_id = cur.lastrowid
    return dict(conn.execute("SELECT * FROM ingesta_run WHERE id = ?", (fila_id,)).fetchone())


def listar_ingestas(conn, *, periodo: str | None = None, limite: int = 20) -> list[dict[str, Any]]:
    """Las últimas corridas, de la más reciente a la más vieja."""
    q = "SELECT * FROM ingesta_run"
    params: list[Any] = []
    if periodo:
        q += " WHERE periodo = ?"
        params.append(periodo)
    q += " ORDER BY corrio_at DESC, id DESC LIMIT ?"
    params.append(int(limite))
    return [dict(r) for r in conn.execute(q, params).fetchall()]
