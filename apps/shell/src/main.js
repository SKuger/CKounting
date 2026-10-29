// Contab desktop shell (Electron). Lifecycle: single-instance lock → show the splash window
// immediately (cosmos intro) while Nitro (which spawns the Python sidecars) boots in parallel → the
// main window loads hidden → the user presses "Ingresar" to reveal it → on quit, tree-kill the
// server so no Python grandchildren are orphaned.
const { app, BrowserWindow, Menu, dialog, shell, ipcMain } = require('electron')
const path = require('node:path')
const crypto = require('node:crypto')
const treeKill = require('tree-kill')
const log = require('electron-log')

// D-089 — Secreto por arranque para la API local. `/api/rpc` es un ejecutor
// universal (recibe db_path, source_path y output_path del cliente); el puerto
// aleatorio en 127.0.0.1 descarta la red, pero no a otro proceso de la máquina
// ni a una página del navegador barriendo puertos. Este token vive solo en
// memoria, viaja a Nitro por env y llega al renderer por el preload: nada que
// no sea nuestra ventana puede leerlo.
const TOKEN_LOCAL = crypto.randomBytes(32).toString('hex')

// One folder for everything Contab (matches Python paths.py base on Windows: %APPDATA%\Contab).
app.setName('Contab')
process.env.CONTAB_VERSION = app.getVersion()
log.initialize()
log.transports.file.level = 'info'

const { startNitro } = require('./nitro')

let splash = null
let win = null
let server = null // { proc, port }
let ready = false        // Nitro up + main window loaded
let enterRequested = false // user pressed "Ingresar" before it was ready

function killServer() {
  if (server && server.proc && server.proc.pid && !server.proc.killed) {
    try { treeKill(server.proc.pid) } catch (e) { log.warn('treeKill failed', e) }
  }
  server = null
}

function createSplash() {
  splash = new BrowserWindow({
    width: 960,
    height: 620,
    frame: false,
    resizable: false,
    center: true,
    backgroundColor: '#04050d',
    show: false,
    alwaysOnTop: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,          // D-088
      webviewTag: false,
      preload: path.join(__dirname, 'splash-preload.js'),
    },
  })
  splash.once('ready-to-show', () => splash.show())
  splash.on('closed', () => { splash = null })
  splash.loadFile(path.join(__dirname, 'splash.html'))
}

// D-088 — Solo estos esquemas salen al navegador del sistema. Sin filtro,
// `shell.openExternal` acepta cualquier cosa, incluido `file://` (que abre o
// ejecuta rutas locales) y esquemas registrados por otras aplicaciones.
const ESQUEMAS_EXTERNOS_PERMITIDOS = new Set(['https:', 'http:', 'mailto:'])

function abrirFuera(urlStr) {
  let u
  try {
    u = new URL(urlStr)
  } catch {
    log.warn('[seguridad] URL inválida, no se abre:', urlStr)
    return
  }
  if (!ESQUEMAS_EXTERNOS_PERMITIDOS.has(u.protocol)) {
    log.warn('[seguridad] esquema no permitido, no se abre:', u.protocol, urlStr)
    return
  }
  shell.openExternal(urlStr)
}

// Cada ventana con las mismas protecciones. Varias a la vez es seguro: la empresa
// va en la URL de cada una (`?db=`), no en un estado compartido.
function crearVentana() {
  const w = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    backgroundColor: '#0a0b1a', // cosmos-ink: no white flash before the app paints
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      // D-088: el renderer no necesita nada del sistema — todo pasa por Nitro.
      sandbox: true,
      webviewTag: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  })
  const origenPropio = `http://127.0.0.1:${server.port}`
  // Un enlace externo (target=_blank) va al navegador del sistema; uno nuestro
  // (Ctrl+clic, o «Abrir otra ventana») abre otra ventana de Contab.
  w.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(origenPropio)) abrirOtraVentana(url)
    else abrirFuera(url)
    return { action: 'deny' }
  })
  w.webContents.on('before-input-event', (evento, input) => {
    if (input.type === 'keyDown' && input.control && !input.shift && !input.alt
        && input.key.toLowerCase() === 'n') {
      evento.preventDefault()
      abrirOtraVentana(w.webContents.getURL())
    }
  })

  // D-088 — La ventana solo puede navegar a NUESTRO servidor. Sin esto, un enlace
  // (o un redirect) llevaba el renderer a un sitio externo CONSERVANDO el puente
  // del preload: la página de fuera quedaba dentro de la app.
  w.webContents.on('will-navigate', (evento, url) => {
    if (!url.startsWith(origenPropio)) {
      evento.preventDefault()
      log.warn('[seguridad] navegación fuera del origen bloqueada:', url)
      abrirFuera(url)
    }
  })
  // Nada de permisos del navegador (cámara, micrófono, geolocalización…): esta
  // app no usa ninguno, así que la respuesta correcta siempre es no.
  w.webContents.session.setPermissionRequestHandler((_wc, permiso, callback) => {
    log.warn('[seguridad] permiso denegado:', permiso)
    callback(false)
  })
  return w
}

