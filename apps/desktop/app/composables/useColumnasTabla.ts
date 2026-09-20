// Visibilidad y agrupación de las columnas de la tabla del Excel DIAN.
//
// Extraído de `load.vue` (#30): la página juntaba seis responsabilidades en 934
// líneas y era el archivo que más se toca del repo. Esto es autónomo — solo
// necesita saber qué columnas trae la carga.
import { computed, ref, type Ref } from 'vue'
import type { VisibilityState } from '@tanstack/vue-table'

/** Columnas que arrancan ocultas: el Excel DIAN trae 32 y la mayoría estorban. */
export const HIDDEN_BY_DEFAULT = new Set<string>([
  'Divisa', 'Forma de Pago', 'Medio de Pago',
  'Fecha Emisión', 'Fecha Recepción',
  'Nombre Emisor', 'Nombre Receptor',
  'Prefijo', 'Folio', 'CUFE/CUDE',
  'ICA', 'IC', 'INC', 'Timbre', 'INC Bolsas',
  'IN Carbono', 'IN Combustibles', 'IC Datos', 'ICL', 'INPP', 'IBUA', 'ICUI',
  'Rete IVA', 'Rete Renta', 'Rete ICA',
  'Estado', 'Grupo',
])

/** Agrupación del panel de columnas. El orden es el que ve el usuario. */
export const COLUMN_GROUPS: Record<string, string[]> = {
  'Identificación': ['Tipo de documento', 'CUFE/CUDE', 'Prefijo', 'Folio', '# de factura'],
  'Tercero': ['NIT Emisor', 'Nombre Emisor', 'NIT Receptor', 'Nombre Receptor'],
  'Fechas': ['Fecha Emisión', 'Fecha Recepción'],
  'Pago': ['Divisa', 'Forma de Pago', 'Medio de Pago'],
  'Importes': ['Total', 'IVA', 'Valor Base', 'Base IVA', 'Diferencia'],
  'Impuestos': ['ICA', 'IC', 'INC', 'Timbre', 'INC Bolsas', 'IN Carbono', 'IN Combustibles', 'IC Datos', 'ICL', 'INPP', 'IBUA', 'ICUI'],
  'Retenciones': ['Rete IVA', 'Rete Renta', 'Rete ICA'],
  'Estado': ['Estado', 'Grupo'],
}

export type GrupoDeColumnas = {
  group: string
  columns: { name: string; visible: boolean }[]
}

/**
 * @param columnasDisponibles las columnas que trae la carga actual (puede estar
 *   vacío mientras no hay datos).
 */
export function useColumnasTabla(columnasDisponibles: Ref<string[]>) {
  const columnVisibility = ref<VisibilityState>({})
  const showColumnsPanel = ref(false)
  const columnsSearch = ref('')

  function toggleColumn(name: string) {
    columnVisibility.value = {
      ...columnVisibility.value,
      [name]: columnVisibility.value[name] === false,
    }
  }

  function showAllColumns() {
    const next: VisibilityState = {}
    for (const col of columnasDisponibles.value) next[col] = true
    columnVisibility.value = next
  }

  function resetColumnsToDefault() {
    const next: VisibilityState = {}
    for (const col of columnasDisponibles.value) next[col] = !HIDDEN_BY_DEFAULT.has(col)
    columnVisibility.value = next
  }

  /**
   * Da visibilidad por defecto a las columnas que aún no la tienen, conservando
   * lo que el usuario ya haya cambiado. Se llama al cargar o recargar las filas.
   */
  function inicializarVisibilidad() {
    const next: VisibilityState = { ...columnVisibility.value }
    for (const col of columnasDisponibles.value) {
      if (!(col in next)) next[col] = !HIDDEN_BY_DEFAULT.has(col)
    }
    columnVisibility.value = next
  }

  function toggleGroup(groupCols: string[], desired: boolean) {
    const next: VisibilityState = { ...columnVisibility.value }
    for (const col of groupCols) {
      if (columnasDisponibles.value.includes(col)) next[col] = desired
    }
    columnVisibility.value = next
  }

  const visibleCount = computed(() =>
    columnasDisponibles.value.reduce(
      (n, c) => n + (columnVisibility.value[c] === false ? 0 : 1),
      0,
    ),
  )

  const columnsForPanel = computed<GrupoDeColumnas[]>(() => {
    const disponibles = columnasDisponibles.value
    if (!disponibles.length) return []
    const needle = columnsSearch.value.trim().toLowerCase()
    const groups: GrupoDeColumnas[] = []
    const seen = new Set<string>()
    for (const [group, cols] of Object.entries(COLUMN_GROUPS)) {
      const filtered = cols
        .filter((c) => disponibles.includes(c))
        .filter((c) => !needle || c.toLowerCase().includes(needle))
        .map((c) => {
          seen.add(c)
          return { name: c, visible: columnVisibility.value[c] !== false }
        })
      if (filtered.length) groups.push({ group, columns: filtered })
    }
    // Catch-all para columnas que no caen en ningún grupo predefinido.
    const others = disponibles
      .filter((c) => !seen.has(c) && (!needle || c.toLowerCase().includes(needle)))
      .map((c) => ({ name: c, visible: columnVisibility.value[c] !== false }))
    if (others.length) groups.push({ group: 'Otros', columns: others })
    return groups
  })

  return {
    columnVisibility,
    showColumnsPanel,
    columnsSearch,
    toggleColumn,
    inicializarVisibilidad,
    showAllColumns,
    resetColumnsToDefault,
    toggleGroup,
    visibleCount,
    columnsForPanel,
  }
}
