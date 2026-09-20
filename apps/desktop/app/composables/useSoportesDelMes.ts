// Panel "Soportes del mes" (D-068): qué PDF tienen CUFE y cuáles no, y
// re-verificarlos sin volver a subir el Excel. Extraído de `load.vue` (#30).
import { ref, type Ref } from 'vue'
import { rpc } from './useRpc'
import { useJob } from './useJob'

export type SoporteFile = {
  name: string
  path: string
  has_cufe: boolean
  extraction_status: string | null
  cufe: string | null
  label: string | null
}

export type SoportesInfo = {
  folder: string | null
  periodo: string | null
  files: SoporteFile[]
  counts: { total: number; with_cufe: number; without_cufe: number }
  reindexed: boolean
  error: string | null
}

type Opciones = {
  dbPath: Ref<string>
  loadId: Ref<number>
  /** Tras re-extraer hay CUFE nuevos: V1 debe volver a correr. */
  alReverificar?: () => Promise<void>
}

export function useSoportesDelMes({ dbPath, loadId, alReverificar }: Opciones) {
  const toast = useToast()
  const job = useJob()

  const soportes = ref<SoportesInfo | null>(null)
  const reverifying = ref(false)
  const soportesOpen = ref(false)

  async function refreshSoportes(opts: { reindex?: boolean; force?: boolean } = {}) {
    if (!dbPath.value || !loadId.value) return
    const params = {
      db_path: dbPath.value, load_id: loadId.value,
      reindex: opts.reindex ?? false, force: opts.force ?? false,
    }
    try {
      // Sin reindex es solo lectura (instantánea). Con reindex se re-extraen los
      // PDF: eso va como trabajo en segundo plano (D-076).
      soportes.value = params.reindex
        ? await job.correr<SoportesInfo>('list_load_soportes', params)
        : await rpc<SoportesInfo>('list_load_soportes', params)
    } catch {
      // El panel es auxiliar: que falle no puede romper la página.
    }
  }

  async function reverificarSoportes() {
    if (reverifying.value) return
    reverifying.value = true
    try {
      await refreshSoportes({ reindex: true, force: true })
      await alReverificar?.()
      const c = soportes.value?.counts
      if (soportes.value?.error) toast.warn('Soportes', soportes.value.error)
      else if (c) {
        toast.success('Soportes re-verificados', `${c.with_cufe}/${c.total} con CUFE encontrado`)
      }
    } catch (exc) {
      toast.error('No se pudieron re-verificar los soportes', String(exc))
    } finally {
      reverifying.value = false
    }
  }

  return { soportes, reverifying, soportesOpen, refreshSoportes, reverificarSoportes, job }
}
