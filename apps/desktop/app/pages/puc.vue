<script setup lang="ts">
import { ArrowLeft, Search, UploadCloud, Plus, Download, Pencil, Archive, ArchiveRestore, Trash2 } from 'lucide-vue-next'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '~/components/ui/select'

type Account = {
  id: number; codigo: string; nombre: string; categoria: string | null; clase: string | null
  relacion_con: string | null; maneja_vencimientos: string | null; diferencia_fiscal: string | null
  activo: number; nivel_agrupacion: string | null; nivel: number; fuente: string; archived: number
}
type Counts = { total: number; activas: number; archivadas: number; manuales: number }
type LastImport = { source_name: string; excel_razon: string | null; imported_at: string; inserted: number; updated: number } | null
type PucList = { accounts: Account[]; counts: Counts; last_import: LastImport }
type ImportPreview = {
  total_rows: number; inserted: number; updated: number
  empresa_nombre: string; empresa_nit: string; source_name: string
  sample_new: { codigo: string; nombre: string }[]
}

const route = useRoute()
const toast = useToast()
const dbPath = computed(() => (route.query.db as string) || '')

const loading = ref(false)
const accounts = ref<Account[]>([])
const counts = ref<Counts>({ total: 0, activas: 0, archivadas: 0, manuales: 0 })
const lastImport = ref<LastImport>(null)
const razonSocial = ref('')

const NIVEL_LABEL: Record<number, string> = { 1: 'Clase', 2: 'Grupo', 3: 'Cuenta', 4: 'Subcuenta', 5: 'Auxiliar' }
const nivelLabel = (n: number) => NIVEL_LABEL[n] || 'Auxiliar'

// ── Filtros ──
const search = ref('')
const claseFilter = ref('all')
const nivelFilter = ref('all')
const estado = ref<'activas' | 'archivadas' | 'todas'>('activas')

const clases = computed(() => Array.from(new Set(accounts.value.map(a => a.clase).filter(Boolean))).sort() as string[])
const niveles = computed(() => Array.from(new Set(accounts.value.map(a => a.nivel))).sort((a, b) => a - b))

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return accounts.value.filter((a) => {
    if (estado.value === 'activas' && a.archived) return false
    if (estado.value === 'archivadas' && !a.archived) return false
    if (claseFilter.value !== 'all' && a.clase !== claseFilter.value) return false
    if (nivelFilter.value !== 'all' && String(a.nivel) !== nivelFilter.value) return false
    if (q && !(a.codigo.includes(q) || a.nombre.toLowerCase().includes(q))) return false
    return true
  })
})

