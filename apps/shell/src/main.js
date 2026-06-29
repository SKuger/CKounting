// Contab desktop shell (Electron). Lifecycle: single-instance lock → start Nitro (which spawns the
// Python sidecars) → open the window pointing at the local server → on quit, tree-kill the server
// so no Python grandchildren are orphaned.
const { app, BrowserWindow, Menu, dialog, shell } = require('electron')
const path = require('node:path')
const treeKill = require('tree-kill')
const log = require('electron-log')

// One folder for everything Contab (matches Python paths.py base on Windows: %APPDATA%\Contab).
app.setName('Contab')
process.env.CONTAB_VERSION = app.getVersion()
log.initialize()
log.transports.file.level = 'info'

const { startNitro } = require('./nitro')

let win = null
let server = null // { proc, port }

function killServer() {
  if (server && server.proc && server.proc.pid && !server.proc.killed) {
    try { treeKill(server.proc.pid) } catch (e) { log.warn('treeKill failed', e) }
  }
  server = null
}

async function createWindow() {
  server = await startNitro()
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
  win.show()
  win.on('closed', () => { win = null })

  // Auto-update only makes sense in the installed app (dev has no update feed).
  if (app.isPackaged) {
    try { require('./updater').initUpdater() } catch (e) { log.warn('updater init failed', e) }
  }
}

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (win) { if (win.isMinimized()) win.restore(); win.focus() }
  })

  app.whenReady().then(createWindow).catch((err) => {
    log.error('startup failed', err)
    dialog.showErrorBox('Contab — error al iniciar', String(err && err.message ? err.message : err))
    killServer()
    app.quit()
  })

  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
}

app.on('window-all-closed', () => {
  killServer()
  if (process.platform !== 'darwin') app.quit()
})
app.on('before-quit', killServer)
process.on('exit', killServer)
