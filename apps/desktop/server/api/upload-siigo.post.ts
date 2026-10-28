import { mkdir, writeFile } from 'node:fs/promises'
import { basename, resolve as joinPath } from 'node:path'
import { callSidecar } from '../utils/sidecar'
import {
  safeFilename,
  uniquePrefix,
  fallbackUploadsDir,
  checkUploadSize,
  purgarSubidasAntiguas,
} from '../utils/uploads'

type EmpresaInfo = { db_path: string; nit: string; default_folder?: string | null }

// Sube el Excel con el catálogo de Siigo de ESTA empresa (hoja «Impuestos» y
// hoja «Comprobantes», D-128) y devuelve la VISTA PREVIA (dry_run) para
// confirmar antes de aplicar. Cada empresa tiene el suyo: el contador manda
// una y carga las demás él mismo.
//
// Con accion=historicos el mismo archivo de carga de Siigo, con su hoja de
// históricos, siembra las reglas por tercero (D-130).
// Contrato único de la API (ver rpc.post.ts): SIEMPRE 200 con {ok:true|false}.
export default defineEventHandler(async (event) => {
  const parts = await readMultipartFormData(event)
  if (!parts) return { ok: false, error: 'No llegaron datos del formulario.' }

  const dbPathPart = parts.find((p) => p.name === 'db_path')
  const filePart = parts.find((p) => p.name === 'file')
  const accion = parts.find((p) => p.name === 'accion')?.data?.toString('utf-8').trim() || 'catalogo'
  if (!dbPathPart?.data) return { ok: false, error: 'Falta la empresa destino.' }
  if (!filePart?.data) return { ok: false, error: 'Falta el archivo Excel.' }

  const dbPath = dbPathPart.data.toString('utf-8').trim()
  if (!dbPath) return { ok: false, error: 'La empresa destino está vacía.' }

  const tooBig = checkUploadSize(filePart.data.length)
  if (tooBig) return { ok: false, error: tooBig }

  let targetDir: string
  try {
    const info = await callSidecar<EmpresaInfo>('open_empresa', { db_path: dbPath })
    const folder = (info.default_folder || '').trim()
    targetDir = folder
      ? joinPath(folder, 'siigo')
      : joinPath(fallbackUploadsDir(), basename(dbPath, '.db'), 'siigo')
  } catch (err) {
    const msg = (err instanceof Error ? err.message : String(err)).replace(/^Error:\s*/, '')
    return { ok: false, error: `No se pudo abrir la empresa: ${msg}` }
  }

  const fileName = `${uniquePrefix()}_${safeFilename(filePart.filename, 'siigo.xlsx')}`
  const savedPath = joinPath(targetDir, fileName)
  try {
    await mkdir(targetDir, { recursive: true })
    await writeFile(savedPath, filePart.data)
    void purgarSubidasAntiguas(targetDir)
  } catch (err) {
    return { ok: false, error: `No se pudo guardar el archivo en ${savedPath}: ${String(err)}` }
  }

  // accion=guardar solo deja el archivo y devuelve dónde quedó: la nómina usa
  // dos archivos (el Excel de nómina y el de carga), y el RPC se llama después.
  if (accion === 'guardar') return { ok: true, result: { saved: true }, saved_to: savedPath }

  try {
    const result = await callSidecar(accion === 'historicos' ? 'siigo_sembrar' : 'siigo_importar', {
      db_path: dbPath,
      source_path: savedPath,
      dry_run: true,
    })
    return { ok: true, result, saved_to: savedPath }
  } catch (err) {
    const msg = (err instanceof Error ? err.message : String(err)).replace(/^Error:\s*/, '')
    return { ok: false, error: msg }
  }
})
