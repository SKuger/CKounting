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
import sqlite3
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
PERSONA_NATURAL_RE = re.compile(r"persona\s+natural", re.IGNORECASE)
TRAMITE_RE = re.compile(r"^\s*Tr[aá]mite\s*$", re.IGNORECASE | re.MULTILINE)
FECHA_RE = re.compile(r"fecha y hora", re.IGNORECASE)
DATOS_RE = re.compile(r"Tipo de documento", re.IGNORECASE)
# Variantes del trámite que NO son la general de persona natural.
EXCLUIR_RE = re.compile(r"veh[ií]culo|el[eé]ctric|h[ií]brid|gran contribuyente", re.IGNORECASE)

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
    """La opción del desplegable "Trámite" que sirve: la GENERAL de Medellín para persona natural,
    p. ej. 'Medellín "Solicitud de devolución y/o compensación persona natural".' No sirven las de
    vehículos eléctricos/híbridos ni gran contribuyente, aunque digan Medellín o persona natural."""
    return next((o for o in opciones if CIUDAD_RE.search(o) and _es_general(o)), None)


def _es_general(opcion: str) -> bool:
    return bool(PERSONA_NATURAL_RE.search(opcion)) and not EXCLUIR_RE.search(opcion)


def _opciones_tramite(page: Page) -> tuple[list[str], object] | None:
    """Lee las opciones del desplegable "Trámite" (un <select class="customSelect"> en el portal).
    Devuelve (opciones, select) o None si no lo encuentra."""
    for sel in page.locator("select").all():
        if not sel.is_visible():
            continue
        opciones = [o.strip() for o in sel.locator("option").all_inner_texts() if o.strip()]
        if opciones:
            return opciones, sel
    return None


def _elegir_opcion(page: Page, opcion: str, select) -> None:
    select.select_option(label=opcion)
    _esperar_carga(page)


# Marca con data-vigia-dia los días clicables del calendario visible y devuelve cuántos hay
# (-1 si no hay calendario a la vista). No supone <table>: busca el contenedor más pequeño con la
# fila DO LU MA MI JU VI SA y, dentro, las hojas visibles cuyo texto es un número de día.
_JS_DIAS = r"""() => {
  const vis = e => e.offsetParent && getComputedStyle(e).visibility !== 'hidden';
  const conts = [...document.querySelectorAll('div,table')].filter(e => vis(e) &&
      /DO\s*LU\s*MA\s*MI\s*JU\s*VI\s*SA/.test(e.innerText || ''));
  if (!conts.length) return -1;
  const cal = conts.sort((a, b) => a.innerText.length - b.innerText.length)[0];
  const dias = [...cal.querySelectorAll('*')].filter(e => vis(e) && e.childElementCount === 0 &&
      /^\d{1,2}$/.test(e.textContent.trim()) &&
      !/disabled|unselectable|inactive/i.test(String(e.className || '') + ' ' + String(e.parentElement?.className || '')));
  document.querySelectorAll('[data-vigia-dia]').forEach(e => e.removeAttribute('data-vigia-dia'));
  dias.forEach((e, i) => e.setAttribute('data-vigia-dia', String(i)));
  return dias.length;
}"""


def _primer_dia(page: Page) -> str | None:
    """Hace clic en la fecha más cercana (el portal solo pinta los días con disponibilidad) y
    devuelve su número; None si el calendario no ofrece días."""
    n = page.evaluate(_JS_DIAS)
    if n == -1:  # calendario plegado: el campo "Fecha" lo despliega
        page.locator("input").locator("visible=true").first.click()
        page.wait_for_timeout(1000)
        n = page.evaluate(_JS_DIAS)
    if n <= 0:
        return None
    dia = page.locator('[data-vigia-dia="0"]')
    numero = dia.inner_text().strip()
    dia.click()
    _esperar_carga(page)
    return numero


def _primera_hora(page: Page) -> str | None:
    """Tras elegir el día aparece el desplegable "Hora"; elige la primera hora disponible."""
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        for sel in page.locator("select").all():
            if not sel.is_visible():
                continue
            horas = [o.strip() for o in sel.locator("option").all_inner_texts() if o.strip()]
            if horas and re.search(r"\d{1,2}:\d{2}", horas[0]):
                sel.select_option(label=horas[0])
                _esperar_carga(page)
                return horas[0]
        page.wait_for_timeout(500)
    return None


