// IPC bridge: spawn the Python sidecar (apps/core/contab_core/sidecar.py) once
// and exchange JSON-lines over stdio. Singleton — survives Nuxt HMR via globalThis.

import { spawn, type ChildProcess } from 'node:child_process'
import { createInterface, type Interface } from 'node:readline'
import { existsSync } from 'node:fs'
import { resolve, dirname, join } from 'node:path'

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

/**
 * Localiza `apps/core` subiendo desde el directorio actual (D-094).
 *
 * No se puede calcular con un número fijo de `..`: el cwd depende de QUIÉN
 * arrancó Nitro. Con `npm run dev` es `apps/desktop`; cuando lo lanza el shell
 * de Electron es `apps/desktop/.output`, y entonces `../core` y `../../apps/core`
 * apuntaban los dos a carpetas inexistentes. El sidecar se lanzaba con un cwd
 * inválido, moría al instante y todas las peticiones fallaban con
 * "Cannot call write after a stream was destroyed".
 *
 * `CONTAB_CORE_DIR` permite fijarlo a mano si hiciera falta.
 */
function resolveCoreDir(): string | null {
  if (process.env.CONTAB_CORE_DIR) return process.env.CONTAB_CORE_DIR

  const marcador = join('contab_core', 'sidecar.py')
  let dir = process.cwd()
  for (let i = 0; i < 6; i++) {
    for (const candidato of [resolve(dir, 'core'), resolve(dir, 'apps', 'core')]) {
      if (existsSync(join(candidato, marcador))) return candidato
    }
    const padre = dirname(dir)
    if (padre === dir) break
    dir = padre
  }
  return null
}

function resolvePythonBin(coreDir: string | null): string {
  if (process.env.CONTAB_PYTHON) return process.env.CONTAB_PYTHON
  // El layout del venv depende del SO: Scripts\python.exe en Windows,
  // bin/python en POSIX. El producto es Windows, así que probar solo
  // 'bin/python' dejaba el modo dev cayendo a 'python3', que en Windows no existe.
  const isWin = process.platform === 'win32'
  const venvRel = isWin ? ['Scripts', 'python.exe'] : ['bin', 'python']
  if (coreDir) {
    const candidate = resolve(coreDir, '.venv', ...venvRel)
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
    const coreDir = resolveCoreDir()
    if (!coreDir) {
      throw new Error(
        'No se encontró apps/core desde ' + process.cwd() + '. ' +
        'Si el servidor corre fuera del repositorio, define CONTAB_CORE_DIR.',
      )
    }
    cmd = resolvePythonBin(coreDir)
    args = ['-u', '-m', 'contab_core.sidecar']
    cwd = coreDir
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

// Timeout por método (ms). El de por defecto asume una operación interactiva.
// Lo que NO tiene techo — extraer los PDFs de un mes, validar un lote entero — no
// vive aquí: se pide con `<método>_async`, devuelve un job_id al instante y el
// progreso se consulta con `job_status` (D-076). Un timeout fijo de 30 s sobre
// trabajo sin límite solo producía un error mientras Python seguía ocupado.
const DEFAULT_TIMEOUT_MS = 30_000
const METHOD_TIMEOUT_MS: Record<string, number> = {
  import_excel: 120_000,
  puc_import: 120_000,
  export_no_conformes: 120_000,
  export_missing_supports: 120_000,
  puc_export: 120_000,
  backup_empresa: 300_000,
  restore_empresa: 300_000,
  consulta_inconsistencias: 120_000,
  rename_soportes: 120_000,
}

function timeoutFor(method: string): number {
  // Los `*_async` solo arrancan el hilo y vuelven: son instantáneos.
  if (method.endsWith('_async')) return 10_000
  return METHOD_TIMEOUT_MS[method] ?? DEFAULT_TIMEOUT_MS
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
    const timer = setTimeout(() => {
      if (state.pending.has(id)) {
        state.pending.delete(id)
        rej(new Error(
          `El sidecar no respondió a tiempo (${method}). Si la operación es larga, ` +
          'debería pedirse como trabajo en segundo plano.',
        ))
      }
    }, timeoutFor(method))

    // Limpiar el temporizador al resolver evita que cada llamada deje un timer
    // vivo reteniendo su closure hasta que venza.
    state.pending.set(id, {
      resolve: (v) => { clearTimeout(timer); res(v as T) },
      reject: (e) => { clearTimeout(timer); rej(e) },
    })
    proc.stdin!.write(payload + '\n', (err) => {
      if (err) {
        clearTimeout(timer)
        state.pending.delete(id)
        rej(err)
      }
    })
  })
}
