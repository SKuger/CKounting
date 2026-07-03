// Recibe el .xlsx (NIT + DV), lo guarda en un temporal y pide al sidecar Python
// que lo parsee → devuelve las filas normalizadas. No toca ninguna empresa: la
// consulta de inconsistencias es independiente del catálogo.
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve as joinPath } from 'node:path'
import { tmpdir } from 'node:os'
import { callSidecar } from '../../utils/sidecar'

function safeFilename(name: string | undefined): string {
  if (!name) return 'inconsistencias.xlsx'
  return name.replace(/[\\/:*?"<>|]/g, '_')
}

function stamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

export default defineEventHandler(async (event) => {
  const parts = await readMultipartFormData(event)
  if (!parts) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'no form data' }
  }
  const filePart = parts.find((p) => p.name === 'file')
  if (!filePart?.data) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'Falta el archivo.' }
  }
  const name = safeFilename(filePart.filename)
  if (!name.toLowerCase().endsWith('.xlsx')) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'Solo se permiten archivos Excel (.xlsx).' }
  }

  const dir = joinPath(tmpdir(), 'contab-inconsistencias')
  await mkdir(dir, { recursive: true })
  const path = joinPath(dir, `${stamp()}-${name}`)
  await writeFile(path, filePart.data)

  try {
    const parsed = await callSidecar<{ rows: unknown[]; total: number; detected: unknown }>(
      'parse_nit_dv',
      { source_path: path },
    )
    return { ok: true, path, ...parsed }
  } catch (err) {
    setResponseStatus(event, 500)
    return { ok: false, error: err instanceof Error ? err.message : String(err) }
  }
})
