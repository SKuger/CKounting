<script setup lang="ts">
import {
  FlexRender,
  createColumnHelper,
  getCoreRowModel,
  getFilteredRowModel,
  useVueTable,
  type ColumnDef,
  type VisibilityState,
} from '@tanstack/vue-table'

const HIDDEN_BY_DEFAULT = new Set<string>([
  'Divisa', 'Forma de Pago', 'Medio de Pago',
  'Fecha Emisión', 'Fecha Recepción',
  'Nombre Emisor', 'Nombre Receptor',
  'Prefijo', 'Folio', 'CUFE/CUDE',
  'ICA', 'IC', 'INC', 'Timbre', 'INC Bolsas',
  'IN Carbono', 'IN Combustibles', 'IC Datos', 'ICL', 'INPP', 'IBUA', 'ICUI',
  'Rete IVA', 'Rete Renta', 'Rete ICA',
  'Estado', 'Grupo',
])

const COLUMN_GROUPS: Record<string, string[]> = {
  'Identificación': ['Tipo de documento', 'CUFE/CUDE', 'Prefijo', 'Folio', '# de factura'],
  'Tercero': ['NIT Emisor', 'Nombre Emisor', 'NIT Receptor', 'Nombre Receptor'],
  'Fechas': ['Fecha Emisión', 'Fecha Recepción'],
  'Pago': ['Divisa', 'Forma de Pago', 'Medio de Pago'],
  'Importes': ['Total', 'IVA', 'Valor Base', 'Base IVA', 'Diferencia'],
  'Impuestos': ['ICA', 'IC', 'INC', 'Timbre', 'INC Bolsas', 'IN Carbono', 'IN Combustibles', 'IC Datos', 'ICL', 'INPP', 'IBUA', 'ICUI'],
  'Retenciones': ['Rete IVA', 'Rete Renta', 'Rete ICA'],
  'Estado': ['Estado', 'Grupo'],
}

type Row = Record<string, unknown>

type LoadRows = {
  total: number
  offset: number
  limit: number
  columns: string[]
  rows: Row[]
  v3_overrides?: number[]
}

type Failure = { row_index: number; reason: string; codes?: string[] }
type RunResult = {
  run_id: number
  total_rows: number
  failing_rows: number
  v1_active: boolean
  indexed_cufe_count: number
  notes: string | null
  failures: Failure[]
  v3_overrides: number[]
}

type ExportResult = {
  path: string
  rows_written: number
}

type EmpresaInfo = {
  default_folder: string | null
  pdfs_folder: string | null
  razon_social: string
}

type LatestRun = {
  run: { id: number; total_rows: number; failing_rows: number; finished_at: string; notes: string | null } | null
  failures: { row_index: number; reason: string }[]
}

const route = useRoute()
const toast = useToast()
const dbPath = computed(() => (route.query.db as string) || '')
const loadId = computed(() => Number(route.query.id || 0))

const empresaInfo = ref<EmpresaInfo | null>(null)
const data = ref<LoadRows | null>(null)
const loading = ref(false)

const validating = ref(false)
const validationRun = ref<RunResult | null>(null)
const latestRun = ref<LatestRun | null>(null)

const exporting = ref(false)
const exportResult = ref<ExportResult | null>(null)
const exportFolder = ref('')
const exportPickerOpen = ref(false)

// D-046: rows the user manually approved (V3 fail suppressed)
const v3Overrides = ref<Set<number>>(new Set())
const togglingOverride = ref<number | null>(null)

const globalFilter = ref('')
const columnVisibility = ref<VisibilityState>({})
const showColumnsPanel = ref(false)
const columnsSearch = ref('')
const onlyFailing = ref(false)

