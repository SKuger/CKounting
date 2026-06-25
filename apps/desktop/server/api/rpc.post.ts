import { callSidecar } from '../utils/sidecar'

export default defineEventHandler(async (event) => {
  const body = await readBody<{ method?: string; params?: Record<string, unknown> }>(event)
  const method = body?.method
  if (!method || typeof method !== 'string') {
    setResponseStatus(event, 400)
    return { ok: false, error: 'missing method' }
  }
  try {
    const result = await callSidecar(method, body.params ?? {})
    return { ok: true, result }
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc)
    setResponseStatus(event, 500)
    return { ok: false, error: message }
  }
})
