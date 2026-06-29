// Manager for the DIAN scraper sidecar (apps/dian-rut, FastAPI + Playwright).
// Unlike the stdio core sidecar, this is a long-running HTTP server: we spawn
// uvicorn once on a fixed local port and proxy to it. Singleton via globalThis
// so it survives Nuxt HMR. If something already answers on the port (orphan or
// standalone run) we reuse it instead of spawning a second copy.

import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'

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

function resolvePythonBin(): string {
  if (process.env.DIAN_PYTHON) return process.env.DIAN_PYTHON
  // apps/desktop is the Nuxt cwd; the venv lives at ../dian-rut/.venv.
  const candidates = [
    resolve(process.cwd(), '..', 'dian-rut', '.venv', 'bin', 'python'),
    resolve(process.cwd(), '..', '..', 'apps', 'dian-rut', '.venv', 'bin', 'python'),
  ]
  for (const c of candidates) if (existsSync(c)) return c
  return 'python3'
}

function dianCwd(): string {
  const a = resolve(process.cwd(), '..', 'dian-rut')
  if (existsSync(a)) return a
  return resolve(process.cwd(), '..', '..', 'apps', 'dian-rut')
}

async function isHealthy(timeoutMs = 1200): Promise<boolean> {
  try {
    const ctrl = new AbortController()
    const t = setTimeout(() => ctrl.abort(), timeoutMs)
    const res = await fetch(`${dianBaseUrl()}/browser-mode-status`, { signal: ctrl.signal })
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
      cmd = resolvePythonBin()
      args = ['-u', '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(DIAN_PORT), '--log-level', 'warning']
      cwd = dianCwd()
    }
    const proc = spawn(cmd, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, PYTHONUNBUFFERED: '1' } })
    state.proc = proc
    proc.stdout?.on('data', (c: Buffer) => process.stderr.write(`[dian-rut] ${c}`))
    proc.stderr?.on('data', (c: Buffer) => process.stderr.write(`[dian-rut] ${c}`))
    proc.on('exit', (code) => {
      console.error('[dian-rut] uvicorn salió con código', code)
      state.proc = null
    })

    const deadline = Date.now() + 30_000
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
