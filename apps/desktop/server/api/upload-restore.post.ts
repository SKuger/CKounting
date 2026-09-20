import { mkdir, unlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { callSidecar } from '../utils/sidecar'
import { safeFilename, uniquePrefix, checkUploadSize } from '../utils/uploads'

// Contrato único de la API (ver rpc.post.ts): SIEMPRE 200 con {ok:true|false}.
export default defineEventHandler(async (event) => {
  const parts = await readMultipartFormData(event)
  if (!parts) return { ok: false, error: 'No llegaron datos del formulario.' }

  const filePart = parts.find((p) => p.name === 'file')
  if (!filePart?.data) return { ok: false, error: 'Falta el archivo de backup.' }

  const tooBig = checkUploadSize(filePart.data.length)
  if (tooBig) return { ok: false, error: tooBig }

  const stagingDir = join(tmpdir(), 'contab-restore')
  await mkdir(stagingDir, { recursive: true })

  const safeName = safeFilename(filePart.filename, 'empresa.contab.zip')
  const stagedPath = join(stagingDir, `${uniquePrefix()}_${safeName}`)
  await writeFile(stagedPath, filePart.data)

  try {
    const result = await callSidecar('restore_empresa', { zip_path: stagedPath })
    return { ok: true, result }
  } catch (err) {
    const msg = (err instanceof Error ? err.message : String(err)).replace(/^Error:\s*/, '')
    return { ok: false, error: msg }
  } finally {
    // Clean up the staged file regardless of success.
    try { await unlink(stagedPath) } catch { /* ignore */ }
  }
})
