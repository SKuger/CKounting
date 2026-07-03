<script setup lang="ts">
import { ArrowLeft, Pencil, FolderOpen, FileSpreadsheet, Trash2, Archive, Download, ChevronRight, EllipsisVertical, CalendarPlus, RotateCcw, FolderSearch } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '~/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '~/components/ui/select'

type EmpresaInfo = {
  db_path: string
  nit: string
  dv: string | null
  razon_social: string
  default_folder: string | null
  archived?: boolean
  created_at: string
}
type Periodo = { periodo: string; load_count: number; row_count: number; pdfs_folder: string | null; indexed_cufe_count: number }
type Carga = { id: number; source_name: string; loaded_at: string; total_rows: number; periodo?: string | null; deleted?: boolean }
type FolderFile = { name: string; path: string; size_bytes: number; mtime: string; imported: boolean; imported_as_load_id: number | null }
type FolderListing = { folder: string | null; files: FolderFile[]; error: string | null }
type BackupResult = { path: string; size_bytes: number; excels_included: number; pdfs_included: number }

const route = useRoute()
const dbPath = computed(() => (route.query.db as string) || '')
const toast = useToast()

const info = ref<EmpresaInfo | null>(null)
const periodos = ref<Periodo[]>([])
const loads = ref<Carga[]>([])
const folderListing = ref<FolderListing>({ folder: null, files: [], error: null })
const loading = ref(false)
const busy = ref(false)

// gestión de empresa (se conserva)
const editingRazon = ref(false)
const razonDraft = ref('')
const savingRazon = ref(false)
const folderPickerOpen = ref(false)
const savingFolder = ref(false)
const backupPickerOpen = ref(false)
const backingUp = ref(false)
const archiveModalOpen = ref(false)
const archiving = ref(false)
const deleteModalOpen = ref(false)
const deleteConfirmNit = ref('')
const deleting = ref(false)

// meses
const newMonthOpen = ref(false)
const newMonth = ref('')
const creatingMonth = ref(false)
const deleteMonthTarget = ref<string | null>(null)
const periodoPickerOpen = ref(false)
const periodoPickerTarget = ref<string | null>(null)
const loadPickerFor = ref<string | null>(null) // periodo para el que se elige Excel
const moveTarget = ref<Carga | null>(null)
const moveDestino = ref('')
const showTrash = ref(false)

const activeLoadsByPeriodo = computed(() => {
  const m = new Map<string, Carga[]>()
  for (const l of loads.value) {
    if (l.deleted || !l.periodo) continue
    if (!m.has(l.periodo)) m.set(l.periodo, [])
    m.get(l.periodo)!.push(l)
  }
  return m
})
const trashedLoads = computed(() => loads.value.filter((l) => l.deleted))
const excelChoices = computed(() => folderListing.value.files.filter((f) => f.name.toLowerCase().endsWith('.xlsx') || f.name.toLowerCase().endsWith('.xls')))

function humanError(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e)
  return m.replace(/^Error:\s*/, '').trim() || 'Ocurrió un error inesperado.'
}
function folderName(path: string): string {
  return path.replace(/[/\\]+$/, '').split(/[/\\]/).pop() || path
}
function monthLabel(periodo: string): string {
  const [y, m] = periodo.split('-').map(Number)
  if (!y || !m) return periodo
  const s = new Date(y, m - 1, 1).toLocaleDateString('es-CO', { month: 'long', year: 'numeric' })
  return s.charAt(0).toUpperCase() + s.slice(1)
}

async function refresh() {
  if (!dbPath.value) return
  loading.value = true
  try {
    info.value = await rpc<EmpresaInfo>('open_empresa', { db_path: dbPath.value })
    await Promise.all([reloadPeriodos(), reloadLoads(), refreshFolderListing()])
  } catch (exc) {
    toast.error('No se pudo abrir la empresa', humanError(exc))
  } finally {
    loading.value = false
  }
}
async function reloadPeriodos() {
  periodos.value = await rpc<Periodo[]>('list_periodos', { db_path: dbPath.value })
}
async function reloadLoads() {
  loads.value = await rpc<Carga[]>('list_loads', { db_path: dbPath.value, include_deleted: true })
}
async function refreshFolderListing() {
  if (!info.value?.default_folder) {
    folderListing.value = { folder: null, files: [], error: null }
    return
  }
  try {
    folderListing.value = await rpc<FolderListing>('list_folder_files', { db_path: dbPath.value })
  } catch (exc) {
    folderListing.value = { folder: null, files: [], error: humanError(exc) }
  }
}

