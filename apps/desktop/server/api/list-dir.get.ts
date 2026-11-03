import { readdir, stat } from 'node:fs/promises'
import { resolve, dirname, sep } from 'node:path'
import { homedir } from 'node:os'

type Entry = { name: string; is_dir: true }

export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const showHidden = query.show_hidden === '1' || query.show_hidden === 'true'

  let target = String(query.path || '').trim()
  if (!target) target = homedir()
  target = resolve(target)

  // Una carpeta que se borró no deja el selector sin salida (el contador,
  // 2026-11-03): se abre la más cercana que sí existe y se dice cuál faltaba.
  const pedido = target
  for (;;) {
    try {
      if ((await stat(target)).isDirectory()) break
    } catch { /* no existe: se sube */ }
    const arriba = dirname(target)
    if (arriba === target) {
      target = homedir()
      break
    }
    target = arriba
  }
  const aviso = target !== pedido
    ? `La carpeta ${pedido} ya no existe. Se muestra la más cercana; elige aquí dónde guardar.`
    : undefined

  let names: string[]
  try {
    names = await readdir(target)
  } catch (err) {
    setResponseStatus(event, 403)
    return { ok: false, error: `Sin permiso para listar ${target}: ${String(err)}` }
  }

  const entries: Entry[] = []
  for (const name of names) {
    if (!showHidden && name.startsWith('.')) continue
    try {
      const fullPath = resolve(target, name)
      const subStat = await stat(fullPath)
      if (subStat.isDirectory()) entries.push({ name, is_dir: true })
    } catch {
      // Skip inaccessible entries silently.
    }
  }

  entries.sort((a, b) => a.name.localeCompare(b.name, 'es', { sensitivity: 'base' }))

  const parent = dirname(target)

  return {
    ok: true,
    path: target,
    parent: parent !== target ? parent : null,
    separator: sep,
    home: homedir(),
    entries,
    aviso,
  }
})
