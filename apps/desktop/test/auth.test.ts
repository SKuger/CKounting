// Autenticación local de la API (#32, D-089).
import { describe, it, expect, vi, afterEach } from 'vitest'

import {
  tokenEsperado,
  autenticacionActiva,
  comprobarToken,
  CABECERA_TOKEN,
} from '../server/utils/auth'

const TOKEN = 'a'.repeat(64)

afterEach(() => vi.unstubAllEnvs())

describe('autenticación local', () => {
  it('está DESACTIVADA sin CONTAB_TOKEN, para que npm run dev siga funcionando', () => {
    vi.stubEnv('CONTAB_TOKEN', '')
    expect(autenticacionActiva()).toBe(false)
    expect(tokenEsperado()).toBeNull()
  })

  it('se activa cuando el shell inyecta el secreto', () => {
    vi.stubEnv('CONTAB_TOKEN', TOKEN)
    expect(autenticacionActiva()).toBe(true)
    expect(tokenEsperado()).toBe(TOKEN)
  })

  it('ignora un token demasiado corto en vez de dar una falsa sensación de seguridad', () => {
    vi.stubEnv('CONTAB_TOKEN', 'corto')
    expect(autenticacionActiva()).toBe(false)
  })

  it('la cabecera es la que espera el cliente', () => {
    expect(CABECERA_TOKEN).toBe('x-contab-token')
  })
})

describe('comprobarToken', () => {
  it('deja pasar cuando no hay autenticación configurada', () => {
    vi.stubEnv('CONTAB_TOKEN', '')
    expect(comprobarToken(undefined)).toBeNull()
  })

  it('rechaza una petición sin credencial', () => {
    vi.stubEnv('CONTAB_TOKEN', TOKEN)
    expect(comprobarToken(undefined)).toContain('sin credencial')
  })

  it('rechaza una credencial equivocada', () => {
    vi.stubEnv('CONTAB_TOKEN', TOKEN)
    expect(comprobarToken('b'.repeat(64))).toContain('inválida')
  })

  it('rechaza una credencial de otra longitud sin reventar', () => {
    // timingSafeEqual exige longitudes iguales: por eso se comparan digests.
    vi.stubEnv('CONTAB_TOKEN', TOKEN)
    expect(comprobarToken('x')).toContain('inválida')
  })

  it('acepta la credencial correcta', () => {
    vi.stubEnv('CONTAB_TOKEN', TOKEN)
    expect(comprobarToken(TOKEN)).toBeNull()
  })
})