def _llenar_datos(page: Page, cedula: str) -> None:
    """Pantalla "Complete los siguientes datos": tipo de documento = cédula, número y aceptación
    del tratamiento de datos. Solo se llama si el usuario lo autorizó explícitamente en Contab."""
    for sel in page.locator("select").all():
        if sel.is_visible():
            opciones = sel.locator("option").all_inner_texts()
            cc = next((o for o in opciones if re.search(r"c[eé]dula de ciudadan", o, re.IGNORECASE)), None)
            if cc:
                sel.select_option(label=cc)
                _esperar_carga(page)
                break
    campo = page.locator("input[type=text], input[type=number], input[type=tel], input:not([type])").locator("visible=true").first
    campo.fill(cedula)
    casilla = page.locator("input[type=checkbox]").locator("visible=true")
    if casilla.count():
        if not casilla.first.is_checked():
            casilla.first.check()
    else:  # casilla propia: el texto "Acepto el tratamiento…"
        page.get_by_text(re.compile(r"Acepto el", re.IGNORECASE)).locator("visible=true").first.click()


def _hasta_datos(page: Page, opcion: str, select) -> tuple[str, str]:
    """Trámite → Siguiente → fecha más cercana → primera hora → Siguiente. Devuelve
    (estado, detalle) con estado ∈ datos | sin_fechas | raro."""
    _elegir_opcion(page, opcion, select)
    _siguiente(page)
    if SIN_CUPO_RE.search(_texto(page)):
        return "sin_fechas", opcion
    if not _aparece(page, FECHA_RE, 30):
        return "raro", f"Trámite elegido: {opcion}. La pantalla siguiente no es la de fecha."
    dia = _primer_dia(page)
    if dia is None:
        return "sin_fechas", opcion
    hora = _primera_hora(page)
    if hora is None:
        return "raro", f"Trámite: {opcion} · día {dia}, pero no apareció ninguna hora."
    _siguiente(page)
    detalle = f"Trámite: {opcion} · Día {dia} · Hora {hora}"
    if not _aparece(page, DATOS_RE, 30):
        return "raro", detalle + ". La pantalla siguiente no es la de datos."
    return "datos", detalle


