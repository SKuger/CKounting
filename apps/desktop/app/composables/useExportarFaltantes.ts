// Exportación del reporte de FALTANTES DE SOPORTE (D-047), 5 columnas.
// Extraído de `load.vue` (#30).
import { computed, ref, type Ref } from 'vue'
import { rpc } from './useRpc'

export type ExportResult = {
  path: string
  rows_written: number
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

  /** Propone `<default_folder>/exports` si el usuario aún no eligió carpeta. */
  function proponerCarpeta(defaultFolder: string | null | undefined) {
    if (exportFolder.value || !defaultFolder) return
    exportFolder.value = `${defaultFolder.replace(/[/\\]+$/, '')}/exports`
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
