import { dianBaseUrl, ensureDianService } from '../../../utils/dianSidecar'

// Catch-all download proxy. Forwards both shapes the sidecar exposes:
//   /api/dian/download/current/<file_id>     -> /download/current/<file_id>  (parcial, en curso)
//   /api/dian/download/resultados_<id>.xlsx  -> /download/<filename>         (final)
export default defineEventHandler(async (event) => {
  const path = getRouterParam(event, 'path')
  if (!path) {
    setResponseStatus(event, 400)
    return { ok: false, error: 'ruta de descarga vacía' }
  }
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/download/${path}`)
})
