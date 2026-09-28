import { dianBaseUrl, ensureDianService } from '../../../utils/dianSidecar'

// Baja de la DIAN el soporte oficial de cada documento del mes. Este camino del
// portal es público: no usa credenciales de nadie, solo el CUFE y el NIT.
export default defineEventHandler(async (event) => {
  await ensureDianService()
  return proxyRequest(event, `${dianBaseUrl()}/portal/soportes`)
})
