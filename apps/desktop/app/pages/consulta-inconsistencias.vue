<script setup lang="ts">
import { ArrowLeft, Download, FolderOpen, RotateCcw, Search, UploadCloud, X } from 'lucide-vue-next'

type RowStatus = 'pending' | 'ok' | 'notfound' | 'error'
type Tipo = 'empresa' | 'persona' | null
type Row = { nit: string; dv: string; razon_social: string; tipo: Tipo; status: RowStatus; error: string | null }
type ParsedRow = { row_index: number; nit: string; dv: string }
type UploadResp =
  | { ok: true; path: string; rows: ParsedRow[]; total: number; detected: { nit_col: number; dv_col: number | null } }
  | { ok: false; error: string }
type ConsultaResp = { nit: string; dv: string; razon_social: string; tipo: Tipo; found: boolean; error: string | null }
type ExportResult = { path: string; rows_written: number }

const DELAY_MS = 450 // pausa cortés entre consultas (no martillar el balanceador de la DIAN)

const toast = useToast()

const file = ref<File | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const rows = ref<Row[]>([])
const running = ref(false)
const cancelRequested = ref(false)
const started = ref(false)

const exportFolder = ref('')
const exportPickerOpen = ref(false)
const exporting = ref(false)
const exportResult = ref<ExportResult | null>(null)

const total = computed(() => rows.value.length)
const doneCount = computed(() => rows.value.filter((r) => r.status !== 'pending').length)
const foundCount = computed(() => rows.value.filter((r) => r.status === 'ok').length)
const notFoundCount = computed(() => rows.value.filter((r) => r.status === 'notfound').length)
const errorCount = computed(() => rows.value.filter((r) => r.status === 'error').length)
const pendingCount = computed(() => rows.value.filter((r) => r.status === 'pending').length)
const percent = computed(() => (total.value ? Math.round((doneCount.value / total.value) * 100) : 0))
const finished = computed(() => started.value && !running.value && pendingCount.value === 0 && total.value > 0)

const buildFilename = () => {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const s = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  return `inconsistencias_${s}.xlsx`
}
const exportPath = computed(() => {
  if (!exportFolder.value) return ''
  return `${exportFolder.value.replace(/[/\\]+$/, '')}/${buildFilename()}`
})

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

function pickFile(files: FileList | null) {
  if (!files || !files.length) return
  const f = files[0]
  if (!f.name.toLowerCase().endsWith('.xlsx')) {
    toast.error('Solo se permiten archivos Excel (.xlsx).')
    return
  }
  file.value = f
}

function onDrop(e: DragEvent) {
  dragging.value = false
  pickFile(e.dataTransfer?.files ?? null)
}

async function upload() {
  if (!file.value || uploading.value) return
  uploading.value = true
  exportResult.value = null
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    const data = await $fetch<UploadResp>('/api/consulta-inconsistencias/upload', { method: 'POST', body: fd })
    if (!data.ok) {
      toast.error('No se pudo leer el Excel', data.error)
      return
    }
    if (!data.rows.length) {
      toast.warn('El Excel no tiene filas con NIT.')
      return
    }
    rows.value = data.rows.map((r) => ({ nit: r.nit, dv: r.dv, razon_social: '', tipo: null, status: 'pending', error: null }))
    started.value = false
    if (data.detected.dv_col === null) {
      toast.info('No vi columna de DV — la calculé automáticamente para cada NIT.')
    }
    toast.success(`${data.rows.length} NIT cargados`, 'Pulsa "Consultar" para traer las razones sociales.')
  } catch (e) {
    toast.error('Error al subir el archivo', String(e))
  } finally {
    uploading.value = false
  }
}

async function consultarRango(targets: Row[]) {
  if (running.value) return
  running.value = true
  started.value = true
  cancelRequested.value = false
  try {
    for (const row of targets) {
      if (cancelRequested.value) break
      try {
        const r = await rpc<ConsultaResp>('consulta_inconsistencias', { nit: row.nit, dv: row.dv })
        row.razon_social = r.razon_social
        row.tipo = r.tipo
        row.error = r.error
        if (r.found) row.status = 'ok'
        else if (r.error && !r.error.startsWith('Sin resultado')) row.status = 'error'
        else row.status = 'notfound'
      } catch (e) {
        row.status = 'error'
        row.error = String(e)
      }
      await sleep(DELAY_MS)
    }
  } finally {
    running.value = false
    if (!cancelRequested.value && pendingCount.value === 0) {
      toast.success('Consulta terminada', `${foundCount.value} encontrados · ${notFoundCount.value} sin resultado · ${errorCount.value} con error`)
    }
  }
}

