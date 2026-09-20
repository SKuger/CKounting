// Renombrado de los PDF de soporte al patrón DD-MM_NIT_RAZON-SOCIAL_FACTURA
// (D-066). Extraído de `load.vue` (#30).
//
// Siempre en dos pasos: primero se pide el PLAN (dry_run) y el usuario lo ve,
// después se aplica. Renombrar archivos del cliente a ciegas no es aceptable.
import { ref, type Ref } from 'vue'
import { rpc } from './useRpc'

export type RenameItem = {
  path: string
  current_name: string
  new_name: string | null
  matched: boolean
  status: string
  reason: string | null
  cufe: string | null
}

export type RenameResult = {
  folder: string
  date_field: string
  dry_run: boolean
  items: RenameItem[]
  counts: Record<string, number>
  manifest: string | null
}

type Opciones = {
  dbPath: Ref<string>
  loadId: Ref<number>
  /** Se llama tras aplicar: los nombres cambiaron y el índice quedó obsoleto. */
  alAplicar?: () => void
}

export function useRenombrarSoportes({ dbPath, loadId, alAplicar }: Opciones) {
  const toast = useToast()

  const renaming = ref(false)
  const applyingRename = ref(false)
  const renameOpen = ref(false)
  const renameApplied = ref(false)
  const renamePlan = ref<RenameResult | null>(null)

  async function previewRename() {
    if (renaming.value) return
    renaming.value = true
    renameApplied.value = false
    try {
      renamePlan.value = await rpc<RenameResult>('rename_soportes', {
        db_path: dbPath.value, load_id: loadId.value, dry_run: true,
      })
      renameOpen.value = true
      const c = renamePlan.value.counts
      if (!c.rename && !c.already) {
        toast.warn('Nada para renombrar', 'Ningún PDF coincide con una fila del Excel de este mes.')
      }
    } catch (exc) {
      toast.error('No se pudo analizar la carpeta', String(exc))
    } finally {
      renaming.value = false
    }
  }

  async function applyRename() {
    if (applyingRename.value) return
    applyingRename.value = true
    try {
      renamePlan.value = await rpc<RenameResult>('rename_soportes', {
        db_path: dbPath.value, load_id: loadId.value, dry_run: false,
      })
      renameApplied.value = true
      const c = renamePlan.value.counts
      toast.success(
        `${c.renamed} archivo(s) renombrado(s)`,
        c.error ? `${c.error} con error` : (renamePlan.value.manifest || undefined),
      )
      alAplicar?.()
    } catch (exc) {
      toast.error('Error al renombrar', String(exc))
    } finally {
      applyingRename.value = false
    }
  }

  return {
    renaming, applyingRename, renameOpen, renameApplied, renamePlan,
    previewRename, applyRename,
  }
}