// Map<row_index, reason> — failures from the last validation_run, with V3
// overrides applied client-side so checkbox toggles feel instant.
const failuresByRow = computed(() => {
  const m = new Map<number, string>()
  const source: Failure[] = (validationRun.value?.failures ?? latestRun.value?.failures ?? []) as Failure[]
  for (const f of source) {
    const codes = f.codes ?? []
    if (codes.length && v3Overrides.value.has(f.row_index)) {
      // Drop V3-coded reasons if the user approved this row.
      const remaining = codes
        .map((c, i) => ({ c, msg: f.reason.split('; ')[i] }))
        .filter((x) => x.c !== 'V3')
        .map((x) => x.msg)
        .filter(Boolean)
      if (remaining.length) m.set(f.row_index, remaining.join('; '))
    } else {
      m.set(f.row_index, f.reason)
    }
  }
  return m
})

const failingCount = computed(() => failuresByRow.value.size)
const totalCount = computed(() =>
  validationRun.value?.total_rows ?? latestRun.value?.run?.total_rows ?? data.value?.total ?? 0,
)
const hasValidationRun = computed(() => Boolean(validationRun.value || latestRun.value?.run))

// A row qualifies for the "Aprobar" checkbox when it currently fails V3
// (i.e., V3 message exists in the latest run for this row_index, regardless of
// whether the user already overrode it).
const v3FailingRows = computed(() => {
  const s = new Set<number>()
  const source: Failure[] = (validationRun.value?.failures ?? []) as Failure[]
  for (const f of source) {
    if ((f.codes ?? []).includes('V3')) s.add(f.row_index)
  }
  // From latest run (no codes), infer V3 by the message text fallback.
  const fromLatest = latestRun.value?.failures ?? []
  for (const f of fromLatest) {
    if (f.reason.includes('IVA no corresponde')) s.add(f.row_index)
  }
  return s
})

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

async function refresh() {
  if (!dbPath.value || !loadId.value) return
  loading.value = true
  try {
    empresaInfo.value = await rpc<EmpresaInfo>('open_empresa', { db_path: dbPath.value })
    if (!exportFolder.value && empresaInfo.value?.default_folder) {
      exportFolder.value = `${empresaInfo.value.default_folder.replace(/[/\\]+$/, '')}/exports`
    }
    data.value = await rpc<LoadRows>('get_load_rows', {
      db_path: dbPath.value,
      load_id: loadId.value,
      offset: 0,
      limit: 5000,
    })
    if (data.value) {
      const next: VisibilityState = { ...columnVisibility.value }
      for (const col of data.value.columns) {
        if (!(col in next)) next[col] = !HIDDEN_BY_DEFAULT.has(col)
      }
      columnVisibility.value = next
      v3Overrides.value = new Set(data.value.v3_overrides ?? [])
    }
    // Fetch latest validation run if any.
    try {
      latestRun.value = await rpc<LatestRun>('get_latest_run_failures', {
        db_path: dbPath.value,
        load_id: loadId.value,
      })
    } catch { /* ignore */ }
    // Auto-validate if there's no prior run, so the chips show up immediately.
    if (!latestRun.value?.run) ejecutarValidaciones({ silent: true })
  } catch (exc) {
    toast.error('No se pudieron cargar las filas', String(exc))
  } finally {
    loading.value = false
  }
}

function toggleColumn(name: string) {
  columnVisibility.value = {
    ...columnVisibility.value,
    [name]: columnVisibility.value[name] === false,
  }
}

function showAllColumns() {
  if (!data.value) return
  const next: VisibilityState = {}
  for (const col of data.value.columns) next[col] = true
  columnVisibility.value = next
}

function resetColumnsToDefault() {
  if (!data.value) return
  const next: VisibilityState = {}
  for (const col of data.value.columns) next[col] = !HIDDEN_BY_DEFAULT.has(col)
  columnVisibility.value = next
}

function toggleGroup(groupCols: string[], desired: boolean) {
  const next: VisibilityState = { ...columnVisibility.value }
  for (const col of groupCols) {
    if (data.value?.columns.includes(col)) next[col] = desired
  }
  columnVisibility.value = next
}

const visibleCount = computed(() => {
  if (!data.value) return 0
  return data.value.columns.reduce(
    (n, c) => n + (columnVisibility.value[c] === false ? 0 : 1),
    0,
  )
})

