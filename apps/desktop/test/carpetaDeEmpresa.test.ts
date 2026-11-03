import { describe, expect, it } from 'vitest'
import { carpetaDeEmpresa } from '../app/composables/useExportarFaltantes'

describe('carpetaDeEmpresa', () => {
  it('sube un nivel cuando la guardada es la de un mes', () => {
    expect(carpetaDeEmpresa('C:\\CARLOS\\ALAGUNA\\2026-10')).toBe('C:\\CARLOS\\ALAGUNA')
    expect(carpetaDeEmpresa('C:\\CARLOS\\ALAGUNA\\2026-10\\')).toBe('C:\\CARLOS\\ALAGUNA')
    expect(carpetaDeEmpresa('/home/c/ALAGUNA/2026-09')).toBe('/home/c/ALAGUNA')
  })

  it('deja quieta la carpeta de una empresa', () => {
    expect(carpetaDeEmpresa('C:\\CARLOS\\ALAGUNA')).toBe('C:\\CARLOS\\ALAGUNA')
    expect(carpetaDeEmpresa('C:\\CARLOS\\2026-10 viejo')).toBe('C:\\CARLOS\\2026-10 viejo')
  })
})
