import { dianBaseUrl, ensureDianService } from '../../utils/dianSidecar'

// Streams the multipart upload (file + client_id) straight to the FastAPI
// sidecar's /upload. proxyRequest preserves the multipart body and boundary.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/upload`)
})