const columnsForPanel = computed(() => {
  if (!data.value) return [] as { group: string; columns: { name: string; visible: boolean }[] }[]
  const needle = columnsSearch.value.trim().toLowerCase()
  const groups: { group: string; columns: { name: string; visible: boolean }[] }[] = []
  const seen = new Set<string>()
  for (const [group, cols] of Object.entries(COLUMN_GROUPS)) {
    const filtered = cols
      .filter((c) => data.value!.columns.includes(c))
      .filter((c) => !needle || c.toLowerCase().includes(needle))
      .map((c) => {
        seen.add(c)
        return { name: c, visible: columnVisibility.value[c] !== false }
      })
    if (filtered.length) groups.push({ group, columns: filtered })
  }
  // Catch-all for columns not in any predefined group.
  const others = data.value.columns
    .filter((c) => !seen.has(c) && (!needle || c.toLowerCase().includes(needle)))
    .map((c) => ({ name: c, visible: columnVisibility.value[c] !== false }))
  if (others.length) groups.push({ group: 'Otros', columns: others })
  return groups
})

function isNotaCredito(row: Row): boolean {
  const tipo = String(row['Tipo de documento'] || '').toLowerCase()
  return tipo.startsWith('nota de cr')
}

const numericColumns = new Set([
  'IVA', 'ICA', 'IC', 'INC', 'Timbre', 'INC Bolsas',
  'IN Carbono', 'IN Combustibles', 'IC Datos', 'ICL', 'INPP', 'IBUA', 'ICUI',
  'Rete IVA', 'Rete Renta', 'Rete ICA', 'Total', 'Valor Base', 'Base IVA', 'Diferencia',
])

const columns = computed<ColumnDef<Row>[]>(() => {
  if (!data.value) return []
  const helper = createColumnHelper<Row>()
  return data.value.columns.map((name) =>
    helper.accessor((r) => r[name], {
      id: name,
      header: name,
      cell: ({ getValue }) => {
        const v = getValue()
        if (v === null || v === undefined || v === '') return ''
        if (typeof v === 'number') {
          if (numericColumns.has(name)) {
            return v.toLocaleString('es-CO', { maximumFractionDigits: 2 })
          }
          return String(v)
        }
        return String(v)
      },
    }),
  )
})

const tableData = computed<Row[]>(() => {
  const all = data.value?.rows ?? []
  if (!onlyFailing.value) return all
  return all.filter((_, idx) => failuresByRow.value.has(idx))
})

const tableMeta = ref({
  isNotaCredito,
  getReason: (rowIndex: number) => failuresByRow.value.get(rowIndex) || '',
})

const table = useVueTable({
  get data() { return tableData.value },
  get columns() { return columns.value },
  state: {
    get globalFilter() { return globalFilter.value },
    get columnVisibility() { return columnVisibility.value },
  },
  onGlobalFilterChange: (v) => { globalFilter.value = String(v ?? '') },
  onColumnVisibilityChange: (updater) => {
    columnVisibility.value =
      typeof updater === 'function' ? updater(columnVisibility.value) : updater
  },
  globalFilterFn: (row, _id, filter) => {
    if (!filter) return true
    const needle = String(filter).toLowerCase()
    return Object.values(row.original as Row).some((cell) =>
      String(cell ?? '').toLowerCase().includes(needle),
    )
  },
  getCoreRowModel: getCoreRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
})

async function ejecutarValidaciones(opts: { silent?: boolean } = {}) {
  validating.value = true
  try {
    const result = await rpc<RunResult>('run_validations', {
      db_path: dbPath.value,
      load_id: loadId.value,
    })
    validationRun.value = result
    v3Overrides.value = new Set(result.v3_overrides ?? Array.from(v3Overrides.value))
    if (!opts.silent) {
      const detail =
        `${result.failing_rows} / ${result.total_rows} no conformes · ` +
        (result.v1_active
          ? `V1 activa (${result.indexed_cufe_count} CUFE indexados)`
          : 'V1 inactiva (sin carpeta de PDFs)')
      toast.success('Validaciones ejecutadas', detail)
    }
    if (result.notes) toast.warn('Notas de validación', result.notes)
  } catch (exc) {
    toast.error('Error al validar', String(exc))
  } finally {
    validating.value = false
  }
}

