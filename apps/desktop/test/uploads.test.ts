// Utilidades compartidas por los endpoints de subida. Cubre los fallos que
// encontró la revisión: rutas XDG hardcodeadas en un producto Windows (#9) y
// `safeFilename` sin tratar los casos reales de Windows (#27).
import { describe, it, expect, vi, afterEach } from 'vitest'

import {
  safeFilename,
  uniquePrefix,
  checkUploadSize,
  contabDataDir,
  MAX_UPLOAD_BYTES,
} from '../server/utils/uploads'

describe('safeFilename', () => {
  it('nunca deja separadores de ruta', () => {
    expect(safeFilename('../../etc/passwd')).not.toContain('/')
    expect(safeFilename('..\\..\\Windows\\System32\\x.xlsx')).not.toContain('\\')
  })

  it('quita los puntos iniciales, que ocultan el archivo o forman ..', () => {
    expect(safeFilename('...oculto.xlsx').startsWith('.')).toBe(false)
    expect(safeFilename('..')).toBe('archivo.xlsx')
  })

  it('quita caracteres ilegales en Windows', () => {
    const limpio = safeFilename('re:por*te?<2024>.xlsx')
    for (const c of [':', '*', '?', '<', '>', '|', '"']) {
      expect(limpio).not.toContain(c)
    }
  })

  it('escapa los nombres reservados de Windows', () => {
    // CON.xlsx no se puede crear en Windows, pase lo que pase.
    expect(safeFilename('CON.xlsx')).toBe('_CON.xlsx')
    expect(safeFilename('nul')).toBe('_nul')
    expect(safeFilename('COM1.txt')).toBe('_COM1.txt')
  })

  it('quita puntos y espacios finales, que Windows no admite', () => {
    expect(safeFilename('informe.  ')).toBe('informe')
  })

  it('cae al nombre por defecto cuando no queda nada', () => {
    expect(safeFilename(undefined)).toBe('archivo.xlsx')
    expect(safeFilename('   ')).toBe('archivo.xlsx')
    expect(safeFilename('///', 'puc.xlsx')).toBe('___')
  })

  it('conserva un nombre normal intacto', () => {
    expect(safeFilename('Reporte DIAN 2024-02.xlsx')).toBe('Reporte DIAN 2024-02.xlsx')
  })
})

describe('uniquePrefix', () => {
  it('no colisiona entre dos subidas del mismo segundo', () => {
    // El bug real: upload-excel usaba solo la marca temporal y dos subidas en el
    // mismo segundo se sobreescribían.
    const prefijos = new Set(Array.from({ length: 200 }, () => uniquePrefix()))
    expect(prefijos.size).toBe(200)
  })

  it('empieza por la fecha, para que ordene cronológicamente', () => {
    expect(uniquePrefix()).toMatch(/^\d{8}-\d{6}_[a-z0-9]+$/)
  })
})

describe('checkUploadSize', () => {
  it('acepta un archivo normal', () => {
    expect(checkUploadSize(2 * 1024 * 1024)).toBeNull()
  })

  it('rechaza lo que no cabe en memoria y lo dice en español', () => {
    const msg = checkUploadSize(MAX_UPLOAD_BYTES + 1)
    expect(msg).toContain('MB')
    expect(msg).toContain('máximo')
  })
})

describe('contabDataDir', () => {
  const original = process.platform

  afterEach(() => {
    Object.defineProperty(process, 'platform', { value: original })
    vi.unstubAllEnvs()
  })

  function forzarPlataforma(p: string) {
    Object.defineProperty(process, 'platform', { value: p })
  }

  it('en Windows usa %APPDATA%\\Contab, igual que paths.py', () => {
    // El bug (#9): Node usaba ~/.local/share/Contab (XDG, Linux) en un producto
    // Windows mientras Python leía en %APPDATA%\Contab. Escribían en sitios
    // distintos y ninguno veía lo del otro.
    forzarPlataforma('win32')
    vi.stubEnv('APPDATA', 'C:\\Users\\Test\\AppData\\Roaming')
    expect(contabDataDir()).toBe('C:\\Users\\Test\\AppData\\Roaming\\Contab')
  })

  it('en Linux respeta XDG_DATA_HOME', () => {
    // `node:path` fija su separador a la plataforma REAL al importarse, así que
    // stubbear process.platform cambia la RAMA pero no el separador. Se comprueba
    // la raíz elegida, que es lo que decide dónde se escribe.
    forzarPlataforma('linux')
    vi.stubEnv('XDG_DATA_HOME', '/home/test/.local/share')
    const dir = contabDataDir().split('\\').join('/')
    expect(dir).toContain('/home/test/.local/share')
    expect(dir.endsWith('/Contab')).toBe(true)
  })

  it('en Windows NO usa la ruta XDG aunque XDG_DATA_HOME esté puesta', () => {
    // El bug exacto (#9): la ruta XDG estaba hardcodeada en un producto Windows.
    forzarPlataforma('win32')
    vi.stubEnv('XDG_DATA_HOME', '/home/test/.local/share')
    vi.stubEnv('APPDATA', 'C:\\Users\\Test\\AppData\\Roaming')
    expect(contabDataDir()).not.toContain('.local')
  })

  it('siempre termina en la carpeta Contab', () => {
    for (const p of ['win32', 'darwin', 'linux']) {
      forzarPlataforma(p)
      expect(contabDataDir().endsWith('Contab')).toBe(true)
    }
  })
})

describe('purgarSubidasAntiguas', () => {
  // #29: cada Excel y cada dump de PUC se guardaban con marca temporal y nadie
  // los borraba nunca.
  it('borra lo viejo y respeta lo reciente', async () => {
    const { mkdtemp, writeFile, utimes, readdir } = await import('node:fs/promises')
    const { tmpdir } = await import('node:os')
    const { join } = await import('node:path')
    const { purgarSubidasAntiguas, RETENCION_SUBIDAS_DIAS } = await import('../server/utils/uploads')

    const dir = await mkdtemp(join(tmpdir(), 'contab-purga-'))
    const viejo = join(dir, 'viejo.xlsx')
    const nuevo = join(dir, 'nuevo.xlsx')
    await writeFile(viejo, 'x')
    await writeFile(nuevo, 'y')

    const hace = (dias: number) => new Date(Date.now() - dias * 86400 * 1000)
    await utimes(viejo, hace(RETENCION_SUBIDAS_DIAS + 1), hace(RETENCION_SUBIDAS_DIAS + 1))

    expect(await purgarSubidasAntiguas(dir)).toBe(1)
    expect(await readdir(dir)).toEqual(['nuevo.xlsx'])
  })

  it('no falla si la carpeta no existe', async () => {
    const { purgarSubidasAntiguas } = await import('../server/utils/uploads')
    expect(await purgarSubidasAntiguas('/ruta/que/no/existe/jamas')).toBe(0)
  })
})
