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
   Y usa el **navegador del sistema** (Chrome o Edge), no el Chromium de
   Playwright: el instalador no lo empaqueta (D-058), así que pedirlo haría que
   estos botones fallaran justo en la app instalada — donde nadie los habría
   probado.
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

import httpx

import dian_paths
from citas import _navegador as navegador_del_sistema
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
  // NO se usa `document.querySelector('form')`: el PRIMER formulario de estas
  // páginas es el de CERRAR SESIÓN, así que serializarlo mandaba un cuerpo sin los
  // campos de la exportación y la DIAN respondía 500. Se arma el cuerpo con los
  // campos que de verdad existen, vengan del formulario que vengan.
  const datos = new URLSearchParams();
  for (const el of document.querySelectorAll('input[name], select[name], textarea[name]')) {
    if (el.disabled) continue;
    if (el.type === 'checkbox' || el.type === 'radio') { if (!el.checked) continue; }
    if (el.form && (el.form.getAttribute('action') || '').toLowerCase().includes('logout')) continue;
    if (!datos.has(el.name)) datos.append(el.name, el.value ?? '');
  }
  datos.set('StartDate', desde);
  datos.set('EndDate', hasta);
  if (grupo !== null) datos.set('GroupCode', grupo);
  if (!datos.has('Type')) datos.set('Type', '1');
  if (!datos.has('AmountAdmin')) datos.set('AmountAdmin', '');

  const token = document.querySelector('input[name="__RequestVerificationToken"]');
  if (token && !datos.has('__RequestVerificationToken'))
    datos.set('__RequestVerificationToken', token.value);

  const faltan = ['StartDate', 'EndDate', 'GroupCode', '__RequestVerificationToken']
    .filter(k => !datos.get(k));
  if (faltan.length)
    return {ok: false, error: 'a la página le faltan campos: ' + faltan.join(', ')};

  const r = await fetch('/Document/Export', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest'},
    body: datos.toString(),
    credentials: 'same-origin',
  });
  const texto = await r.text();
  return {ok: r.ok, status: r.status, cuerpo: texto.slice(0, 300), campos: [...datos.keys()]};
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

    perfil = Path(dian_paths.BROWSER_PROFILE_DIR) / f"listado-{int(time.time())}"
    async with async_playwright() as p:
        contexto = await p.chromium.launch_persistent_context(
            str(perfil),
            executable_path=navegador_del_sistema(),   # D-058: no hay Chromium propio
            headless=False,          # sin ventana el portal bloquea la petición
            accept_downloads=True,
            viewport={"width": 1400, "height": 900},
            # El banner «software automatizado está controlando Chrome» no es solo
        # feo: es la señal que leen el reCAPTCHA y el Turnstile para rechazarnos.
        args=["--disable-blink-features=AutomationControlled", "--disable-infobars"],
        ignore_default_args=["--enable-automation"],
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


# ────────────────── Soportes por CUFE: el camino público (2.6) ──────────────────
# Cualquier documento se baja dando CUFE + NIT, **sin credenciales de nadie**.
# Lo que Cloudflare protege es la vista de documento DENTRO de la sesión
# (`/Document/Received`), no esta búsqueda pública.
#
# **El navegador ya no baja los PDF: solo fabrica tokens.** Hacerlo a golpe de
# clics costaba ~25 s por documento, casi todo esperas a ciegas. La misma cadena
# por HTTP tarda 2-3 s, porque el portero del camino público —el Turnstile— viaja
# como un campo del formulario y no como cookie, así que se puede trasplantar a un
# cliente HTTP. Medido contra el portal real el 2026-10-01.
#
# Lo que impide que esto sea instantáneo, y conviene no volver a pelearlo:
#
# 1. **El token es de un solo uso.** Sirve para un documento y se quema. Renovarlo
#    con `turnstile.reset()` cuesta entre 2 y 9 s, y es el verdadero techo: por eso
#    hay una pestaña cosechando en segundo plano mientras los obreros descargan.
# 2. **El portal rechaza una parte de los intentos** —403, o HTML en vez de PDF,
#    siempre en el último paso—. No se encontró patrón; se reintenta con un token
#    nuevo, que sale más barato que averiguar por qué.
# 3. **Cada documento necesita sesión propia.** Reusando la misma cookie el acierto
#    cae a 1 de 6; con un cliente nuevo por documento sube a 3 de 5 por intento.
# 4. **El portal deja correr un rato y luego cierra la llave.** Medido con el
#    septiembre real del usuario: los primeros 7 documentos a 5,6 s cada uno, y del
#    octavo en adelante aparece «Un momento, estamos comprobando que no sea un bot»
#    y todo se va al respaldo. Por eso hay cortacircuitos: tras unos cuantos fallos
#    seguidos se deja de intentar por HTTP, porque si no se paga dos veces —el
#    intento rápido Y los clics— y la corrida sale MÁS lenta que no haber optimizado
#    nada. Eso ya pasó: 33 s por documento contra los 25 s del camino a clics.
#
# El PDF llega CIFRADO con el NIT. Quien lo lea después tiene que pasar esa
# contraseña; `contab_core.pdf_cufe` ya lo hace.

BUSCAR_URL = f"{PORTAL}/User/SearchDocument"
MOSTRAR_URL = f"{PORTAL}/Document/ShowDocumentToPublic"
BAJAR_URL = f"{PORTAL}/Document/DownloadPDF"
CDP_URL = "http://127.0.0.1:9222"   # el navegador del usuario, si está escuchando
INTENTOS_POR_DOCUMENTO = 2
OBREROS = 2
TOKENS_EN_COLA = 3
ESPERA_MAXIMA_TOKEN = 90    # si el portal nos marcó, dejan de salir tokens
FALLOS_PARA_RENDIRSE = 3    # seguidos: el portal cerró la llave para esta corrida


@dataclass
class Soportes:
    bajados: list[str] = field(default_factory=list)
    sin_encontrar: list[str] = field(default_factory=list)
    fallidos: list[str] = field(default_factory=list)
    ya_estaban: list[str] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "bajados": self.bajados,
            "sin_encontrar": self.sin_encontrar,
            "fallidos": self.fallidos,
            "ya_estaban": self.ya_estaban,
            "total": len(self.bajados) + len(self.sin_encontrar) + len(self.fallidos),
        }


