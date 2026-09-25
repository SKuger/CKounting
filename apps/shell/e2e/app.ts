// Arranque y parada de la aplicación para el smoke end-to-end.
//
// REGLA INNEGOCIABLE: esto NO puede tocar los datos reales del usuario.
// `paths.py` resuelve la carpeta de datos con %APPDATA% en Windows y
// XDG_DATA_HOME en Linux, así que se apuntan ambas a un temporal antes de
// lanzar Electron. Electron se lo pasa a Nitro y Nitro al sidecar Python, de
// modo que toda la cadena escribe dentro del temporal.
//
// (Durante la revisión, ejecutar la suite de pytest en Windows escribió en el
// %APPDATA%\Contab real del usuario, incluidos los tests que BORRAN empresas.
// De ahí que esto sea lo primero del archivo y no un detalle.)
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { existsSync } from 'node:fs'
import { _electron as electron, type ElectronApplication, type Page } from '@playwright/test'

const RAIZ_SHELL = resolve(__dirname, '..')
const RAIZ_APPS = resolve(RAIZ_SHELL, '..')

export type AppEnMarcha = {
  app: ElectronApplication
  /** La ventana principal (la que sirve Nitro), no el splash. */
  ventana: Page
  /** Carpeta de datos aislada. Aquí acaban las empresas creadas por el test. */
  dataDir: string
  /** Credencial local que generó el shell, leída del preload. */
  token: string
  cerrar: () => Promise<void>
}

function pythonDelVenv(): string | undefined {
  const rel = process.platform === 'win32'
    ? ['Scripts', 'python.exe']
    : ['bin', 'python']
  const candidato = join(RAIZ_APPS, 'core', '.venv', ...rel)
  return existsSync(candidato) ? candidato : undefined
}

/** Qué falta para poder correr el smoke, o null si está todo. */
export function requisitosQueFaltan(): string | null {
  const salidaNuxt = join(RAIZ_APPS, 'desktop', '.output', 'server', 'index.mjs')
  if (!existsSync(salidaNuxt)) {
    return `falta el build de Nuxt (${salidaNuxt}). Corre: cd apps/desktop && npm run build`
  }
  if (!pythonDelVenv()) {
    return 'falta el venv de apps/core. Corre: cd apps/core && py -m venv .venv && .venv/Scripts/pip install -e ".[dev]"'
  }
  return null
}

export async function arrancarApp(): Promise<AppEnMarcha> {
  const dataDir = await mkdtemp(join(tmpdir(), 'contab-e2e-'))

  const app = await electron.launch({
    args: [RAIZ_SHELL],
    env: {
      ...process.env,
      // ── Aislamiento (ver cabecera) ──
      APPDATA: dataDir,
      XDG_DATA_HOME: dataDir,
      // Electron guarda aquí su propio estado; fuera del perfil del usuario.
      ELECTRON_ENABLE_LOGGING: '1',
      // En dev no hay sidecar de PyInstaller: Nitro usa este intérprete.
      CONTAB_PYTHON: pythonDelVenv()!,
    },
  })

  // El shell abre primero el splash y carga la ventana principal oculta. La
  // principal es la que apunta al servidor de Nitro.
  const ventana = await esperarVentanaPrincipal(app)
  await ventana.waitForLoadState('domcontentloaded')

  // La credencial que el preload inyectó (D-089). Que exista ya demuestra que
  // el puente sobrevive a `sandbox: true`.
  const token = await ventana.evaluate(() => (window as { contab?: { token?: string } }).contab?.token ?? '')

  return {
    app,
    ventana,
    dataDir,
    token,
    cerrar: async () => {
      await app.close().catch(() => {})
      await rm(dataDir, { recursive: true, force: true }).catch(() => {})
    },
  }
}

async function esperarVentanaPrincipal(app: ElectronApplication, msLimite = 90_000): Promise<Page> {
  const limite = Date.now() + msLimite
  while (Date.now() < limite) {
    for (const w of app.windows()) {
      // El splash es un file://; la ventana real la sirve Nitro por http.
      if (w.url().startsWith('http://127.0.0.1:')) return w
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  const urls = app.windows().map((w) => w.url())
  throw new Error(
    `La ventana principal no apareció en ${msLimite / 1000}s. Ventanas: ${JSON.stringify(urls)}`,
  )
}

/** Llama a un RPC desde la página, con la credencial que ya lleva el $fetch global. */
export async function rpc<T = unknown>(
  ventana: Page, metodo: string, params: Record<string, unknown> = {},
): Promise<T> {
  const res = await ventana.evaluate(
    async ({ metodo, params }) => {
      const r = await fetch('/api/rpc', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-contab-token': (window as { contab?: { token?: string } }).contab?.token ?? '',
        },
        body: JSON.stringify({ method: metodo, params }),
      })
      return { status: r.status, body: await r.json() }
    },
    { metodo, params },
  )
  const body = res.body as { ok: boolean; result?: T; error?: string }
  if (!body.ok) throw new Error(`${metodo}: ${body.error}`)
  return body.result as T
}
