<script setup lang="ts">
import { ArrowLeft, Pencil, FolderOpen, RefreshCw, FileText, Copy, Trash2, Archive, Download, ChevronRight } from 'lucide-vue-next'

type EmpresaInfo = {
  db_path: string
  nit: string
  dv: string | null
  razon_social: string
  default_folder: string | null
  pdfs_folder: string | null
  archived?: boolean
  created_at: string
}

type BackupResult = {
  path: string
  size_bytes: number
  excels_included: number
  pdfs_included: number
}

type PdfFile = {
  name: string
  path: string
  size_bytes: number
  mtime: string
  extraction_status: 'ok' | 'no_text' | 'error' | null
  cufe_count: number
  cufes: { value: string; label: string | null }[]
  is_stale: boolean
}

type PdfListing = {
  folder: string | null
  files: PdfFile[]
  indexed_cufe_count: number
  error: string | null
}

type IndexStats = {
  folder: string
  total_pdfs: number
  indexed_now: number
  cached: number
  failed: string[]
  no_cufe: string[]
}

type Carga = {
  id: number
  source_name: string
  loaded_at: string
  total_rows: number
  sheet_name: string | null
}

type FolderFile = {
  name: string
  path: string
  size_bytes: number
  mtime: string
  imported: boolean
  imported_as_load_id: number | null
}

type FolderListing = {
  folder: string | null
  files: FolderFile[]
  error: string | null
}

type ImportResult = {
  load_id: number
  sheet_name: string
  total_rows: number
  columns: string[]
}

const route = useRoute()
const dbPath = computed(() => (route.query.db as string) || '')

const info = ref<EmpresaInfo | null>(null)
const cargas = ref<Carga[]>([])
const folderListing = ref<FolderListing>({ folder: null, files: [], error: null })
const loading = ref(false)

const toast = useToast()
const importing = ref(false)
const importingPath = ref<string>('')
const lastImportMsg = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const showUpload = ref(false)

const savingFolder = ref(false)
const folderPickerOpen = ref(false)

// E2 — gestión de empresa
const editingRazon = ref(false)
const razonDraft = ref('')
const savingRazon = ref(false)
const backupPickerOpen = ref(false)
const backingUp = ref(false)
const backupResult = ref<BackupResult | null>(null)
const archiving = ref(false)
const deleteModalOpen = ref(false)
const deleteConfirmNit = ref('')
const deleting = ref(false)

const pdfsListing = ref<PdfListing>({ folder: null, files: [], indexed_cufe_count: 0, error: null })
const savingPdfsFolder = ref(false)
const pdfsPickerOpen = ref(false)
const reindexing = ref(false)
const indexStats = ref<IndexStats | null>(null)

const pendingFiles = computed(() => folderListing.value.files.filter((f) => !f.imported))

async function refresh() {
  if (!dbPath.value) return
  loading.value = true
  try {
    info.value = await rpc<EmpresaInfo>('open_empresa', { db_path: dbPath.value })
    cargas.value = await rpc<Carga[]>('list_loads', { db_path: dbPath.value })
    await refreshFolderListing()
    await refreshPdfsListing()
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    loading.value = false
  }
}

async function refreshPdfsListing() {
  if (!dbPath.value || !info.value?.pdfs_folder) {
    pdfsListing.value = { folder: null, files: [], indexed_cufe_count: 0, error: null }
    return
  }
  try {
    pdfsListing.value = await rpc<PdfListing>('list_pdfs_folder_files', {
      db_path: dbPath.value,
    })
  } catch (exc) {
    pdfsListing.value = { folder: null, files: [], indexed_cufe_count: 0, error: String(exc) }
  }
}

async function persistPdfsFolder(folder: string | null) {
  savingPdfsFolder.value = true
  try {
    info.value = await rpc<EmpresaInfo>('set_pdfs_folder', {
      db_path: dbPath.value,
      folder,
    })
    await refreshPdfsListing()
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    savingPdfsFolder.value = false
  }
}

function onPdfsFolderPicked(path: string) { persistPdfsFolder(path) }
function clearPdfsFolder() { persistPdfsFolder(null) }

