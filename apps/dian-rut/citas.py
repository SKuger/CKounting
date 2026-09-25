"""Vigía de citas DIAN: Devoluciones · Videoatención · Persona natural · Medellín (D-104).

Recorre agendamiento.dian.gov.co como lo haría una persona, cada 1–2 minutos, en un hilo propio con
Playwright síncrono (el loop asyncio de uvicorn vive en otro hilo). Si el portal responde "No se
encontraron especialidades…", no hay cupo. Si avanza a otra pantalla, se detiene ahí con el
navegador abierto, guarda captura, suena y avisa, para que el usuario termine la reserva.
No evade CAPTCHA ni protecciones anti-bot: si aparece uno, también es "detenerse y avisar".
"""
from __future__ import annotations

import datetime as dt
import os
import random
import re
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from dian_paths import WORKDIR

PORTAL_URL = "https://agendamiento.dian.gov.co/"
CIUDAD = "Medellín"
CIUDAD_RE = re.compile(r"medell[ií]n", re.IGNORECASE)
SIN_CUPO_RE = re.compile(r"No se encontraron especialidades", re.IGNORECASE)
CAPTCHA_RE = re.compile(r"captcha|no soy un robot", re.IGNORECASE)
PERSONA_NATURAL_RE = re.compile(r"persona\s+natural", re.IGNORECASE)
SOLICITUD_RE = re.compile(r"Solicitud de devoluci", re.IGNORECASE)
TRAMITE_RE = re.compile(r"^\s*Tr[aá]mite\s*$", re.IGNORECASE | re.MULTILINE)
FECHA_RE = re.compile(r"fecha y hora", re.IGNORECASE)

# Espera al azar entre revisiones (el usuario pidió 1–2 min; 3 era demasiado lento).
ESPERA_MIN_S, ESPERA_MAX_S = 60, 120
PASO_TIMEOUT_MS = 90_000  # el portal tarda ~15 s por paso; a veces bastante más

CITAS_DIR = Path(WORKDIR) / "citas"
CAPTURAS = CITAS_DIR / "capturas"
PERFIL = CITAS_DIR / "browser_profile"
MENSAJE = CITAS_DIR / "CITA_DIAN.txt"


# ─── recorrido del portal ──────────────────────────────────────────────────────────────────────

def _texto(page: Page) -> str:
    return page.inner_text("body")


def _cargando(page: Page) -> bool:
    return page.get_by_text("Cargando", exact=True).locator("visible=true").count() > 0


def _esperar_carga(page: Page) -> None:
    """El portal pone un overlay "Cargando" tras cada clic. Esperamos a verlo ausente 2 s seguidos:
    a veces aparece con retraso, y hacer clic con el overlay encima se queda colgado."""
    limite = time.monotonic() + PASO_TIMEOUT_MS / 1000
    libre_desde = None
    while time.monotonic() < limite:
        if _cargando(page):
            libre_desde = None
        elif libre_desde is None:
            libre_desde = time.monotonic()
        elif time.monotonic() - libre_desde >= 2:
            return
        page.wait_for_timeout(300)
    raise RuntimeError("el portal se quedó en 'Cargando' más de 90 s")


def _clic(page: Page, patron: str) -> None:
    loc = page.get_by_text(re.compile(patron, re.IGNORECASE)).locator("visible=true").first
    loc.wait_for(state="visible")
    loc.scroll_into_view_if_needed()
    loc.click()
    _esperar_carga(page)


def _aparece(page: Page, patron: re.Pattern[str], segundos: float) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if patron.search(_texto(page)):
            return True
        page.wait_for_timeout(500)
    return False


def _siguiente(page: Page) -> None:
    page.locator("text=Siguiente >> visible=true").last.click()
    _esperar_carga(page)


def _avanzar_hasta(page: Page, patron: str) -> None:
    """Tras elegir una tarjeta, la siguiente pregunta suele aparecer sola; si no, pulsamos Siguiente."""
    esperado = re.compile(patron, re.IGNORECASE)
    if _aparece(page, esperado, 5):
        return
    _siguiente(page)
    if not _aparece(page, esperado, 30):
        raise RuntimeError(f"no apareció la pantalla esperada ({patron})")


def tramite_medellin(opciones: list[str]) -> str | None:
    """La opción del desplegable "Trámite" que sirve: Medellín + persona natural. Las opciones
    vienen por ciudad, p. ej. 'Bucaramanga “Solicitud de devolución y/o compensación persona natural”.'"""
    return next((o for o in opciones if CIUDAD_RE.search(o) and PERSONA_NATURAL_RE.search(o)), None)


