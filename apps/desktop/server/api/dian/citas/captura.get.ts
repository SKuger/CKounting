import { dianBaseUrl, ensureDianService } from '../../../utils/dianSidecar'

// Captura PNG de la pantalla donde el vigía encontró cupo (o el CAPTCHA).
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/citas/captura`)
})
