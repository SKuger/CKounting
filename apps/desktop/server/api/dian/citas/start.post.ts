import { dianBaseUrl, ensureDianService } from '../../../utils/dianSidecar'

// Arranca la búsqueda de cita. Idempotente: si ya corre, el sidecar responde started=false.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/citas/start`)
})