def _oculto(html: str, nombre: str) -> str | None:
    """El valor de un `<input hidden>`, venga el `value` antes o después del `name`."""
    for patron in (
        r'name="%s"[^>]*value="([^"]*)"' % nombre,
        r'value="([^"]*)"[^>]*name="%s"' % nombre,
    ):
        m = re.search(patron, html)
        if m:
            return m.group(1)
    return None


_JS_TOKEN = (
    "() => (document.querySelector('[name=\"cf-turnstile-response\"]')||{}).value||''"
)
_JS_RENOVAR = """() => {
  try { window.turnstile && window.turnstile.reset(); } catch (e) {}
  const el = document.querySelector('[name="cf-turnstile-response"]');
  if (el) el.value = '';
}"""


# El portal mete delante un muro del WAF de Azure —«Un momento, estamos
# comprobando que no sea un bot»— que no es el Turnstile y no tiene su campo.
# Sin reconocerlo, la cosechadora se queda mirando una página que nunca va a dar
# un token, se rinde en silencio, y la corrida entera se va al respaldo a clics
# sin que nadie entienda por qué. Es lo que vio el usuario.
MUROS = ("comprobando que no sea un bot", "azure waf", "request blocked",
         "solicitud bloqueada")


async def _hay_muro(pagina) -> bool:
    try:
        return any(m in (await pagina.inner_text("body")).lower() for m in MUROS)
    except Exception:
        return False


async def _esperar_muro(pagina, avisa) -> bool:
    """Espera a que el WAF nos deje pasar. False si no cede."""
    for intento in range(5):
        if not await _hay_muro(pagina):
            return True
        avisa("La DIAN está comprobando que no somos un robot; esperando…")
        await pagina.wait_for_timeout(6_000 * (intento + 1))
        try:
            await pagina.reload(wait_until="domcontentloaded", timeout=60_000)
        except Exception:
            return False
    return not await _hay_muro(pagina)