// Pedida por el contador (2026-10-29): trabajar dos cosas a la vez, por ejemplo
// la causación de una empresa mientras mira otra.
function abrirOtraVentana(url) {
  if (!server) return
  const origenPropio = `http://127.0.0.1:${server.port}`
  const destino = url && url.startsWith(origenPropio) ? url : `${origenPropio}/`
  const w = crearVentana()
  w.once('ready-to-show', () => w.show())
  w.loadURL(destino).catch((e) => log.error('otra ventana no cargó', e))
}

async function createMainWindow() {
  Menu.setApplicationMenu(null)
  win = crearVentana()
  await win.loadURL(`http://127.0.0.1:${server.port}/`)
  win.on('closed', () => { win = null })

  // Auto-update only makes sense in the installed app (dev has no update feed).
  if (app.isPackaged) {
    try { require('./updater').initUpdater() } catch (e) { log.warn('updater init failed', e) }
  }
}

// Reveal the app: close the splash and show the (already loaded) main window.
function revealApp() {
  if (!win) return
  if (splash) { try { splash.close() } catch (e) { /* noop */ } splash = null }
  win.show()
  win.focus()
}

// "Ingresar" pressed in the splash. Reveal now if ready; otherwise mark intent and tell the splash
// to show its "Entrando…" state until Nitro finishes.
ipcMain.on('splash:enter', () => {
  if (ready && win) revealApp()
  else { enterRequested = true; if (splash) splash.webContents.send('splash:loading') }
})

// "Salir de Contab" desde la UI (SidebarUser) → cerrar el programa. before-quit hace el treeKill.
ipcMain.on('app:quit', () => app.quit())
ipcMain.on('app:nueva-ventana', (evento) => abrirOtraVentana(evento.sender.getURL()))

// El preload lo pide de forma síncrona al construir el puente (D-089).
ipcMain.on('contab:token', (evento) => { evento.returnValue = TOKEN_LOCAL })

async function boot() {
  createSplash()
  server = await startNitro(TOKEN_LOCAL)
  await createMainWindow()
  ready = true
  if (enterRequested) revealApp() // user already clicked while it was still booting
}

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  // Volver a abrir el ícono con Contab ya abierto da otra ventana, sin un
  // segundo servidor. Si todavía está arrancando, se enfoca lo que haya.
  app.on('second-instance', () => {
    if (ready) { abrirOtraVentana(); return }
    const w = win || splash
    if (w) { if (w.isMinimized && w.isMinimized()) w.restore(); w.focus() }
  })

  app.whenReady().then(boot).catch((err) => {
    log.error('startup failed', err)
    if (splash) { try { splash.close() } catch (e) { /* noop */ } }
    dialog.showErrorBox('Contab — error al iniciar', String(err && err.message ? err.message : err))
    killServer()
    app.quit()
  })

  // macOS: al reactivar sin ventanas, reabrir la ventana — NO volver a arrancar
  // todo. `boot()` levantaría un SEGUNDO servidor Nitro con sus sidecars, dejando
  // el primero huérfano (D-088).
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length > 0) return
    if (server) createMainWindow().then(revealApp).catch((e) => log.error('reactivar falló', e))
    else boot().catch((e) => log.error('arranque falló', e))
  })
}

app.on('window-all-closed', () => {
  killServer()
  if (process.platform !== 'darwin') app.quit()
})
app.on('before-quit', killServer)
// `process.on('exit')` NO servía: treeKill es asíncrono y en 'exit' ya no se
// puede programar nada. El cierre limpio lo hace 'before-quit'; esto es la red
// para una caída del proceso principal, donde matar el árbol al menos se INTENTA
// de forma síncrona antes de irse (D-088).
process.on('uncaughtException', (err) => {
  log.error('excepción no capturada en el proceso principal', err)
  killServer()
})