function startEditingRazon() {
  if (!info.value) return
  razonDraft.value = info.value.razon_social
  editingRazon.value = true
}

async function saveRazon() {
  if (!razonDraft.value.trim()) return
  savingRazon.value = true
  try {
    info.value = await rpc<EmpresaInfo>('update_empresa', {
      db_path: dbPath.value,
      razon_social: razonDraft.value.trim(),
    })
    editingRazon.value = false
    toast.success('Razón social actualizada')
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    savingRazon.value = false
  }
}

async function onBackupFolderPicked(folder: string) {
  backupPickerOpen.value = false
  backingUp.value = true
  backupResult.value = null
  try {
    backupResult.value = await rpc<BackupResult>('backup_empresa', {
      db_path: dbPath.value,
      dest_folder: folder,
    })
    toast.success(
      `Backup creado (${fmtSizeBytes(backupResult.value.size_bytes)})`,
      `${backupResult.value.excels_included} Excels + ${backupResult.value.pdfs_included} PDFs`,
    )
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    backingUp.value = false
  }
}

async function archiveEmpresa() {
  if (!confirm('¿Archivar esta empresa? Quedará oculta de la lista principal pero el archivo .db se conserva.')) return
  archiving.value = true
  try {
    await rpc('archive_empresa', { db_path: dbPath.value })
    toast.success('Empresa archivada')
    await navigateTo('/')
  } catch (exc) {
    toast.error('Algo falló', String(exc))
    archiving.value = false
  }
}

function openDeleteModal() {
  deleteConfirmNit.value = ''
  deleteModalOpen.value = true
}

async function confirmDelete() {
  if (!info.value) return
  if (deleteConfirmNit.value.trim() !== info.value.nit) return
  deleting.value = true
  try {
    await rpc('delete_empresa', {
      db_path: dbPath.value,
      confirm_nit: deleteConfirmNit.value.trim(),
    })
    toast.success('Empresa eliminada permanentemente')
    await navigateTo('/')
  } catch (exc) {
    toast.error('Algo falló', String(exc))
    deleting.value = false
  }
}

function fmtSizeBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  return `${(bytes / (1024 ** 3)).toFixed(2)} GB`
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Older browsers / non-secure contexts.
    const textarea = document.createElement('textarea')
    textarea.value = text
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
}

async function reindexPdfs() {
  reindexing.value = true
  indexStats.value = null
  try {
    const res = await rpc<{ folder: string; stats: IndexStats; error: string | null }>(
      'reindex_pdfs', { db_path: dbPath.value }
    )
    if (res.error) throw new Error(res.error)
    indexStats.value = res.stats
    await refreshPdfsListing()
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    reindexing.value = false
  }
}