async function load() {
  if (!dbPath.value) return
  loading.value = true
  try {
    const info = await rpc<{ razon_social: string }>('open_empresa', { db_path: dbPath.value })
    razonSocial.value = info.razon_social
    const data = await rpc<PucList>('puc_list', { db_path: dbPath.value, include_archived: true })
    accounts.value = data.accounts
    counts.value = data.counts
    lastImport.value = data.last_import
  } catch (e) {
    toast.error('No se pudo cargar el PUC', String(e))
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(dbPath, load)

// ── Subir dump (vista previa → aplicar) ──
const uploading = ref(false)
const preview = ref<ImportPreview | null>(null)
const previewPath = ref('')
const previewOpen = ref(false)
const applying = ref(false)

async function onDumpPicked(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('db_path', dbPath.value)
    fd.append('file', file)
    const res = await $fetch<{ ok: boolean; error?: string; result?: ImportPreview; saved_to?: string }>(
      '/api/upload-puc', { method: 'POST', body: fd },
    )
    if (!res.ok || !res.result) throw new Error(res.error || 'error al subir')
    preview.value = res.result
    previewPath.value = res.saved_to || ''
    previewOpen.value = true
  } catch (e) {
    toast.error('No se pudo subir el dump', humanError(e))
  } finally {
    uploading.value = false
  }
}

async function applyImport() {
  if (!previewPath.value) return
  applying.value = true
  try {
    const r = await rpc<ImportPreview>('puc_import', { db_path: dbPath.value, source_path: previewPath.value, dry_run: false })
    toast.success('PUC importado', `${r.inserted} nuevas · ${r.updated} actualizadas`)
    previewOpen.value = false
    preview.value = null
    await load()
  } catch (e) {
    toast.error('No se pudo importar', String(e))
  } finally {
    applying.value = false
  }
}

function humanError(e: unknown): string {
  // $fetch, en respuestas con status de error, deja el body en e.data → ahí viene
  // el mensaje real del sidecar (formato, NIT…). Lo preferimos al genérico "500…".
  const anyE = e as { data?: { error?: string }; message?: string }
  const s = String(anyE?.data?.error ?? anyE?.message ?? e)
  return s.replace(/^Error:\s*/, '')
}

// ── Crear / editar cuenta ──
const formOpen = ref(false)
const editingId = ref<number | null>(null)
const savingAccount = ref(false)
const empty = () => ({ codigo: '', nombre: '', clase: '', categoria: '', relacion_con: '', maneja_vencimientos: '', diferencia_fiscal: '', nivel_agrupacion: '', activo: true })
const form = reactive(empty())

function openNew() {
  editingId.value = null
  Object.assign(form, empty())
  formOpen.value = true
}
function openEdit(a: Account) {
  editingId.value = a.id
  Object.assign(form, {
    codigo: a.codigo, nombre: a.nombre, clase: a.clase || '', categoria: a.categoria || '',
    relacion_con: a.relacion_con || '', maneja_vencimientos: a.maneja_vencimientos || '',
    diferencia_fiscal: a.diferencia_fiscal || '', nivel_agrupacion: a.nivel_agrupacion || '', activo: !!a.activo,
  })
  formOpen.value = true
}
async function saveAccount() {
  if (!form.codigo.trim() || !form.nombre.trim()) {
    toast.warn('Faltan datos', 'El código y el nombre son obligatorios.')
    return
  }
  savingAccount.value = true
  try {
    await rpc('puc_save_account', { db_path: dbPath.value, account_id: editingId.value, account: { ...form } })
    toast.success(editingId.value ? 'Cuenta actualizada' : 'Cuenta agregada')
    formOpen.value = false
    await load()
  } catch (e) {
    toast.error('No se pudo guardar', humanError(e))
  } finally {
    savingAccount.value = false
  }
}
async function toggleArchive(a: Account) {
  try {
    await rpc('puc_archive_account', { db_path: dbPath.value, account_id: a.id, archived: !a.archived })
    await load()
  } catch (e) {
    toast.error('No se pudo archivar', String(e))
  }
}
async function removeAccount(a: Account) {
  if (!window.confirm(`¿Eliminar definitivamente la cuenta ${a.codigo} — ${a.nombre}? Esto no se puede deshacer.`)) return
  try {
    await rpc('puc_delete_account', { db_path: dbPath.value, account_id: a.id })
    toast.success('Cuenta eliminada')
    await load()
  } catch (e) {
    toast.error('No se pudo eliminar', String(e))
  }
}

// ── Exportar ──
const exportOpen = ref(false)
async function onExportFolder(path: string) {
  exportOpen.value = false
  try {
    const d = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
    const out = `${path.replace(/[/\\]+$/, '')}/PUC_${stamp}.xlsx`
    const r = await rpc<{ path: string; rows_written: number }>('puc_export', { db_path: dbPath.value, output_path: out })
    toast.success('PUC exportado', `${r.rows_written} cuentas → ${r.path}`)
  } catch (e) {
    toast.error('No se pudo exportar', String(e))
  }
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-3">
    <header class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
      <NuxtLink :to="{ path: '/empresa', query: { db: dbPath } }" class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft class="size-3.5" /> {{ razonSocial || 'Empresa' }}
      </NuxtLink>
      <span class="text-border">/</span>
      <h1 class="font-heading text-xl font-medium tracking-tight">Plan de Cuentas (PUC)</h1>
      <p class="text-sm text-muted-foreground">
        <strong class="text-foreground">{{ counts.total }}</strong> cuentas
        · {{ counts.activas }} activas
        <template v-if="counts.archivadas"> · {{ counts.archivadas }} archivadas</template>
        <template v-if="counts.manuales"> · {{ counts.manuales }} manuales</template>
        <template v-if="lastImport"> · <span class="text-muted-foreground">último dump: {{ lastImport.source_name }}</span></template>
      </p>
    </header>

    <!-- Barra de acciones -->
    <section class="flex flex-col gap-2 rounded-lg border border-border bg-card p-2">
      <div class="flex flex-wrap items-center gap-2">
        <div class="relative min-w-48 flex-1">
          <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input v-model="search" class="pl-8" placeholder="Buscar por código o nombre…" />
        </div>

        <Select v-model="claseFilter">
          <SelectTrigger class="w-44"><SelectValue placeholder="Clase" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas las clases</SelectItem>
            <SelectItem v-for="c in clases" :key="c" :value="c">{{ c }}</SelectItem>
          </SelectContent>
        </Select>

        <Select v-model="nivelFilter">
          <SelectTrigger class="w-36"><SelectValue placeholder="Nivel" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos los niveles</SelectItem>
            <SelectItem v-for="n in niveles" :key="n" :value="String(n)">{{ nivelLabel(n) }}</SelectItem>
          </SelectContent>
        </Select>

        <div class="inline-flex overflow-hidden rounded-md border border-border">
          <button
            v-for="opt in (['activas','todas','archivadas'] as const)" :key="opt" type="button"
            class="px-2.5 py-1 text-xs font-medium transition-colors"
            :class="estado === opt ? 'bg-primary text-primary-foreground' : 'bg-transparent text-muted-foreground hover:bg-accent'"
            @click="estado = opt"
          >{{ opt === 'activas' ? 'Activas' : opt === 'todas' ? 'Todas' : 'Archivadas' }}</button>
        </div>

        <span class="flex-1" />

        <Button as-child variant="secondary" :disabled="uploading">
          <label class="cursor-pointer">
            <UploadCloud class="size-4" /> {{ uploading ? 'Subiendo…' : 'Subir dump' }}
            <input type="file" accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel" hidden @change="onDumpPicked">
          </label>
        </Button>
        <Button @click="openNew"><Plus class="size-4" /> Agregar cuenta</Button>
        <Button variant="secondary" :disabled="!counts.total" @click="exportOpen = true"><Download class="size-4" /> Exportar</Button>
      </div>
    </section>

    <!-- Tabla -->
    <section class="min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-card">
      <div v-if="loading && !accounts.length" class="p-8 text-center text-sm text-muted-foreground">Cargando plan de cuentas…</div>

      <div v-else-if="!accounts.length" class="flex flex-col items-center gap-2 py-14 text-center">
        <div class="text-4xl opacity-40">📚</div>
        <h3 class="font-heading text-lg text-foreground">Sin plan de cuentas</h3>
        <p class="max-w-md text-sm text-muted-foreground">Sube el dump de Excel de las cuentas contables de esta empresa, o agrega cuentas a mano.</p>
      </div>

      <div v-else class="puc-wrapper">
        <table class="data">
          <thead>
            <tr>
              <th>Código</th>
              <th>Nombre</th>
              <th>Tipo</th>
              <th>Clase</th>
              <th>Categoría</th>
              <th class="center">Activo</th>
              <th class="right">Acciones</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in filtered" :key="a.id" :class="{ archived: a.archived }">
              <td class="font-mono" :style="{ paddingLeft: ((a.nivel - 1) * 14 + 12) + 'px' }">
                {{ a.codigo }}
                <span v-if="a.fuente === 'manual'" class="ml-1 rounded bg-accent px-1 text-[9px] uppercase tracking-wide text-muted-foreground">man</span>
              </td>
              <td :class="a.nivel <= 2 ? 'font-medium' : ''">{{ a.nombre }}</td>
              <td>
                <span class="inline-flex rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">{{ nivelLabel(a.nivel) }}</span>
              </td>
              <td class="text-muted-foreground">{{ a.clase || '—' }}</td>
              <td class="text-muted-foreground">{{ a.categoria || '—' }}</td>
              <td class="center">
                <span v-if="a.activo" class="text-status-success" title="Activa">Sí</span>
                <span v-else class="text-muted-foreground" title="Inactiva">No</span>
              </td>
              <td class="right">
                <div class="inline-flex items-center gap-0.5">
                  <button class="icon-btn" title="Editar" @click="openEdit(a)"><Pencil class="size-3.5" /></button>
                  <button class="icon-btn" :title="a.archived ? 'Desarchivar' : 'Archivar'" @click="toggleArchive(a)">
                    <ArchiveRestore v-if="a.archived" class="size-3.5" />
                    <Archive v-else class="size-3.5" />
                  </button>
                  <button class="icon-btn danger" title="Eliminar" @click="removeAccount(a)"><Trash2 class="size-3.5" /></button>
                </div>
              </td>
            </tr>
            <tr v-if="!filtered.length">
              <td colspan="7" class="py-8 text-center text-sm text-muted-foreground">
                Ninguna cuenta coincide con el filtro.
                <Button variant="ghost" size="sm" class="ml-1" @click="search = ''; claseFilter = 'all'; nivelFilter = 'all'; estado = 'activas'">Limpiar filtros</Button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Vista previa del dump -->
    <Dialog v-model:open="previewOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Vista previa del dump</DialogTitle>
          <DialogDescription>Se fusiona por código: nada se borra, tus cuentas manuales se conservan.</DialogDescription>
        </DialogHeader>
        <div v-if="preview" class="flex flex-col gap-3">
          <div class="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
            <div><span class="text-muted-foreground">Empresa del Excel:</span> <strong>{{ preview.empresa_nombre || '—' }}</strong></div>
            <div><span class="text-muted-foreground">NIT:</span> <span class="font-mono">{{ preview.empresa_nit || '—' }}</span></div>
          </div>
          <div class="flex gap-3 text-sm">
            <div class="flex-1 rounded-md border border-border px-3 py-2 text-center">
              <div class="text-lg font-semibold text-status-success">{{ preview.inserted }}</div>
              <div class="text-xs text-muted-foreground">nuevas</div>
            </div>
            <div class="flex-1 rounded-md border border-border px-3 py-2 text-center">
              <div class="text-lg font-semibold text-status-info">{{ preview.updated }}</div>
              <div class="text-xs text-muted-foreground">actualizadas</div>
            </div>
            <div class="flex-1 rounded-md border border-border px-3 py-2 text-center">
              <div class="text-lg font-semibold text-foreground">{{ preview.total_rows }}</div>
              <div class="text-xs text-muted-foreground">en el dump</div>
            </div>
          </div>
          <div v-if="preview.sample_new?.length" class="text-xs text-muted-foreground">
            Ejemplos de nuevas: <span class="font-mono">{{ preview.sample_new.slice(0, 6).map(s => s.codigo).join(', ') }}</span>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="previewOpen = false">Cancelar</Button>
          <Button :disabled="applying" @click="applyImport">{{ applying ? 'Importando…' : 'Aplicar importación' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Crear / editar cuenta -->
    <Dialog v-model:open="formOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{{ editingId ? 'Editar cuenta' : 'Agregar cuenta' }}</DialogTitle>
          <DialogDescription>El código define el nivel (1=Clase, 2=Grupo, 4=Cuenta, 6=Subcuenta, 8=Auxiliar).</DialogDescription>
        </DialogHeader>
        <div class="grid grid-cols-2 gap-3">
          <div class="flex flex-col gap-1">
            <Label class="text-xs">Código *</Label>
            <Input v-model="form.codigo" class="font-mono" placeholder="11050501" />
          </div>
          <div class="flex flex-col gap-1">
            <Label class="text-xs">Clase</Label>
            <Input v-model="form.clase" placeholder="Activo" />
          </div>
          <div class="col-span-2 flex flex-col gap-1">
            <Label class="text-xs">Nombre *</Label>
            <Input v-model="form.nombre" placeholder="Caja general" />
          </div>
          <div class="flex flex-col gap-1">
            <Label class="text-xs">Categoría</Label>
            <Input v-model="form.categoria" placeholder="Caja - Bancos" />
          </div>
          <div class="flex flex-col gap-1">
            <Label class="text-xs">Relación con</Label>
            <Input v-model="form.relacion_con" placeholder="Sin asignar" />
          </div>
          <div class="flex flex-col gap-1">
            <Label class="text-xs">Maneja vencimientos</Label>
            <Input v-model="form.maneja_vencimientos" placeholder="No maneja vencimiento" />
          </div>
          <div class="flex flex-col gap-1">
            <Label class="text-xs">Diferencia fiscal</Label>
            <Input v-model="form.diferencia_fiscal" placeholder="No" />
          </div>
          <div class="flex flex-col gap-1">
            <Label class="text-xs">Nivel agrupación</Label>
            <Input v-model="form.nivel_agrupacion" placeholder="Transaccional" />
          </div>
          <label class="flex items-center gap-2 self-end pb-2 text-sm">
            <input v-model="form.activo" type="checkbox" class="size-4 accent-primary"> Cuenta activa
          </label>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="formOpen = false">Cancelar</Button>
          <Button :disabled="savingAccount" @click="saveAccount">{{ savingAccount ? 'Guardando…' : 'Guardar' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <DirectoryPicker :open="exportOpen" :initial-path="''" title="Carpeta donde se guardará el PUC (.xlsx)" @pick="onExportFolder" @close="exportOpen = false" />
  </div>
</template>

<style scoped>
.puc-wrapper { overflow: auto; height: 100%; }
table.data {
  border-collapse: separate; border-spacing: 0;
  width: 100%; min-width: max-content;
  font-size: 0.8rem; font-variant-numeric: tabular-nums;
}
table.data th, table.data td {
  padding: 0.3rem 0.6rem;
  border-bottom: 1px solid var(--border);
  white-space: nowrap; vertical-align: middle; text-align: left;
}
table.data th {
  position: sticky; top: 0; z-index: 1;
  background: var(--muted);
  font-weight: 600; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--muted-foreground);
}
table.data th.center, table.data td.center { text-align: center; }
table.data th.right, table.data td.right { text-align: right; }
table.data tbody tr:hover { background: color-mix(in oklab, var(--primary) 5%, transparent); }
table.data tbody tr.archived td { opacity: 0.5; }
table.data tbody tr.archived td:nth-child(2) { text-decoration: line-through; }
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 0.25rem; border-radius: var(--radius-sm);
  color: var(--muted-foreground); transition: background 0.12s, color 0.12s;
}
.icon-btn:hover { background: var(--accent); color: var(--foreground); }
.icon-btn.danger:hover { color: var(--status-error); }
</style>
