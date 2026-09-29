import { dianBaseUrl, ensureDianService } from '../../../utils/dianSidecar'

// Arranca la descarga del listado del mes desde el portal de la DIAN.
// El enlace de acceso viaja en el cuerpo y NO se guarda en ninguna parte: ni acá,
// ni en el sidecar, ni en la base. Es una llave a la cuenta DIAN del cliente.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/portal/descargar`)
})