const consultarTodos = () => consultarRango(rows.value.filter((r) => r.status === 'pending'))

function reintentarFallidos() {
  const failed = rows.value.filter((r) => r.status === 'error')
  for (const r of failed) { r.status = 'pending'; r.error = null }
  consultarRango(failed)
}

function cancelar() {
  cancelRequested.value = true
  toast.info('Deteniendo…', 'Se detendrá al terminar la consulta en curso.')
}

async function exportar() {
  if (!exportPath.value) { toast.warn('Elige una carpeta de salida primero'); return }
  exporting.value = true
  try {
    exportResult.value = await rpc<ExportResult>('export_inconsistencias', {
      rows: rows.value.map((r) => ({ nit: r.nit, dv: r.dv, razon_social: r.razon_social, tipo: r.tipo })),
      output_path: exportPath.value,
    })
    toast.success(`Exportado (${exportResult.value.rows_written} filas)`, exportResult.value.path)
  } catch (e) {
    toast.error('Error al exportar', String(e))
  } finally {
    exporting.value = false
  }
}

function onExportFolderPicked(path: string) {
  exportFolder.value = path
  exportPickerOpen.value = false
  toast.info('Carpeta de salida elegida', path)
}

function reset() {
  file.value = null
  rows.value = []
  started.value = false
  running.value = false
  cancelRequested.value = false
  exportResult.value = null
  exportFolder.value = ''
}

