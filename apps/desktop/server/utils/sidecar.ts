// IPC bridge: spawn the Python sidecar (apps/core/contab_core/sidecar.py) once
// and exchange JSON-lines over stdio. Singleton — survives Nuxt HMR via globalThis.

import { spawn, type ChildProcess } from 'node:child_process'
import { createInterface, type Interface } from 'node:readline'
import { existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'

type PendingResolver = {
  resolve: (value: unknown) => void
  reject: (error: Error) => void
}

type SidecarState = {
  proc: ChildProcess | null
  rl: Interface | null
  pending: Map<string, PendingResolver>
  nextId: number
}

const GLOBAL_KEY = '__contab_sidecar__'

function getState(): SidecarState {
  const g = globalThis as Record<string, unknown>
  if (!g[GLOBAL_KEY]) {
    g[GLOBAL_KEY] = {
      proc: null,
      rl: null,
      pending: new Map(),
      nextId: 1,
    } satisfies SidecarState
  }
  return g[GLOBAL_KEY] as SidecarState
}

function resolvePythonBin(): string {
  if (process.env.CONTAB_PYTHON) return process.env.CONTAB_PYTHON
  // El venv vive en ../core/.venv, pero su layout depende del SO: Scripts\python.exe
  // en Windows, bin/python en POSIX. El producto es Windows, así que probar solo
  // 'bin/python' dejaba el modo dev cayendo a 'python3', que en Windows no existe.
  const isWin = process.platform === 'win32'
  const venvRel = isWin ? ['Scripts', 'python.exe'] : ['bin', 'python']
  // apps/desktop is the Nuxt cwd; the venv lives at ../core/.venv.
  const roots = [
    resolve(process.cwd(), '..', 'core', '.venv'),
    resolve(process.cwd(), '..', '..', 'apps', 'core', '.venv'),
  ]
  for (const root of roots) {
    const candidate = resolve(root, ...venvRel)
    if (existsSync(candidate)) return candidate
  }
  return isWin ? 'python' : 'python3'
}

function ensureProcess() {
  const state = getState()
  if (state.proc && !state.proc.killed) return state.proc

  // Packaged (Electron): CONTAB_SIDECAR_BIN points at the PyInstaller executable, which embeds the
  // entrypoint — spawn it directly (no `-m`). Dev: fall back to `python -m contab_core.sidecar`.
  const sidecarBin = process.env.CONTAB_SIDECAR_BIN
  let cmd: string
  let args: string[]
  let cwd: string
  if (sidecarBin) {
    cmd = sidecarBin
    args = []
    cwd = dirname(sidecarBin)
  } else {
    cmd = resolvePythonBin()
    args = ['-u', '-m', 'contab_core.sidecar']
    const coreDir = resolve(process.cwd(), '..', 'core')
    cwd = existsSync(coreDir) ? coreDir : resolve(process.cwd(), '..', '..', 'apps', 'core')
  }

  const proc = spawn(cmd, args, {
    cwd,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  })
  state.proc = proc
  state.rl = createInterface({ input: proc.stdout! })

  state.rl.on('line', (line: string) => {
    if (!line.trim()) return
    let msg: { id?: string; result?: unknown; error?: { message?: string; code?: string } }
    try {
      msg = JSON.parse(line)
    } catch (exc) {
      console.error('[contab-sidecar] non-json line:', line)
      return
    }
    const id = String(msg.id ?? '')
    const pending = state.pending.get(id)
    if (!pending) {
      console.warn('[contab-sidecar] unknown response id:', id, msg)
      return
    }
    state.pending.delete(id)
    if (msg.error) pending.reject(new Error(msg.error.message || msg.error.code || 'sidecar error'))
    else pending.resolve(msg.result)
  })

  proc.stderr?.on('data', (chunk: Buffer) => {
    process.stderr.write(`[contab-sidecar stderr] ${chunk}`)
  })

  proc.on('exit', (code) => {
    console.error('[contab-sidecar] process exited with code', code)
    for (const p of state.pending.values()) p.reject(new Error(`sidecar exited (${code})`))
    state.pending.clear()
    state.proc = null
    state.rl = null
  })

  return proc
}

export async function callSidecar<T = unknown>(
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  const state = getState()
  const proc = ensureProcess()
  const id = String(state.nextId++)
  const payload = JSON.stringify({ id, method, params })
  return new Promise<T>((res, rej) => {
    state.pending.set(id, {
      resolve: (v) => res(v as T),
      reject: rej,
    })
    proc.stdin!.write(payload + '\n', (err) => {
      if (err) {
        state.pending.delete(id)
        rej(err)
      }
    })
    setTimeout(() => {
      if (state.pending.has(id)) {
        state.pending.delete(id)
        rej(new Error(`sidecar timeout (method=${method}, id=${id})`))
      }
    }, 30_000)
  })
}
