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
  if (!name) return 'puc.xlsx'
  return name.replace(/[\\/:*?"<>|]/g, '_')
}

function timestamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    [d.getFullYear(), pad(d.getMonth() + 1), pad(d.getDate())].join('') +
    '-' +
    [pad(d.getHours()), pad(d.getMinutes()), pad(d.getSeconds())].join('')
  )
}

function fallbackUploadsDir(): string {
  return joinPath(homedir(), '.local', 'share', 'Contab', 'uploads')
}

// Sube un dump de PUC, lo guarda, y devuelve la VISTA PREVIA (dry_run) para
// confirmar antes de aplicar. El bloqueo por NIT (D-070) ocurre en `puc_import`.
export default defineEventHandler(async (event) => {
  const parts = await readMultipartFormData(event)
  if (!parts) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'No llegaron datos del formulario.' }
  }

  const dbPathPart = parts.find((p) => p.name === 'db_path')
  const filePart = parts.find((p) => p.name === 'file')
  if (!dbPathPart?.data) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'Falta la empresa destino.' }
  }
  if (!filePart?.data) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'Falta el archivo Excel.' }
  }
  const dbPath = dbPathPart.data.toString('utf-8').trim()
  if (!dbPath) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'La empresa destino está vacía.' }
  }

  // Guardar el dump en <default_folder>/puc/ (o en el fallback de uploads).
  let targetDir: string
  try {
    const info = await callSidecar<EmpresaInfo>('open_empresa', { db_path: dbPath })
    const folder = (info.default_folder || '').trim()
    targetDir = folder
      ? joinPath(folder, 'puc')
      : joinPath(fallbackUploadsDir(), basename(dbPath, '.db'), 'puc')
  } catch (err) {
    setResponseStatus(event, 500)
    return { ok: false, error: `No se pudo abrir la empresa: ${String(err)}` }
  }

  // Sufijo aleatorio: evita que dos subidas en el mismo segundo se sobreescriban.
  const rand = Math.random().toString(36).slice(2, 8)
  const fileName = `${timestamp()}_${rand}_${safeFilename(filePart.filename)}`
  const savedPath = joinPath(targetDir, fileName)
  try {
    await mkdir(targetDir, { recursive: true })
    await writeFile(savedPath, filePart.data)
  } catch (err) {
    setResponseStatus(event, 500)
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
    setResponseStatus(event, 500)
    return { ok: false, error: String(err) }
  }
})