async def _cosechar_tokens(pagina, cola: asyncio.Queue, parar: asyncio.Event,
                           avisa) -> None:
    """Mantiene la cola surtida de tokens del Turnstile. Muere cuando se le dice."""
    await pagina.goto(BUSCAR_URL, wait_until="domcontentloaded", timeout=60_000)
    # Al frente a propósito: Chrome congela las pestañas de fondo y el Turnstile
    # deja de resolverse, así que la corrida se queda esperando un token que no
    # va a llegar.
    try:
        await pagina.bring_to_front()
    except Exception:
        pass
    while not parar.is_set():
        token = ""
        for _ in range(80):          # hasta 20 s: renovar tarda lo que tarda
            if parar.is_set():
                return
            try:
                token = await pagina.evaluate(_JS_TOKEN)
            except Exception:
                return               # la pestaña se cerró; no es un error
            if token:
                break
            await pagina.wait_for_timeout(250)
        if not token:
            # Puede ser el muro del WAF, que no trae campo del Turnstile.
            if await _hay_muro(pagina):
                if not await _esperar_muro(pagina, avisa):
                    return
                continue
            return
        await cola.put(token)
        try:
            await pagina.evaluate(_JS_RENOVAR)
        except Exception:
            return


async def _bajar_por_http(
    cliente: httpx.AsyncClient, token: str, cufe: str, nit: str, carpeta: Path
) -> tuple[str | None, str | None]:
    """Un documento por HTTP. Devuelve (nombre del archivo, motivo del fallo)."""
    r = await cliente.get(BUSCAR_URL)
    rvt = _oculto(r.text, "__RequestVerificationToken")
    busqueda = await cliente.post(BUSCAR_URL, data={
        "__RequestVerificationToken": rvt or "",
        "cf-turnstile-response": token,
        "DocumentKey": cufe,
        "SearchDocumentNit": nit,
    })
    # La respuesta no es el documento: es un formulario puente que el navegador
    # reenvía solo. Aquí se reenvía a mano.
    ident = _oculto(busqueda.text, "Id")
    pase = _oculto(busqueda.text, "Token")
    captcha = _oculto(busqueda.text, "Captcha")
    rvt2 = _oculto(busqueda.text, "__RequestVerificationToken")
    if not (ident and pase):
        return None, "la búsqueda no devolvió el documento"

    documento = await cliente.post(MOSTRAR_URL, data={
        "__RequestVerificationToken": rvt2 or "",
        "Id": ident, "Token": pase, "Captcha": captcha or "", "Nit": nit,
    })
    if "DATOS DEL EMISOR" not in documento.text.upper():
        return None, "no se llegó a la página del documento"

    pdf = await cliente.post(
        BAJAR_URL,
        data={
            "__RequestVerificationToken": _oculto(documento.text, "__RequestVerificationToken") or rvt2 or "",
            "trackId": cufe, "token": pase, "captcha": captcha or "",
        },
        headers={"Referer": MOSTRAR_URL},
    )
    if "pdf" not in pdf.headers.get("content-type", ""):
        return None, f"la descarga devolvió {pdf.status_code}"

    destino = carpeta / f"{cufe}.pdf"
    # Nunca se pisa un soporte que ya estaba: el del cliente puede ser el bueno.
    if destino.exists():
        destino = carpeta / f"{destino.stem}_dian{destino.suffix}"
    destino.write_bytes(pdf.content)
    return destino.name, None


async def _un_soporte(pagina, cufe: str, nit: str, carpeta: Path) -> str | None:
    """A clics, como lo haría una persona. Es el respaldo cuando el HTTP no pasa.

    Devuelve el nombre del archivo, o None si la DIAN no tiene ese documento —y
    esa distinción es la razón de conservarlo: el camino HTTP no sabe separar
    «no existe» de «me rechazaron», y aquí la página lo dice.
    """
    await pagina.goto(BUSCAR_URL, wait_until="domcontentloaded", timeout=60_000)
    await pagina.wait_for_timeout(2_500)
    await pagina.fill("#DocumentKey", cufe)
    await pagina.wait_for_timeout(400)
    try:
        await pagina.fill("#SearchDocumentNit", str(nit))
    except Exception:
        pass
    try:
        await pagina.get_by_role("button", name="Buscar").first.click(timeout=10_000)
    except Exception:
        await pagina.locator("button[type=submit], input[type=submit]").first.click()
    await pagina.wait_for_timeout(5_000)

    if "DATOS DEL EMISOR" not in (await pagina.inner_text("body")).upper():
        return None      # la DIAN no lo tiene, o el NIT no corresponde

    # «Descargar PDF» NO baja nada: es un `a.downloadLink` que abre un aviso —«Este
    # archivo contiene contraseña y corresponde al NIT…»— y la descarga solo arranca
    # al pulsar «Aceptar». Sin ese segundo clic, `expect_download` espera un archivo
    # que nunca sale y revienta a los 60 s. Se culpó a Cloudflare; no era.
    async with pagina.expect_download(timeout=60_000) as info:
        await pagina.locator("a.downloadLink").first.click()
        await pagina.wait_for_timeout(1_200)
        await pagina.get_by_role("button", name="Aceptar").first.click(timeout=15_000)
    bajada = await info.value
    nombre = bajada.suggested_filename or f"{cufe[:16]}.pdf"
    destino = carpeta / nombre
    if destino.exists():
        destino = carpeta / f"{destino.stem}_dian{destino.suffix}"
    await bajada.save_as(str(destino))
    return destino.name