def recorrido(page: Page, estudiar=None, cedula: str | None = None) -> tuple[str, str, str]:
    """Devuelve (resultado, texto_pantalla, detalle).

    resultado ∈ sin_cupo | otra_ciudad | sin_fechas | hay_cupo | captcha
    `estudiar`: si se pasa y el trámite es de otra ciudad, se sigue ese trámite hasta la pantalla de
    datos (sin llenarla) para capturar las pantallas (ver _estudiar_flujo).
    `cedula`: solo si el usuario autorizó que el bot llene su documento y acepte el tratamiento.
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
    if _captcha_visible(page):
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
            detalle = " | ".join(opciones)
            if estudiar:
                modelo = next((o for o in opciones if _es_general(o)), opciones[0])
                detalle += " · " + _estudiar_flujo(page, modelo, select, estudiar)
            return "otra_ciudad", _texto(page), detalle

        estado, detalle = _hasta_datos(page, elegida, select)
        if estado == "sin_fechas":
            return "sin_fechas", _texto(page), detalle
        if estado == "raro":
            return "hay_cupo", _texto(page), detalle + " Revísala tú."
        if _captcha_visible(page):
            return "captcha", _texto(page), detalle
        if not cedula:
            return "hay_cupo", _texto(page), detalle + ". Llena tu documento y acepta el tratamiento de datos."
        _llenar_datos(page, cedula)
        _siguiente(page)
        if _captcha_visible(page):
            return "captcha", _texto(page), detalle + " · Cédula llenada."
        return "hay_cupo", _texto(page), detalle + " · Cédula llenada y tratamiento aceptado. Completa lo que sigue."
    except Exception as e:  # noqa: BLE001
        return "hay_cupo", _texto(page), f"Hay trámites pero me trabé ({str(e).splitlines()[0][:120]}): termina tú."


def _captcha_visible(page: Page) -> bool:
    """¿Hay un desafío de CAPTCHA a la vista? El portal carga SIEMPRE un reCAPTCHA invisible
    (iframe `anchor` con scale(0)); lo que cuenta es la ventana del desafío (`bframe`) abierta."""
    for f in page.locator("iframe[src*='recaptcha/api2/bframe'], iframe[src*='hcaptcha']").all():
        caja = f.bounding_box() if f.is_visible() else None
        if caja and caja["height"] > 100:
            return True
    return False


def _estudiar_flujo(page: Page, opcion: str, select, guardar) -> str:
    """Sigue un trámite que NO sirve (otra ciudad) solo para capturar las pantallas que vienen:
    calendario y la siguiente al día. Nunca escribe datos ni confirma. `guardar(etiqueta)` deja
    captura + HTML. Devuelve un resumen para el registro."""
    try:
        estado, detalle = _hasta_datos(page, opcion, select)
        guardar("estudio_3_siguiente" if estado == "datos" else "estudio_parcial")
        return f"estudio ({estado}): {detalle}"
    except Exception as e:  # noqa: BLE001 — estudiar nunca debe tumbar la búsqueda
        guardar("estudio_error")
        return f"estudio incompleto ({str(e).splitlines()[0][:100]})"


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


# ─── la cola de personas (contab.db, tabla del núcleo: apps/core/contab_core/cita_personas.py) ──

def _ruta_program_db() -> Path:
    """contab.db, con el mismo criterio que apps/core/contab_core/paths.py (Nuxt lo pasa por env)."""
    if os.environ.get("CONTAB_PROGRAM_DB"):
        return Path(os.environ["CONTAB_PROGRAM_DB"])
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "Contab" / "contab.db"


def _cola(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(_ruta_program_db(), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def siguiente_pendiente() -> dict | None:
    rows = _cola("SELECT id, cedula, nombre, correo, celular, autoriza_tratamiento FROM cita_persona"
                 " WHERE estado = 'pendiente' ORDER BY id LIMIT 1")
    return dict(rows[0]) if rows else None


def marcar_en_curso(pid: int, detalle: str) -> None:
    _cola("UPDATE cita_persona SET estado = 'en_curso', detalle = ?, updated_at = datetime('now')"
          " WHERE id = ? AND estado = 'pendiente'", (detalle[:500], pid))


def estado_de(pid: int) -> str | None:
    rows = _cola("SELECT estado FROM cita_persona WHERE id = ?", (pid,))
    return rows[0]["estado"] if rows else None


def _quien(persona: dict) -> str:
    return f"{persona.get('nombre') or 'sin nombre'} (CC {persona['cedula']})"


# ─── el vigía ─────────────────────────────────────────────────────────────────────────────────

class _VentanaCerrada(Exception):
    pass


class Vigia:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        # La pausa al encontrar cupo NO puede depender de la base de datos. Antes se
        # reanudaba sola en cuanto la persona dejaba de estar `en_curso`, y si el
        # marcado fallaba —su error solo se anotaba como aviso— la espera terminaba
        # al instante, el bot volvía a navegar y se perdía el cupo encontrado.
        # Ahora solo la levanta un acto del usuario: Continuar, o resolver a la
        # persona en Contab.
        self._continuar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._log: deque[dict] = deque(maxlen=200)
        self.estado = "detenido"  # detenido | iniciando | revisando | esperando | hay_cupo | captcha
        self.pausado = False
        self.intentos = 0
        self.sin_cupo = 0
        self.ultima_revision: str | None = None
        self.proxima_revision: str | None = None
        self.pantalla: str | None = None
        self.detalle: str | None = None
        self.captura: Path | None = None
        self.persona: dict | None = None

    # API pública (la llaman los endpoints de FastAPI desde el hilo del loop)

    def iniciar(self) -> bool:
        with self._lock:
            if self._hilo and self._hilo.is_alive():
                return False
            self._stop.clear()
            self._continuar.clear()
            self.pausado = False
            self.estado, self.intentos, self.sin_cupo = "iniciando", 0, 0
            self.pantalla = self.detalle = self.captura = self.proxima_revision = self.persona = None
            self._hilo = threading.Thread(target=self._correr, name="vigia-citas", daemon=True)
            self._hilo.start()
            return True

    def detener(self) -> None:
        self._stop.set()
        self._continuar.set()      # que una pausa no deje el hilo colgado

    def continuar(self) -> dict:
        """Reanuda la búsqueda después de un cupo encontrado. Sin esto, el bot se
        queda quieto para siempre: perder un cupo por seguir buscando es peor que
        quedarse esperando de más."""
        if not self.pausado:
            return {"reanudado": False, "motivo": "La búsqueda no está en pausa."}
        self._continuar.set()
        self._anotar("info", "Continuar: sigo buscando la siguiente cita")
        return {"reanudado": True}

    def snapshot(self) -> dict:
        return {
            "activo": bool(self._hilo and self._hilo.is_alive()),
            "estado": self.estado,
            "pausado": self.pausado,
            "intentos": self.intentos,
            "sin_cupo": self.sin_cupo,
            "ultima_revision": self.ultima_revision,
            "proxima_revision": self.proxima_revision,
            "espera_s": [ESPERA_MIN_S, ESPERA_MAX_S],
            "pantalla": self.pantalla,
            "detalle": self.detalle,
            "persona": ({k: self.persona.get(k) for k in ("id", "cedula", "nombre")}
                        if self.persona else None),
            "hay_captura": bool(self.captura and self.captura.exists()),
            "log": list(self._log)[-60:],
        }

    def ruta_captura(self) -> Path | None:
        return self.captura if self.captura and self.captura.exists() else None

    # interno

    def _anotar(self, nivel: str, msg: str) -> None:
        self._log.append({"t": dt.datetime.now().isoformat(timespec="seconds"), "nivel": nivel, "msg": msg})
        print(f"[citas] {nivel}: {msg}", file=sys.stderr, flush=True)

    def _ya_estudiado(self) -> bool:
        return any(CAPTURAS.glob("*_estudio_3_siguiente.png"))

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
            try:
                persona = siguiente_pendiente()
            except sqlite3.Error as e:
                self._anotar("error", f"No pude leer la lista de personas: {e}")
                return True
            if persona is None:
                self._anotar("ok", "No quedan personas pendientes por agendar. Búsqueda terminada.")
                return True
            if not self.persona or self.persona["id"] != persona["id"]:
                self._anotar("info", f"Buscando cita para {_quien(persona)}")
            self.persona = persona
            self.intentos += 1
            self.estado = "revisando"
            self.proxima_revision = None
            page = self._pagina(ctx)
            try:
                estudiar = None if self._ya_estudiado() else (lambda etiqueta, p=page: self._evidencia(p, etiqueta))
                cedula = persona["cedula"] if persona["autoriza_tratamiento"] else None
                resultado, texto, detalle = recorrido(page, estudiar, cedula)
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
                self._anotar("info", f"Revisión {self.intentos}: hay trámites pero no en {CIUDAD} ({detalle[:300]}); sigo buscando")
                self._evidencia(page, "otra_ciudad")
            elif resultado == "sin_fechas":
                self._anotar("info", f"Revisión {self.intentos}: hay trámite en {CIUDAD} pero sin días disponibles; sigo buscando")
                self._evidencia(page, "sin_fechas")
            elif resultado in ("hay_cupo", "captcha"):
                self._encontrado(page, resultado, texto, detalle)
                # La ventana queda EN ESA PANTALLA y la búsqueda se detiene hasta que
                # el usuario pulse Continuar. No se vuelve a navegar por nada: el
                # cupo encontrado dura poco y volver al portal lo pierde.
                if not self._esperar_usuario(persona):
                    return True
                if page.is_closed():
                    raise _VentanaCerrada()
                continue

            espera = random.uniform(ESPERA_MIN_S, ESPERA_MAX_S) * min(1 + fallos, 4)
            self.estado = "esperando"
            self.proxima_revision = (dt.datetime.now() + dt.timedelta(seconds=espera)).isoformat(timespec="seconds")
            if self._stop.wait(espera):
                return True
        return True

    def _esperar_usuario(self, persona: dict) -> bool:
        """Pausa la búsqueda hasta que el usuario la reanude. False si pulsaron Detener.

        Se levanta de dos maneras, **ambas actos deliberados del usuario**:

        - pulsar *Continuar* en Contab, o
        - marcar a la persona como **agendada** (o quitarla de la lista).

        Lo que ya NO la levanta es que la persona siga en `pendiente`. Antes bastaba
        con que no estuviera `en_curso`, así que un fallo al marcarla —que solo se
        anotaba como aviso— reanudaba la búsqueda sola, el bot volvía a navegar y el
        cupo encontrado se perdía. Quedarse esperando de más es barato; perder un
        cupo no.
        """
        self.pausado = True
        self._continuar.clear()
        self._anotar("ok", f"En pausa: la ventana queda en esa pantalla. Pulsa «Continuar» cuando termines.")
        try:
            while not self._stop.is_set():
                if self._continuar.wait(1):
                    self.pantalla = self.detalle = self.captura = None
                    return not self._stop.is_set()
                try:
                    estado = estado_de(persona["id"])
                except sqlite3.Error:
                    continue
                if estado in ("agendada", None):
                    txt = "agendada" if estado == "agendada" else "quitada de la lista"
                    self._anotar("ok", f"{_quien(persona)}: {txt}. Sigo con la siguiente persona.")
                    self.pantalla = self.detalle = self.captura = None
                    return True
            return False
        finally:
            self.pausado = False

    def _encontrado(self, page: Page, resultado: str, texto: str, detalle: str) -> None:
        persona = self.persona or {"cedula": "?"}
        detalle = f"{_quien(persona)} · {detalle}"
        try:
            if self.persona:
                marcar_en_curso(self.persona["id"], detalle)
        except sqlite3.Error as e:
            self._anotar("warn", f"No pude anotar el resultado en la lista: {e}")
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
            "La ventana del navegador quedó abierta en esa pantalla: termina la reserva ahí y marca a la\n"
            "persona como agendada en Contab (Consultas DIAN → Citas); el bot sigue con la siguiente.\n"
            f"Captura: {self.captura}\n\n---- Lo que muestra el portal ----\n{self.pantalla}\n",
            encoding="utf-8",
        )
        _avisar(titulo, f"{encabezado}\n{detalle}\n\nTermina la reserva en la ventana del navegador que quedó abierta.")


vigia = Vigia()