// ── carpeta de Excels de la empresa (fuente; D-036 auto-listado) ──
async function persistFolder(folder: string | null) {
  savingFolder.value = true
  try {
    info.value = await rpc<EmpresaInfo>('set_default_folder', { db_path: dbPath.value, folder })
    await refreshFolderListing()
  } catch (exc) {
    toast.error('No se pudo guardar la carpeta', humanError(exc))
  } finally {
    savingFolder.value = false
  }
}
function onFolderPicked(path: string) { folderPickerOpen.value = false; persistFolder(path) }

// ── meses ──
async function createMonth() {
  if (!/^\d{4}-\d{2}$/.test(newMonth.value)) { toast.warn('Elige un mes válido'); return }
  creatingMonth.value = true
  try {
    await rpc('create_periodo', { db_path: dbPath.value, periodo: newMonth.value })
    newMonthOpen.value = false
    newMonth.value = ''
    await reloadPeriodos()
  } catch (exc) {
    toast.error('No se pudo crear el mes', humanError(exc))
  } finally {
    creatingMonth.value = false
  }
}
async function confirmDeleteMonth() {
  const periodo = deleteMonthTarget.value
  if (!periodo) return
  busy.value = true
  try {
    await rpc('delete_periodo', { db_path: dbPath.value, periodo })
    toast.success(`Mes ${periodo} borrado`)
    deleteMonthTarget.value = null
    await Promise.all([reloadPeriodos(), reloadLoads()])
  } catch (exc) {
    toast.error('No se pudo borrar el mes', humanError(exc))
  } finally {
    busy.value = false
  }
}

// ── carpeta de soportes DEL MES ──
function openPeriodoPicker(periodo: string) { periodoPickerTarget.value = periodo; periodoPickerOpen.value = true }
async function setPeriodoFolder(periodo: string, folder: string | null) {
  busy.value = true
  try {
    await rpc('set_periodo_pdfs_folder', { db_path: dbPath.value, periodo, folder })
    await reloadPeriodos()
  } catch (exc) {
    toast.error('No se pudo guardar la carpeta de soportes', humanError(exc))
  } finally {
    busy.value = false
  }
}
function onPeriodoFolderPicked(path: string) {
  const periodo = periodoPickerTarget.value
  periodoPickerOpen.value = false
  if (periodo) setPeriodoFolder(periodo, path)
}

// ── Excel del mes: cargar (desde la carpeta) / mover / papelera / restaurar ──
async function importInto(periodo: string, sourcePath: string) {
  busy.value = true
  try {
    await rpc('import_excel', { db_path: dbPath.value, source_path: sourcePath, periodo })
    loadPickerFor.value = null
    toast.success('Excel cargado en el mes')
    await Promise.all([reloadPeriodos(), reloadLoads(), refreshFolderListing()])
  } catch (exc) {
    toast.error('No se pudo cargar el Excel', humanError(exc))
  } finally {
    busy.value = false
  }
}
async function confirmMove() {
  if (!moveTarget.value || !moveDestino.value) return
  busy.value = true
  try {
    await rpc('set_load_periodo', { db_path: dbPath.value, load_id: moveTarget.value.id, periodo: moveDestino.value })
    toast.success('Excel movido de mes')
    moveTarget.value = null
    moveDestino.value = ''
    await Promise.all([reloadPeriodos(), reloadLoads()])
  } catch (exc) {
    toast.error('No se pudo mover el Excel', humanError(exc))
  } finally {
    busy.value = false
  }
}
async function trashLoad(load: Carga) {
  busy.value = true
  try {
    await rpc('soft_delete_load', { db_path: dbPath.value, load_id: load.id })
    toast.success('Excel enviado a la papelera')
    await Promise.all([reloadPeriodos(), reloadLoads()])
  } catch (exc) {
    toast.error('No se pudo enviar a la papelera', humanError(exc))
  } finally {
    busy.value = false
  }
}
async function restoreLoad(load: Carga) {
  busy.value = true
  try {
    await rpc('restore_load', { db_path: dbPath.value, load_id: load.id })
    toast.success('Excel restaurado')
    await Promise.all([reloadPeriodos(), reloadLoads()])
  } catch (exc) {
    toast.error('No se pudo restaurar', humanError(exc))
  } finally {
    busy.value = false
  }
}