async function refreshFolderListing() {
  if (!dbPath.value || !info.value?.default_folder) {
    folderListing.value = { folder: null, files: [], error: null }
    return
  }
  try {
    folderListing.value = await rpc<FolderListing>('list_folder_files', {
      db_path: dbPath.value,
    })
  } catch (exc) {
    folderListing.value = { folder: null, files: [], error: String(exc) }
  }
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function fmtDate(iso: string): string {
  return iso.replace('T', ' ').slice(0, 19)
}

async function importarPath(filePath: string) {
  importing.value = true
  importingPath.value = filePath
  lastImportMsg.value = ''
  try {
    const result = await rpc<ImportResult>('import_excel', {
      db_path: dbPath.value,
      source_path: filePath,
    })
    const fileName = filePath.split('/').pop() || filePath
    lastImportMsg.value = `${fileName} → ${result.total_rows} filas (load_id=${result.load_id})`
    cargas.value = await rpc<Carga[]>('list_loads', { db_path: dbPath.value })
    await refreshFolderListing()
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    importing.value = false
    importingPath.value = ''
  }
}

async function importarPendientes() {
  for (const f of pendingFiles.value) {
    await importarPath(f.path)
  }
}

async function handleExcelPicked(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  importing.value = true
  lastImportMsg.value = ''
  try {
    const fd = new FormData()
    fd.append('db_path', dbPath.value)
    fd.append('file', file)
    const res = await $fetch<{
      ok: boolean
      result?: ImportResult
      saved_to?: string
      error?: string
    }>('/api/upload-excel', { method: 'POST', body: fd })
    if (!res.ok || !res.result) throw new Error(res.error || 'error desconocido')
    lastImportMsg.value = `${file.name} → ${res.result.total_rows} filas (load_id=${res.result.load_id})`
    cargas.value = await rpc<Carga[]>('list_loads', { db_path: dbPath.value })
    await refreshFolderListing()
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    importing.value = false
    if (fileInputRef.value) fileInputRef.value.value = ''
  }
}

async function persistFolder(folder: string | null) {
  savingFolder.value = true
  try {
    info.value = await rpc<EmpresaInfo>('set_default_folder', {
      db_path: dbPath.value,
      folder,
    })
    await refreshFolderListing()
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    savingFolder.value = false
  }
}

function onFolderPicked(path: string) { persistFolder(path) }
function clearFolder() { persistFolder(null) }

onMounted(refresh)
watch(dbPath, refresh)
</script>

<template>
  <div class="mx-auto flex w-full max-w-6xl flex-col gap-5">
    <header v-if="info" class="flex flex-wrap items-end justify-between gap-3">
      <div class="min-w-0 flex-1">
        <NuxtLink to="/" class="mb-1 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft class="size-3.5" /> Empresas
        </NuxtLink>
        <div class="flex flex-wrap items-center gap-2">
          <template v-if="editingRazon">
            <Input
              v-model="razonDraft"
              :disabled="savingRazon"
              class="h-10 max-w-sm text-lg"
              @keyup.enter="saveRazon"
              @keyup.escape="editingRazon = false"
            />
            <Button variant="secondary" :disabled="savingRazon || !razonDraft.trim()" @click="saveRazon">
              {{ savingRazon ? 'Guardando…' : 'Guardar' }}
            </Button>
            <Button variant="ghost" :disabled="savingRazon" @click="editingRazon = false">Cancelar</Button>
          </template>
          <template v-else>
            <h1 class="font-heading text-2xl font-medium tracking-tight">{{ info.razon_social }}</h1>
            <Button variant="ghost" size="sm" title="Editar razón social" @click="startEditingRazon">
              <Pencil class="size-3.5" /> Editar
            </Button>
          </template>
        </div>
        <p class="text-sm text-muted-foreground">
          NIT <strong class="text-foreground">{{ info.nit }}{{ info.dv ? `-${info.dv}` : '' }}</strong>
          <span class="ml-1 text-xs">(inmutable)</span>
          <span class="mx-1.5 text-border">·</span>
          <span v-if="info.default_folder" class="font-mono text-xs">{{ info.default_folder }}</span>
          <span v-else>sin carpeta configurada</span>
        </p>
      </div>
      <div class="flex gap-2">
        <Button variant="secondary" :disabled="savingFolder" @click="folderPickerOpen = true">
          <FolderOpen class="size-4" /> {{ info.default_folder ? 'Cambiar carpeta' : 'Elegir carpeta' }}
        </Button>
        <Button v-if="info.default_folder" variant="ghost" :disabled="savingFolder" @click="clearFolder">Quitar</Button>
      </div>
    </header>

    <Card v-else-if="loading"><CardContent class="py-10 text-center text-muted-foreground">Cargando empresa…</CardContent></Card>
    <Card v-else>
      <CardContent class="py-6">
        <div class="rounded-md border border-status-error/30 bg-status-error-bg px-3 py-2 text-sm text-status-error">
          Empresa no encontrada. <NuxtLink to="/" class="underline">Volver</NuxtLink>
        </div>
      </CardContent>
    </Card>

    <DirectoryPicker
      :open="folderPickerOpen"
      :initial-path="info?.default_folder || ''"
      title="Carpeta de archivos de la empresa"
      @pick="onFolderPicked"
      @close="folderPickerOpen = false"
    />

    <div v-if="info" class="grid items-start gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Archivos en la carpeta</CardTitle>
          <CardDescription>
            <template v-if="folderListing.folder">
              {{ folderListing.files.length }} archivo(s)
              <span v-if="pendingFiles.length">· {{ pendingFiles.length }} sin importar</span>
            </template>
            <template v-else>Configura una carpeta para ver tus Excels aquí.</template>
          </CardDescription>
          <CardAction v-if="info.default_folder" class="flex items-center gap-2">
            <Button variant="ghost" size="icon-sm" :disabled="loading" title="Refrescar" @click="refreshFolderListing">
              <RefreshCw class="size-4" />
            </Button>
            <Button v-if="pendingFiles.length > 1" size="sm" :disabled="importing" @click="importarPendientes">
              Importar pendientes ({{ pendingFiles.length }})
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent class="flex flex-col gap-3">
          <div v-if="folderListing.error" class="rounded-md border border-status-warning/30 bg-status-warning-bg px-3 py-2 text-sm text-status-warning">
            {{ folderListing.error }}
          </div>
          <p v-if="info.default_folder && !folderListing.files.length && !folderListing.error" class="py-6 text-center text-sm text-muted-foreground">
            La carpeta está vacía. Pon tus reportes <span class="font-mono">.xlsx</span> ahí.
          </p>

          <ul v-if="folderListing.files.length" class="flex flex-col gap-2">
            <li
              v-for="f in folderListing.files"
              :key="f.path"
              class="flex items-center gap-3 rounded-md border px-3 py-2.5 transition-colors"
              :class="importingPath === f.path ? 'border-primary bg-primary/5' : f.imported ? 'border-border bg-card opacity-90' : 'border-border bg-card'"
            >
              <FileText class="size-5 shrink-0 text-muted-foreground" />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="truncate font-medium">{{ f.name }}</span>
                  <span v-if="f.imported" class="inline-flex shrink-0 items-center rounded-full bg-status-success-bg px-2 py-0.5 text-[10px] font-medium text-status-success">importado</span>
                </div>
                <div class="text-xs text-muted-foreground">
                  {{ fmtSize(f.size_bytes) }} · {{ fmtDate(f.mtime) }}
                  <NuxtLink
                    v-if="f.imported_as_load_id"
                    :to="{ path: '/load', query: { db: dbPath, id: f.imported_as_load_id } }"
                    class="ml-1 text-primary hover:underline"
                  >ver carga →</NuxtLink>
                </div>
              </div>
              <Button size="sm" :variant="f.imported ? 'outline' : 'default'" :disabled="importing" @click="importarPath(f.path)">
                {{ importingPath === f.path ? 'Importando…' : f.imported ? 'Re-importar' : 'Importar' }}
              </Button>
            </li>
          </ul>

          <details class="border-t border-border pt-3" :open="showUpload">
            <summary class="cursor-pointer text-sm text-muted-foreground hover:text-foreground" @click="showUpload = !showUpload">
              Importar desde otra ubicación…
            </summary>
            <p class="mt-1 text-xs text-muted-foreground">Sube un Excel que no esté en la carpeta de la empresa.</p>
            <Button as-child variant="outline" size="sm" class="mt-2" :disabled="importing">
              <label class="cursor-pointer">
                <input
                  ref="fileInputRef"
                  type="file"
                  accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                  :disabled="importing"
                  class="hidden"
                  @change="handleExcelPicked"
                >
                <FolderOpen class="size-4" /> Elegir archivo…
              </label>
            </Button>
          </details>

          <div v-if="lastImportMsg" class="rounded-md border border-status-success/30 bg-status-success-bg px-3 py-2 text-sm text-status-success">{{ lastImportMsg }}</div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Soportes PDF</CardTitle>
          <CardDescription>
            <template v-if="pdfsListing.folder">
              {{ pdfsListing.files.length }} PDF(s) · {{ pdfsListing.indexed_cufe_count }} CUFE indexados
            </template>
            <template v-else>Carpeta para la Validación 1 (CUFE en PDFs).</template>
          </CardDescription>
          <CardAction v-if="info.pdfs_folder">
            <Button variant="ghost" size="sm" :disabled="reindexing" @click="reindexPdfs">
              <RefreshCw class="size-4" :class="reindexing ? 'animate-spin' : ''" /> {{ reindexing ? 'Indexando…' : 'Re-indexar' }}
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent class="flex flex-col gap-3">
          <div class="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" :disabled="savingPdfsFolder" @click="pdfsPickerOpen = true">
              <FolderOpen class="size-4" /> {{ info.pdfs_folder ? 'Cambiar carpeta' : 'Elegir carpeta de PDFs' }}
            </Button>
            <Button v-if="info.pdfs_folder" variant="ghost" size="sm" :disabled="savingPdfsFolder" @click="clearPdfsFolder">Quitar</Button>
          </div>
          <div v-if="info.pdfs_folder" class="break-all font-mono text-xs text-muted-foreground">{{ info.pdfs_folder }}</div>

          <div v-if="pdfsListing.error" class="rounded-md border border-status-warning/30 bg-status-warning-bg px-3 py-2 text-sm text-status-warning">{{ pdfsListing.error }}</div>

          <div v-if="indexStats" class="rounded-md border border-status-success/30 bg-status-success-bg px-3 py-2 text-sm text-status-success">
            {{ indexStats.indexed_now }} nuevo(s), {{ indexStats.cached }} en caché
            <span v-if="indexStats.no_cufe.length"> · {{ indexStats.no_cufe.length }} sin CUFE</span>
            <span v-if="indexStats.failed.length"> · {{ indexStats.failed.length }} con error</span>
          </div>

          <ul v-if="pdfsListing.files.length" class="flex flex-col gap-2">
            <li v-for="f in pdfsListing.files" :key="f.path" class="flex flex-col rounded-md border border-border bg-card px-3 py-2.5">
              <div class="flex items-center gap-3">
                <FileText class="size-5 shrink-0 text-muted-foreground" />
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-1.5">
                    <span class="truncate font-medium">{{ f.name }}</span>
                    <span v-if="f.extraction_status === 'ok' && f.cufes.length" class="inline-flex shrink-0 items-center rounded-full bg-status-success-bg px-2 py-0.5 text-[10px] font-medium text-status-success">{{ f.cufes[0].label || 'CUFE' }} encontrado</span>
                    <span v-else-if="f.extraction_status === 'no_text'" class="inline-flex shrink-0 items-center rounded-full bg-status-warning-bg px-2 py-0.5 text-[10px] font-medium text-status-warning">sin CUFE</span>
                    <span v-else-if="f.extraction_status === 'error'" class="inline-flex shrink-0 items-center rounded-full bg-status-error-bg px-2 py-0.5 text-[10px] font-medium text-status-error">error</span>
                    <span v-else class="inline-flex shrink-0 items-center rounded-full bg-status-warning-bg px-2 py-0.5 text-[10px] font-medium text-status-warning">sin indexar</span>
                    <span v-if="f.is_stale" class="inline-flex shrink-0 items-center rounded-full bg-status-warning-bg px-2 py-0.5 text-[10px] font-medium text-status-warning">modificado</span>
                  </div>
                  <div class="text-xs text-muted-foreground">{{ fmtSize(f.size_bytes) }} · {{ fmtDate(f.mtime) }}</div>
                </div>
              </div>
              <div v-if="f.cufes.length" class="mt-2 flex items-center gap-2 border-t border-dashed border-border pt-2 font-mono text-xs">
                <span class="shrink-0 text-muted-foreground">{{ f.cufes[0].label || 'CUFE' }}:</span>
                <span class="min-w-0 flex-1 truncate text-foreground" :title="f.cufes[0].value">{{ f.cufes[0].value }}</span>
                <Button variant="ghost" size="icon-sm" title="Copiar" @click="copyToClipboard(f.cufes[0].value)"><Copy class="size-3.5" /></Button>
              </div>
            </li>
          </ul>
          <p v-else-if="info.pdfs_folder && !pdfsListing.error" class="py-6 text-center text-sm text-muted-foreground">Sin PDFs en esta carpeta.</p>
        </CardContent>
      </Card>
      <DirectoryPicker
        :open="pdfsPickerOpen"
        :initial-path="info?.pdfs_folder || ''"
        title="Carpeta de soportes (PDFs)"
        @pick="onPdfsFolderPicked"
        @close="pdfsPickerOpen = false"
      />

      <Card>
        <CardHeader>
          <CardTitle>Cargas</CardTitle>
          <CardDescription>Historial de importaciones de esta empresa.</CardDescription>
        </CardHeader>
        <CardContent>
          <p v-if="!cargas.length" class="py-6 text-center text-sm text-muted-foreground">Aún no hay cargas.</p>
          <ul v-else class="flex flex-col gap-2">
            <li v-for="c in cargas" :key="c.id">
              <button
                type="button"
                class="flex w-full items-center gap-3 rounded-md border border-border bg-card px-3 py-2.5 text-left transition-colors hover:bg-accent"
                @click="navigateTo({ path: '/load', query: { db: dbPath, id: c.id } })"
              >
                <span class="shrink-0 font-mono text-sm text-muted-foreground">#{{ c.id }}</span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate font-medium">{{ c.source_name }}</span>
                  <span class="block text-xs text-muted-foreground">{{ c.total_rows }} filas · {{ c.loaded_at }}</span>
                </span>
                <ChevronRight class="size-4 shrink-0 text-muted-foreground" />
              </button>
            </li>
          </ul>
        </CardContent>
      </Card>

      <Card class="md:col-span-2">
        <CardHeader>
          <CardTitle>Acciones</CardTitle>
          <CardDescription>Backup, archivar o eliminar esta empresa.</CardDescription>
        </CardHeader>
        <CardContent class="flex flex-col gap-3">
          <div class="flex flex-wrap items-center gap-2">
            <Button variant="secondary" :disabled="backingUp" @click="backupPickerOpen = true">
              <Download class="size-4" /> {{ backingUp ? 'Generando…' : 'Hacer backup' }}
            </Button>
            <Button variant="ghost" :disabled="archiving" @click="archiveEmpresa">
              <Archive class="size-4" /> {{ archiving ? 'Archivando…' : 'Archivar' }}
            </Button>
            <span class="flex-1" />
            <Button variant="destructive" @click="openDeleteModal"><Trash2 class="size-4" /> Eliminar permanentemente</Button>
          </div>
          <div v-if="backupResult" class="rounded-md border border-status-success/30 bg-status-success-bg px-3 py-2 text-sm text-status-success">
            Backup creado: <span class="font-mono">{{ backupResult.path }}</span>
            ({{ fmtSizeBytes(backupResult.size_bytes) }}, {{ backupResult.excels_included }} Excels, {{ backupResult.pdfs_included }} PDFs).
          </div>
        </CardContent>
      </Card>
    </div>

    <DirectoryPicker
      :open="backupPickerOpen"
      :initial-path="info?.default_folder || ''"
      title="Carpeta donde se guardará el backup (.contab.zip)"
      @pick="onBackupFolderPicked"
      @close="backupPickerOpen = false"
    />

    <Dialog v-model:open="deleteModalOpen">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Eliminar empresa</DialogTitle>
          <DialogDescription>Confirma la eliminación permanente de esta empresa.</DialogDescription>
        </DialogHeader>
        <div class="flex flex-col gap-3">
          <div class="rounded-md border border-status-error/30 bg-status-error-bg px-3 py-2 text-sm text-status-error">
            Esta acción es <strong>irreversible</strong>. El archivo .db se borra permanentemente.
            Si quieres conservar la información, archiva la empresa o haz backup primero.
          </div>
          <div class="flex flex-col gap-1.5">
            <Label for="del-nit">Escribe el NIT <strong class="text-foreground">{{ info?.nit }}</strong> para confirmar:</Label>
            <Input id="del-nit" v-model="deleteConfirmNit" :placeholder="info?.nit" inputmode="numeric" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="secondary" @click="deleteModalOpen = false">Cancelar</Button>
          <Button variant="destructive" :disabled="deleting || deleteConfirmNit.trim() !== info?.nit" @click="confirmDelete">
            {{ deleting ? 'Eliminando…' : 'Eliminar permanentemente' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
