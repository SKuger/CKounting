import { dianBaseUrl, ensureDianService } from '../../utils/dianSidecar'

// Reports whether a human-driven Chrome (remote debugging on :9222) is available
// for the scraper to attach to, vs. falling back to fully automatic mode.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/browser-mode-status`)
})
