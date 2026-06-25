import { mkdir, unlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { callSidecar } from '../utils/sidecar'

export default defineEventHandler(async (event) => {
  const parts = await readMultipartFormData(event)
  if (!parts) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'no form data' }
  }

  const filePart = parts.find((p) => p.name === 'file')
  if (!filePart?.data) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'missing file' }
  }

  const stagingDir = join(tmpdir(), 'contab-restore')
  await mkdir(stagingDir, { recursive: true })

  const stamp = Date.now().toString(36)
  const safeName = (filePart.filename || 'empresa.contab.zip').replace(/[\\/:*?"<>|]/g, '_')
  const stagedPath = join(stagingDir, `${stamp}_${safeName}`)
  await writeFile(stagedPath, filePart.data)

  try {
    const result = await callSidecar('restore_empresa', { zip_path: stagedPath })
    return { ok: true, result }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    setResponseStatus(event, 500)
    return { ok: false, error: msg }
  } finally {
    // Clean up the staged file regardless of success.
    try { await unlink(stagedPath) } catch { /* ignore */ }
  }
})
