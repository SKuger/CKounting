// Autenticación local del servidor Nitro (D-089).
//
// El problema: `/api/rpc` es un ejecutor universal — recibe `db_path`,
// `source_path` y `output_path` del cliente sin validar — y no pide credencial
// alguna. El puerto es aleatorio y solo escucha en 127.0.0.1, lo cual descarta la
// red, pero NO descarta a otro proceso de la misma máquina ni a una página del
// navegador barriendo puertos de localhost: quien lo alcance puede leer, escribir
// y borrar empresas.
//
// La solución es un secreto por arranque: el shell de Electron lo genera, se lo
// pasa a Nitro por env, y Nitro lo inyecta en la página. Cada petición lo lleva
// de vuelta. Un proceso ajeno no puede leerlo porque nunca toca el HTML.
//
// En DESARROLLO (sin CONTAB_TOKEN en el entorno) no se exige nada: `npm run dev`
// tiene que seguir funcionando con curl y con el navegador suelto.

import { createHash, timingSafeEqual } from 'node:crypto'

export const CABECERA_TOKEN = 'x-contab-token'

export function tokenEsperado(): string | null {
  const t = process.env.CONTAB_TOKEN
  return t && t.length >= 16 ? t : null
}

/** true cuando hay token configurado, es decir, en la app empaquetada. */
export function autenticacionActiva(): boolean {
  return tokenEsperado() !== null
}

function igualdadConstante(a: string, b: string): boolean {
  // Se comparan los digests: timingSafeEqual exige la misma longitud, y hashear
  // evita además filtrar el tamaño del secreto por el tiempo de respuesta.
  const ha = createHash('sha256').update(a).digest()
  const hb = createHash('sha256').update(b).digest()
  return timingSafeEqual(ha, hb)
}

/**
 * Comprueba la credencial recibida.
 * Devuelve `null` si pasa, o el mensaje de error si no.
 *
 * Recibe el valor de la cabecera, no el evento de h3: así la regla se puede
 * probar sin montar un servidor ni depender de los auto-imports de Nitro.
 */
export function comprobarToken(recibido: string | undefined): string | null {
  const esperado = tokenEsperado()
  if (!esperado) return null // modo desarrollo

  if (!recibido) return 'Petición sin credencial local.'
  if (!igualdadConstante(recibido, esperado)) return 'Credencial local inválida.'
  return null
}
