// Helpers compartidos por los endpoints de subida (upload-excel, upload-puc,
// consulta-inconsistencias/upload). Estaban copiados literalmente en cada uno y ya
// habían divergido: solo upload-puc tenía el sufijo anti-colisión.

import { homedir } from 'node:os'
import { resolve as joinPath } from 'node:path'

// Nombres reservados de Windows: un archivo llamado CON.xlsx no se puede crear.
const WIN_RESERVED = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)/i

/** Nombre de archivo seguro en cualquier SO. Nunca devuelve algo con separadores. */
export function safeFilename(name: string | undefined, fallback = 'archivo.xlsx'): string {
  if (!name) return fallback
  let clean = name
    .replace(/[\\/]/g, '_')          // separadores de ruta
    .replace(/[:*?"<>|]/g, '_')      // ilegales en Windows
    // eslint-disable-next-line no-control-regex
    .replace(/[\x00-\x1f]/g, '')     // control chars
    .replace(/^\.+/, '')             // '..' y ocultos
    .replace(/[. ]+$/, '')           // Windows no admite puntos/espacios finales
    .trim()
  if (WIN_RESERVED.test(clean)) clean = `_${clean}`
  return clean || fallback
}

/** Marca temporal + sufijo aleatorio: dos subidas en el mismo segundo no se pisan. */
export function uniquePrefix(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const stamp =
    `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
    `-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  return `${stamp}_${Math.random().toString(36).slice(2, 8)}`
}

/**
 * Carpeta de datos de Contab, con el MISMO criterio que apps/core/contab_core/paths.py.
 *
 * Antes estaba hardcodeado `~/.local/share/Contab` (XDG, Linux) en un producto de
 * Windows: Node escribía en un sitio y Python leía en otro (%APPDATA%\Contab).
 */
export function contabDataDir(): string {
  if (process.platform === 'win32') {
    return joinPath(process.env.APPDATA || joinPath(homedir(), 'AppData', 'Roaming'), 'Contab')
  }
  if (process.platform === 'darwin') {
    return joinPath(homedir(), 'Library', 'Application Support', 'Contab')
  }
  return joinPath(process.env.XDG_DATA_HOME || joinPath(homedir(), '.local', 'share'), 'Contab')
}

export function fallbackUploadsDir(): string {
  return joinPath(contabDataDir(), 'uploads')
}

/** Tamaño máximo de una subida. readMultipartFormData bufferea en memoria. */
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024

export function checkUploadSize(bytes: number): string | null {
  if (bytes > MAX_UPLOAD_BYTES) {
    const mb = (bytes / 1024 / 1024).toFixed(1)
    return `El archivo pesa ${mb} MB y el máximo son ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.`
  }
  return null
}