async def _abrir_navegador(p, carpeta: Path, avisa):
    """El navegador del usuario si está escuchando; si no, uno nuestro.

    Cloudflare rechaza cada vez más al navegador que lanza Playwright, aunque se
    le pase el Chrome del sistema: la verificación sale en rojo y la búsqueda no
    pasa. Conectándose por CDP al navegador que el usuario ya tiene abierto —el
    mismo «modo humano» que el scraper del RUT usa desde D-058— Cloudflare ve un
    navegador normal, porque lo es.

    Devuelve (contexto, cerrar), donde `cerrar` NO cierra el navegador del
    usuario: solo lo que hayamos abierto nosotros.
    """
    try:
        navegador = await p.chromium.connect_over_cdp(CDP_URL, timeout=4_000)
        contexto = navegador.contexts[0] if navegador.contexts else await navegador.new_context()
        avisa("Usando tu navegador (modo humano).")
        mias: list = []

        async def cerrar():
            for pagina in mias:
                try:
                    await pagina.close()
                except Exception:
                    pass
        return contexto, cerrar, mias
    except Exception:
        pass

    # El perfil NO va dentro de la carpeta de soportes: ahí viven los PDF del
    # contador, y el indexador y el renombrador recorren esa carpeta entera.
    perfil = Path(dian_paths.BROWSER_PROFILE_DIR) / f"soportes-{int(time.time())}"
    contexto = await p.chromium.launch_persistent_context(
        str(perfil),
        executable_path=navegador_del_sistema(),   # D-058: no hay Chromium propio
        headless=False,          # sin ventana el portal bloquea
        accept_downloads=True,
        viewport={"width": 1400, "height": 900},
        # El banner «software automatizado está controlando Chrome» no es solo
        # feo: es la señal que leen el reCAPTCHA y el Turnstile para rechazarnos.
        args=["--disable-blink-features=AutomationControlled", "--disable-infobars"],
        ignore_default_args=["--enable-automation"],
    )
    avisa("Abrimos un navegador propio: la DIAN puede pedir la verificación.")

    async def cerrar():
        try:
            await contexto.close()
        finally:
            shutil.rmtree(perfil, ignore_errors=True)
    return contexto, cerrar, None


def ya_esta(carpeta: Path, cufe: str) -> bool:
    """¿Este soporte ya está bajado? Es lo que permite retomar donde se quedó.

    Se mira el disco y no el índice de CUFEs de la base, porque el índice solo se
    refresca al terminar la corrida: si se para a la mitad —o se cae— el índice
    todavía no sabe nada de lo bajado y volvería a pedirlo todo. El nombre del
    archivo ES el CUFE, así que el disco ya lleva la cuenta.
    """
    return (carpeta / f"{cufe}.pdf").exists()


