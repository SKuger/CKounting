// Exige la credencial local en TODA la API (D-089).
//
// Va como middleware y no endpoint por endpoint a propósito: así un endpoint
// nuevo queda protegido por omisión en vez de por acordarse.
import { comprobarToken, autenticacionActiva, CABECERA_TOKEN } from '../utils/auth'

// `/api/version` queda fuera: no toca datos y la necesita el arranque de la UI.
const ABIERTAS = new Set(['/api/version'])

export default defineEventHandler((event) => {
  if (!autenticacionActiva()) return // desarrollo: sin token configurado

  const ruta = getRequestURL(event).pathname
  if (!ruta.startsWith('/api/')) return
  if (ABIERTAS.has(ruta)) return

  const error = comprobarToken(getHeader(event, CABECERA_TOKEN))
  if (error) {
    // 401 de verdad: esto SÍ es un fallo de transporte/autorización, no un error
    // de dominio, así que aquí el código HTTP es el correcto (cf. D-071).
    throw createError({ statusCode: 401, statusMessage: error })
  }
})
