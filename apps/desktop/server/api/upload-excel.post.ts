import { mkdir, writeFile } from 'node:fs/promises'
import { basename, resolve as joinPath } from 'node:path'
import { homedir } from 'node:os'
import { callSidecar } from '../utils/sidecar'

type EmpresaInfo = {
  db_path: string
  nit: string
  razon_social: string
  default_folder?: string | null
}

function safeFilename(name: string | undefined): string {
  if (!name) return 'import.xlsx'
  return name.replace(/[\\/:*?"<>|]/g, '_')
}

function timestamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return [
    d.getFullYear(),
    pad(d.getMonth() + 1),
    pad(d.getDate()),
  ].join('') + '-' + [
    pad(d.getHours()),
    pad(d.getMinutes()),
    pad(d.getSeconds()),
  ].join('')
}

function fallbackUploadsDir(): string {
  return joinPath(homedir(), '.local', 'share', 'Contab', 'uploads')
}

export default defineEventHandler(async (event) => {
  const parts = await readMultipartFormData(event)
  if (!parts) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'no form data' }
  }

  const dbPathPart = parts.find((p) => p.name === 'db_path')
  const filePart = parts.find((p) => p.name === 'file')

  if (!dbPathPart?.data) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'missing db_path' }
  }
  if (!filePart?.data) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'missing file' }
  }

  const dbPath = dbPathPart.data.toString('utf-8').trim()
  if (!dbPath) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'empty db_path' }
  }

  // El modelo por meses exige el periodo destino: el Excel se carga DENTRO de un mes.
  const periodoPart = parts.find((p) => p.name === 'periodo')
  const periodo = periodoPart?.data ? periodoPart.data.toString('utf-8').trim() : ''
  if (!periodo) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'falta el mes (periodo) destino' }
  }

  // Look up the empresa's default_folder to decide where to save the upload.
  let targetDir: string
  try {
    const info = await callSidecar<EmpresaInfo>('open_empresa', { db_path: dbPath })
    const folder = (info.default_folder || '').trim()
    targetDir = folder
      ? joinPath(folder, 'imports')
      : joinPath(fallbackUploadsDir(), basename(dbPath, '.db'))
  } catch (err) {
    setResponseStatus(event, 500)
    return { ok: false, error: `open_empresa failed: ${String(err)}` }
  }

  const fileName = `${timestamp()}_${safeFilename(filePart.filename)}`
  const savedPath = joinPath(targetDir, fileName)

  try {
    await mkdir(targetDir, { recursive: true })
    await writeFile(savedPath, filePart.data)
  } catch (err) {
    setResponseStatus(event, 500)
    return {
      ok: false,
      error: `No se pudo guardar el archivo en ${savedPath}: ${String(err)}`,
    }
  }

  try {
    const result = await callSidecar('import_excel', {
      db_path: dbPath,
      source_path: savedPath,
      periodo,
    })
    return { ok: true, result, saved_to: savedPath }
  } catch (err) {
    setResponseStatus(event, 500)
    return { ok: false, error: String(err) }
  }
})
