import { dianBaseUrl, ensureDianService } from '../../../../../utils/dianSidecar'

// Detiene una corrida de soportes. Lo ya bajado se queda en la carpeta, y la
// siguiente corrida lo salta: el nombre de cada archivo es su CUFE.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  const id = getRouterParam(event, 'id')
  return proxyRequest(event, `${dianBaseUrl()}/portal/soportes/detener/${id}`)
})
