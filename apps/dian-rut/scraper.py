import asyncio
import os
import traceback
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from dian_paths import BROWSER_PROFILE_DIR, ERRORS_DIR

DIAN_URL = "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces"


# Mapeo exacto de etiquetas DIAN → nombre de columna Excel
FIELD_MAP = {
    "NIT":              "NIT_RESULTADO",
    "DV":               "DV",
    "PRIMER APELLIDO":  "Primer Apellido",
    "SEGUNDO APELLIDO": "Segundo Apellido",
    "PRIMER NOMBRE":    "Primer Nombre",
    "OTROS NOMBRES":    "Otros Nombres",
    "FECHA ACTUAL":     "Fecha Actual",
    "ESTADO":           "Estado",
}

# Orden fijo de columnas de salida
COLUMNAS_SALIDA = [
    "DV", "Primer Apellido", "Segundo Apellido",
    "Primer Nombre", "Otros Nombres", "Fecha Actual", "Estado"
]


def _es_etiqueta_dian(linea_upper: str) -> bool:
    """Devuelve True si la línea corresponde a alguna etiqueta oficial DIAN.
    Usa comparación parcial por palabras clave para tolerar variaciones de formato JSF."""
    checks = [
        ("DV",) in [("DV",)] and linea_upper.strip() == "DV",
        "PRIMER" in linea_upper and "APELLIDO" in linea_upper and "SEGUNDO" not in linea_upper,
        "SEGUNDO" in linea_upper and "APELLIDO" in linea_upper,
        "PRIMER" in linea_upper and "NOMBRE" in linea_upper and "OTROS" not in linea_upper,
        "OTROS" in linea_upper and "NOMBRE" in linea_upper,
        "FECHA" in linea_upper and "ACTUAL" in linea_upper,
        linea_upper.strip() in ("NIT", "ESTADO", "DV"),
    ]
    return any(checks)


def _detectar_campo(linea_upper: str) -> str:
    """Mapea una línea a su columna Excel correspondiente usando coincidencia parcial.
    Retorna el nombre de columna destino o cadena vacía si no es una etiqueta."""
    u = linea_upper.strip()
    if u == "DV":
        return "DV"
    if u == "NIT":
        return "NIT_RESULTADO"
    if u == "ESTADO":
        return "Estado"
    if "FECHA" in u and "ACTUAL" in u:
        return "Fecha Actual"
    if "PRIMER" in u and "APELLIDO" in u and "SEGUNDO" not in u:
        return "Primer Apellido"
    if "SEGUNDO" in u and "APELLIDO" in u:
        return "Segundo Apellido"
    if "OTROS" in u and "NOMBRE" in u:
        return "Otros Nombres"
    if "PRIMER" in u and "NOMBRE" in u:
        return "Primer Nombre"
    return ""


def _parsear_resultados_dian(body_text: str) -> dict:
    """Parser de barrido único en dos fases para resultados DIAN.

    Fase 1 — Misma línea: si una línea contiene 'ETIQUETA: valor', extrae el valor inline.
    Fase 2 — Siguiente línea: si la etiqueta está sola, la siguiente línea no vacía es el valor.

    Reglas de tolerancia:
    - Coincidencia parcial por palabras clave (no exacta).
    - Tolerante a mayúsculas, espacios y variaciones JSF.
    - Siempre retorna todos los campos; campos no encontrados quedan vacíos.
    - Un campo captura exactamente un valor; nunca concatena múltiples campos.
    """
    # Registro con todas las columnas inicializadas vacías
    registro = {
        "NIT_RESULTADO": "",
        "DV":            "",
        "Primer Apellido":  "",
        "Segundo Apellido": "",
        "Primer Nombre":    "",
        "Otros Nombres":    "",
        "Fecha Actual":     "",
        "Estado":           "",
    }

    lineas = [l.strip() for l in body_text.splitlines() if l.strip()]
    campo_pendiente = None

    for linea in lineas:
        u = linea.upper()

        # --- Fase 1: buscar patrón "ETIQUETA: valor" en la misma línea ---
        campo_inline = ""
        valor_inline = ""
        for sep in (":", " - ", "\t"):
            if sep in linea:
                partes = linea.split(sep, 1)
                candidato = partes[0].strip().upper()
                campo_candidato = _detectar_campo(candidato)
                if campo_candidato:
                    campo_inline = campo_candidato
                    valor_inline = partes[1].strip()
                    break

        if campo_inline and valor_inline and not registro[campo_inline]:
            registro[campo_inline] = valor_inline
            campo_pendiente = None
            continue

        # --- Fase 2: detectar etiqueta sola y esperar la siguiente línea ---
        campo_detectado = _detectar_campo(u)
        if campo_detectado:
            campo_pendiente = campo_detectado
        elif campo_pendiente and not registro[campo_pendiente]:
            # Esta línea no es una etiqueta conocida → es el valor del campo pendiente
            registro[campo_pendiente] = linea
            campo_pendiente = None

    return registro

