"""Conduce el navegador contra el portal de la DIAN (Fase 2).

Lo que automatiza es exactamente lo que el contador hace a mano: entra con el
enlace que le llegó al correo, pide el listado de un mes, espera a que la DIAN lo
genere y baja el ZIP. Ver `docs/dian-portal.md` para la cadena verificada.

**El enlace de acceso no se guarda en ninguna parte.** Llega por parámetro, vive en
memoria mientras dura la corrida y se descarta. No entra a la base, ni al log, ni
al mensaje de un error: es una llave a la cuenta DIAN de un cliente.

Tres cosas aprendidas contra el portal real, que explican por qué el código no es
más simple:

1. **Sin ventana no funciona.** Con `headless=True` responde «Solicitud bloqueada
   por controles de seguridad». Por eso se lanza con ventana.
2. **El campo de fechas ignora que le escriban** — es un calendario propio. En vez
   de pelear con el widget, se envía el formulario por `fetch` desde la propia
   página, reusando sus campos y cambiando solo las fechas y el grupo.
3. **La exportación es asíncrona.** Crear la solicitud no devuelve el archivo: hay
   que sondear la tabla hasta que aparezca lista.
"""
from __future__ import annotations

import asyncio
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from playwright.async_api import async_playwright

PORTAL = "https://catalogo-vpfe.dian.gov.co"
EXPORT_URL = f"{PORTAL}/Document/Export"

GRUPOS = {"todos": "0", "emitidos": "1", "recibidos": "2"}

# Cada cuánto se le pregunta al portal si ya generó el listado, y hasta cuándo.
ESPERA_ENTRE_SONDEOS = 5.0
ESPERA_MAXIMA = 180.0

_RE_ENLACE = re.compile(r"^https://catalogo-vpfe\.dian\.gov\.co/User/AuthToken\?", re.I)
_RE_RANGO = re.compile(r"Desde\s+(\d{2}-\d{2}-\d{4})\s+Hasta\s+(\d{2}-\d{2}-\d{4})", re.I)


class PortalError(RuntimeError):
    """Falla con mensaje en español para la UI. Nunca incluye el enlace de acceso."""


@dataclass
class Descarga:
    empresa: str
    archivo: Path
    filas_estimadas: int | None = None
    avisos: list[str] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "empresa": self.empresa,
            "archivo": str(self.archivo),
            "filas_estimadas": self.filas_estimadas,
            "avisos": self.avisos,
        }


def _valida_enlace(enlace: str) -> None:
    """El enlace tiene que ser del portal de la DIAN. Nunca se registra su valor."""
    if not _RE_ENLACE.match((enlace or "").strip()):
        raise PortalError(
            "El enlace de acceso no parece de la DIAN. Debe ser el que llega al "
            "correo, de la forma https://catalogo-vpfe.dian.gov.co/User/AuthToken?…"
        )


# El formulario se envía desde la propia página: así viajan sus campos tal como
# están (incluido el token anti-CSRF) y solo se cambian fechas y grupo. Pelear con
# el calendario del widget sería más frágil y no aporta nada.
_JS_EXPORTAR = """
async ({desde, hasta, grupo}) => {
  const form = document.querySelector('form') ||
               document.querySelector('#export-range')?.closest('form');
  if (!form) return {ok: false, error: 'no encontré el formulario de exportación'};
  const datos = new URLSearchParams();
  for (const [k, v] of new FormData(form).entries()) datos.append(k, v);
  datos.set('StartDate', desde);
  datos.set('EndDate', hasta);
  if (grupo !== null) datos.set('GroupCode', grupo);
  if (!datos.has('Type')) datos.set('Type', '1');
  const r = await fetch('/Document/Export', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest'},
    body: datos.toString(),
    credentials: 'same-origin',
  });
  const texto = await r.text();
  return {ok: r.ok, status: r.status, cuerpo: texto.slice(0, 300),
          campos: [...datos.keys()]};
}
"""


async def _fila_lista(pagina, desde: str, hasta: str) -> str | None:
    """Href de descarga de la solicitud que cubre ese rango, o None si aún no está.

    Se compara por el rango que muestra la tabla (dd-mm-aaaa) y no por la posición:
    el portal deja las solicitudes viejas ahí, y bajarse la de otro mes sería el
    peor error posible — entraría contabilidad del mes equivocado.
    """
    esperado = (
        f"{desde[8:10]}-{desde[5:7]}-{desde[0:4]}",
        f"{hasta[8:10]}-{hasta[5:7]}-{hasta[0:4]}",
    )
    for fila in await pagina.locator("table tbody tr").all():
        try:
            texto = await fila.inner_text()
        except Exception:
            continue
        m = _RE_RANGO.search(texto.replace("\t", " "))
        if not m or (m.group(1), m.group(2)) != esperado:
            continue
        for enlace in await fila.locator("a[href*='DownloadExportedZipFile']").all():
            href = await enlace.get_attribute("href")
            if href:
                return href
    return None


