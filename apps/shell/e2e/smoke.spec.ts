// Smoke end-to-end de la aplicación REAL (#20).
//
// Qué cubre que no cubría nada: que Electron arranca, levanta Nitro, Nitro
// levanta el sidecar PYTHON (el arreglo de la ruta del venv en Windows, #8),
// el preload entrega la credencial pese a `sandbox: true` (#32) y la API la
// exige de verdad. Y luego el flujo que de verdad usa el contador: crear
// empresa, subir el Excel, validar, y borrar viendo que va a la papelera (#13).
import { readdir, readFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { existsSync } from 'node:fs'
import { test, expect } from '@playwright/test'

import { arrancarApp, requisitosQueFaltan, rpc, type AppEnMarcha } from './app'

const MUESTRA_EXCEL = resolve(__dirname, '..', '..', '..', 'docs', 'samples', 'Ejemplo_LaDian.xlsx')

const falta = requisitosQueFaltan()
test.skip(falta !== null, falta ?? '')

let app: AppEnMarcha

test.beforeAll(async () => { app = await arrancarApp() })
test.afterAll(async () => { await app?.cerrar() })

test('la cadena completa arranca: Electron → Nitro → sidecar Python', async () => {
  // Que la ventana exista ya prueba que Nitro respondió. Que el ping conteste
  // prueba que el sidecar Python arrancó — lo que NO pasaba en Windows antes
  // del #8, porque se buscaba `.venv/bin/python` y se caía a `python3`.
  const pong = await rpc<{ pong: boolean }>(app.ventana, 'ping')
  expect(pong.pong).toBe(true)
})

test('el preload entrega la credencial local pese al sandbox', async () => {
  // #31 puso `sandbox: true`; #32 hace que la API exija credencial. Si el puente
  // se hubiera roto con el sandbox, la aplicación instalada quedaría inservible
  // y ni vitest ni pytest lo verían.
  expect(app.token).toMatch(/^[0-9a-f]{64}$/)
})

test('la API rechaza una petición sin credencial', async () => {
  const res = await app.ventana.evaluate(async () => {
    const r = await fetch('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method: 'ping', params: {} }),
    })
    return r.status
  })
  expect(res).toBe(401)
})

test('las dependencias externas están y se pueden comprobar', async () => {
  // #16: si falta Poppler hay que poder DECIRLO, no marcar el mes entero como
  // «sin soporte».
  const dep = await rpc<{ ok: boolean; pdftotext: { disponible: boolean; error: string | null } }>(
    app.ventana, 'check_dependencies',
  )
  expect(dep.pdftotext.disponible, dep.pdftotext.error ?? '').toBe(true)
})