async function exportar() {
  if (!exportPath.value) {
    toast.warn('Elige una carpeta de salida primero')
    return
  }
  exporting.value = true
  try {
    // D-047: el reporte ahora es de FALTANTES DE SOPORTE (V1), 5 columnas.
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

async function toggleOverride(rowIndex: number) {
  const active = !v3Overrides.value.has(rowIndex)
  togglingOverride.value = rowIndex
  try {
    const res = await rpc<{ v3_overrides: number[] }>('toggle_validation_override', {
      db_path: dbPath.value,
      load_id: loadId.value,
      row_index: rowIndex,
      code: 'V3',
      active,
    })
    v3Overrides.value = new Set(res.v3_overrides)
    toast.success(active ? 'Fila aprobada manualmente' : 'Aprobación quitada')
  } catch (exc) {
    toast.error('No se pudo actualizar la aprobación', String(exc))
  } finally {
    togglingOverride.value = null
  }
}

// Keyboard shortcuts.
function onKey(e: KeyboardEvent) {
  if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
  if (e.key === '/') {
    e.preventDefault()
    document.querySelector<HTMLInputElement>('input[data-role="global-search"]')?.focus()
  } else if (e.key.toLowerCase() === 'v' && !e.metaKey && !e.ctrlKey) {
    ejecutarValidaciones()
  } else if (e.key.toLowerCase() === 'f' && !e.metaKey && !e.ctrlKey) {
    onlyFailing.value = !onlyFailing.value
  }
}

onMounted(() => {
  refresh()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
watch(loadId, refresh)
</script>

<template>
  <div class="load-page">
    <header class="empresa-hero">
      <div>
        <NuxtLink :to="{ path: '/empresa', query: { db: dbPath } }" class="back-link">
          ← {{ empresaInfo?.razon_social || 'Empresa' }}
        </NuxtLink>
        <h1>Carga #{{ loadId }}</h1>
        <div class="muted small">
          <template v-if="data">{{ data.total }} filas · {{ data.columns.length }} columnas</template>
          <template v-if="hasValidationRun">
            <span class="dot">·</span>
            <span :class="failingCount > 0 ? 'text-danger' : 'text-ok'">
              <strong>{{ failingCount }} / {{ totalCount }}</strong> no conformes
            </span>
          </template>
        </div>
      </div>
    </header>

    <section class="load-toolbar">
      <div class="load-toolbar-row">
        <div class="search-wrap">
          <span class="search-icon">⌕</span>
          <input
            v-model="globalFilter"
            placeholder="Buscar en todas las columnas…  (/)"
            data-role="global-search"
          />
        </div>
        <button
          class="secondary"
          :class="{ 'pressed': onlyFailing }"
          :disabled="!hasValidationRun"
          @click="onlyFailing = !onlyFailing"
          title="Atajo: f"
        >
          {{ onlyFailing ? '✓ Solo no conformes' : 'Solo no conformes' }}
          <span v-if="hasValidationRun" class="badge-count">{{ failingCount }}</span>
        </button>
        <div style="position: relative">
          <button class="secondary" @click="showColumnsPanel = !showColumnsPanel">
            Columnas · {{ visibleCount }}/{{ data?.columns.length ?? 0 }}
          </button>
          <div v-if="showColumnsPanel" class="columns-panel">
            <div class="row" style="justify-content: space-between; margin-bottom: 0.4rem; gap: 0.4rem">
              <input v-model="columnsSearch" placeholder="Buscar columna…" style="flex: 1" />
              <button class="ghost" @click="showAllColumns">Todo</button>
              <button class="ghost" @click="resetColumnsToDefault">Restaurar</button>
              <button class="ghost" @click="showColumnsPanel = false">✕</button>
            </div>
            <div class="columns-groups">
              <div v-for="g in columnsForPanel" :key="g.group" class="column-group">
                <div class="column-group-head">
                  <span>{{ g.group }}</span>
                  <div class="row" style="gap: 0.2rem">
                    <button class="ghost" style="padding: 0.1rem 0.3rem; font-size: 0.7rem"
                      @click="toggleGroup(g.columns.map(c => c.name), true)">+</button>
                    <button class="ghost" style="padding: 0.1rem 0.3rem; font-size: 0.7rem"
                      @click="toggleGroup(g.columns.map(c => c.name), false)">−</button>
                  </div>
                </div>
                <div class="columns-grid-2">
                  <label v-for="col in g.columns" :key="col.name" class="column-toggle">
                    <input type="checkbox" :checked="col.visible" @change="toggleColumn(col.name)" />
                    <span>{{ col.name }}</span>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>
        <span class="spacer" />
        <button :disabled="validating || !data" @click="ejecutarValidaciones()" title="Atajo: v">
          {{ validating ? 'Validando…' : 'Validar' }}
        </button>
        <button class="secondary" @click="exportPickerOpen = true">
          📂 {{ exportFolder ? 'Cambiar salida' : 'Carpeta de salida' }}
        </button>
        <button :disabled="exporting || !exportPath" @click="exportar">
          {{ exporting ? 'Exportando…' : 'Exportar faltantes de soporte' }}
        </button>
      </div>
      <div v-if="exportPath" class="muted mono small">
        Se guardará en: {{ exportPath }}
      </div>
    </section>

    <DirectoryPicker
      :open="exportPickerOpen"
      :initial-path="exportFolder || empresaInfo?.default_folder || ''"
      title="Carpeta donde se guardará el reporte"
      @pick="onExportFolderPicked"
      @close="exportPickerOpen = false"
    />

    <section v-if="loading && !data" class="table-card">
      <div class="data-table-wrapper">
        <table class="data">
          <thead>
            <tr><th v-for="n in 8" :key="n" class="skel-cell">···</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in 8" :key="r"><td v-for="c in 8" :key="c" class="skel-cell"><span class="skel-bar" /></td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-else-if="data && !data.rows.length" class="card center empty-state">
      <div class="empty-icon">📭</div>
      <h3 style="color: var(--text); margin-top: 0.5rem">Carga vacía</h3>
      <p class="muted small">El Excel no tiene filas de datos.</p>
    </section>

    <section v-else-if="data" class="table-card">
      <div class="data-table-wrapper">
        <table class="data">
          <thead>
            <tr v-for="hg in table.getHeaderGroups()" :key="hg.id">
              <th class="status-col"></th>
              <th
                v-for="h in hg.headers"
                :key="h.id"
                :class="{ num: numericColumns.has(h.column.id) }"
              >
                <FlexRender :render="h.column.columnDef.header" :props="h.getContext()" />
              </th>
              <th class="approve-col" title="Aprobación manual">Aprobar</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in table.getRowModel().rows"
              :key="row.id"
              :class="{
                'row-failing': failuresByRow.has(Number(row.id)),
                'row-overridden': v3Overrides.has(Number(row.id)),
              }"
            >
              <td class="status-col">
                <template v-if="failuresByRow.has(Number(row.id))">
                  <span
                    class="chip nc status-chip"
                    :title="failuresByRow.get(Number(row.id))"
                  >⚠</span>
                </template>
                <template v-else-if="hasValidationRun">
                  <span class="status-ok" title="Pasa todas las validaciones">✓</span>
                </template>
              </td>
              <td
                v-for="cell in row.getVisibleCells()"
                :key="cell.id"
                :class="{ num: numericColumns.has(cell.column.id) }"
              >
                <template v-if="cell.column.id === 'Tipo de documento' && isNotaCredito(row.original as Row)">
                  <span class="chip nc" style="margin-right: 6px">NC</span>
                </template>
                <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
              </td>
              <td class="approve-col">
                <template v-if="v3FailingRows.has(Number(row.id)) || v3Overrides.has(Number(row.id))">
                  <label class="approve-check" :title="v3Overrides.has(Number(row.id)) ? 'Aprobado: V3 ignorado para esta fila' : 'Aprobar V3 manualmente'">
                    <input
                      type="checkbox"
                      :checked="v3Overrides.has(Number(row.id))"
                      :disabled="togglingOverride === Number(row.id)"
                      @change="toggleOverride(Number(row.id))"
                    />
                  </label>
                </template>
              </td>
            </tr>
            <tr v-if="onlyFailing && table.getRowModel().rows.length === 0">
              <td :colspan="visibleCount + 2" class="empty muted">
                Sin filas no conformes con el filtro actual.
                <button class="ghost" style="margin-left: 0.4rem" @click="onlyFailing = false">Mostrar todas</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.search-wrap { position: relative; flex: 1 1 18rem; min-width: 12rem; }
.search-wrap input { padding-left: 1.7rem; width: 100%; }
.search-icon { position: absolute; left: 0.5rem; top: 50%; transform: translateY(-50%); color: var(--muted); font-size: 0.85rem; }

.text-danger { color: var(--chip-nc-fg); }
.text-ok { color: var(--chip-ok-fg); }

.badge-count {
  background: var(--chip-nc-bg);
  color: var(--chip-nc-fg);
  border: 1px solid var(--chip-nc-border);
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 0.7rem;
  margin-left: 0.4rem;
  font-weight: 700;
}
.secondary.pressed {
  background: var(--accent-soft);
  border-color: rgba(94,106,210,0.35);
  color: var(--accent-hover);
  font-weight: 600;
}

.status-col {
  width: 32px;
  text-align: center !important;
  padding: 0.35rem 0.4rem !important;
  position: sticky;
  left: 0;
  background: var(--panel-2);
  z-index: 2;
  border-right: 1px solid var(--border);
}
table.data tbody tr:hover .status-col { background: var(--panel-3); }
.status-chip { display: inline-flex; align-items: center; justify-content: center; cursor: help; padding: 1px 6px; }
.status-ok { color: var(--ok); font-weight: 700; opacity: 0.7; }
.row-failing td:not(.status-col):not(.approve-col) {
  background: rgba(214, 40, 40, 0.05) !important;
}
.row-failing:hover td:not(.status-col):not(.approve-col) {
  background: rgba(214, 40, 40, 0.10) !important;
}
.row-overridden td:not(.status-col):not(.approve-col) {
  background: rgba(16, 185, 129, 0.05) !important;
}
.row-overridden:hover td:not(.status-col):not(.approve-col) {
  background: rgba(16, 185, 129, 0.10) !important;
}

.approve-col {
  width: 80px;
  text-align: center !important;
  padding: 0.35rem 0.5rem !important;
  position: sticky;
  right: 0;
  background: var(--panel-2);
  border-left: 1px solid var(--border);
  z-index: 2;
  font-size: 0.7rem;
  color: var(--muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
table.data tbody tr:hover .approve-col { background: var(--panel-3); }
.approve-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0.2rem;
  border-radius: 4px;
}
.approve-check input { accent-color: var(--ok); width: 16px; height: 16px; cursor: pointer; }
.approve-check:hover { background: var(--accent-soft); }

.skel-cell { height: 32px; }
.skel-bar {
  display: block; height: 0.7rem; width: 70%; border-radius: 4px;
  background: linear-gradient(90deg, var(--panel-2), var(--panel-3), var(--panel-2));
  background-size: 200% 100%;
  animation: skel-shimmer 1.4s linear infinite;
}
@keyframes skel-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.empty-state { padding: 2rem 1rem; }
.empty-icon { font-size: 2.5rem; opacity: 0.4; }

.columns-groups { display: flex; flex-direction: column; gap: 0.4rem; }
.column-group {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.35rem 0.5rem;
}
.column-group-head {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 0.72rem; color: var(--muted); font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.04em;
  margin-bottom: 0.3rem;
}
.columns-grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.1rem 0.4rem; }
</style>
