import { dianBaseUrl, ensureDianService } from '../../../utils/dianSidecar'

// Detiene la búsqueda y cierra la ventana del navegador del vigía.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/citas/stop`)
})
