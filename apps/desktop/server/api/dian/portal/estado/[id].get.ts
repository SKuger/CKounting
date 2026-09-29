import { dianBaseUrl, ensureDianService } from '../../../../utils/dianSidecar'

// Estado de una descarga en curso: la DIAN genera el listado de forma asíncrona.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  const id = getRouterParam(event, 'id')
  return proxyRequest(event, `${dianBaseUrl()}/portal/estado/${id}`)
})