// ── gestión de empresa (conservada) ──
function startEditingRazon() { if (info.value) { razonDraft.value = info.value.razon_social; editingRazon.value = true } }
async function saveRazon() {
  if (!razonDraft.value.trim()) return
  savingRazon.value = true
  try {
    info.value = await rpc<EmpresaInfo>('update_empresa', { db_path: dbPath.value, razon_social: razonDraft.value.trim() })
    editingRazon.value = false
    toast.success('Razón social actualizada')
  } catch (exc) {
    toast.error('No se pudo actualizar', humanError(exc))
  } finally {
    savingRazon.value = false
  }
}
async function onBackupFolderPicked(folder: string) {
  backupPickerOpen.value = false
  backingUp.value = true
  try {
    const r = await rpc<BackupResult>('backup_empresa', { db_path: dbPath.value, dest_folder: folder })
    toast.success(`Backup creado (${fmtSize(r.size_bytes)})`, `${r.excels_included} Excels + ${r.pdfs_included} PDFs`)
  } catch (exc) {
    toast.error('No se pudo hacer el backup', humanError(exc))
  } finally {
    backingUp.value = false
  }
}
async function confirmArchive() {
  archiving.value = true
  try {
    await rpc('archive_empresa', { db_path: dbPath.value })
    toast.success('Empresa archivada')
    await navigateTo('/')
  } catch (exc) {
    toast.error('No se pudo archivar', humanError(exc))
    archiving.value = false
  }
}
function openDeleteModal() { deleteConfirmNit.value = ''; deleteModalOpen.value = true }
async function confirmDelete() {
  if (!info.value || deleteConfirmNit.value.trim() !== info.value.nit) return
  deleting.value = true
  try {
    await rpc('delete_empresa', { db_path: dbPath.value, confirm_nit: deleteConfirmNit.value.trim() })
    toast.success('Empresa eliminada permanentemente')
    await navigateTo('/')
  } catch (exc) {
    toast.error('No se pudo eliminar', humanError(exc))
    deleting.value = false
  }
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  return `${(bytes / (1024 ** 3)).toFixed(2)} GB`
}

onMounted(refresh)
watch(dbPath, refresh)
</script>

