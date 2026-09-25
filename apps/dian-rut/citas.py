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

from dian_paths import WORKDIR
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeout

PORTAL_URL = "https://agendamiento.dian.gov.co/"
CIUDAD = "Medellín"
CIUDAD_RE = re.compile(r"medell[ií]n", re.IGNORECASE)
SIN_CUPO_RE = re.compile(r"No se encontraron especialidades", re.IGNORECASE)
CAPTCHA_RE = re.compile(r"captcha|no soy un robot", re.IGNORECASE)
# Si el portal lista estas ciudades y Medellín no, el cupo no sirve y seguimos vigilando.
OTRAS_CIUDADES_RE = re.compile(
    r"bogot[aá]|\bcali\b|barranquilla|bucaramanga|cartagena|pereira|manizales|c[uú]cuta|ibagu[eé]", re.IGNORECASE
)

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


def clasificar(texto: str, hay_captcha_iframe: bool = False) -> str:
    """Estado a partir de la pantalla tras elegir el servicio:
    sin_cupo | captcha | medellin | otra_ciudad | desconocida."""
    if SIN_CUPO_RE.search(texto):
        return "sin_cupo"
    if hay_captcha_iframe or CAPTCHA_RE.search(texto):
        return "captcha"
    if CIUDAD_RE.search(texto):
        return "medellin"
    if OTRAS_CIUDADES_RE.search(texto):
        return "otra_ciudad"
    return "desconocida"


def _elegir_medellin(page: Page) -> bool:
    for sel in page.locator("select").all():
        opciones = sel.locator("option").all_inner_texts()
        medellin = next((o for o in opciones if CIUDAD_RE.search(o)), None)
        if medellin:
            sel.select_option(label=medellin)
            _esperar_carga(page)
            return True
    try:
        _clic(page, r"medell[ií]n")
        return True
    except (PWTimeout, RuntimeError):
        return False


def recorrido(page: Page) -> tuple[str, str]:
    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    _esperar_carga(page)
    _clic(page, r"^\s*Agendar cita\s*$")

    _clic(page, r"Persona\s*Natural")
    _avanzar_hasta(page, r"prefiere la cita")

    _clic(page, r"Videoatenci[oó]n")
    _avanzar_hasta(page, r"tipo de servicio")

    _clic(page, r"^\s*Devoluciones\.?\s*$")
    if not SIN_CUPO_RE.search(_texto(page)):
        _siguiente(page)
        _aparece(page, SIN_CUPO_RE, 10)

    texto = _texto(page)
    iframe_captcha = page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha']").count() > 0
    estado = clasificar(texto, iframe_captcha)
    if estado == "medellin":
        _elegir_medellin(page)
        texto = _texto(page)
    return estado, texto


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
        self.captura: Path | None = None

    # API pública (la llaman los endpoints de FastAPI desde el hilo del loop)

    def iniciar(self) -> bool:
        with self._lock:
            if self._hilo and self._hilo.is_alive():
                return False
            self._stop.clear()
            self.estado, self.intentos, self.sin_cupo = "iniciando", 0, 0
            self.pantalla = self.captura = self.proxima_revision = None
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
                resultado, texto = recorrido(page)
                fallos = 0
            except Exception as e:
                if self._stop.is_set():
                    return True
                if page.is_closed() or "has been closed" in str(e):
                    raise _VentanaCerrada() from e
                fallos += 1
                self._anotar("warn", f"Revisión {self.intentos} falló: {str(e).splitlines()[0][:160]}")
                self._evidencia(page, "error")
                resultado, texto = "error", ""
            self.ultima_revision = dt.datetime.now().isoformat(timespec="seconds")

            if resultado == "sin_cupo":
                self.sin_cupo += 1
                self._anotar("info", f"Revisión {self.intentos}: sin cupo")
                if self.sin_cupo == 1:  # evidencia de que el recorrido llegó de verdad al aviso
                    self._evidencia(page, "sin_cupo")
            elif resultado == "otra_ciudad":
                self._anotar("info", f"Revisión {self.intentos}: hay cupo pero no en {CIUDAD}; sigo buscando")
                self._evidencia(page, "otra_ciudad")
            elif resultado in ("medellin", "desconocida", "captcha"):
                self._encontrado(page, resultado, texto)
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

    def _encontrado(self, page: Page, resultado: str, texto: str) -> None:
        self.estado = "captcha" if resultado == "captcha" else "hay_cupo"
        self.captura = self._evidencia(page, self.estado)
        self.pantalla = _resumen_pantalla(texto)
        if resultado == "captcha":
            titulo, encabezado = "Cita DIAN: CAPTCHA", "El portal pidió un CAPTCHA: termínalo tú en la ventana abierta."
        elif resultado == "medellin":
            titulo, encabezado = "Cita DIAN: ¡hay cupo!", f"¡HAY CUPO en {CIUDAD}! Devoluciones · Videoatención."
        else:
            titulo = "Cita DIAN: ¡el portal avanzó!"
            encabezado = f"El portal pasó de 'sin cupo' a una pantalla nueva. Revisa si es para {CIUDAD}."
        self._anotar("ok", encabezado)
        MENSAJE.write_text(
            f"{encabezado}\nDetectado: {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
            "La ventana del navegador quedó abierta en esa pantalla: termina la reserva ahí.\n"
            f"Captura: {self.captura}\n\n---- Lo que muestra el portal ----\n{self.pantalla}\n",
            encoding="utf-8",
        )
        _avisar(titulo, f"{encabezado}\nTermina la reserva en la ventana del navegador que quedó abierta.")


vigia = Vigia()
