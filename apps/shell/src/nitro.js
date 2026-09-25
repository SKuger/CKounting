// Starts the Nuxt/Nitro Node server as a child process of Electron, using Electron's bundled Node
// (ELECTRON_RUN_AS_NODE=1 → no separate node.exe needed). Injects the env hooks so Nitro spawns the
// packaged PyInstaller sidecars + bundled Poppler. Returns { proc, port } once the server answers.
const { spawn } = require('node:child_process')
const net = require('node:net')
const http = require('node:http')
const fs = require('node:fs')
const log = require('electron-log')
const paths = require('./paths')

function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.unref()
    srv.on('error', reject)
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address()
      srv.close(() => resolve(port))
    })
  })
}

function httpOk(port) {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port, path: '/', timeout: 2000 }, (res) => {
      res.resume()
      resolve(res.statusCode != null && res.statusCode < 500)
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => { req.destroy(); resolve(false) })
  })
}

async function waitForServer(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await httpOk(port)) return
    await new Promise((r) => setTimeout(r, 400))
  }
  throw new Error(`El servidor no respondió en ${timeoutMs / 1000}s (puerto ${port}).`)
}

async function startNitro(tokenLocal) {
  const p = paths.compute()
  if (!fs.existsSync(p.serverEntry)) {
    throw new Error(`No se encontró el servidor en ${p.serverEntry}. ¿Falta 'nuxt build'?`)
  }
  // writable runtime dir for the DIAN sidecar (uploads/results/errors/browser_profile)
  fs.mkdirSync(p.dianWorkdir, { recursive: true })

  const port = await findFreePort()
  // D-089: el sidecar DIAN también en un puerto aleatorio. Estaba fijo en 8756,
  // o sea adivinable por cualquier proceso local, y el servicio no pide
  // credencial. Un puerto aleatorio por arranque no es autenticación, pero sube
  // bastante el listón frente a un barrido de puertos conocidos.
  const dianPort = await findFreePort()
  const env = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: '1',
    HOST: '127.0.0.1',
    NITRO_HOST: '127.0.0.1',
    PORT: String(port),
    NITRO_PORT: String(port),
    CONTAB_VERSION: require('electron').app.getVersion(),
    // D-089: su presencia ACTIVA la autenticación de la API. En `npm run dev` no
    // se define, así que el modo desarrollo sigue funcionando sin credencial.
    CONTAB_TOKEN: tokenLocal,
    DIAN_WORKDIR: p.dianWorkdir,
    DIAN_PORT: String(dianPort),
    PLAYWRIGHT_BROWSERS_PATH: p.playwrightBrowsers,
  }
  if (p.coreSidecarBin) env.CONTAB_SIDECAR_BIN = p.coreSidecarBin
  if (p.dianSidecarBin) env.DIAN_SIDECAR_BIN = p.dianSidecarBin
  if (p.pdftotext) env.CONTAB_PDFTOTEXT = p.pdftotext

  log.info('[nitro] starting', p.serverEntry, 'port', port, 'dianPort', dianPort, 'coreBin', p.coreSidecarBin || '(dev python)')
  const proc = spawn(process.execPath, [p.serverEntry], {
    cwd: p.serverRoot,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  proc.stdout.on('data', (d) => log.info('[nitro]', String(d).trimEnd()))
  proc.stderr.on('data', (d) => log.warn('[nitro]', String(d).trimEnd()))
  proc.on('exit', (code) => log.warn('[nitro] exited', code))

  await waitForServer(port)
  return { proc, port }
}

module.exports = { startNitro }
