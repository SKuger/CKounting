// Exportación del reporte de FALTANTES DE SOPORTE (D-047), 5 columnas.
// Extraído de `load.vue` (#30).
import { computed, ref, type Ref } from 'vue'
import { rpc } from './useRpc'

export type ExportResult = {
  path: string
  rows_written: number
}

export const MES_AL_FINAL = /[/\\]\d{4}-\d{2}$/

/** La carpeta de la empresa: si la guardada es la de un mes (`…/AAAA-MM`), su madre. */
export function carpetaDeEmpresa(ruta: string): string {
  const limpia = ruta.replace(/[/\\]+$/, '')
  return MES_AL_FINAL.test(limpia) ? limpia.replace(MES_AL_FINAL, '') : limpia
}

export function useExportarFaltantes(dbPath: Ref<string>, loadId: Ref<number>) {
  const toast = useToast()

  const exporting = ref(false)
  const exportResult = ref<ExportResult | null>(null)
  const exportFolder = ref('')
  const exportPickerOpen = ref(false)

  function buildExportFilename(id: number): string {
    const d = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const stamp =
      `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-` +
      `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
    return `faltantes_soporte_load${id}_${stamp}.xlsx`
  }

  const exportPath = computed(() => {
    if (!exportFolder.value) return ''
    const trimmed = exportFolder.value.replace(/[/\\]+$/, '')
    return `${trimmed}/${buildExportFilename(loadId.value)}`
  })

  function onExportFolderPicked(path: string) {
    exportFolder.value = path
    exportPickerOpen.value = false
    toast.info('Carpeta de salida elegida', path)
  }

  /** Propone `<empresa>/<mes de la carga>/exports` si el usuario aún no eligió carpeta. */
  function proponerCarpeta(defaultFolder: string | null | undefined, periodo: string | null) {
    if (exportFolder.value || !defaultFolder) return
    const raiz = defaultFolder.replace(/[/\\]+$/, '')
    const sep = raiz.includes('\\') ? '\\' : '/'
    // Una carpeta de empresa que es la de un mes (…\2026-10) dejaba la carga de
    // septiembre exportando a octubre (el contador, 2026-11-03).
    const empresa = carpetaDeEmpresa(raiz)
    exportFolder.value = periodo ? [empresa, periodo, 'exports'].join(sep) : `${raiz}${sep}exports`
  }

  async function exportar() {
    if (!exportPath.value) {
      toast.warn('Elige una carpeta de salida primero')
      return
    }
    exporting.value = true
    try {
      exportResult.value = await rpc<ExportResult>('export_missing_supports', {
        db_path: dbPath.value,
        load_id: loadId.value,
        output_path: exportPath.value,
      })
      toast.success(
        `Faltantes de soporte exportados (${exportResult.value.rows_written} filas)`,
        exportResult.value.path,
      )
    } catch (exc) {
      toast.error('Error al exportar', String(exc))
    } finally {
      exporting.value = false
    }
  }

  return {
    exporting, exportResult, exportFolder, exportPickerOpen, exportPath,
    onExportFolderPicked, proponerCarpeta, exportar,
  }
}
