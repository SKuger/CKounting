// Recibe el .xlsx (NIT + DV), lo guarda en un temporal y pide al sidecar Python
// que lo parsee → devuelve las filas normalizadas. No toca ninguna empresa: la
// consulta de inconsistencias es independiente del catálogo.
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve as joinPath } from 'node:path'
import { tmpdir } from 'node:os'
import { callSidecar } from '../../utils/sidecar'
import { safeFilename, uniquePrefix, checkUploadSize } from '../../utils/uploads'

// Contrato único de la API (ver rpc.post.ts): SIEMPRE 200 con {ok:true|false}.
export default defineEventHandler(async (event) => {
  const parts = await readMultipartFormData(event)
  if (!parts) return { ok: false, error: 'No llegaron datos del formulario.' }
  const filePart = parts.find((p) => p.name === 'file')
  if (!filePart?.data) return { ok: false, error: 'Falta el archivo.' }

  const tooBig = checkUploadSize(filePart.data.length)
  if (tooBig) return { ok: false, error: tooBig }

  const name = safeFilename(filePart.filename, 'inconsistencias.xlsx')
  if (!name.toLowerCase().endsWith('.xlsx')) {
    return { ok: false, error: 'Solo se permiten archivos Excel (.xlsx).' }
  }

  const dir = joinPath(tmpdir(), 'contab-inconsistencias')
  await mkdir(dir, { recursive: true })
  const path = joinPath(dir, `${uniquePrefix()}-${name}`)
  await writeFile(path, filePart.data)

  try {
    const parsed = await callSidecar<{ rows: unknown[]; total: number; detected: unknown }>(
      'parse_nit_dv',
      { source_path: path },
    )
    return { ok: true, path, ...parsed }
  } catch (err) {
    const msg = (err instanceof Error ? err.message : String(err)).replace(/^Error:\s*/, '')
    return { ok: false, error: msg }
  }
})
