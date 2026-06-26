import { DIAN_PORT, ensureDianService } from '../../utils/dianSidecar'

// Ensures the DIAN sidecar is running and hands the client the port it should
// open its WebSocket against (the WS connects straight to localhost; uploads
// and downloads go through the proxy routes to keep a single HTTP origin).
export default defineEventHandler(async (event) => {
  try {
    await ensureDianService()
    return { ok: true, port: DIAN_PORT }
  } catch (err) {
    setResponseStatus(event, 503)
    return { ok: false, error: String(err) }
  }
})
