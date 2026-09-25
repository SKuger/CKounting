import { callSidecar } from '../utils/sidecar'

// Contrato único de la API (ver también upload-*.post.ts): SIEMPRE 200 con
// {ok:true|false}. Un error de dominio del sidecar ("el NIT del Excel no coincide…")
// no es un fallo de transporte: si se devuelve con status 500, `$fetch` lanza antes
// de que useRpc pueda leer el cuerpo y el usuario acaba viendo
// "FetchError: 500 Internal Server Error" en vez del mensaje real.
export default defineEventHandler(async (event) => {
  const body = await readBody<{ method?: string; params?: Record<string, unknown> }>(event)
  const method = body?.method
  if (!method || typeof method !== 'string') {
    return { ok: false, error: 'Petición inválida: falta el método.' }
  }
  try {
    const result = await callSidecar(method, body.params ?? {})
    return { ok: true, result }
  } catch (exc) {
    const message = (exc instanceof Error ? exc.message : String(exc)).replace(/^Error:\s*/, '')
    return { ok: false, error: message }
  }
})