function statusBadgeClass(s: RowStatus): string {
  if (s === 'ok') return 'bg-status-success-bg text-status-success'
  if (s === 'error') return 'bg-status-error-bg text-status-error'
  if (s === 'notfound') return 'bg-muted text-muted-foreground'
  return 'bg-muted text-muted-foreground'
}
function statusLabel(s: RowStatus): string {
  if (s === 'ok') return 'OK'
  if (s === 'error') return 'Error'
  if (s === 'notfound') return 'Sin resultado'
  return 'Pendiente'
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-5xl flex-col gap-4">
    <NuxtLink to="/consulta-dian" class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
      <ArrowLeft class="size-3.5" /> Consultas DIAN
    </NuxtLink>

    <div>
      <h1 class="font-heading text-2xl font-medium tracking-tight">Consulta DIAN · Inconsistencias</h1>
      <p class="text-sm text-muted-foreground">
        Sube un Excel con las columnas <span class="font-mono">NIT</span> y <span class="font-mono">DV</span>
        (dígito de verificación) y Contab trae el nombre de cada tercero desde el portal MUISCA:
        <strong>Razón Social</strong> si es empresa, o el <strong>nombre completo</strong> si es persona natural
        (va el documento en la columna NIT). El resultado se exporta a Excel.
        <span class="text-muted-foreground">Si falta el DV, se calcula solo.</span>
      </p>
    </div>

    <!-- Paso 1: cargar archivo -->
    <Card v-if="!rows.length">
      <CardContent class="flex flex-col gap-4">
        <div
          class="flex flex-col items-center gap-2 rounded-lg border-[1.5px] border-dashed px-4 py-6 text-center transition-colors"
          :class="dragging ? 'border-primary bg-primary/5' : 'border-input'"
          @dragenter.prevent="dragging = true"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <UploadCloud class="size-6 text-muted-foreground" />
          <p v-if="file">Archivo: <span class="font-mono">{{ file.name }}</span></p>
          <p v-else class="text-muted-foreground">Arrastra aquí tu Excel <span class="font-mono">.xlsx</span> o selecciónalo</p>
          <Button as-child variant="outline" size="sm">
            <label class="cursor-pointer">
              Elegir archivo
              <input type="file" accept=".xlsx" hidden @change="pickFile(($event.target as HTMLInputElement).files)">
            </label>
          </Button>
        </div>
        <div class="flex items-center gap-3">
          <Button :disabled="!file || uploading" @click="upload">
            {{ uploading ? 'Leyendo…' : 'Cargar NITs' }}
          </Button>
        </div>
      </CardContent>
    </Card>

    <!-- Paso 2/3: consultar + resultado -->
    <template v-else>
      <Card>
        <CardContent class="flex flex-col gap-3">
          <!-- barra de acciones -->
          <div class="flex flex-wrap items-center gap-3">
            <Button v-if="pendingCount && !running" @click="consultarTodos">
              <Search class="size-4" /> Consultar {{ pendingCount }} tercero{{ pendingCount === 1 ? '' : 's' }}
            </Button>
            <Button v-if="running" variant="secondary" @click="cancelar">
              <X class="size-4" /> Detener
            </Button>
            <Button v-if="!running && errorCount" variant="secondary" @click="reintentarFallidos">
              <RotateCcw class="size-4" /> Reintentar {{ errorCount }} con error
            </Button>
            <Button variant="ghost" :disabled="running" @click="reset">Nueva consulta</Button>
          </div>

          <!-- progreso -->
          <div class="flex items-center gap-3">
            <div class="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div class="h-full bg-primary transition-[width] duration-300" :style="{ width: percent + '%' }" />
            </div>
            <span class="font-mono text-sm tabular-nums">{{ doneCount }} / {{ total }}</span>
          </div>
          <p class="text-sm text-muted-foreground">
            <span class="text-status-success">{{ foundCount }} encontrados</span> ·
            {{ notFoundCount }} sin resultado ·
            <span :class="errorCount ? 'text-status-error' : ''">{{ errorCount }} con error</span>
          </p>

          <!-- exportar -->
          <div class="flex flex-wrap items-center gap-3 border-t border-border pt-3">
            <Button variant="secondary" :disabled="running" @click="exportPickerOpen = true">
              <FolderOpen class="size-4" /> Carpeta de salida
            </Button>
            <Button :disabled="exporting || !exportPath || running || !finished" @click="exportar">
              <Download class="size-4" /> Exportar a Excel
            </Button>
            <span v-if="!finished && started" class="text-xs text-muted-foreground">Termina la consulta para exportar.</span>
          </div>
          <p v-if="exportPath && !exportResult" class="break-all font-mono text-xs text-muted-foreground">
            Se guardará en: {{ exportPath }}
          </p>
          <p v-if="exportResult" class="break-all font-mono text-xs text-status-success">
            ✓ Guardado en: {{ exportResult.path }}
          </p>
        </CardContent>
      </Card>

      <!-- tabla de resultados en vivo -->
      <Card>
        <CardContent class="p-0">
          <div class="max-h-[52vh] overflow-auto">
            <table class="w-full text-sm">
              <thead class="sticky top-0 bg-card">
                <tr class="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th class="px-3 py-2 font-medium">#</th>
                  <th class="px-3 py-2 font-medium">NIT</th>
                  <th class="px-3 py-2 font-medium">DV</th>
                  <th class="px-3 py-2 font-medium">Razón Social / Nombre</th>
                  <th class="px-3 py-2 font-medium">Tipo</th>
                  <th class="px-3 py-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in rows" :key="i" class="border-b border-border/60 last:border-0">
                  <td class="px-3 py-1.5 font-mono tabular-nums text-muted-foreground">{{ i + 1 }}</td>
                  <td class="px-3 py-1.5 font-mono tabular-nums">{{ r.nit }}</td>
                  <td class="px-3 py-1.5 font-mono tabular-nums text-muted-foreground">{{ r.dv }}</td>
                  <td class="px-3 py-1.5">
                    <span v-if="r.razon_social">{{ r.razon_social }}</span>
                    <span v-else-if="r.error && r.status === 'error'" class="text-status-error">{{ r.error }}</span>
                    <span v-else class="text-muted-foreground">—</span>
                  </td>
                  <td class="px-3 py-1.5">
                    <span v-if="r.tipo === 'persona'" class="text-xs text-muted-foreground">Persona</span>
                    <span v-else-if="r.tipo === 'empresa'" class="text-xs text-muted-foreground">Empresa</span>
                    <span v-else class="text-muted-foreground">—</span>
                  </td>
                  <td class="px-3 py-1.5">
                    <span class="inline-flex rounded-full px-2 py-0.5 text-xs font-medium" :class="statusBadgeClass(r.status)">
                      {{ statusLabel(r.status) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </template>

    <DirectoryPicker
      :open="exportPickerOpen"
      :initial-path="''"
      title="Carpeta donde se guardará el Excel de razones sociales"
      @pick="onExportFolderPicked"
      @close="exportPickerOpen = false"
    />
  </div>
</template>
