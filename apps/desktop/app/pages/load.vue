<script setup lang="ts">
import { Search, ArrowLeft, FolderOpen, Pencil, RefreshCw, ChevronRight } from 'lucide-vue-next'
import {
  FlexRender,
  createColumnHelper,
  getCoreRowModel,
  getFilteredRowModel,
  useVueTable,
  type ColumnDef,
} from '@tanstack/vue-table'

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

// D-046: rows the user manually approved (V3 fail suppressed)
const v3Overrides = ref<Set<number>>(new Set())
const togglingOverride = ref<number | null>(null)

const globalFilter = ref('')
const onlyFailing = ref(false)

// #30 — la gestión de columnas vive en su propio composable.
const columnasDisponibles = computed(() => data.value?.columns ?? [])
const {
  columnVisibility, showColumnsPanel, columnsSearch,
  toggleColumn, inicializarVisibilidad, showAllColumns, resetColumnsToDefault, toggleGroup,
  visibleCount, columnsForPanel,
} = useColumnasTabla(columnasDisponibles)

// #30 — exportación y renombrado, cada uno en su composable.
const {
  exporting, exportResult, exportFolder, exportPickerOpen, exportPath,
  onExportFolderPicked, proponerCarpeta, exportar,
} = useExportarFaltantes(dbPath, loadId)

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

async function refresh() {
  if (!dbPath.value || !loadId.value) return
  loading.value = true
  try {
    empresaInfo.value = await rpc<EmpresaInfo>('open_empresa', { db_path: dbPath.value })
    proponerCarpeta(empresaInfo.value?.default_folder)
    data.value = await rpc<LoadRows>('get_load_rows', {
      db_path: dbPath.value,
      load_id: loadId.value,
      offset: 0,
      limit: 5000,
    })
    if (data.value) {
      inicializarVisibilidad()
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
    // Panel de soportes del mes (solo lectura; se puebla del índice ya existente).
    refreshSoportes()
  } catch (exc) {
    toast.error('No se pudieron cargar las filas', String(exc))
  } finally {
    loading.value = false
  }
}

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
  // Cada fila lleva su índice ORIGINAL (__idx). Es lo que usa `getRowId` para que
  // `row.id` NO se desalinee al filtrar "Solo no conformes": failuresByRow / v3Overrides
  // están indexados por ese índice absoluto, no por la posición dentro del subconjunto.
  const all = (data.value?.rows ?? []).map((r, i) => ({ ...r, __idx: i })) as Row[]
  if (!onlyFailing.value) return all
  return all.filter((r) => failuresByRow.value.has((r as Row & { __idx: number }).__idx))
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
    return Object.entries(row.original as Row)
      .filter(([k]) => k !== '__idx')
      .some(([, cell]) => String(cell ?? '').toLowerCase().includes(needle))
  },
  getRowId: (row) => String((row as Row & { __idx: number }).__idx),
  getCoreRowModel: getCoreRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
})

// D-076: validar re-indexa la carpeta de soportes del mes, que no tiene techo de
// duracion. Va como trabajo en segundo plano con progreso, no como peticion que
// revienta a los 30 s mientras Python sigue trabajando.
const jobValidar = useJob()

// Vista unificada para la barra: solo uno de los dos corre a la vez.
const trabajo = computed(() => {
  const j = jobValidar.corriendo.value ? jobValidar : jobSoportes.corriendo.value ? jobSoportes : null
  return {
    activo: j !== null,
    percent: j ? j.progreso.value.percent : null,
    etiqueta: j ? j.etiqueta.value : '',
  }
})

async function cancelarTrabajo() {
  await Promise.all([jobValidar.cancelar(), jobSoportes.cancelar()])
}