<template>
  <div class="mx-auto flex w-full max-w-6xl flex-col gap-4">
    <!-- Header -->
    <header v-if="info" class="flex flex-wrap items-end justify-between gap-3">
      <div class="min-w-0 flex-1">
        <NuxtLink to="/" class="mb-1 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft class="size-3.5" /> Empresas
        </NuxtLink>
        <div class="flex flex-wrap items-center gap-2">
          <template v-if="editingRazon">
            <Input v-model="razonDraft" :disabled="savingRazon" class="h-10 max-w-sm text-lg" @keyup.enter="saveRazon" @keyup.escape="editingRazon = false" />
            <Button variant="secondary" :disabled="savingRazon || !razonDraft.trim()" @click="saveRazon">{{ savingRazon ? 'Guardando…' : 'Guardar' }}</Button>
            <Button variant="ghost" :disabled="savingRazon" @click="editingRazon = false">Cancelar</Button>
          </template>
          <template v-else>
            <h1 class="font-heading text-2xl font-medium tracking-tight">{{ info.razon_social }}</h1>
            <Button variant="ghost" size="sm" title="Editar razón social" @click="startEditingRazon"><Pencil class="size-3.5" /> Editar</Button>
          </template>
        </div>
        <p class="text-sm text-muted-foreground">
          NIT <strong class="text-foreground">{{ info.nit }}{{ info.dv ? `-${info.dv}` : '' }}</strong>
          <span class="mx-1.5 text-border">·</span>
          <span v-if="info.default_folder" class="text-xs" :title="info.default_folder">Carpeta de Excels: <span class="text-foreground">{{ folderName(info.default_folder) }}</span></span>
          <span v-else class="text-xs">sin carpeta de Excels</span>
        </p>
      </div>
      <div class="flex gap-2">
        <Button variant="secondary" data-tour="empresa-carpeta" :disabled="savingFolder" @click="folderPickerOpen = true">
          <FolderOpen class="size-4" /> {{ info.default_folder ? 'Cambiar carpeta de Excels' : 'Elegir carpeta de Excels' }}
        </Button>
        <Popover>
          <PopoverTrigger as-child>
            <Button variant="outline" size="icon" aria-label="Más acciones"><EllipsisVertical class="size-4" /></Button>
          </PopoverTrigger>
          <PopoverContent align="end" :side-offset="6" class="w-56 p-1">
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent disabled:opacity-50" :disabled="backingUp" @click="backupPickerOpen = true">
              <Download class="size-4" /> {{ backingUp ? 'Generando…' : 'Hacer backup' }}
            </button>
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent disabled:opacity-50" :disabled="archiving" @click="archiveModalOpen = true">
              <Archive class="size-4" /> Archivar
            </button>
            <div class="my-1 h-px bg-border" />
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-destructive transition-colors hover:bg-accent" @click="openDeleteModal">
              <Trash2 class="size-4" /> Eliminar permanentemente
            </button>
          </PopoverContent>
        </Popover>
      </div>
    </header>

    <Card v-else-if="loading"><CardContent class="py-10 text-center text-muted-foreground">Cargando empresa…</CardContent></Card>
    <Card v-else><CardContent class="py-6"><div class="rounded-md border border-status-error/30 bg-status-error-bg px-3 py-2 text-sm text-status-error">Empresa no encontrada. <NuxtLink to="/" class="underline">Volver</NuxtLink></div></CardContent></Card>

    <!-- Meses (ambientes) -->
    <Card v-if="info" data-tour="empresa-periodos">
      <CardHeader>
        <CardTitle>Meses</CardTitle>
        <CardDescription>Cada mes es un ambiente: su Excel, su carpeta de soportes y su validación.</CardDescription>
        <CardAction class="flex items-center gap-2">
          <Button v-if="trashedLoads.length" variant="ghost" size="sm" :class="showTrash ? 'text-foreground' : ''" @click="showTrash = !showTrash">
            <RotateCcw class="size-4" /> Papelera ({{ trashedLoads.length }})
          </Button>
          <Button size="sm" data-tour="empresa-crear-mes" @click="newMonthOpen = true"><CalendarPlus class="size-4" /> Crear mes</Button>
        </CardAction>
      </CardHeader>
      <CardContent class="flex flex-col gap-3">
        <p v-if="!periodos.length" class="py-8 text-center text-sm text-muted-foreground">
          Aún no hay meses. Crea el primero con <strong class="text-foreground">«Crear mes»</strong> y luego carga su Excel.
        </p>

        <div v-for="p in periodos" :key="p.periodo" class="rounded-lg border border-border bg-card p-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="min-w-0">
              <div class="font-medium">{{ monthLabel(p.periodo) }} <span class="font-mono text-xs text-muted-foreground">{{ p.periodo }}</span></div>
              <div class="text-xs text-muted-foreground">{{ p.load_count }} Excel · {{ p.row_count }} filas · {{ p.indexed_cufe_count }} CUFE indexados</div>
            </div>
            <div class="flex items-center gap-1.5">
              <Button variant="secondary" size="sm" :disabled="busy" @click="openPeriodoPicker(p.periodo)">
                <FolderOpen class="size-4" /> {{ p.pdfs_folder ? 'Cambiar soportes' : 'Elegir soportes' }}
              </Button>
              <Button variant="ghost" size="icon-sm" title="Borrar mes" :disabled="busy" @click="deleteMonthTarget = p.periodo"><Trash2 class="size-4" /></Button>
            </div>
          </div>

          <div class="mt-1 text-xs text-muted-foreground" :title="p.pdfs_folder || ''">
            Soportes: <span v-if="p.pdfs_folder" class="text-foreground">{{ folderName(p.pdfs_folder) }}</span><span v-else>sin carpeta</span>
          </div>

          <!-- Excel del mes -->
          <div class="mt-2 border-t border-dashed border-border pt-2">
            <template v-if="activeLoadsByPeriodo.get(p.periodo)?.length">
              <div v-for="c in activeLoadsByPeriodo.get(p.periodo)" :key="c.id" class="flex flex-wrap items-center gap-2 py-1">
                <FileSpreadsheet class="size-4 shrink-0 text-muted-foreground" />
                <span class="min-w-0 flex-1 truncate text-sm">{{ c.source_name }} <span class="text-muted-foreground">· {{ c.total_rows }} filas</span></span>
                <Button size="sm" @click="navigateTo({ path: '/load', query: { db: dbPath, id: c.id } })">Abrir y validar <ChevronRight class="size-3.5" /></Button>
                <Button variant="ghost" size="sm" :disabled="busy" @click="moveTarget = c">Mover</Button>
                <Button variant="ghost" size="icon-sm" title="Enviar a papelera" :disabled="busy" @click="trashLoad(c)"><Trash2 class="size-4" /></Button>
              </div>
            </template>
            <div v-else class="flex items-center justify-between gap-2">
              <span class="text-sm text-muted-foreground">Sin Excel en este mes.</span>
              <Button variant="outline" size="sm" :disabled="busy || !info.default_folder" :title="info.default_folder ? '' : 'Primero elige la carpeta de Excels de la empresa'" @click="loadPickerFor = p.periodo">
                <FolderSearch class="size-4" /> Cargar Excel
              </Button>
            </div>
          </div>
        </div>

        <!-- Papelera de Excels -->
        <div v-if="showTrash && trashedLoads.length" class="rounded-lg border border-dashed border-border bg-muted/30 p-3">
          <div class="mb-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Papelera</div>
          <div v-for="c in trashedLoads" :key="c.id" class="flex items-center gap-2 py-1">
            <FileSpreadsheet class="size-4 shrink-0 text-muted-foreground opacity-70" />
            <span class="min-w-0 flex-1 truncate text-sm text-muted-foreground">{{ c.source_name }} <span v-if="c.periodo" class="font-mono">· {{ c.periodo }}</span></span>
            <Button variant="ghost" size="sm" :disabled="busy" @click="restoreLoad(c)"><RotateCcw class="size-3.5" /> Restaurar</Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Pickers de carpeta -->
    <DirectoryPicker :open="folderPickerOpen" :initial-path="info?.default_folder || ''" title="Carpeta de Excels de la empresa" @pick="onFolderPicked" @close="folderPickerOpen = false" />
    <DirectoryPicker :open="periodoPickerOpen" :initial-path="info?.default_folder || ''" :title="periodoPickerTarget ? `Carpeta de soportes de ${monthLabel(periodoPickerTarget)}` : 'Carpeta de soportes del mes'" @pick="onPeriodoFolderPicked" @close="periodoPickerOpen = false" />
    <DirectoryPicker :open="backupPickerOpen" :initial-path="info?.default_folder || ''" title="Carpeta donde se guardará el backup (.contab.zip)" @pick="onBackupFolderPicked" @close="backupPickerOpen = false" />

    <!-- Crear mes -->
    <Dialog v-model:open="newMonthOpen">
      <DialogContent class="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Crear mes</DialogTitle>
          <DialogDescription>Elige el mes que vas a trabajar. Luego cargas su Excel y su carpeta de soportes.</DialogDescription>
        </DialogHeader>
        <div class="flex flex-col gap-1.5">
          <Label for="new-month">Mes</Label>
          <Input id="new-month" v-model="newMonth" type="month" @keyup.enter="createMonth" />
        </div>
        <DialogFooter>
          <Button variant="secondary" @click="newMonthOpen = false">Cancelar</Button>
          <Button :disabled="!/^\d{4}-\d{2}$/.test(newMonth) || creatingMonth" @click="createMonth">{{ creatingMonth ? 'Creando…' : 'Crear mes' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Elegir Excel de la carpeta para un mes -->
    <Dialog :open="loadPickerFor !== null" @update:open="(v) => { if (!v) loadPickerFor = null }">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Cargar Excel {{ loadPickerFor ? `— ${monthLabel(loadPickerFor)}` : '' }}</DialogTitle>
          <DialogDescription>Elige el reporte de la DIAN (de tu carpeta de Excels) para este mes.</DialogDescription>
        </DialogHeader>
        <div class="flex max-h-80 flex-col gap-1.5 overflow-y-auto">
          <p v-if="!excelChoices.length" class="py-6 text-center text-sm text-muted-foreground">No hay Excels en la carpeta de la empresa.</p>
          <button v-for="f in excelChoices" :key="f.path" type="button" class="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-left text-sm transition-colors hover:bg-accent disabled:opacity-50" :disabled="busy" @click="loadPickerFor && importInto(loadPickerFor, f.path)">
            <FileSpreadsheet class="size-4 shrink-0 text-muted-foreground" />
            <span class="min-w-0 flex-1 truncate">{{ f.name }}</span>
            <span v-if="f.imported" class="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">ya cargado</span>
          </button>
        </div>
      </DialogContent>
    </Dialog>

    <!-- Mover Excel a otro mes -->
    <Dialog :open="moveTarget !== null" @update:open="(v) => { if (!v) moveTarget = null }">
      <DialogContent class="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Mover Excel de mes</DialogTitle>
          <DialogDescription>Elige el mes destino para «{{ moveTarget?.source_name }}».</DialogDescription>
        </DialogHeader>
        <div class="flex flex-col gap-1.5">
          <Label>Mes destino</Label>
          <Select :model-value="moveDestino" @update:model-value="moveDestino = String($event ?? '')">
            <SelectTrigger class="w-full"><SelectValue placeholder="Elegir mes…" /></SelectTrigger>
            <SelectContent><SelectItem v-for="p in periodos" :key="p.periodo" :value="p.periodo">{{ monthLabel(p.periodo) }} ({{ p.periodo }})</SelectItem></SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="secondary" @click="moveTarget = null">Cancelar</Button>
          <Button :disabled="!moveDestino || busy" @click="confirmMove">Mover</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Borrar mes -->
    <Dialog :open="deleteMonthTarget !== null" @update:open="(v) => { if (!v) deleteMonthTarget = null }">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Borrar mes {{ deleteMonthTarget }}</DialogTitle>
          <DialogDescription>Se elimina el mes y el Excel que tenga cargado. Los soportes en disco no se tocan. Esta acción no se puede deshacer.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="secondary" @click="deleteMonthTarget = null">Cancelar</Button>
          <Button variant="destructive" :disabled="busy" @click="confirmDeleteMonth">Borrar mes</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Archivar empresa -->
    <Dialog v-model:open="archiveModalOpen">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Archivar empresa</DialogTitle>
          <DialogDescription>Quedará oculta de la lista principal, pero sus datos se conservan y puedes desarchivarla cuando quieras.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="secondary" @click="archiveModalOpen = false">Cancelar</Button>
          <Button :disabled="archiving" @click="confirmArchive">{{ archiving ? 'Archivando…' : 'Archivar' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Eliminar empresa -->
    <Dialog v-model:open="deleteModalOpen">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Eliminar empresa</DialogTitle>
          <DialogDescription>Confirma la eliminación permanente de esta empresa.</DialogDescription>
        </DialogHeader>
        <div class="flex flex-col gap-3">
          <div class="rounded-md border border-status-error/30 bg-status-error-bg px-3 py-2 text-sm text-status-error">
            Esta acción es <strong>irreversible</strong>. Si quieres conservar la información, archiva la empresa o haz backup primero.
          </div>
          <div class="flex flex-col gap-1.5">
            <Label for="del-nit">Escribe el NIT <strong class="text-foreground">{{ info?.nit }}</strong> para confirmar:</Label>
            <Input id="del-nit" v-model="deleteConfirmNit" :placeholder="info?.nit" inputmode="numeric" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="secondary" @click="deleteModalOpen = false">Cancelar</Button>
          <Button variant="destructive" :disabled="deleting || deleteConfirmNit.trim() !== info?.nit" @click="confirmDelete">{{ deleting ? 'Eliminando…' : 'Eliminar permanentemente' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
