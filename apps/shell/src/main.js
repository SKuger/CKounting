// Contab desktop shell (Electron). Lifecycle: single-instance lock → show the splash window
// immediately (cosmos intro) while Nitro (which spawns the Python sidecars) boots in parallel → the
// main window loads hidden → the user presses "Ingresar" to reveal it → on quit, tree-kill the
// server so no Python grandchildren are orphaned.
const { app, BrowserWindow, Menu, dialog, shell, ipcMain } = require('electron')
const path = require('node:path')
const treeKill = require('tree-kill')
const log = require('electron-log')

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
      preload: path.join(__dirname, 'splash-preload.js'),
    },
  })
  splash.once('ready-to-show', () => splash.show())
  splash.on('closed', () => { splash = null })
  splash.loadFile(path.join(__dirname, 'splash.html'))
}

async function createMainWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    backgroundColor: '#0a0b1a', // cosmos-ink: no white flash before the app paints
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  })
  Menu.setApplicationMenu(null)
  // open external links (target=_blank) in the system browser, not a new Electron window
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' } })
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

async function boot() {
  createSplash()
  server = await startNitro()
  await createMainWindow()
  ready = true
  if (enterRequested) revealApp() // user already clicked while it was still booting
}

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
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

  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) boot() })
}

app.on('window-all-closed', () => {
  killServer()
  if (process.platform !== 'darwin') app.quit()
})
app.on('before-quit', killServer)
process.on('exit', killServer)