def _opciones_tramite(page: Page) -> tuple[list[str], object] | None:
    """Lee las opciones del desplegable "Trámite". Devuelve (opciones, cómo_elegir) o None si no
    encuentra el desplegable. Cubre <select> nativo y listas propias."""
    for sel in page.locator("select").all():
        if not sel.is_visible():
            continue
        opciones = [o.strip() for o in sel.locator("option").all_inner_texts() if o.strip()]
        if opciones:
            return opciones, sel
    # Lista propia: la abrimos y leemos lo que se vea con "Solicitud".
    try:
        page.locator("[role=combobox], .dropdown-toggle, select, input").locator("visible=true").last.click()
        page.wait_for_timeout(800)
    except Exception:  # noqa: BLE001
        return None
    items = page.get_by_text(SOLICITUD_RE).locator("visible=true")
    opciones = [t.strip() for t in items.all_inner_texts() if t.strip()]
    return (opciones, None) if opciones else None


def _elegir_opcion(page: Page, opcion: str, select) -> None:
    if select is not None:
        select.select_option(label=opcion)
    else:
        page.get_by_text(opcion, exact=True).locator("visible=true").first.click()
    _esperar_carga(page)


def _primer_dia(page: Page) -> str | None:
    """Hace clic en el primer día disponible del calendario y devuelve su número; None si el
    calendario no ofrece días. El portal solo pinta los días con disponibilidad."""
    calendario = page.locator("table").filter(has_text=re.compile(r"DO\s*LU\s*MA\s*MI")).locator("visible=true")
    if not calendario.count():
        page.locator("input").locator("visible=true").first.click()  # el campo "Fecha" lo despliega
        page.wait_for_timeout(1000)
    dias = calendario.first.locator("td").filter(has_text=re.compile(r"^\s*\d{1,2}\s*$")).locator("visible=true")
    for i in range(dias.count()):
        dia = dias.nth(i)
        clases = (dia.get_attribute("class") or "") + " " + (dia.locator("*").first.get_attribute("class") or "" if dia.locator("*").count() else "")
        if re.search(r"disabled|unselectable|other-month-disabled", clases):
            continue
        numero = dia.inner_text().strip()
        (dia.locator("a, button, span").first if dia.locator("a, button, span").count() else dia).click()
        _esperar_carga(page)
        return numero
    return None


def recorrido(page: Page) -> tuple[str, str, str]:
    """Devuelve (resultado, texto_pantalla, detalle).

    resultado ∈ sin_cupo | otra_ciudad | sin_fechas | hay_cupo | captcha
    """
    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    _esperar_carga(page)
    _clic(page, r"^\s*Agendar cita\s*$")

    _clic(page, r"Persona\s*Natural")
    _avanzar_hasta(page, r"prefiere la cita")

    _clic(page, r"Videoatenci[oó]n")
    _avanzar_hasta(page, r"tipo de servicio")

    _clic(page, r"^\s*Devoluciones\.?\s*$")
    if _aparece(page, SIN_CUPO_RE, 3):
        return "sin_cupo", _texto(page), ""
    if not _aparece(page, TRAMITE_RE, 15):
        _siguiente(page)
        if _aparece(page, SIN_CUPO_RE, 10):
            return "sin_cupo", _texto(page), ""
    if page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha']").count() or CAPTCHA_RE.search(_texto(page)):
        return "captcha", _texto(page), ""

    # Desde aquí el portal ofrece trámites. Cualquier paso que no salga como en el manual del usuario
    # es "detenerse y avisar": perder un cupo real por un selector sería lo peor.
    try:
        leidas = _opciones_tramite(page)
        if leidas is None:
            return "hay_cupo", _texto(page), "El portal ofrece trámites pero no pude leer el desplegable: revísalo tú."
        opciones, select = leidas
        elegida = tramite_medellin(opciones)
        if not elegida:
            return "otra_ciudad", _texto(page), " | ".join(opciones)
        _elegir_opcion(page, elegida, select)
        _siguiente(page)

        if SIN_CUPO_RE.search(_texto(page)):
            return "sin_fechas", _texto(page), elegida
        if not _aparece(page, FECHA_RE, 30):
            return "hay_cupo", _texto(page), f"Trámite elegido: {elegida}. La pantalla siguiente no es la de fecha: revísala tú."
        dia = _primer_dia(page)
        if dia is None:
            return "sin_fechas", _texto(page), elegida
        _siguiente(page)
        return "hay_cupo", _texto(page), f"Trámite: {elegida} · Día elegido: {dia}. Completa los datos que siguen."
    except Exception as e:  # noqa: BLE001
        return "hay_cupo", _texto(page), f"Hay trámites pero me trabé ({str(e).splitlines()[0][:120]}): termina tú."


# ─── avisos locales (Windows) ─────────────────────────────────────────────────────────────────

def _resumen_pantalla(texto: str) -> str:
    lineas = "\n".join(l.strip() for l in texto.splitlines() if l.strip())
    return lineas.split("Dirección de Impuestos y Aduanas Nacionales")[0].strip()


