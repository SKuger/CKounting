// El composable que sustituye a la llamada síncrona que reventaba a los 30 s
// (#6, D-076). Se moquea `rpc` para no necesitar el sidecar Python.
import { describe, it, expect, vi, beforeEach } from 'vitest'

const rpcMock = vi.fn()
vi.mock('../app/composables/useRpc', () => ({ rpc: (...a: unknown[]) => rpcMock(...a) }))

const { useJob } = await import('../app/composables/useJob')

function estado(over: Record<string, unknown> = {}) {
  return {
    job_id: 'j1',
    method: 'run_validations',
    status: 'running',
    progress: { done: 0, total: 0, message: '', percent: null },
    result: null,
    error: null,
    elapsed_seconds: 0,
    ...over,
  }
}

beforeEach(() => {
  rpcMock.mockReset()
  vi.useFakeTimers()
})

/**
 * Avanza los temporizadores hasta que la promesa se asiente.
 * Se le engancha un manejador ANTES de avanzar: si no, un rechazo queda sin
 * manejar mientras corren los timers y Vitest lo reporta como error suelto.
 */
async function correrHastaElFinal<T>(p: Promise<T>): Promise<T> {
  const asentada = p.then(
    (v) => ({ ok: true as const, v }),
    (e) => ({ ok: false as const, e }),
  )
  for (let i = 0; i < 50; i++) await vi.advanceTimersByTimeAsync(500)
  const r = await asentada
  if (r.ok) return r.v
  throw r.e
}

/** Deja que se resuelvan las microtareas pendientes sin disparar el siguiente sondeo. */
const asentar = () => vi.advanceTimersByTimeAsync(0)

describe('useJob', () => {
  it('pide el método con sufijo _async y luego sondea job_status', async () => {
    rpcMock
      .mockResolvedValueOnce({ job_id: 'j1' })
      .mockResolvedValueOnce(estado({ status: 'done', result: { failing_rows: 3 } }))

    const { correr } = useJob()
    const res = await correrHastaElFinal(correr('run_validations', { load_id: 7 }))

    expect(rpcMock.mock.calls[0]).toEqual(['run_validations_async', { load_id: 7 }])
    expect(rpcMock.mock.calls[1][0]).toBe('job_status')
    expect(res).toEqual({ failing_rows: 3 })
  })

  it('publica el progreso intermedio', async () => {
    rpcMock
      .mockResolvedValueOnce({ job_id: 'j1' })
      .mockResolvedValueOnce(estado({
        progress: { done: 3, total: 12, message: 'Leyendo factura.pdf', percent: 25 },
      }))
      .mockResolvedValueOnce(estado({ status: 'done', result: 'ok' }))

    const { correr, progreso, etiqueta } = useJob()
    const p = correr('reindex_pdfs')
    // Solo hasta el PRIMER sondeo: el siguiente devuelve 'done' y sobreescribe
    // el progreso, así que asertar después no probaría nada.
    await asentar()

    expect(progreso.value.percent).toBe(25)
    expect(etiqueta.value).toBe('Leyendo factura.pdf · 3 de 12')
    await correrHastaElFinal(p)
  })

  it('propaga el mensaje de error del trabajo, no uno genérico', async () => {
    rpcMock
      .mockResolvedValueOnce({ job_id: 'j1' })
      .mockResolvedValueOnce(estado({ status: 'error', error: 'La carpeta de soportes no existe.' }))

    const { correr } = useJob()
    await expect(correrHastaElFinal(correr('run_validations')))
      .rejects.toThrow('La carpeta de soportes no existe.')
  })

  it('distingue la cancelación de un fallo', async () => {
    rpcMock
      .mockResolvedValueOnce({ job_id: 'j1' })
      .mockResolvedValueOnce(estado({ status: 'cancelled' }))

    const { correr } = useJob()
    await expect(correrHastaElFinal(correr('reindex_pdfs'))).rejects.toThrow('Cancelado')
  })

  it('marca corriendo mientras dura y lo limpia al terminar, incluso si falla', async () => {
    rpcMock
      .mockResolvedValueOnce({ job_id: 'j1' })
      .mockResolvedValueOnce(estado({ status: 'running' }))   // sigue en marcha
      .mockResolvedValueOnce(estado({ status: 'error', error: 'x' }))

    const { correr, corriendo } = useJob()
    expect(corriendo.value).toBe(false)
    const p = correr('run_validations')
    await asentar()
    expect(corriendo.value).toBe(true)
    await expect(correrHastaElFinal(p)).rejects.toThrow()
    expect(corriendo.value).toBe(false)
  })

  it('cancelar no hace nada si no hay trabajo en curso', async () => {
    const { cancelar } = useJob()
    await cancelar()
    expect(rpcMock).not.toHaveBeenCalled()
  })

  it('etiqueta por defecto cuando el trabajo aún no informó nada', async () => {
    const { etiqueta } = useJob()
    expect(etiqueta.value).toBe('Trabajando…')
  })
})
