// Manager for the DIAN scraper sidecar (apps/dian-rut, FastAPI + Playwright).
// Unlike the stdio core sidecar, this is a long-running HTTP server: we spawn
// uvicorn once on a fixed local port and proxy to it. Singleton via globalThis
// so it survives Nuxt HMR. If something already answers on the port (orphan or
// standalone run) we reuse it instead of spawning a second copy.

import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve, dirname, join } from 'node:path'

export const DIAN_PORT = Number(process.env.DIAN_PORT) || 8756

type DianState = {
  proc: ChildProcess | null
  starting: Promise<void> | null
}

const GLOBAL_KEY = '__contab_dian_sidecar__'

function getState(): DianState {
  const g = globalThis as Record<string, unknown>
  if (!g[GLOBAL_KEY]) {
    g[GLOBAL_KEY] = { proc: null, starting: null } satisfies DianState
  }
  return g[GLOBAL_KEY] as DianState
}

export function dianBaseUrl(): string {
  return `http://127.0.0.1:${DIAN_PORT}`
}

/**
 * Localiza `apps/dian-rut` subiendo desde el directorio actual (D-094).
 * Mismo criterio que utils/sidecar.ts: el cwd depende de quién arrancó Nitro
 * (`apps/desktop` con npm run dev, `apps/desktop/.output` desde el shell), así
 * que contar `..` fijos no vale.
 */
function dianCwd(): string | null {
  if (process.env.DIAN_DIR) return process.env.DIAN_DIR
  let dir = process.cwd()
  for (let i = 0; i < 6; i++) {
    for (const candidato of [resolve(dir, 'dian-rut'), resolve(dir, 'apps', 'dian-rut')]) {
      if (existsSync(join(candidato, 'main.py'))) return candidato
    }
    const padre = dirname(dir)
    if (padre === dir) break
    dir = padre
  }
  return null
}

function resolvePythonBin(dianDir: string | null): string {
  if (process.env.DIAN_PYTHON) return process.env.DIAN_PYTHON
  // Mismo criterio que utils/sidecar.ts: el layout del venv depende del SO.
  const isWin = process.platform === 'win32'
  const venvRel = isWin ? ['Scripts', 'python.exe'] : ['bin', 'python']
  if (dianDir) {
    const candidate = resolve(dianDir, '.venv', ...venvRel)
    if (existsSync(candidate)) return candidate
  }
  return isWin ? 'python' : 'python3'
}

async function isHealthy(timeoutMs = 1200): Promise<boolean> {
  try {
    const ctrl = new AbortController()
    const t = setTimeout(() => ctrl.abort(), timeoutMs)
    const res = await fetch(`${dianBaseUrl()}/health`, { signal: ctrl.signal })
    clearTimeout(t)
    return res.ok
  } catch {
    return false
  }
}

export async function ensureDianService(): Promise<void> {
  const state = getState()
  if (await isHealthy()) return
  if (state.starting) return state.starting

  state.starting = (async () => {
    // Packaged (Electron): DIAN_SIDECAR_BIN points at the PyInstaller exe (run_server.py embeds
    // uvicorn) — spawn it directly with --host/--port. Dev: `python -m uvicorn main:app`.
    const sidecarBin = process.env.DIAN_SIDECAR_BIN
    let cmd: string
    let args: string[]
    let cwd: string
    if (sidecarBin) {
      cmd = sidecarBin
      args = ['--host', '127.0.0.1', '--port', String(DIAN_PORT)]
      cwd = dirname(sidecarBin)
    } else {
      const dianDir = dianCwd()
      if (!dianDir) {
        throw new Error(
          'No se encontró apps/dian-rut desde ' + process.cwd() + '. ' +
          'Si el servidor corre fuera del repositorio, define DIAN_DIR.',
        )
      }
      cmd = resolvePythonBin(dianDir)
      args = ['-u', '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(DIAN_PORT), '--log-level', 'warning']
      cwd = dianDir
    }
    const proc = spawn(cmd, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, PYTHONUNBUFFERED: '1' } })
    state.proc = proc
    proc.stdout?.on('data', (c: Buffer) => process.stderr.write(`[dian-rut] ${c}`))
    proc.stderr?.on('data', (c: Buffer) => process.stderr.write(`[dian-rut] ${c}`))
    proc.on('exit', (code) => {
      console.error('[dian-rut] uvicorn salió con código', code)
      state.proc = null
    })

    // Arranque en frío (pandas + playwright) pasa de 30 s en Windows.
    const deadline = Date.now() + 90_000
    while (Date.now() < deadline) {
      if (await isHealthy(1000)) return
      await new Promise((r) => setTimeout(r, 500))
    }
    throw new Error('El servicio DIAN no respondió a tiempo (uvicorn no arrancó).')
  })()

  try {
    await state.starting
  } finally {
    state.starting = null
  }
}
