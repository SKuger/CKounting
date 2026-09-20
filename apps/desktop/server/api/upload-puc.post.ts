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

// Sube un dump de PUC, lo guarda, y devuelve la VISTA PREVIA (dry_run) para
// confirmar antes de aplicar. El bloqueo por NIT (D-070) ocurre en `puc_import`.
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

  // Guardar el dump en <default_folder>/puc/ (o en el fallback de uploads).
  let targetDir: string
  try {
    const info = await callSidecar<EmpresaInfo>('open_empresa', { db_path: dbPath })
    const folder = (info.default_folder || '').trim()
    targetDir = folder
      ? joinPath(folder, 'puc')
      : joinPath(fallbackUploadsDir(), basename(dbPath, '.db'), 'puc')
  } catch (err) {
    const msg = (err instanceof Error ? err.message : String(err)).replace(/^Error:\s*/, '')
    return { ok: false, error: `No se pudo abrir la empresa: ${msg}` }
  }

  const fileName = `${uniquePrefix()}_${safeFilename(filePart.filename, 'puc.xlsx')}`
  const savedPath = joinPath(targetDir, fileName)
  try {
    await mkdir(targetDir, { recursive: true })
    await writeFile(savedPath, filePart.data)
  } catch (err) {
    return { ok: false, error: `No se pudo guardar el archivo en ${savedPath}: ${String(err)}` }
  }

  // Vista previa (dry_run): parsea, valida el NIT (bloquea si no coincide) y cuenta
  // cuántas se agregarían/actualizarían — sin escribir aún.
  try {
    const result = await callSidecar('puc_import', {
      db_path: dbPath,
      source_path: savedPath,
      dry_run: true,
    })
    return { ok: true, result, saved_to: savedPath }
  } catch (err) {
    await unlink(savedPath).catch(() => {})
    const msg = (err instanceof Error ? err.message : String(err)).replace(/^Error:\s*/, '')
    return { ok: false, error: msg }
  }
})
