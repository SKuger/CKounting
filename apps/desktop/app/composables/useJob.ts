// Lanza una operación larga como trabajo en segundo plano y sigue su progreso
// (D-076). Sustituye a la llamada síncrona que reventaba a los 30 s mientras el
// sidecar seguía trabajando.
//
//   const { correr, progreso, corriendo, cancelar } = useJob()
//   const res = await correr('run_validations', { db_path, load_id })
//
import { ref, computed } from 'vue'
import { rpc } from './useRpc'

export type JobProgress = {
  done: number
  total: number
  message: string
  percent: number | null
}

type JobStatus = {
  job_id: string
  method: string
  status: 'running' | 'done' | 'error' | 'cancelled'
  progress: JobProgress
  result: unknown
  error: string | null
  elapsed_seconds: number
}

const SIN_PROGRESO: JobProgress = { done: 0, total: 0, message: '', percent: null }

// Cada cuánto se pregunta por el avance. 400 ms da una barra fluida sin inundar
// el sidecar: `job_status` solo lee un diccionario en memoria.
const INTERVALO_MS = 400

export function useJob() {
  const progreso = ref<JobProgress>({ ...SIN_PROGRESO })
  const jobId = ref<string | null>(null)
  const corriendo = computed(() => jobId.value !== null)

  async function correr<T = unknown>(
    metodo: string,
    params: Record<string, unknown> = {},
  ): Promise<T> {
    const inicio = await rpc<{ job_id: string }>(`${metodo}_async`, params)
    jobId.value = inicio.job_id
    progreso.value = { ...SIN_PROGRESO }

    try {
      for (;;) {
        const estado = await rpc<JobStatus>('job_status', { job_id: inicio.job_id })
        progreso.value = estado.progress
        if (estado.status === 'done') return estado.result as T
        if (estado.status === 'cancelled') throw new Error('Cancelado.')
        if (estado.status === 'error') throw new Error(estado.error || 'El trabajo falló.')
        await new Promise((r) => setTimeout(r, INTERVALO_MS))
      }
    } finally {
      jobId.value = null
    }
  }

  async function cancelar(): Promise<void> {
    if (!jobId.value) return
    await rpc('job_cancel', { job_id: jobId.value })
  }

  /** "Leyendo factura.pdf · 3 de 12" para pintar bajo la barra. */
  const etiqueta = computed(() => {
    const p = progreso.value
    if (!p.message && !p.total) return 'Trabajando…'
    const cuenta = p.total ? ` · ${p.done} de ${p.total}` : ''
    return `${p.message || 'Trabajando…'}${cuenta}`
  })

  return { correr, cancelar, progreso, etiqueta, corriendo, jobId }
}
