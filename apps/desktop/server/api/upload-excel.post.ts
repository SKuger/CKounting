import { mkdir, writeFile, unlink } from 'node:fs/promises'
import { basename, resolve as joinPath } from 'node:path'
import { callSidecar } from '../utils/sidecar'
import {
  safeFilename,
  uniquePrefix,
  fallbackUploadsDir,
  checkUploadSize,
} from '../utils/uploads'

type EmpresaInfo = {
  db_path: string
  nit: string
  razon_social: string
  default_folder?: string | null
}

// Contrato único de la API (ver rpc.post.ts): SIEMPRE 200 con {ok:true|false}.
export default defineEventHandler(async (event) => {
  const parts = await readMultipartFormData(event)
  if (!parts) return { ok: false, error: 'No llegaron datos del formulario.' }

  const dbPathPart = parts.find((p) => p.name === 'db_path')
  const filePart = parts.find((p) => p.name === 'file')

  if (!dbPathPart?.data) return { ok: false, error: 'Falta la empresa destino.' }
  if (!filePart?.data) return { ok: false, error: 'Falta el archivo Excel.' }

  const dbPath = dbPathPart.data.toString('utf-8').trim()
  if (!dbPath) return { ok: false, error: 'La empresa destino está vacía.' }

  const tooBig = checkUploadSize(filePart.data.length)
  if (tooBig) return { ok: false, error: tooBig }

  // El modelo por meses exige el periodo destino: el Excel se carga DENTRO de un mes.
  const periodoPart = parts.find((p) => p.name === 'periodo')
  const periodo = periodoPart?.data ? periodoPart.data.toString('utf-8').trim() : ''
  if (!periodo) return { ok: false, error: 'Falta el mes (periodo) destino.' }

  // Look up the empresa's default_folder to decide where to save the upload.
  let targetDir: string
  try {
    const info = await callSidecar<EmpresaInfo>('open_empresa', { db_path: dbPath })
    const folder = (info.default_folder || '').trim()
    targetDir = folder
      ? joinPath(folder, 'imports')
      : joinPath(fallbackUploadsDir(), basename(dbPath, '.db'))
  } catch (err) {
    const msg = (err instanceof Error ? err.message : String(err)).replace(/^Error:\s*/, '')
    return { ok: false, error: `No se pudo abrir la empresa: ${msg}` }
  }

  const fileName = `${uniquePrefix()}_${safeFilename(filePart.filename, 'import.xlsx')}`
  const savedPath = joinPath(targetDir, fileName)

  try {
    await mkdir(targetDir, { recursive: true })
    await writeFile(savedPath, filePart.data)
  } catch (err) {
    return { ok: false, error: `No se pudo guardar el archivo en ${savedPath}: ${String(err)}` }
  }

  try {
    const result = await callSidecar('import_excel', {
      db_path: dbPath,
      source_path: savedPath,
      periodo,
    })
    return { ok: true, result, saved_to: savedPath }
  } catch (err) {
    // La importación falló → el archivo guardado es basura: no dejarlo acumulándose.
    await unlink(savedPath).catch(() => {})
    const msg = (err instanceof Error ? err.message : String(err)).replace(/^Error:\s*/, '')
    return { ok: false, error: msg }
  }
})