async def perform_scraping(nits: list[int | str | float], results: list[dict], client_id: str, send_log, save_callback=None):
    async with async_playwright() as p:
        mode = "automated"
        context = None
        page = None
        
        # 1. Attempt Human Mode (CDP)
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            if browser.contexts:
                context = browser.contexts[0]
                
                # Check for existing DIAN tab to reuse
                dian_page = None
                for p_page in context.pages:
                    if "muisca.dian.gov.co" in p_page.url:
                        dian_page = p_page
                        break
                
                if dian_page:
                    page = dian_page
                    await send_log(client_id, "success", {"message": "Reutilizando pestaña de la DIAN activa (Modo Humano)."})
                else:
                    page = context.pages[0] if context.pages else await context.new_page()
                    await send_log(client_id, "info", {"message": "Conectado al navegador real (Modo Humano). Nueva pestaña."})
                
                mode = "human"
        except Exception as cdp_err:
            await send_log(client_id, "info", {"message": "No se detectó navegador real en el puerto 9222. Fallback a modo automatizado..."})
            
        # 2. Automated Fallback
        if mode == "automated":
            # Directorio para el perfil del navegador (ayuda a pasar Cloudflare). Escribible: DIAN_WORKDIR.
            user_data_dir = BROWSER_PROFILE_DIR
            os.makedirs(user_data_dir, exist_ok=True)
            
            # Iniciar Stealth configuration solo en modo automático
            stealth_enforcer = Stealth()

            # Lanzar contexto persistente
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox"
                ],
                ignore_default_args=["--enable-automation"],
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
            )
            
            # Usar la primera página o crear una
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Aplicar stealth profundo
            await stealth_enforcer.apply_stealth_async(page)
            
            # Movimiento inicial aleatorio para simular humano
            await page.mouse.move(100, 100)
            await asyncio.sleep(1)
            await page.mouse.move(300, 400, steps=10)

        await send_log(client_id, "info", {"message": f"Navegando al portal de la DIAN..."})
        try:
            # Navegación inicial
            await page.goto(DIAN_URL, wait_until="commit", timeout=90000)
            
            # Si redirige al home, forzar una segunda carga (truco para JSF)
            # Reducido wait de 5s a 1s o esperar selector directamente
            await page.wait_for_timeout(2000)
            if "inicio.faces" in page.url or "WebRutMuisca" not in page.url:
                await send_log(client_id, "info", {"message": "Detectada redirección al inicio, forzando carga directa..."})
                await page.goto(DIAN_URL, wait_until="domcontentloaded", timeout=60000)
            
            await page.wait_for_load_state("domcontentloaded")
            
        except Exception as e:
            await send_log(client_id, "error", {"message": f"Error en navegación inicial: {str(e)}"})
            
        # Selectores conocidos
        nit_selector = "input[name*='numNit']"
        btn_selector = "input[name*='btnBuscar']"
        
        # Locators cacheados para eficiencia
        nit_input = page.locator(nit_selector)
        buscar_btn = page.locator(btn_selector)
        
        await send_log(client_id, "info", {"message": "Esperando validación de Cloudflare o carga de la página (Resuelva CAPTCHA si aparece)..."})
        
        try:
            # Esperar que el input sea visible (timeout largo por CAPTCHA inicial)
            await nit_input.wait_for(state="visible", timeout=300000) 
            await send_log(client_id, "info", {"message": "Formulario RUT detectado."})
        except Exception:
            await send_log(client_id, "error", {"message": "Tiempo de espera agotado para el formulario RUT."})
            await context.close()
            return

        for index, nit in enumerate(nits):
            start_time = asyncio.get_event_loop().time()
            progress_pct = int((index / len(nits)) * 100)
            nit_str = str(int(nit)).strip() if isinstance(nit, float) else str(nit).strip()
            
            await send_log(client_id, "progress", {
                "message": f"Consultando NIT: {nit_str} ({index+1}/{len(nits)})", 
                "percent": progress_pct
            })
            
            try:
                # 1. Asegurar que estamos en el formulario de búsqueda sin recargar
                # Si hay múltiples pestañas, cerrar todas menos la principal
                while len(context.pages) > 1:
                    await context.pages[-1].close()
                
                # Si la página actual no muestra el NIT (por error previo o navegación interna), forzar retorno
                if not await nit_input.is_visible():
                    # Buscar botón "Volver" o similar antes de hacer goto()
                    btn_volver = page.locator("input[name*='btnVolver'], input[value*='Volver'], button:has-text('Volver')")
                    if await btn_volver.count() > 0 and await btn_volver.first.is_visible():
                        await btn_volver.first.click()
                    else:
                        await page.goto(DIAN_URL, wait_until="domcontentloaded", timeout=30000)
                
                # Esperar a que el input esté listo para recibir datos
                await nit_input.wait_for(state="visible", timeout=20000)
                
                # 2. Llenar NIT (fill es más rápido que type)
                await nit_input.fill("")
                await nit_input.fill(nit_str)
                
                # 3. Ejecutar búsqueda
                result_page = page
                try:
                    # Capturamos la posible nueva pestaña
                    async with context.expect_page(timeout=5000) as new_page_info:
                        await buscar_btn.click()
                    result_page = await new_page_info.value
                except Exception:
                    # No abrió pestaña nueva, los resultados cargan en la misma
                    pass

                # 4. Esperar resultados con esperas inteligentes (QUITADO SLEEP FIJO)
                # Selector clave: el campo 'Estado' o 'Razón Social'
                try:
                    # Esperar que aparezca cualquiera de los campos de resultado
                    await result_page.wait_for_selector("td:has-text('Estado'), td:has-text('Nombre')", timeout=12000)
                except Exception:
                    pass

                # 5. Extracción directa y optimizada
                registro = await result_page.evaluate("""() => {
                    const g = (id) => {
                        const el = document.getElementById(id);
                        return el ? (el.value || el.innerText || '').trim() : '';
                    };
                    const prefix = 'vistaConsultaEstadoRUT:formConsultaEstadoRUT:';
                    
                    // Optimización: buscar Fecha Actual específicamente
                    let fechaActual = '';
                    const cells = document.querySelectorAll('td');
                    for (let i = 0; i < cells.length; i++) {
                        if (cells[i].innerText.includes('Fecha Actual')) {
                            if (cells[i+1]) fechaActual = cells[i+1].innerText.trim();
                            break;
                        }
                    }

                    return {
                        'DV':               g(prefix + 'dv'),
                        'Primer Apellido':  g(prefix + 'primerApellido'),
                        'Segundo Apellido': g(prefix + 'segundoApellido'),
                        'Primer Nombre':    g(prefix + 'primerNombre'),
                        'Otros Nombres':    g(prefix + 'otrosNombres'),
                        'Razón Social':     g(prefix + 'razonSocial'),
                        'Fecha Actual':     fechaActual,
                        'Estado':           g(prefix + 'estado'),
                    };
                }""")

                estado = registro.get("Estado", "")

                # Fallback solo si el evaluador rápido no encontró el estado
                if not estado:
                    content = await result_page.content()
                    if "ACTIVO" in content.upper(): estado = "REGISTRO ACTIVO"
                    elif "CANCELADO" in content.upper(): estado = "CANCELADO"
                    else: estado = "No Encontrado"

                exito = estado not in ("No Encontrado", "", "Error")
                
                nombre_log = " ".join(filter(None, [
                    registro.get("Primer Nombre", ""),
                    registro.get("Primer Apellido", ""),
                    registro.get("Razón Social", ""),
                ])) or nit_str

                results.append({
                    "NIT":              nit_str,
                    "DV":               registro.get("DV", ""),
                    "Primer Nombre":    registro.get("Primer Nombre", ""),
                    "Otros Nombres":    registro.get("Otros Nombres", ""),
                    "Primer Apellido":  registro.get("Primer Apellido", ""),
                    "Segundo Apellido": registro.get("Segundo Apellido", ""),
                    "Razón Social":     registro.get("Razón Social", ""),
                    "Fecha Actual":     registro.get("Fecha Actual", ""),
                    "Estado":           estado,
                    "Resultado":        "Éxito" if exito else "Fallo/No Encontrado",
                    "Error":            ""
                })

                end_time = asyncio.get_event_loop().time()
                elapsed = end_time - start_time
                await send_log(client_id, "success", {"message": f"NIT {nit_str}: {estado} ({elapsed:.2f}s)"})
                
                if save_callback:
                    await save_callback(results)
                    
            except Exception as e:
                error_msg = str(e)
                screenshot_path = os.path.join(ERRORS_DIR, f"error_{nit_str}.png")
                try: await page.screenshot(path=screenshot_path)
                except: pass
                
                await send_log(client_id, "error", {"message": f"Error NIT {nit_str}: {error_msg[:80]}"})
                results.append({"NIT": nit_str, "Estado": "Error", "Resultado": "Error", "Error": error_msg[:100]})

        await send_log(client_id, "progress", {"message": "Proceso completado.", "percent": 100})
        if mode == "automated":
            await context.close()
        else:
            await send_log(client_id, "info", {"message": "Desconectando de Chrome real. (Pestaña no se cerrará para preservar sesión)"})