async function ejecutarValidaciones(opts: { silent?: boolean } = {}) {
  validating.value = true
  try {
    const result = await jobValidar.correr<RunResult>('run_validations', {
      db_path: dbPath.value,
      load_id: loadId.value,
    })
    validationRun.value = result
    v3Overrides.value = new Set(result.v3_overrides ?? Array.from(v3Overrides.value))
    // run_validations re-indexa la carpeta del mes → refrescar el panel de soportes.
    refreshSoportes()
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

// #30 — el renombrado de soportes vive en su propio composable.
const {
  renaming, applyingRename, renameOpen, renameApplied, renamePlan,
  previewRename, applyRename,
} = useRenombrarSoportes({ dbPath, loadId, alAplicar: () => refreshSoportes() })

// #30 — el panel de soportes del mes vive en su propio composable.
const {
  soportes, reverifying, soportesOpen, refreshSoportes, reverificarSoportes,
  job: jobSoportes,
} = useSoportesDelMes({
  dbPath,
  loadId,
  // Tras re-extraer hay CUFE nuevos: V1 tiene que volver a correr para que la
  // tabla refleje lo que se acaba de leer.
  alReverificar: () => ejecutarValidaciones({ silent: true }),
})

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
  <div class="flex h-full min-h-0 flex-col">
    <DirectoryPicker
      :open="exportPickerOpen"
      :initial-path="exportFolder || empresaInfo?.default_folder || ''"
      title="Carpeta donde se guardará el reporte"
      @pick="onExportFolderPicked"
      @close="exportPickerOpen = false"
    />
    <header class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
      <NuxtLink :to="{ path: '/empresa', query: { db: dbPath } }" class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft class="size-3.5" /> {{ empresaInfo?.razon_social || 'Empresa' }}
      </NuxtLink>
      <span class="text-border">/</span>
      <h1 class="font-heading text-xl font-medium tracking-tight">Carga #{{ loadId }}</h1>
      <p class="text-sm text-muted-foreground">
        <template v-if="data">{{ data.total }} filas · {{ data.columns.length }} columnas</template>
        <template v-if="hasValidationRun">
          <span class="mx-1.5 text-border">·</span>
          <span :class="failingCount > 0 ? 'text-status-error' : 'text-status-success'">
            <strong>{{ failingCount }} / {{ totalCount }}</strong> no conformes
          </span>
          <HelpHint title="¿Qué es «no conforme»?">Son las filas que no pasan alguna validación (V1 soporte, V2 nota crédito, V3 tarifa de IVA). Son las que debes revisar.</HelpHint>
        </template>
      </p>
    </header>

    <section class="flex flex-col gap-2 rounded-lg border border-border bg-card p-2">
      <div class="flex flex-wrap items-center gap-2">
        <div class="relative min-w-48 flex-1">
          <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            v-model="globalFilter"
            class="pl-8"
            placeholder="Buscar en todas las columnas…  (/)"
            data-role="global-search"
          />
        </div>
        <Button
          data-tour="load-solo-nc"
          :variant="onlyFailing ? 'default' : 'outline'"
          :disabled="!hasValidationRun"
          title="Atajo: f"
          @click="onlyFailing = !onlyFailing"
        >
          {{ onlyFailing ? '✓ Solo no conformes' : 'Solo no conformes' }}
          <span v-if="hasValidationRun" class="ml-1 inline-flex items-center rounded-full bg-status-error-bg px-1.5 text-[10px] font-bold text-status-error">{{ failingCount }}</span>
        </Button>
        <Popover v-model:open="showColumnsPanel">
          <PopoverTrigger as-child>
            <Button variant="outline">Columnas · {{ visibleCount }}/{{ data?.columns.length ?? 0 }}</Button>
          </PopoverTrigger>
          <PopoverContent align="start" :side-offset="6" class="w-96 p-2">
            <div class="mb-2 flex items-center gap-2">
              <Input v-model="columnsSearch" placeholder="Buscar columna…" class="h-8 flex-1" />
              <Button variant="ghost" size="sm" @click="showAllColumns">Todo</Button>
              <Button variant="ghost" size="sm" @click="resetColumnsToDefault">Restaurar</Button>
            </div>
            <div class="flex max-h-[50vh] flex-col gap-1.5 overflow-y-auto">
              <div v-for="g in columnsForPanel" :key="g.group" class="rounded-md border border-border bg-muted/40 px-2 py-1.5">
                <div class="mb-1 flex items-center justify-between font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                  <span>{{ g.group }}</span>
                  <div class="flex gap-1">
                    <button type="button" class="rounded px-1.5 text-sm hover:bg-accent" @click="toggleGroup(g.columns.map(c => c.name), true)">+</button>
                    <button type="button" class="rounded px-1.5 text-sm hover:bg-accent" @click="toggleGroup(g.columns.map(c => c.name), false)">−</button>
                  </div>
                </div>
                <div class="grid grid-cols-2 gap-x-2 gap-y-0.5">
                  <label v-for="col in g.columns" :key="col.name" class="flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 text-sm hover:bg-accent">
                    <input type="checkbox" class="size-3.5 accent-primary" :checked="col.visible" @change="toggleColumn(col.name)">
                    <span class="truncate">{{ col.name }}</span>
                  </label>
                </div>
              </div>
            </div>
          </PopoverContent>
        </Popover>
        <span class="flex-1" />
        <Button data-tour="load-validar" :disabled="validating || !data" title="Atajo: v" @click="ejecutarValidaciones()">
          {{ validating ? 'Validando…' : 'Validar' }}
        </Button>
        <!-- D-076: progreso real del trabajo en segundo plano. Antes la operación
             era opaca y reventaba a los 30 s sin decir en qué iba. -->
        <div v-if="trabajo.activo" class="flex min-w-56 items-center gap-2">
          <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" role="progressbar"
               :aria-valuenow="trabajo.percent ?? undefined" aria-valuemin="0" aria-valuemax="100">
            <div
              class="h-full rounded-full bg-primary transition-all duration-300"
              :class="trabajo.percent === null ? 'w-1/3 animate-pulse' : ''"
              :style="trabajo.percent !== null ? { width: `${trabajo.percent}%` } : undefined"
            />
          </div>
          <span class="max-w-56 truncate text-xs text-muted-foreground" :title="trabajo.etiqueta">
            {{ trabajo.etiqueta }}
          </span>
          <button type="button" class="text-xs text-muted-foreground underline hover:text-foreground"
                  @click="cancelarTrabajo">Cancelar</button>
        </div>
        <Button variant="secondary" @click="exportPickerOpen = true">
          <FolderOpen class="size-4" /> {{ exportFolder ? 'Cambiar salida' : 'Carpeta de salida' }}
        </Button>
        <Button data-tour="load-exportar" :disabled="exporting || !exportPath" @click="exportar">
          {{ exporting ? 'Exportando…' : 'Exportar faltantes de soporte' }}
        </Button>
        <Button data-tour="load-renombrar" variant="secondary" :disabled="renaming || !data" title="Renombra los PDF del mes según el Excel" @click="previewRename">
          <Pencil class="size-4" /> {{ renaming ? 'Analizando…' : 'Renombrar soportes' }}
        </Button>
      </div>
      <p v-if="exportPath" class="break-all font-mono text-xs text-muted-foreground">
        Se guardará en: {{ exportPath }}
      </p>
    </section>

    <section v-if="data && soportes" data-tour="load-soportes" class="rounded-lg border border-border bg-card">
      <div class="flex flex-wrap items-center gap-2 px-3 py-2">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 text-sm font-medium transition-colors hover:text-foreground"
          @click="soportesOpen = !soportesOpen"
        >
          <ChevronRight class="size-4 text-muted-foreground transition-transform" :class="soportesOpen ? 'rotate-90' : ''" />
          📎 Soportes del mes
        </button>
        <span v-if="soportes.error" class="text-xs text-muted-foreground">· {{ soportes.error }}</span>
        <span v-else class="text-xs text-muted-foreground">
          · <strong class="text-foreground">{{ soportes.counts.total }}</strong> archivos ·
          <span class="text-status-success">{{ soportes.counts.with_cufe }} con CUFE</span>
          <template v-if="soportes.counts.without_cufe">
            · <span class="text-status-error">{{ soportes.counts.without_cufe }} sin CUFE</span>
          </template>
        </span>
        <span class="flex-1" />
        <Button
          variant="secondary"
          size="sm"
          :disabled="reverifying || !data"
          title="Re-lee los CUFE de la carpeta del mes y refresca las validaciones, sin re-subir el Excel"
          @click="reverificarSoportes"
        >
          <RefreshCw class="size-3.5" :class="reverifying ? 'animate-spin' : ''" />
          {{ reverifying ? 'Verificando…' : 'Re-verificar soportes' }}
        </Button>
      </div>

      <div v-if="soportesOpen && soportes.files.length" class="max-h-64 overflow-auto border-t border-border">
        <table class="w-full text-xs">
          <tbody>
            <tr
              v-for="f in soportes.files"
              :key="f.path"
              class="border-b border-border/60"
              :class="!f.has_cufe && f.extraction_status ? 'bg-status-error-bg/40' : ''"
            >
              <td class="w-6 px-3 py-1.5 text-center align-top">
                <span v-if="f.has_cufe" class="text-status-success" title="CUFE encontrado">✓</span>
                <span v-else-if="f.extraction_status" class="text-status-error" title="No se encontró CUFE">⚠</span>
                <span v-else class="text-muted-foreground" title="Sin verificar aún">•</span>
              </td>
              <td class="px-2 py-1.5 align-top font-mono break-all">{{ f.name }}</td>
              <td class="px-3 py-1.5 align-top text-right font-mono text-muted-foreground">
                <span v-if="f.cufe" :title="f.cufe">
                  <span v-if="f.label" class="mr-1 rounded bg-muted px-1 text-[10px] uppercase">{{ f.label }}</span>{{ f.cufe.slice(0, 12) }}…{{ f.cufe.slice(-8) }}
                </span>
                <span v-else-if="f.extraction_status" class="italic text-status-error">sin CUFE</span>
                <span v-else class="italic">sin verificar</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="soportesOpen" class="border-t border-border px-3 py-4 text-center text-xs text-muted-foreground">
        {{ soportes.error || 'No hay PDFs en la carpeta de este mes.' }}
      </div>
    </section>


    <Dialog v-model:open="renameOpen">
      <DialogContent class="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Renombrar soportes</DialogTitle>
          <DialogDescription>
            Patrón <span class="font-mono">DD-MM_NIT_RAZÓN-SOCIAL_FACTURA</span>, tomado del cruce con el Excel del mes.
            Se renombran en la misma carpeta y se deja un manifiesto <span class="font-mono">_renombrados.csv</span> para revertir.
          </DialogDescription>
        </DialogHeader>

        <div v-if="renamePlan" class="flex flex-col gap-3">
          <p class="text-sm text-muted-foreground">
            <span class="font-medium text-status-success">{{ (renamePlan.counts.rename || 0) + (renamePlan.counts.renamed || 0) }} a renombrar</span>
            <template v-if="renamePlan.counts.already"> · {{ renamePlan.counts.already }} ya con su nombre</template>
            <template v-if="(renamePlan.counts.nomatch || 0) + (renamePlan.counts.skip || 0)"> · {{ (renamePlan.counts.nomatch || 0) + (renamePlan.counts.skip || 0) }} sin identificar</template>
            <template v-if="renamePlan.counts.error"> · <span class="text-status-error">{{ renamePlan.counts.error }} con error</span></template>
          </p>

          <div class="max-h-[46vh] overflow-auto rounded-md border border-border">
            <table class="w-full text-xs">
              <thead class="sticky top-0 bg-muted">
                <tr class="text-left text-muted-foreground">
                  <th class="px-2 py-1.5 font-medium">Actual</th>
                  <th class="px-2 py-1.5 font-medium"></th>
                  <th class="px-2 py-1.5 font-medium">Nuevo / motivo</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(it, i) in renamePlan.items" :key="i" class="border-t border-border/60 align-top">
                  <td class="px-2 py-1 font-mono break-all">{{ it.current_name }}</td>
                  <td class="px-2 py-1 text-muted-foreground">→</td>
                  <td class="px-2 py-1 font-mono break-all">
                    <span v-if="it.new_name" :class="it.status === 'renamed' ? 'text-status-success' : it.status === 'already' ? 'text-muted-foreground' : ''">{{ it.new_name }}</span>
                    <span v-else class="italic text-muted-foreground">{{ it.reason }}</span>
                    <span v-if="it.status === 'error'" class="text-status-error"> · {{ it.reason }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p v-if="renameApplied && renamePlan.manifest" class="break-all font-mono text-xs text-status-success">
            ✓ Aplicado. Manifiesto: {{ renamePlan.manifest }}
          </p>
        </div>

        <DialogFooter>
          <Button variant="ghost" @click="renameOpen = false">{{ renameApplied ? 'Cerrar' : 'Cancelar' }}</Button>
          <Button
            v-if="!renameApplied"
            :disabled="applyingRename || !(renamePlan && renamePlan.counts.rename)"
            @click="applyRename"
          >
            {{ applyingRename ? 'Renombrando…' : `Aplicar (${renamePlan?.counts.rename ?? 0})` }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <section v-if="loading && !data" class="min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-card">
      <div class="data-table-wrapper">
        <table class="data">
          <thead>
            <tr><th v-for="n in 8" :key="n">···</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in 8" :key="r"><td v-for="c in 8" :key="c"><span class="skel-bar" /></td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-else-if="data && !data.rows.length" class="rounded-lg border border-border bg-card py-10 text-center">
      <div class="text-4xl opacity-40">📭</div>
      <h3 class="mt-2 font-heading text-lg text-foreground">Carga vacía</h3>
      <p class="text-sm text-muted-foreground">El Excel no tiene filas de datos.</p>
    </section>

    <section v-else-if="data" class="min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-card">
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
                    class="inline-flex items-center justify-center rounded-full bg-status-error-bg px-1.5 text-status-error"
                    :title="failuresByRow.get(Number(row.id))"
                  >⚠</span>
                </template>
                <template v-else-if="hasValidationRun">
                  <span class="font-bold text-status-success opacity-70" title="Pasa todas las validaciones">✓</span>
                </template>
              </td>
              <td
                v-for="cell in row.getVisibleCells()"
                :key="cell.id"
                :class="{ num: numericColumns.has(cell.column.id) }"
              >
                <template v-if="cell.column.id === 'Tipo de documento' && isNotaCredito(row.original as Row)">
                  <span class="mr-1.5 inline-flex items-center rounded-full bg-status-error-bg px-1.5 text-[10px] font-medium text-status-error">NC</span>
                </template>
                <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
              </td>
              <td class="approve-col">
                <template v-if="v3FailingRows.has(Number(row.id)) || v3Overrides.has(Number(row.id))">
                  <label class="inline-flex cursor-pointer items-center justify-center rounded p-1 hover:bg-accent" :title="v3Overrides.has(Number(row.id)) ? 'Aprobado: V3 ignorado para esta fila' : 'Aprobar V3 manualmente'">
                    <input
                      type="checkbox"
                      class="size-4 cursor-pointer accent-primary"
                      :checked="v3Overrides.has(Number(row.id))"
                      :disabled="togglingOverride === Number(row.id)"
                      @change="toggleOverride(Number(row.id))"
                    >
                  </label>
                </template>
              </td>
            </tr>
            <tr v-if="onlyFailing && table.getRowModel().rows.length === 0">
              <td :colspan="visibleCount + 2" class="py-6 text-center text-sm text-muted-foreground">
                Sin filas no conformes con el filtro actual.
                <Button variant="ghost" size="sm" class="ml-1" @click="onlyFailing = false">Mostrar todas</Button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* Data grid — token-based (no raw hex / palette utilities). The wrapper fills its flex parent
   (height:100%) so ONLY the table scrolls — the page itself never grows (no double scroll). */
.data-table-wrapper { overflow: auto; height: 100%; }
table.data {
  border-collapse: separate; border-spacing: 0;
  width: max-content; min-width: 100%;
  font-size: 0.8rem; font-variant-numeric: tabular-nums;
}
table.data th, table.data td {
  padding: 0.3rem 0.6rem;
  border-bottom: 1px solid var(--border);
  white-space: nowrap; vertical-align: middle;
}
table.data th {
  background: var(--muted);
  position: sticky; top: 0; z-index: 1;
  text-align: left; font-weight: 600;
  color: var(--muted-foreground);
  font-size: 0.72rem;
}
table.data td.num, table.data th.num { text-align: right; }
table.data tbody tr:hover td { background: color-mix(in oklab, var(--primary) 5%, transparent); }

.status-col {
  width: 34px; text-align: center !important;
  padding: 0.25rem 0.4rem !important;
  position: sticky; left: 0; z-index: 2;
  background: var(--muted);
  border-right: 1px solid var(--border);
}
table.data tbody tr:hover .status-col { background: color-mix(in oklab, var(--primary) 8%, var(--muted)); }

.approve-col {
  width: 84px; text-align: center !important;
  padding: 0.25rem 0.5rem !important;
  position: sticky; right: 0; z-index: 2;
  background: var(--muted);
  border-left: 1px solid var(--border);
  font-size: 0.68rem; color: var(--muted-foreground);
  font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
}
table.data tbody tr:hover .approve-col { background: color-mix(in oklab, var(--primary) 8%, var(--muted)); }

.row-failing td:not(.status-col):not(.approve-col) { background: color-mix(in oklab, var(--status-error) 8%, transparent) !important; }
.row-failing:hover td:not(.status-col):not(.approve-col) { background: color-mix(in oklab, var(--status-error) 14%, transparent) !important; }
.row-overridden td:not(.status-col):not(.approve-col) { background: color-mix(in oklab, var(--status-success) 8%, transparent) !important; }
.row-overridden:hover td:not(.status-col):not(.approve-col) { background: color-mix(in oklab, var(--status-success) 14%, transparent) !important; }

.skel-bar {
  display: block; height: 0.7rem; width: 70%; border-radius: 4px;
  background: linear-gradient(90deg, var(--muted), var(--accent), var(--muted));
  background-size: 200% 100%;
  animation: skel-shimmer 1.4s linear infinite;
}
@keyframes skel-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