def _avisar(titulo: str, cuerpo: str) -> None:
    """Ventana siempre encima + pitidos + toast. La ventana va primero porque sale aunque el
    usuario tenga las notificaciones de Windows apagadas (era su caso)."""
    if sys.platform != "win32":
        return
    import ctypes
    import winsound

    flags = 0x30 | 0x40000 | 0x10000 | 0x1000  # WARNING | TOPMOST | SETFOREGROUND | SYSTEMMODAL
    threading.Thread(target=ctypes.windll.user32.MessageBoxW, args=(None, cuerpo, titulo, flags), daemon=True).start()
    for _ in range(6):
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        time.sleep(0.7)
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null;"
        "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$t=$x.GetElementsByTagName('text');"
        "$t.Item(0).AppendChild($x.CreateTextNode($env:VIGIA_TITULO)) > $null;"
        "$t.Item(1).AppendChild($x.CreateTextNode($env:VIGIA_CUERPO)) > $null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($x))"
    )
    env = {**os.environ, "VIGIA_TITULO": titulo, "VIGIA_CUERPO": cuerpo[:250]}
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], env=env, timeout=30,
                       check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:  # noqa: BLE001 — el toast es un extra; nunca debe tumbar al vigía
        pass


def _navegador() -> str | None:
    """Chrome o Edge del sistema. El instalador no trae Chromium propio (D-058), así que en la app
    instalada esto es lo que corre; en dev, si no hay ninguno, cae al Chromium de Playwright."""
    if os.environ.get("DIAN_CITAS_BROWSER"):
        return os.environ["DIAN_CITAS_BROWSER"]
    if sys.platform != "win32":
        return None
    raices = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")]
    for rel in (("Google", "Chrome", "Application", "chrome.exe"), ("Microsoft", "Edge", "Application", "msedge.exe")):
        for raiz in raices:
            if raiz and (p := Path(raiz, *rel)).exists():
                return str(p)
    return None


# ─── el vigía ─────────────────────────────────────────────────────────────────────────────────

class _VentanaCerrada(Exception):
    pass


