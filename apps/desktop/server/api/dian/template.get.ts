import { dianBaseUrl, ensureDianService } from '../../utils/dianSidecar'

// Proxies the upload template (plantilla_rut.xlsx) served by the sidecar's StaticFiles.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/static/plantilla_rut.xlsx`)
})
