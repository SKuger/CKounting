<script setup lang="ts">
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
  <div class="empresa-page">
    <header v-if="info" class="empresa-hero">
      <div style="flex: 1; min-width: 0">
        <NuxtLink to="/" class="back-link">← Empresas</NuxtLink>
        <div class="razon-row">
          <template v-if="editingRazon">
            <input
              v-model="razonDraft"
              :disabled="savingRazon"
              style="font-size: 1.4rem; padding: 0.3rem 0.55rem; min-width: 14rem"
              @keyup.enter="saveRazon"
              @keyup.escape="editingRazon = false"
            />
            <button class="secondary" :disabled="savingRazon || !razonDraft.trim()" @click="saveRazon">
              {{ savingRazon ? 'Guardando…' : 'Guardar' }}
            </button>
            <button class="ghost" :disabled="savingRazon" @click="editingRazon = false">Cancelar</button>
          </template>
          <template v-else>
            <h1>{{ info.razon_social }}</h1>
            <button class="ghost" style="padding: 0.2rem 0.5rem; font-size: 0.78rem" title="Editar razón social" @click="startEditingRazon">
              ✎ Editar
            </button>
          </template>
        </div>
        <div class="muted">
          NIT <strong>{{ info.nit }}{{ info.dv ? `-${info.dv}` : '' }}</strong>
          <span class="muted small" style="margin-left: 0.5rem">(inmutable)</span>
          <span class="dot">·</span>
          <span v-if="info.default_folder" class="mono small">{{ info.default_folder }}</span>
          <span v-else class="muted">sin carpeta configurada</span>
        </div>
      </div>
      <div class="hero-actions">
        <button class="secondary" :disabled="savingFolder" @click="folderPickerOpen = true">
          📂 {{ info.default_folder ? 'Cambiar carpeta' : 'Elegir carpeta' }}
        </button>
        <button v-if="info.default_folder" class="ghost" :disabled="savingFolder" @click="clearFolder">
          Quitar
        </button>
      </div>
    </header>

    <section v-else-if="loading" class="card center muted">Cargando empresa…</section>
    <section v-else class="card">
      <div class="alert error">Empresa no encontrada. <NuxtLink to="/">Volver</NuxtLink></div>
    </section>

    <DirectoryPicker
      :open="folderPickerOpen"
      :initial-path="info?.default_folder || ''"
      title="Carpeta de archivos de la empresa"
      @pick="onFolderPicked"
      @close="folderPickerOpen = false"
    />

    <div v-if="info" class="empresa-grid">
      <section class="card panel files-panel">
        <div class="panel-head">
          <div>
            <h2>Archivos en la carpeta</h2>
            <div class="muted small" v-if="folderListing.folder">
              {{ folderListing.files.length }} archivo(s)
              <span v-if="pendingFiles.length">· {{ pendingFiles.length }} sin importar</span>
            </div>
            <div v-else class="muted small">Configura una carpeta para ver tus Excels aquí.</div>
          </div>
          <div class="row" v-if="info.default_folder">
            <button class="ghost" :disabled="loading" @click="refreshFolderListing">↻</button>
            <button
              v-if="pendingFiles.length > 1"
              :disabled="importing"
              @click="importarPendientes"
            >
              Importar pendientes ({{ pendingFiles.length }})
            </button>
          </div>
        </div>

        <div v-if="folderListing.error" class="alert warn" style="margin-top: 0.6rem">
          {{ folderListing.error }}
        </div>

        <div v-if="info.default_folder && !folderListing.files.length && !folderListing.error"
          class="empty muted">
          La carpeta está vacía. Pon tus reportes <span class="mono">.xlsx</span> ahí.
        </div>

        <ul v-if="folderListing.files.length" class="file-list">
          <li
            v-for="f in folderListing.files"
            :key="f.path"
            class="file-row"
            :class="{ 'is-imported': f.imported, 'is-importing': importingPath === f.path }"
          >
            <div class="file-icon">📄</div>
            <div class="file-meta">
              <div class="file-name">
                {{ f.name }}
                <span v-if="f.imported" class="chip ok">importado</span>
              </div>
              <div class="muted small">
                {{ fmtSize(f.size_bytes) }} · {{ fmtDate(f.mtime) }}
                <NuxtLink
                  v-if="f.imported_as_load_id"
                  :to="{ path: '/load', query: { db: dbPath, id: f.imported_as_load_id } }"
                  class="small"
                  style="margin-left: 0.4rem"
                >
                  ver carga →
                </NuxtLink>
              </div>
            </div>
            <button
              class="file-action"
              :disabled="importing"
              @click="importarPath(f.path)"
            >
              {{
                importingPath === f.path
                  ? 'Importando…'
                  : f.imported ? 'Re-importar' : 'Importar'
              }}
            </button>
          </li>
        </ul>

        <details class="upload-secondary" :open="showUpload">
          <summary @click="showUpload = !showUpload">Importar desde otra ubicación…</summary>
          <p class="muted small">Sube un Excel que no esté en la carpeta de la empresa.</p>
          <label class="file-picker">
            <input
              ref="fileInputRef"
              type="file"
              accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
              :disabled="importing"
              @change="handleExcelPicked"
              style="display: none"
            />
            <span class="button-like">📂 Elegir archivo…</span>
          </label>
        </details>

        <div v-if="lastImportMsg" class="alert ok" style="margin-top: 0.7rem">{{ lastImportMsg }}</div>
      </section>

      <section class="card panel pdfs-panel">
        <div class="panel-head">
          <div>
            <h2>Soportes PDF</h2>
            <div class="muted small" v-if="pdfsListing.folder">
              {{ pdfsListing.files.length }} PDF(s) · {{ pdfsListing.indexed_cufe_count }} CUFE indexados
            </div>
            <div v-else class="muted small">Carpeta para la Validación 1 (CUFE en PDFs).</div>
          </div>
          <div class="row" v-if="info.pdfs_folder">
            <button class="ghost" :disabled="reindexing" @click="reindexPdfs">
              {{ reindexing ? 'Indexando…' : '↻ Re-indexar' }}
            </button>
          </div>
        </div>
        <div class="row" style="margin-top: 0.5rem">
          <button class="secondary" :disabled="savingPdfsFolder" @click="pdfsPickerOpen = true">
            📂 {{ info.pdfs_folder ? 'Cambiar carpeta' : 'Elegir carpeta de PDFs' }}
          </button>
          <button v-if="info.pdfs_folder" class="ghost" :disabled="savingPdfsFolder" @click="clearPdfsFolder">
            Quitar
          </button>
        </div>
        <div v-if="info.pdfs_folder" class="muted mono small" style="margin-top: 0.4rem">
          {{ info.pdfs_folder }}
        </div>

        <div v-if="pdfsListing.error" class="alert warn" style="margin-top: 0.6rem">{{ pdfsListing.error }}</div>

        <div v-if="indexStats" class="alert ok" style="margin-top: 0.6rem">
          {{ indexStats.indexed_now }} nuevo(s), {{ indexStats.cached }} en caché
          <span v-if="indexStats.no_cufe.length"> · {{ indexStats.no_cufe.length }} sin CUFE</span>
          <span v-if="indexStats.failed.length"> · {{ indexStats.failed.length }} con error</span>
        </div>

        <ul v-if="pdfsListing.files.length" class="file-list" style="margin-top: 0.6rem">
          <li v-for="f in pdfsListing.files" :key="f.path" class="pdf-row">
            <div class="pdf-row-top">
              <div class="file-icon">📄</div>
              <div class="file-meta">
                <div class="file-name">
                  {{ f.name }}
                  <span v-if="f.extraction_status === 'ok' && f.cufes.length" class="chip ok">
                    {{ f.cufes[0].label || 'CUFE' }} encontrado
                  </span>
                  <span v-else-if="f.extraction_status === 'no_text'" class="chip warn">sin CUFE</span>
                  <span v-else-if="f.extraction_status === 'error'" class="chip nc">error</span>
                  <span v-else class="chip warn">sin indexar</span>
                  <span v-if="f.is_stale" class="chip warn">modificado</span>
                </div>
                <div class="muted small">{{ fmtSize(f.size_bytes) }} · {{ fmtDate(f.mtime) }}</div>
              </div>
            </div>
            <div v-if="f.cufes.length" class="pdf-cufe-line mono">
              <span class="muted small">{{ f.cufes[0].label || 'CUFE' }}:</span>
              <span class="cufe-hex" :title="f.cufes[0].value">{{ f.cufes[0].value }}</span>
              <button
                class="ghost"
                style="padding: 0.1rem 0.4rem; font-size: 0.7rem"
                @click="copyToClipboard(f.cufes[0].value)"
                title="Copiar"
              >⧉</button>
            </div>
          </li>
        </ul>
        <div v-else-if="info.pdfs_folder && !pdfsListing.error" class="empty muted">
          Sin PDFs en esta carpeta.
        </div>
      </section>
      <DirectoryPicker
        :open="pdfsPickerOpen"
        :initial-path="info?.pdfs_folder || ''"
        title="Carpeta de soportes (PDFs)"
        @pick="onPdfsFolderPicked"
        @close="pdfsPickerOpen = false"
      />

      <section class="card panel loads-panel">
        <div class="panel-head">
          <div>
            <h2>Cargas</h2>
            <div class="muted small">Historial de importaciones de esta empresa.</div>
          </div>
        </div>
        <div v-if="!cargas.length" class="empty muted">Aún no hay cargas.</div>
        <ul v-else class="loads-list">
          <li
            v-for="c in cargas"
            :key="c.id"
            class="load-row"
            @click="navigateTo({ path: '/load', query: { db: dbPath, id: c.id } })"
          >
            <div class="load-id mono">#{{ c.id }}</div>
            <div class="load-meta">
              <div class="load-name">{{ c.source_name }}</div>
              <div class="muted small">
                {{ c.total_rows }} filas · {{ c.loaded_at }}
              </div>
            </div>
            <div class="muted small mono">→</div>
          </li>
        </ul>
      </section>

      <section class="card panel actions-panel">
        <div class="panel-head">
          <div>
            <h2>Acciones</h2>
            <div class="muted small">Backup, archivar o eliminar esta empresa.</div>
          </div>
        </div>
        <div class="row" style="margin-top: 0.6rem">
          <button class="secondary" :disabled="backingUp" @click="backupPickerOpen = true">
            {{ backingUp ? 'Generando…' : '💾 Hacer backup' }}
          </button>
          <button class="ghost" :disabled="archiving" @click="archiveEmpresa">
            {{ archiving ? 'Archivando…' : '📦 Archivar' }}
          </button>
          <span class="spacer" />
          <button class="danger" @click="openDeleteModal">🗑 Eliminar permanentemente</button>
        </div>
        <div v-if="backupResult" class="alert ok" style="margin-top: 0.7rem">
          Backup creado: <span class="mono">{{ backupResult.path }}</span>
          ({{ fmtSizeBytes(backupResult.size_bytes) }},
          {{ backupResult.excels_included }} Excels,
          {{ backupResult.pdfs_included }} PDFs).
        </div>
      </section>
    </div>

    <DirectoryPicker
      :open="backupPickerOpen"
      :initial-path="info?.default_folder || ''"
      title="Carpeta donde se guardará el backup (.contab.zip)"
      @pick="onBackupFolderPicked"
      @close="backupPickerOpen = false"
    />

    <div v-if="deleteModalOpen" class="modal-backdrop" @click.self="deleteModalOpen = false">
      <div class="modal" style="max-width: 480px">
        <header class="modal-header">
          <h2 style="margin: 0">Eliminar empresa</h2>
          <button class="ghost" style="padding: 0.3rem 0.6rem" @click="deleteModalOpen = false">✕</button>
        </header>
        <div class="modal-body" style="padding: 1rem 1.1rem">
          <div class="alert error" style="margin-bottom: 0.7rem">
            Esta acción es <strong>irreversible</strong>. El archivo .db se borra permanentemente.
            Si quieres conservar la información, archiva la empresa o haz backup primero.
          </div>
          <p class="muted small" style="margin-bottom: 0.5rem">
            Escribe el NIT <strong style="color: var(--text)">{{ info?.nit }}</strong> para confirmar:
          </p>
          <input
            v-model="deleteConfirmNit"
            :placeholder="info?.nit"
            style="width: 100%"
            inputmode="numeric"
          />
        </div>
        <footer class="modal-footer">
          <span class="spacer" />
          <button class="secondary" @click="deleteModalOpen = false">Cancelar</button>
          <button
            class="danger"
            :disabled="deleting || deleteConfirmNit.trim() !== info?.nit"
            @click="confirmDelete"
          >
            {{ deleting ? 'Eliminando…' : 'Eliminar permanentemente' }}
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.razon-row { display: flex; align-items: center; gap: 0.5rem; margin: 0.1rem 0; flex-wrap: wrap; }
.razon-row h1 { margin: 0; }
.actions-panel { grid-column: 1 / -1; }
</style>