class Vigia:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._hilo: threading.Thread | None = None
        self._log: deque[dict] = deque(maxlen=200)
        self.estado = "detenido"  # detenido | iniciando | revisando | esperando | hay_cupo | captcha
        self.intentos = 0
        self.sin_cupo = 0
        self.ultima_revision: str | None = None
        self.proxima_revision: str | None = None
        self.pantalla: str | None = None
        self.detalle: str | None = None
        self.captura: Path | None = None

    # API pública (la llaman los endpoints de FastAPI desde el hilo del loop)

    def iniciar(self) -> bool:
        with self._lock:
            if self._hilo and self._hilo.is_alive():
                return False
            self._stop.clear()
            self.estado, self.intentos, self.sin_cupo = "iniciando", 0, 0
            self.pantalla = self.detalle = self.captura = self.proxima_revision = None
            self._hilo = threading.Thread(target=self._correr, name="vigia-citas", daemon=True)
            self._hilo.start()
            return True

    def detener(self) -> None:
        self._stop.set()

    def snapshot(self) -> dict:
        return {
            "activo": bool(self._hilo and self._hilo.is_alive()),
            "estado": self.estado,
            "intentos": self.intentos,
            "sin_cupo": self.sin_cupo,
            "ultima_revision": self.ultima_revision,
            "proxima_revision": self.proxima_revision,
            "espera_s": [ESPERA_MIN_S, ESPERA_MAX_S],
            "pantalla": self.pantalla,
            "detalle": self.detalle,
            "hay_captura": bool(self.captura and self.captura.exists()),
            "log": list(self._log)[-60:],
        }

    def ruta_captura(self) -> Path | None:
        return self.captura if self.captura and self.captura.exists() else None

    # interno

    def _anotar(self, nivel: str, msg: str) -> None:
        self._log.append({"t": dt.datetime.now().isoformat(timespec="seconds"), "nivel": nivel, "msg": msg})
        print(f"[citas] {nivel}: {msg}", file=sys.stderr, flush=True)

    def _evidencia(self, page: Page, etiqueta: str) -> Path | None:
        try:
            base = CAPTURAS / f"{dt.datetime.now():%Y%m%d-%H%M%S}_{etiqueta}"
            page.screenshot(path=f"{base}.png", full_page=True)
            Path(f"{base}.html").write_text(page.content(), encoding="utf-8")
            return Path(f"{base}.png")
        except Exception:  # noqa: BLE001
            return None

    def _correr(self) -> None:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        navegador = _navegador()
        self._anotar("info", f"Iniciando búsqueda: Devoluciones · Videoatención · {CIUDAD}")
        try:
            with sync_playwright() as pw:
                while not self._stop.is_set():
                    try:
                        ctx = pw.chromium.launch_persistent_context(
                            str(PERFIL), executable_path=navegador, headless=False, viewport={"width": 1280, "height": 900}
                        )
                    except Exception as e:  # noqa: BLE001
                        self._anotar("error", f"No pude abrir el navegador: {str(e).splitlines()[0][:200]}")
                        return
                    try:
                        if self._bucle(ctx):
                            return
                    except _VentanaCerrada:
                        self._anotar("warn", "Se cerró la ventana del navegador; la vuelvo a abrir y sigo buscando")
                    finally:
                        try:
                            ctx.close()
                        except Exception:  # noqa: BLE001 — ya cerrada
                            pass
        except Exception as e:  # noqa: BLE001
            self._anotar("error", f"Error inesperado: {str(e).splitlines()[0][:200]}")
        finally:
            self.estado = "detenido"
            self.proxima_revision = None
            self._anotar("info", "Búsqueda detenida")

    def _pagina(self, ctx) -> Page:
        try:
            page = next((p for p in ctx.pages if not p.is_closed()), None) or ctx.new_page()
        except Exception as e:
            raise _VentanaCerrada() from e
        page.set_default_timeout(PASO_TIMEOUT_MS)
        return page

    def _bucle(self, ctx) -> bool:
        """Revisa hasta que haya que parar. True = terminar la búsqueda; si el usuario cierra la
        ventana en plena búsqueda se lanza _VentanaCerrada para reabrirla."""
        fallos = 0
        while not self._stop.is_set():
            self.intentos += 1
            self.estado = "revisando"
            self.proxima_revision = None
            page = self._pagina(ctx)
            try:
                resultado, texto, detalle = recorrido(page)
                fallos = 0
            except Exception as e:
                if self._stop.is_set():
                    return True
                if page.is_closed() or "has been closed" in str(e):
                    raise _VentanaCerrada() from e
                fallos += 1
                self._anotar("warn", f"Revisión {self.intentos} falló: {str(e).splitlines()[0][:160]}")
                self._evidencia(page, "error")
                resultado, texto, detalle = "error", "", ""
            self.ultima_revision = dt.datetime.now().isoformat(timespec="seconds")

            if resultado == "sin_cupo":
                self.sin_cupo += 1
                self._anotar("info", f"Revisión {self.intentos}: sin cupo")
                if self.sin_cupo == 1:  # evidencia de que el recorrido llegó de verdad al aviso
                    self._evidencia(page, "sin_cupo")
            elif resultado == "otra_ciudad":
                self._anotar("info", f"Revisión {self.intentos}: hay trámites pero no en {CIUDAD} ({detalle[:160]}); sigo buscando")
                self._evidencia(page, "otra_ciudad")
            elif resultado == "sin_fechas":
                self._anotar("info", f"Revisión {self.intentos}: hay trámite en {CIUDAD} pero sin días disponibles; sigo buscando")
                self._evidencia(page, "sin_fechas")
            elif resultado in ("hay_cupo", "captcha"):
                self._encontrado(page, resultado, texto, detalle)
                # Nos quedamos con la ventana abierta hasta que el usuario pulse Detener o la cierre.
                while not self._stop.is_set() and not page.is_closed():
                    self._stop.wait(1)
                return True

            espera = random.uniform(ESPERA_MIN_S, ESPERA_MAX_S) * min(1 + fallos, 4)
            self.estado = "esperando"
            self.proxima_revision = (dt.datetime.now() + dt.timedelta(seconds=espera)).isoformat(timespec="seconds")
            if self._stop.wait(espera):
                return True
        return True

    def _encontrado(self, page: Page, resultado: str, texto: str, detalle: str) -> None:
        self.estado = resultado
        self.captura = self._evidencia(page, self.estado)
        self.pantalla = _resumen_pantalla(texto)
        self.detalle = detalle
        if resultado == "captcha":
            titulo, encabezado = "Cita DIAN: CAPTCHA", "El portal pidió un CAPTCHA: termínalo tú en la ventana abierta."
        else:
            titulo, encabezado = "Cita DIAN: ¡hay cupo!", f"¡HAY CUPO en {CIUDAD}! Devoluciones · Videoatención."
        self._anotar("ok", f"{encabezado} {detalle}".strip())
        MENSAJE.write_text(
            f"{encabezado}\n{detalle}\nDetectado: {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
            "La ventana del navegador quedó abierta en esa pantalla: termina la reserva ahí.\n"
            f"Captura: {self.captura}\n\n---- Lo que muestra el portal ----\n{self.pantalla}\n",
            encoding="utf-8",
        )
        _avisar(titulo, f"{encabezado}\n{detalle}\n\nTermina la reserva en la ventana del navegador que quedó abierta.")


vigia = Vigia()
