import { dianBaseUrl, ensureDianService } from '../../../utils/dianSidecar'

// Estado del vigía de citas DIAN (D-104): lo sondea la página /consulta-citas.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/citas/status`)
})