async def descargar_listado(
    enlace: str,
    desde: str,
    hasta: str,
    carpeta: str | Path,
    *,
    etiqueta: str = "listado",
    grupo: str = "todos",
    nit_receptor: str | None = None,
    progreso: Callable[[str], None] | None = None,
) -> Descarga:
    """Entra con el enlace, pide el listado del rango y devuelve el ZIP descargado.

    El rango llega ya calculado y validado por `contab_core.dian_portal`: acá no se
    interpreta nada del dominio, solo se conduce el navegador.
    """
    _valida_enlace(enlace)
    codigo_grupo = GRUPOS.get((grupo or "todos").lower())
    if codigo_grupo is None:
        raise PortalError(f"Grupo desconocido: «{grupo}» (esperado: {', '.join(GRUPOS)})")

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    avisa = progreso or (lambda _m: None)

    perfil = carpeta / f".perfil-{int(time.time())}"
    async with async_playwright() as p:
        contexto = await p.chromium.launch_persistent_context(
            str(perfil),
            headless=False,          # sin ventana el portal bloquea la petición
            accept_downloads=True,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()

            avisa("Entrando al portal…")
            await pagina.goto(enlace, wait_until="domcontentloaded", timeout=90_000)
            await pagina.wait_for_timeout(4_000)
            cuerpo = await pagina.inner_text("body")
            if "bloqueada por controles de seguridad" in cuerpo.lower():
                raise PortalError(
                    "El portal bloqueó la conexión por controles de seguridad. "
                    "Vuelve a intentarlo en unos minutos."
                )
            empresa = _nombre_empresa(cuerpo)
            if not empresa:
                raise PortalError(
                    "El enlace no abrió sesión. Puede estar vencido o ya usado: "
                    "pide uno nuevo al correo y vuelve a intentarlo."
                )
            avisa(f"Dentro como {empresa}")

            await pagina.goto(EXPORT_URL, wait_until="domcontentloaded", timeout=60_000)
            await pagina.wait_for_timeout(3_000)
            if nit_receptor:
                try:
                    await pagina.locator("#ReceiverCode").fill(str(nit_receptor))
                except Exception:
                    pass

            avisa(f"Pidiendo el listado de {etiqueta}…")
            res = await pagina.evaluate(
                _JS_EXPORTAR, {"desde": desde, "hasta": hasta, "grupo": codigo_grupo}
            )
            if not res.get("ok"):
                raise PortalError(
                    "La DIAN no aceptó la solicitud de exportación "
                    f"(estado {res.get('status')}). {res.get('error') or ''}".strip()
                )

            avisa("La DIAN está generando el archivo…")
            href = await _esperar_listado(pagina, desde, hasta, avisa)

            avisa("Descargando…")
            async with pagina.expect_download(timeout=90_000) as info:
                await pagina.evaluate("h => { window.location.href = h }", href)
            bajada = await info.value
            zip_destino = carpeta / f"dian-{etiqueta}.zip"
            await bajada.save_as(str(zip_destino))
            avisa("Listo")
            return Descarga(empresa=empresa, archivo=zip_destino)
        finally:
            await contexto.close()
            # El perfil lleva la sesión abierta de un cliente: no se deja en disco.
            shutil.rmtree(perfil, ignore_errors=True)


async def _esperar_listado(pagina, desde: str, hasta: str, avisa) -> str:
    limite = time.monotonic() + ESPERA_MAXIMA
    while True:
        href = await _fila_lista(pagina, desde, hasta)
        if href:
            return href
        if time.monotonic() > limite:
            raise PortalError(
                "La DIAN no terminó de generar el listado a tiempo. La solicitud "
                "queda hecha en el portal: vuelve a intentarlo en unos minutos y se "
                "descargará sin volver a pedirla."
            )
        await asyncio.sleep(ESPERA_ENTRE_SONDEOS)
        avisa("Esperando a que la DIAN termine…")
        await pagina.reload(wait_until="domcontentloaded", timeout=60_000)
        await pagina.wait_for_timeout(2_000)


def _nombre_empresa(cuerpo: str) -> str | None:
    """La empresa cuya sesión se abrió, tal como la muestra el portal."""
    lineas = [x.strip() for x in cuerpo.split("\n") if x.strip()]
    for i, linea in enumerate(lineas):
        if "factura electr" in linea.lower() and "ambiente" in linea.lower():
            for siguiente in lineas[i + 1 : i + 4]:
                if len(siguiente) > 5 and not siguiente.lower().startswith("inicio"):
                    return siguiente
    return None