async def descargar_soportes(
    documentos: list[dict[str, str]],
    carpeta: str | Path,
    *,
    progreso: Callable[[str], None] | None = None,
    parado: Callable[[], bool] | None = None,
) -> Soportes:
    """Baja el soporte oficial de cada documento. `documentos`: [{cufe, nit}, …].

    Devuelve SIEMPRE lo conseguido, aunque algo reviente a mitad: los PDF ya
    están en la carpeta, y decir «falló» sin decir cuáles se bajaron obliga a
    empezar de cero.
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    avisa = progreso or (lambda _m: None)
    hay_que_parar = parado or (lambda: False)
    res = Soportes()

    pendientes: asyncio.Queue = asyncio.Queue()
    for doc in documentos:
        cufe = (doc.get("cufe") or "").strip().lower()
        if cufe and ya_esta(carpeta, cufe):
            res.ya_estaban.append(f"{cufe}.pdf")
            continue
        pendientes.put_nowait(doc)
    total = pendientes.qsize()
    if res.ya_estaban:
        avisa(f"{len(res.ya_estaban)} ya estaban; faltan {total}.")
    hechos = 0

    async with async_playwright() as p:
        contexto, cerrar, mias = await _abrir_navegador(p, carpeta, avisa)
        try:
            fabrica = contexto.pages[0] if contexto.pages else await contexto.new_page()
            if mias is not None and fabrica not in contexto.pages[:1]:
                mias.append(fabrica)
            respaldo = None
            cola: asyncio.Queue = asyncio.Queue(maxsize=TOKENS_EN_COLA)
            parar = asyncio.Event()
            # El User-Agent se lee ANTES de lanzar la cosechadora: evaluar sobre
            # una página en plena navegación destruye el contexto de ejecución.
            ua = await fabrica.evaluate("() => navigator.userAgent")
            cosechadora = asyncio.create_task(_cosechar_tokens(fabrica, cola, parar, avisa))
            # El respaldo a clics es de uno en uno: comparte pestaña.
            turno_respaldo = asyncio.Lock()

            rendidos = 0          # fallos seguidos del camino rápido
            rendido = False       # y, una vez cerrada la llave, no se reabre

            async def obrero() -> None:
                nonlocal hechos, rendidos, rendido, respaldo
                while True:
                    if hay_que_parar():
                        return
                    try:
                        doc = pendientes.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    cufe = (doc.get("cufe") or "").strip().lower()
                    nit = str(doc.get("nit") or "").strip()
                    if not cufe or not nit:
                        res.fallidos.append(cufe or "(sin CUFE)")
                        continue
                    hechos += 1
                    avisa(f"Bajando {hechos} de {total}…")
                    nombre = None
                    intentos = 0 if rendido else INTENTOS_POR_DOCUMENTO
                    for _ in range(intentos):
                        if hay_que_parar():
                            return
                        try:
                            token = await asyncio.wait_for(
                                cola.get(), timeout=ESPERA_MAXIMA_TOKEN)
                        except asyncio.TimeoutError:
                            # El portal dejó de dar tokens: muestra «estamos
                            # comprobando que no sea un bot». Colgarse esperando
                            # sería lo peor; se deja constancia y se sigue.
                            break
                        # El resultado se guarda FUERA del try: cerrar el cliente
                        # puede reventar con el PDF ya en disco, y darlo entonces
                        # por fallido hacía que el respaldo lo bajara otra vez —17
                        # duplicados `_dian` en una corrida de 32, y el doble de
                        # tiempo.
                        hecho = None
                        try:
                            async with httpx.AsyncClient(
                                timeout=30, follow_redirects=True,
                                headers={"User-Agent": ua, "Origin": PORTAL,
                                         "Referer": BUSCAR_URL},
                            ) as cliente:
                                hecho = await _bajar_por_http(
                                    cliente, token, cufe, nit, carpeta)
                        except Exception:
                            pass
                        nombre = hecho[0] if hecho else None
                        if nombre:
                            rendidos = 0
                            break
                        rendidos += 1
                        # Se queda rendido para el resto de la corrida: un acierto
                        # suelto después del freno no significa que la llave se
                        # haya reabierto, y reintentar vuelve a pagarse dos veces.
                        if rendidos >= FALLOS_PARA_RENDIRSE:
                            rendido = True
                            avisa("La DIAN nos frenó: seguimos, pero más despacio.")
                            break
                    if nombre:
                        res.bajados.append(nombre)
                        continue
                    if hay_que_parar():
                        return
                    # Agotados los intentos rápidos, se va a clics: es lento, pero
                    # es lo único que distingue «la DIAN no lo tiene» de un rechazo.
                    async with turno_respaldo:
                        if respaldo is None:
                            respaldo = await contexto.new_page()
                            if mias is not None:
                                mias.append(respaldo)
                        fallo = None
                        for sobra in (True, False):
                            try:
                                nombre = await _un_soporte(respaldo, cufe, nit, carpeta)
                            except Exception as e:
                                fallo = e
                                if sobra:
                                    await asyncio.sleep(3)   # un respiro y se repite
                                    continue
                            else:
                                fallo = None
                            break
                        if fallo is not None:
                            res.fallidos.append(cufe)
                        else:
                            (res.bajados if nombre else res.sin_encontrar).append(
                                nombre or cufe)

            try:
                await asyncio.gather(*[obrero() for _ in range(OBREROS)])
            finally:
                parar.set()
                cosechadora.cancel()
        finally:
            await cerrar()
    return res