test('flujo real: crear empresa → subir Excel → validar', async () => {
  const empresa = await rpc<{ db_path: string; nit: string }>(app.ventana, 'create_empresa', {
    nit: '900181831', razon_social: 'REAL Seguros E2E',
  })
  expect(empresa.nit).toBe('900181831')

  // La empresa se creó DENTRO del temporal, no en los datos del usuario.
  expect(empresa.db_path.toLowerCase()).toContain(app.dataDir.toLowerCase())

  // #11: crearla otra vez tiene que fallar con un mensaje claro, no fingir éxito.
  await expect(
    rpc(app.ventana, 'create_empresa', { nit: '900181831', razon_social: 'REAL Seguros E2E' }),
  ).rejects.toThrow(/[Yy]a existe/)

  await rpc(app.ventana, 'create_periodo', { db_path: empresa.db_path, periodo: '2024-02' })

  // Subida real por el endpoint multipart, con la credencial del preload.
  const xlsxBase64 = (await readFile(MUESTRA_EXCEL)).toString('base64')
  const subida = await app.ventana.evaluate(
    async ({ dbPath, b64 }) => {
      const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
      const fd = new FormData()
      fd.set('db_path', dbPath)
      fd.set('periodo', '2024-02')
      fd.set('file', new Blob([bin]), 'Ejemplo_LaDian.xlsx')
      const r = await fetch('/api/upload-excel', {
        method: 'POST',
        headers: { 'x-contab-token': (window as { contab?: { token?: string } }).contab?.token ?? '' },
        body: fd,
      })
      return r.json()
    },
    { dbPath: empresa.db_path, b64: xlsxBase64 },
  )
  expect(subida.ok, subida.error).toBe(true)

  const cargas = await rpc<{ id: number }[]>(app.ventana, 'list_loads', { db_path: empresa.db_path })
  expect(cargas.length).toBe(1)

  // Validar como TRABAJO EN SEGUNDO PLANO (#6): devuelve job_id al instante.
  const job = await rpc<{ job_id: string; status: string }>(app.ventana, 'run_validations_async', {
    db_path: empresa.db_path, load_id: cargas[0]!.id,
  })
  expect(job.status).toBe('running')

  const resultado = await esperarJob(app.ventana, job.job_id)
  expect(resultado.total_rows).toBe(11)
  expect(resultado.failing_rows).toBeGreaterThan(0) // la muestra trae filas sin soporte

  // #23: el resumen se agrega EN SQL, sin cargar el lote a memoria.
  const resumen = await rpc<{ periodos: { periodo: string; documentos: number }[] }>(
    app.ventana, 'resumen_periodos', { db_path: empresa.db_path },
  )
  expect(resumen.periodos[0]?.periodo).toBe('2024-02')
  expect(resumen.periodos[0]?.documentos).toBe(11)
})

test('borrar una empresa la manda a la papelera, no al vacío', async () => {
  const empresa = await rpc<{ db_path: string }>(app.ventana, 'create_empresa', {
    nit: '830126625', razon_social: 'Para Borrar E2E',
  })
  expect(existsSync(empresa.db_path)).toBe(true)

  // #13: con el NIT equivocado no se borra nada.
  await expect(
    rpc(app.ventana, 'delete_empresa', { db_path: empresa.db_path, confirm_nit: '123' }),
  ).rejects.toThrow(/no coincide/)
  expect(existsSync(empresa.db_path)).toBe(true)

  const res = await rpc<{ papelera: string; dias_retencion: number }>(
    app.ventana, 'delete_empresa', { db_path: empresa.db_path, confirm_nit: '830126625' },
  )
  expect(existsSync(empresa.db_path)).toBe(false)
  expect(existsSync(res.papelera)).toBe(true)
  expect(res.dias_retencion).toBe(30)

  // Y se puede recuperar.
  const enPapelera = await rpc<{ archivo: string; nit: string }[]>(app.ventana, 'papelera_list')
  const suya = enPapelera.find((e) => e.nit === '830126625')
  expect(suya).toBeTruthy()

  const vuelta = await rpc<{ db_path: string }>(app.ventana, 'papelera_restore', {
    archivo: suya!.archivo,
  })
  expect(existsSync(vuelta.db_path)).toBe(true)
})

test('los datos del usuario no se tocan: todo vive en el temporal', async () => {
  // La comprobación que más importa de este archivo.
  const empresas = await readdir(join(app.dataDir, 'Contab', 'empresas'))
  expect(empresas.length).toBeGreaterThan(0)
  expect(empresas.some((f) => f.includes('900181831'))).toBe(true)
})

async function esperarJob(
  ventana: AppEnMarcha['ventana'], jobId: string, msLimite = 90_000,
): Promise<{ total_rows: number; failing_rows: number }> {
  const limite = Date.now() + msLimite
  while (Date.now() < limite) {
    const estado = await rpc<{
      status: string; error: string | null; result: { total_rows: number; failing_rows: number }
    }>(ventana, 'job_status', { job_id: jobId })
    if (estado.status === 'done') return estado.result
    if (estado.status !== 'running') throw new Error(`El trabajo acabó en ${estado.status}: ${estado.error}`)
    await new Promise((r) => setTimeout(r, 400))
  }
  throw new Error('El trabajo no terminó a tiempo')
}
