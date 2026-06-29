// Resolves every runtime path the shell needs, for BOTH dev (running `electron .` against the
// sibling apps in the repo) and packaged (electron-builder copies artifacts to process.resourcesPath
// via `extraResources`). Returns absolute paths + the env vars to inject into the Nitro child.
const path = require('node:path')
const fs = require('node:fs')
const { app } = require('electron')

const WIN = process.platform === 'win32'
const EXE = WIN ? '.exe' : ''

// Everything Contab-related lives under one folder (matches the Python paths.py base on Windows:
// %APPDATA%\Contab). app name is forced to 'Contab' in main.js so Electron's own dirs land here too.
function contabDataDir() {
  return path.join(app.getPath('appData'), 'Contab')
}

function firstExisting(...candidates) {
  for (const c of candidates) if (c && fs.existsSync(c)) return c
  return null
}

// dev = running from the repo (not packaged). Artifacts are siblings under apps/.
function compute() {
  const packaged = app.isPackaged
  const res = process.resourcesPath // only meaningful when packaged
  const repoApps = path.resolve(__dirname, '..', '..') // apps/shell/src -> apps/

  // ── Nitro (Nuxt .output) ──
  const serverRoot = packaged
    ? path.join(res, 'server')
    : path.join(repoApps, 'desktop', '.output')
  const serverEntry = path.join(serverRoot, 'server', 'index.mjs')

  // ── core sidecar (PyInstaller onedir) ──
  const coreSidecarBin = packaged
    ? path.join(res, 'core-sidecar', `contab-sidecar${EXE}`)
    : firstExisting(path.join(repoApps, 'core', 'dist', 'contab-sidecar', `contab-sidecar${EXE}`))

  // ── DIAN sidecar (PyInstaller onedir) ──
  const dianSidecarBin = packaged
    ? path.join(res, 'dian-sidecar', `dian-sidecar${EXE}`)
    : firstExisting(path.join(repoApps, 'dian-rut', 'dist', 'dian-sidecar', `dian-sidecar${EXE}`))

  // ── Poppler / pdftotext ──
  const pdftotext = packaged
    ? path.join(res, 'poppler', `pdftotext${EXE}`)
    : null // dev/Linux: use PATH

  // ── writable runtime dirs ──
  const dianWorkdir = path.join(contabDataDir(), 'dian')
  const playwrightBrowsers = path.join(contabDataDir(), 'ms-playwright')

  return {
    packaged,
    serverRoot,
    serverEntry,
    coreSidecarBin,
    dianSidecarBin,
    pdftotext,
    dianWorkdir,
    playwrightBrowsers,
  }
}

module.exports = { compute, contabDataDir }
