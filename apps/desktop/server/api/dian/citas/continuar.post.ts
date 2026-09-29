import { dianBaseUrl, ensureDianService } from '../../../utils/dianSidecar'

// Reanuda la búsqueda después de un cupo encontrado. Mientras está en pausa, la
// ventana del navegador se queda en esa pantalla: el bot no vuelve a navegar.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/citas/continuar`)
})
