<script setup lang="ts">
import { ArrowLeft, Pencil, FolderOpen, FileSpreadsheet, Trash2, Archive, Download, ChevronRight, EllipsisVertical, CalendarPlus, RotateCcw, UploadCloud, BookText, Landmark, Plus, X, Users, Search, Sparkles, CloudDownload, Loader2 } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '~/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '~/components/ui/select'

type EmpresaInfo = { db_path: string; nit: string; dv: string | null; razon_social: string; archived?: boolean; created_at: string; default_folder?: string | null; pdfs_folder?: string | null }
type Periodo = { periodo: string; load_count: number; row_count: number; pdfs_folder: string | null; indexed_cufe_count: number }
type Carga = { id: number; source_name: string; loaded_at: string; total_rows: number; periodo?: string | null; deleted?: boolean }
type BackupResult = { path: string; size_bytes: number; excels_included: number; pdfs_included: number }
type PerfilFiscal = {
  vigencia_desde: string; regimen: string; responsable_iva: boolean; periodicidad_iva: string | null
  agente_retefuente: boolean; agente_reteiva: boolean; agente_reteica: boolean
  autorretenedor_renta: boolean; gran_contribuyente: boolean; ciiu: string | null; notas: string | null
}
type Tercero = {
  nit: string; dv: string | null; razon_social: string; tipo: string | null
  responsabilidades: string[]; ciiu: string | null; municipio: string | null
  estado_rut: string | null; consultado_at: string | null; origen: string; notas: string | null
}
type Ingesta = {
  id: number; periodo: string; camino: string; estado: string
  documentos: number | null; error: string | null; empresa_dian: string | null; corrio_at: string
}
type MunicipioIca = { id: number; municipio: string; codigo_dane: string | null; actividad: string | null; tarifa_por_mil: string; vigencia_desde: string }

const route = useRoute()
const dbPath = computed(() => (route.query.db as string) || '')
const toast = useToast()

const info = ref<EmpresaInfo | null>(null)
const periodos = ref<Periodo[]>([])
const loads = ref<Carga[]>([])
const loading = ref(false)
const busy = ref(false)

// gestión de empresa
const editingRazon = ref(false)
const razonDraft = ref('')
const savingRazon = ref(false)
const backupPickerOpen = ref(false)
const backingUp = ref(false)
const archiveModalOpen = ref(false)
const archiving = ref(false)
const deleteModalOpen = ref(false)
const deleteConfirmNit = ref('')
const deleting = ref(false)

// meses
const newMonthOpen = ref(false)
const now = new Date()
const newMonthMes = ref(String(now.getMonth() + 1).padStart(2, '0'))
const newMonthAnio = ref(String(now.getFullYear()))
const newMonthValue = computed(() => (newMonthAnio.value && newMonthMes.value) ? `${newMonthAnio.value}-${newMonthMes.value}` : '')
const MESES = [
  { v: '01', l: 'Enero' }, { v: '02', l: 'Febrero' }, { v: '03', l: 'Marzo' },
  { v: '04', l: 'Abril' }, { v: '05', l: 'Mayo' }, { v: '06', l: 'Junio' },
  { v: '07', l: 'Julio' }, { v: '08', l: 'Agosto' }, { v: '09', l: 'Septiembre' },
  { v: '10', l: 'Octubre' }, { v: '11', l: 'Noviembre' }, { v: '12', l: 'Diciembre' },
]
const ANIOS = Array.from({ length: 6 }, (_, i) => String(now.getFullYear() + 1 - i))
const creatingMonth = ref(false)
const deleteMonthTarget = ref<string | null>(null)
const periodoPickerOpen = ref(false)
const periodoPickerTarget = ref<string | null>(null)
const moveTarget = ref<Carga | null>(null)
const moveDestino = ref('')
const showTrash = ref(false)

// ── perfil fiscal ──
function hoyISO(): string { return new Date().toISOString().slice(0, 10) }
const perfil = ref<PerfilFiscal | null>(null)
const perfiles = ref<PerfilFiscal[]>([])
const municipiosIca = ref<MunicipioIca[]>([])
const perfilOpen = ref(false)
const savingPerfil = ref(false)
const perfilHistorial = ref(false)
const icaOpen = ref(false)
const savingIca = ref(false)
const perfilDraft = reactive({
  vigencia_desde: hoyISO(), regimen: 'ordinario', responsable_iva: false,
  periodicidad_iva: 'bimestral', agente_retefuente: false, agente_reteiva: false,
  agente_reteica: false, autorretenedor_renta: false, gran_contribuyente: false,
  ciiu: '', notas: '',
})
const icaDraft = reactive({ municipio: '', codigo_dane: '', actividad: '', tarifa_por_mil: '', vigencia_desde: hoyISO() })
// ── traer de la DIAN ──
// El enlace de acceso vive en este campo y en ninguna parte más: no se guarda en
// la base, ni se manda a un log. Es una llave a la cuenta DIAN del cliente.
const dianEnlace = ref('')
const dianMes = ref(String(now.getMonth() + 1).padStart(2, '0'))
const dianAnio = ref(String(now.getFullYear()))
const dianPeriodo = computed(() => (dianAnio.value && dianMes.value) ? `${dianAnio.value}-${dianMes.value}` : '')
const dianEstado = ref<'inactivo' | 'corriendo' | 'listo' | 'error'>('inactivo')
const dianMensaje = ref('')
const dianResultado = ref<{ archivo: string; empresa: string | null } | null>(null)
const dianImportando = ref(false)
const ingestas = ref<Ingesta[]>([])
const soportesEstado = ref<'inactivo' | 'corriendo' | 'listo'>('inactivo')
const soportesMensaje = ref('')
const soportesResumen = ref<{ bajados: number; sin_encontrar: number; fallidos: number } | null>(null)

// ── terceros ──
const terceros = ref<Tercero[]>([])
const tercerosCounts = ref({ total: 0, con_rut: 0, sin_rut: 0 })
const tercerosBuscar = ref('')
const tercerosAbierto = ref(false)
const sembrando = ref(false)
const consultandoNit = ref<string | null>(null)
const terceroOpen = ref(false)
const savingTercero = ref(false)
const terceroDraft = reactive({ nit: '', razon_social: '', ciiu: '', municipio: '', responsabilidades: '', notas: '' })

const BANDERAS_PERFIL = [
  { key: 'agente_retefuente', label: 'Agente de retefuente' },
  { key: 'agente_reteiva', label: 'Agente de ReteIVA' },
  { key: 'agente_reteica', label: 'Agente de ReteICA' },
  { key: 'autorretenedor_renta', label: 'Autorretenedor de renta' },
  { key: 'gran_contribuyente', label: 'Gran contribuyente' },
] as const
const banderasActivas = computed(() =>
  perfil.value ? BANDERAS_PERFIL.filter((b) => perfil.value?.[b.key]) : [],
)

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
    await Promise.all([reloadPeriodos(), reloadLoads(), reloadPerfil(), reloadTerceros(), reloadIngestas()])
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

// ── perfil fiscal ──
// Lo que la empresa es ante la DIAN decide cada retención de la causación. Va
// fechado: si en agosto la nombran autorretenedora, marzo se sigue calculando
// con lo que era en marzo.
async function reloadPerfil() {
  const r = await rpc<{ perfil: PerfilFiscal | null; perfiles: PerfilFiscal[]; municipios_ica: MunicipioIca[] }>(
    'get_perfil_fiscal', { db_path: dbPath.value },
  )
  perfil.value = r.perfil
  perfiles.value = r.perfiles
  municipiosIca.value = r.municipios_ica
}

function openPerfil(base?: PerfilFiscal) {
  const src = base ?? perfil.value
  Object.assign(perfilDraft, {
    vigencia_desde: base?.vigencia_desde ?? hoyISO(),
    regimen: src?.regimen ?? 'ordinario',
    responsable_iva: src?.responsable_iva ?? false,
    periodicidad_iva: src?.periodicidad_iva ?? 'bimestral',
    agente_retefuente: src?.agente_retefuente ?? false,
    agente_reteiva: src?.agente_reteiva ?? false,
    agente_reteica: src?.agente_reteica ?? false,
    autorretenedor_renta: src?.autorretenedor_renta ?? false,
    gran_contribuyente: src?.gran_contribuyente ?? false,
    ciiu: src?.ciiu ?? '',
    notas: src?.notas ?? '',
  })
  perfilOpen.value = true
}

async function savePerfil() {
  savingPerfil.value = true
  try {
    await rpc('save_perfil_fiscal', { db_path: dbPath.value, perfil: { ...perfilDraft } })
    await reloadPerfil()
    perfilOpen.value = false
    toast.success('Perfil fiscal guardado', `Vigente desde ${perfilDraft.vigencia_desde}`)
  } catch (exc) {
    toast.error('No se pudo guardar el perfil fiscal', humanError(exc))
  } finally {
    savingPerfil.value = false
  }
}

async function deletePerfilVersion(vigencia: string) {
  try {
    await rpc('delete_perfil_fiscal', { db_path: dbPath.value, vigencia_desde: vigencia })
    await reloadPerfil()
  } catch (exc) {
    toast.error('No se pudo borrar esa versión', humanError(exc))
  }
}

async function saveMunicipio() {
  savingIca.value = true
  try {
    await rpc('save_municipio_ica', { db_path: dbPath.value, municipio: { ...icaDraft } })
    await reloadPerfil()
    icaOpen.value = false
    Object.assign(icaDraft, { municipio: '', codigo_dane: '', actividad: '', tarifa_por_mil: '', vigencia_desde: hoyISO() })
  } catch (exc) {
    toast.error('No se pudo guardar el municipio', humanError(exc))
  } finally {
    savingIca.value = false
  }
}

// ── traer de la DIAN ──
async function reloadIngestas() {
  const r = await rpc<{ ingestas: Ingesta[] }>('listar_ingestas', { db_path: dbPath.value, limite: 5 })
  ingestas.value = r.ingestas
}

// Toda corrida queda anotada, sobre todo las que fallan: el portal falla de formas
// que no se repiten, y sin registro cada fallo se investiga desde cero.
async function anotarFallo(mensaje: string) {
  try {
    await rpc('registrar_ingesta', {
      db_path: dbPath.value, periodo: dianPeriodo.value, camino: 'portal',
      estado: 'error', error: mensaje,
    })
    await reloadIngestas()
  } catch { /* que falle la anotación no puede tapar el fallo original */ }
}

// Baja de la DIAN el soporte oficial de los documentos que no lo tienen. Este
// camino del portal es público —CUFE + NIT, sin credenciales— y el Cloudflare no
// interrumpe entre búsquedas, así que puede correr solo.
async function bajarSoportes(periodo: string) {
  soportesEstado.value = 'corriendo'
  soportesMensaje.value = 'Viendo cuáles faltan…'
  soportesResumen.value = null
  try {
    const faltantes = await rpc<{ carpeta: string | null; faltan: { cufe: string; nit: string }[]; total: number }>(
      'documentos_sin_soporte', { db_path: dbPath.value, periodo },
    )
    if (!faltantes.carpeta) {
      throw new Error('Este mes no tiene carpeta de soportes. Configúrala primero.')
    }
    if (!faltantes.faltan.length) {
      soportesEstado.value = 'inactivo'
      toast.success('No falta ninguno', `Los ${faltantes.total} documentos de ${periodo} ya tienen soporte.`)
      return
    }

    const inicio = await $fetch<{ id: string }>('/api/dian/portal/soportes', {
      method: 'POST',
      body: { documentos: faltantes.faltan, carpeta: faltantes.carpeta },
    })
    for (;;) {
      await new Promise((r) => setTimeout(r, 3000))
      const e = await $fetch<{ estado: string; mensaje: string; bajados?: string[]; sin_encontrar?: string[]; fallidos?: string[]; error?: string }>(
        `/api/dian/portal/estado/${inicio.id}`,
      )
      soportesMensaje.value = e.mensaje || ''
      if (e.estado === 'listo') {
        // Los PDF del portal vienen cifrados con el NIT: sin releerlos con la
        // contraseña quedarían marcados como protegidos y la validación diría
        // que no hay soporte.
        await rpc('reindexar_soportes_con_nit', { db_path: dbPath.value, carpeta: faltantes.carpeta })
        soportesEstado.value = 'listo'
        soportesResumen.value = {
          bajados: e.bajados?.length ?? 0,
          sin_encontrar: e.sin_encontrar?.length ?? 0,
          fallidos: e.fallidos?.length ?? 0,
        }
        await reloadPeriodos()
        return
      }
      if (e.estado === 'error') {
        throw new Error(e.error || 'La descarga de soportes falló.')
      }
    }
  } catch (exc) {
    soportesEstado.value = 'inactivo'
    toast.error('No se pudieron bajar los soportes', humanError(exc))
  }
}

async function bajarDeLaDian() {
  if (!info.value?.default_folder) {
    toast.error('Falta la carpeta de Excels', 'Configúrala arriba: ahí se guarda lo que baje de la DIAN.')
    return
  }
  dianEstado.value = 'corriendo'
  dianMensaje.value = 'Validando…'
  dianResultado.value = null
  try {
    // El core valida el enlace y calcula el rango del mes; si algo está mal, se
    // sabe ANTES de abrir un navegador contra la DIAN.
    const plan = await rpc<{ enlace: string; desde: string; hasta: string; grupo: string; etiqueta: string }>(
      'preparar_descarga_dian', { periodo: dianPeriodo.value, enlace: dianEnlace.value },
    )
    dianMensaje.value = 'Abriendo el portal…'
    const inicio = await $fetch<{ id: string }>('/api/dian/portal/descargar', {
      method: 'POST',
      body: { ...plan, carpeta: info.value.default_folder, nit_receptor: info.value.nit },
    })
    // El enlace ya cumplió: fuera del campo, para que no quede en pantalla.
    dianEnlace.value = ''

    for (;;) {
      await new Promise((r) => setTimeout(r, 2500))
      const e = await $fetch<{ estado: string; mensaje: string; archivo: string | null; empresa: string | null; error: string | null }>(
        `/api/dian/portal/estado/${inicio.id}`,
      )
      dianMensaje.value = e.mensaje || ''
      if (e.estado === 'listo') {
        dianEstado.value = 'listo'
        dianResultado.value = { archivo: e.archivo || '', empresa: e.empresa }
        return
      }
      if (e.estado === 'error') {
        dianEstado.value = 'error'
        dianMensaje.value = e.error || 'La descarga falló.'
        await anotarFallo(dianMensaje.value)
        return
      }
    }
  } catch (exc) {
    dianEstado.value = 'error'
    dianMensaje.value = humanError(exc)
    await anotarFallo(dianMensaje.value)
  }
}

async function importarDescarga() {
  if (!dianResultado.value) return
  dianImportando.value = true
  try {
    const r = await rpc<{ total_rows: number; periodo: string }>('importar_descarga_dian', {
      db_path: dbPath.value, archivo: dianResultado.value.archivo, periodo: dianPeriodo.value,
    })
    await refresh()
    await reloadIngestas()
    dianEstado.value = 'inactivo'
    dianResultado.value = null
    toast.success(`${r.total_rows} filas importadas`, `Quedaron en el mes ${r.periodo}`)
  } catch (exc) {
    toast.error('No se pudo importar', humanError(exc))
  } finally {
    dianImportando.value = false
  }
}

// ── terceros ──
// El tercero es la contraparte: el proveedor en una compra, el cliente en una
// venta. Hasta ahora existían solo implícitos, repetidos en cada fila del Excel.
async function reloadTerceros() {
  const r = await rpc<{ terceros: Tercero[]; counts: { total: number; con_rut: number; sin_rut: number } }>(
    'terceros_list', { db_path: dbPath.value, buscar: tercerosBuscar.value || undefined },
  )
  terceros.value = r.terceros
  tercerosCounts.value = r.counts
}

async function sembrarTerceros() {
  sembrando.value = true
  try {
    const r = await rpc<{ encontrados: number; nuevos: number; completados: number }>(
      'terceros_sembrar', { db_path: dbPath.value },
    )
    await reloadTerceros()
    tercerosAbierto.value = true
    toast.success(
      `${r.nuevos} terceros nuevos`,
      `${r.encontrados} encontrados en el Excel · ${r.completados} completados`,
    )
  } catch (exc) {
    toast.error('No se pudo derivar el catálogo', humanError(exc))
  } finally {
    sembrando.value = false
  }
}

async function consultarRut(t: Tercero) {
  consultandoNit.value = t.nit
  try {
    const r = await rpc<{ consulta: { found: boolean; razon_social: string } }>(
      'tercero_consultar_rut', { db_path: dbPath.value, nit: t.nit, dv: t.dv },
    )
    await reloadTerceros()
    if (r.consulta.found) toast.success('RUT consultado', r.consulta.razon_social)
    else toast.error('Sin resultado en la DIAN', `El NIT ${t.nit} no devolvió datos`)
  } catch (exc) {
    toast.error('No se pudo consultar el RUT', humanError(exc))
  } finally {
    consultandoNit.value = null
  }
}

function openTercero(t?: Tercero) {
  Object.assign(terceroDraft, {
    nit: t?.nit ?? '',
    razon_social: t?.razon_social ?? '',
    ciiu: t?.ciiu ?? '',
    municipio: t?.municipio ?? '',
    responsabilidades: (t?.responsabilidades ?? []).join(', '),
    notas: t?.notas ?? '',
  })
  terceroOpen.value = true
}

async function saveTercero() {
  savingTercero.value = true
  try {
    await rpc('tercero_save', { db_path: dbPath.value, tercero: { ...terceroDraft } })
    await reloadTerceros()
    terceroOpen.value = false
  } catch (exc) {
    toast.error('No se pudo guardar el tercero', humanError(exc))
  } finally {
    savingTercero.value = false
  }
}

async function deleteMunicipio(id: number) {
  try {
    await rpc('delete_municipio_ica', { db_path: dbPath.value, municipio_id: id })
    await reloadPerfil()
  } catch (exc) {
    toast.error('No se pudo quitar el municipio', humanError(exc))
  }
}

// ── meses ──
async function createMonth() {
  const periodo = newMonthValue.value
  if (!/^\d{4}-\d{2}$/.test(periodo)) { toast.warn('Elige mes y año'); return }
  creatingMonth.value = true
  try {
    await rpc('create_periodo', { db_path: dbPath.value, periodo })
    newMonthOpen.value = false
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

// ── Excel del mes: subir (por archivo) / mover / papelera / restaurar ──
async function onExcelPicked(e: Event, periodo: string) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  busy.value = true
  try {
    const fd = new FormData()
    fd.append('db_path', dbPath.value)
    fd.append('periodo', periodo)
    fd.append('file', file)
    const res = await $fetch<{ ok: boolean; error?: string }>('/api/upload-excel', { method: 'POST', body: fd })
    if (!res.ok) throw new Error(res.error || 'error al importar')
    toast.success(`Excel cargado en ${monthLabel(periodo)}`)
    await Promise.all([reloadPeriodos(), reloadLoads()])
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

// ── gestión de empresa ──
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
    const res = await rpc<{ dias_retencion: number }>('delete_empresa', {
      db_path: dbPath.value, confirm_nit: deleteConfirmNit.value.trim(),
    })
    toast.success(
      'Empresa eliminada',
      `Se conserva en la papelera ${res.dias_retencion} días por si hace falta recuperarla.`,
    )
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
        </p>
      </div>
      <div class="flex gap-2">
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
        <CardDescription>Cada mes es un ambiente: sube su Excel, elige su carpeta de soportes y valídalo.</CardDescription>
        <CardAction class="flex items-center gap-2">
          <Button v-if="trashedLoads.length" variant="ghost" size="sm" :class="showTrash ? 'text-foreground' : ''" @click="showTrash = !showTrash">
            <RotateCcw class="size-4" /> Papelera ({{ trashedLoads.length }})
          </Button>
          <Button size="sm" data-tour="empresa-crear-mes" @click="newMonthOpen = true"><CalendarPlus class="size-4" /> Crear mes</Button>
        </CardAction>
      </CardHeader>
      <CardContent class="flex flex-col gap-3">
        <p v-if="!periodos.length" class="py-8 text-center text-sm text-muted-foreground">
          Aún no hay meses. Crea el primero con <strong class="text-foreground">«Crear mes»</strong> y luego sube su Excel.
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
              <Button as-child variant="outline" size="sm" :disabled="busy">
                <label class="cursor-pointer">
                  <UploadCloud class="size-4" /> Cargar Excel
                  <input type="file" accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel" hidden @change="onExcelPicked($event, p.periodo)">
                </label>
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

    <!-- Traer de la DIAN — el listado del mes, sin bajarlo a mano (Fase 2) -->
    <Card v-if="info">
      <CardHeader>
        <CardTitle class="flex items-center gap-2"><CloudDownload class="size-4 text-muted-foreground" /> Traer de la DIAN</CardTitle>
        <CardDescription>
          Pega el enlace de acceso que la DIAN manda al correo, elige el mes, y Contab hace el
          resto: entra al portal, pide el listado, espera a que lo generen y lo baja. Nada entra a
          la contabilidad hasta que lo apruebes.
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <template v-if="dianEstado === 'inactivo'">
          <div class="grid gap-1.5">
            <Label for="dian-enlace">Enlace de acceso</Label>
            <Input
              id="dian-enlace"
              v-model="dianEnlace"
              type="password"
              autocomplete="off"
              placeholder="https://catalogo-vpfe.dian.gov.co/User/AuthToken?…"
            />
            <p class="text-xs text-muted-foreground">
              No se guarda en ningún lado: se usa para esta descarga y se descarta. Es una llave a
              la cuenta DIAN de la empresa.
            </p>
          </div>

          <div class="flex flex-wrap items-end gap-3">
            <div class="grid gap-1.5">
              <Label>Mes</Label>
              <Select v-model="dianMes">
                <SelectTrigger class="w-40"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="m in MESES" :key="m.v" :value="m.v">{{ m.l }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="grid gap-1.5">
              <Label>Año</Label>
              <Select v-model="dianAnio">
                <SelectTrigger class="w-28"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="a in ANIOS" :key="a" :value="a">{{ a }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button :disabled="!dianEnlace || !dianPeriodo" @click="bajarDeLaDian">
              <CloudDownload class="size-4" /> Bajar {{ dianPeriodo }}
            </Button>
          </div>

          <p v-if="!info.default_folder" class="text-sm text-amber-600 dark:text-amber-400">
            Falta configurar la carpeta de Excels: es donde se guarda lo que baje.
          </p>
        </template>

        <template v-else-if="dianEstado === 'corriendo'">
          <div class="flex items-center gap-3 text-sm text-muted-foreground">
            <Loader2 class="size-4 shrink-0 animate-spin" />
            <span>{{ dianMensaje }}</span>
          </div>
          <p class="text-xs text-muted-foreground">
            Se abrió una ventana del navegador: el portal de la DIAN no acepta conexiones sin
            ventana. Déjala trabajar; se cierra sola al terminar.
          </p>
        </template>

        <template v-else-if="dianEstado === 'listo'">
          <div class="rounded-md border border-primary/40 bg-primary/5 p-4">
            <p class="text-sm text-foreground">
              Listo<template v-if="dianResultado?.empresa">, entrando como <strong>{{ dianResultado.empresa }}</strong></template>.
              El archivo de <strong>{{ dianPeriodo }}</strong> está descargado y <strong>todavía no se ha importado</strong>.
            </p>
            <div class="mt-3 flex flex-wrap gap-2">
              <Button :disabled="dianImportando" @click="importarDescarga">
                {{ dianImportando ? 'Importando…' : `Importar a ${dianPeriodo}` }}
              </Button>
              <Button variant="ghost" :disabled="dianImportando" @click="dianEstado = 'inactivo'; dianResultado = null">
                Descartar
              </Button>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="rounded-md border border-destructive/40 bg-destructive/5 p-4">
            <p class="text-sm text-foreground">{{ dianMensaje }}</p>
            <Button variant="outline" size="sm" class="mt-3" @click="dianEstado = 'inactivo'">Volver a intentar</Button>
          </div>
        </template>

        <!-- Soportes oficiales, por CUFE -->
        <div class="border-t border-border pt-3">
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div class="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Soportes oficiales</div>
              <p class="mt-1 max-w-prose text-xs text-muted-foreground">
                La DIAN entrega el soporte de cualquier documento con solo el CUFE y el NIT, sin
                credenciales. En vez de esperar a que el cliente los mande, los bajamos nosotros.
              </p>
            </div>
            <Button
              variant="outline" size="sm"
              :disabled="soportesEstado === 'corriendo' || !dianPeriodo"
              @click="bajarSoportes(dianPeriodo)"
            >
              <CloudDownload class="size-3.5" /> Bajar los de {{ dianPeriodo }}
            </Button>
          </div>
          <p v-if="soportesEstado === 'corriendo'" class="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 class="size-3.5 shrink-0 animate-spin" /> {{ soportesMensaje }}
          </p>
          <p v-else-if="soportesEstado === 'listo' && soportesResumen" class="text-sm text-foreground">
            {{ soportesResumen.bajados }} bajados<template v-if="soportesResumen.sin_encontrar">
            · {{ soportesResumen.sin_encontrar }} que la DIAN no tiene</template><template v-if="soportesResumen.fallidos">
            · {{ soportesResumen.fallidos }} fallidos</template>.
          </p>
        </div>

        <!-- Bitácora: el portal falla de formas que no se repiten -->
        <div v-if="ingestas.length" class="border-t border-border pt-3">
          <div class="mb-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Últimas corridas</div>
          <div v-for="g in ingestas" :key="g.id" class="flex items-start gap-2 py-1 text-sm">
            <span
              class="mt-1 size-1.5 shrink-0 rounded-full"
              :class="g.estado === 'ok' ? 'bg-primary' : 'bg-destructive'"
            />
            <span class="min-w-0 flex-1">
              <span class="font-mono text-xs text-muted-foreground">{{ g.corrio_at }}</span>
              · {{ g.periodo }}
              <template v-if="g.estado === 'ok'"> · {{ g.documentos }} documentos</template>
              <span v-else class="text-muted-foreground"> · {{ g.error }}</span>
            </span>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Perfil fiscal — qué es la empresa ante la DIAN (Fase 1.1) -->
    <Card v-if="info">
      <CardHeader>
        <CardTitle class="flex items-center gap-2"><Landmark class="size-4 text-muted-foreground" /> Perfil fiscal</CardTitle>
        <CardDescription>
          Qué es esta empresa ante la DIAN: régimen, responsabilidades y municipios de ICA.
          De aquí salen las retenciones al causar, así que cada dato vale <strong>desde una fecha</strong>:
          si en agosto la nombran autorretenedora, marzo se sigue calculando con lo que era en marzo.
        </CardDescription>
        <CardAction>
          <Button size="sm" :variant="perfil ? 'outline' : 'default'" @click="openPerfil()">
            <Pencil v-if="perfil" class="size-3.5" /><Plus v-else class="size-4" />
            {{ perfil ? 'Actualizar' : 'Configurar' }}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent class="space-y-4">
        <p v-if="!perfil" class="text-sm text-muted-foreground">
          Sin configurar. Mientras no esté, no se puede calcular ninguna retención —
          y calcularla sobre un supuesto sería peor que no calcularla.
        </p>

        <template v-else>
          <div class="grid gap-3 sm:grid-cols-3">
            <div>
              <div class="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Régimen</div>
              <div class="text-sm capitalize">{{ perfil.regimen }}</div>
            </div>
            <div>
              <div class="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">IVA</div>
              <div class="text-sm">
                <template v-if="perfil.responsable_iva">Responsable · {{ perfil.periodicidad_iva }}</template>
                <template v-else>No responsable</template>
              </div>
            </div>
            <div>
              <div class="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">CIIU</div>
              <div class="text-sm">{{ perfil.ciiu || '—' }}</div>
            </div>
          </div>

          <div class="flex flex-wrap gap-1.5">
            <Badge v-for="b in banderasActivas" :key="b.key" variant="secondary">{{ b.label }}</Badge>
            <span v-if="!banderasActivas.length" class="text-sm text-muted-foreground">Sin responsabilidades de retención marcadas.</span>
          </div>

          <p class="font-mono text-[11px] text-muted-foreground">Vigente desde {{ perfil.vigencia_desde }}</p>
          <p v-if="perfil.notas" class="text-sm text-muted-foreground">{{ perfil.notas }}</p>
        </template>

        <Separator />

        <!-- Municipios de ICA -->
        <div>
          <div class="mb-2 flex items-center justify-between">
            <div class="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Municipios de ICA</div>
            <Button variant="ghost" size="sm" @click="icaOpen = true"><Plus class="size-3.5" /> Agregar</Button>
          </div>
          <p v-if="!municipiosIca.length" class="text-sm text-muted-foreground">
            Ninguno. El ICA es municipal: la misma empresa retiene a tarifas distintas en municipios distintos.
          </p>
          <div v-for="m in municipiosIca" :key="m.id" class="flex items-center gap-2 py-1">
            <span class="min-w-0 flex-1 truncate text-sm">
              {{ m.municipio }}
              <span v-if="m.actividad" class="text-muted-foreground">· {{ m.actividad }}</span>
              <span class="font-mono text-muted-foreground"> · {{ m.tarifa_por_mil }} por mil · desde {{ m.vigencia_desde }}</span>
            </span>
            <Button variant="ghost" size="sm" @click="deleteMunicipio(m.id)"><X class="size-3.5" /></Button>
          </div>
        </div>

        <!-- Historial de versiones -->
        <div v-if="perfiles.length > 1">
          <Button variant="ghost" size="sm" @click="perfilHistorial = !perfilHistorial">
            {{ perfilHistorial ? 'Ocultar' : 'Ver' }} historial ({{ perfiles.length }} versiones)
          </Button>
          <div v-if="perfilHistorial" class="mt-1 border-t border-border pt-2">
            <div v-for="v in perfiles" :key="v.vigencia_desde" class="flex items-center gap-2 py-1">
              <span class="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                <span class="font-mono">{{ v.vigencia_desde }}</span> · {{ v.regimen }}
                <span v-if="v.responsable_iva">· IVA {{ v.periodicidad_iva }}</span>
              </span>
              <Button variant="ghost" size="sm" @click="openPerfil(v)"><Pencil class="size-3.5" /></Button>
              <Button variant="ghost" size="sm" @click="deletePerfilVersion(v.vigencia_desde)"><Trash2 class="size-3.5" /></Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Editar el perfil fiscal -->
    <Dialog :open="perfilOpen" @update:open="perfilOpen = $event">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Perfil fiscal</DialogTitle>
          <DialogDescription>
            Guardar con una fecha nueva crea otra versión y deja intacta la anterior;
            guardar con una fecha que ya existe actualiza esa versión.
          </DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-2">
          <div class="grid gap-2 sm:grid-cols-2">
            <div class="grid gap-1.5">
              <Label>Vigente desde</Label>
              <Input v-model="perfilDraft.vigencia_desde" type="date" />
            </div>
            <div class="grid gap-1.5">
              <Label>Régimen</Label>
              <Select v-model="perfilDraft.regimen">
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="ordinario">Ordinario</SelectItem>
                  <SelectItem value="simple">SIMPLE</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <Checkbox id="resp-iva" v-model="perfilDraft.responsable_iva" />
            <Label for="resp-iva">Responsable de IVA</Label>
          </div>
          <div v-if="perfilDraft.responsable_iva" class="grid gap-1.5">
            <Label>Periodicidad de IVA</Label>
            <Select v-model="perfilDraft.periodicidad_iva">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="bimestral">Bimestral</SelectItem>
                <SelectItem value="cuatrimestral">Cuatrimestral</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="grid gap-2">
            <div v-for="b in BANDERAS_PERFIL" :key="b.key" class="flex items-center gap-2">
              <Checkbox :id="b.key" v-model="perfilDraft[b.key]" />
              <Label :for="b.key">{{ b.label }}</Label>
            </div>
          </div>

          <div class="grid gap-2 sm:grid-cols-2">
            <div class="grid gap-1.5">
              <Label>Actividad CIIU</Label>
              <Input v-model="perfilDraft.ciiu" placeholder="6201" maxlength="4" />
            </div>
            <div class="grid gap-1.5">
              <Label>Notas</Label>
              <Input v-model="perfilDraft.notas" placeholder="Opcional" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" :disabled="savingPerfil" @click="perfilOpen = false">Cancelar</Button>
          <Button :disabled="savingPerfil" @click="savePerfil">Guardar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Agregar municipio de ICA -->
    <Dialog :open="icaOpen" @update:open="icaOpen = $event">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Municipio de ICA</DialogTitle>
          <DialogDescription>La tarifa va por mil y también tiene fecha de vigencia.</DialogDescription>
        </DialogHeader>
        <div class="grid gap-3 py-2">
          <div class="grid gap-1.5">
            <Label>Municipio</Label>
            <Input v-model="icaDraft.municipio" placeholder="Medellín" />
          </div>
          <div class="grid gap-2 sm:grid-cols-2">
            <div class="grid gap-1.5">
              <Label>Código DANE</Label>
              <Input v-model="icaDraft.codigo_dane" placeholder="05001" maxlength="5" />
            </div>
            <div class="grid gap-1.5">
              <Label>Tarifa por mil</Label>
              <Input v-model="icaDraft.tarifa_por_mil" placeholder="6,9" />
            </div>
          </div>
          <div class="grid gap-2 sm:grid-cols-2">
            <div class="grid gap-1.5">
              <Label>Actividad</Label>
              <Input v-model="icaDraft.actividad" placeholder="Opcional" />
            </div>
            <div class="grid gap-1.5">
              <Label>Vigente desde</Label>
              <Input v-model="icaDraft.vigencia_desde" type="date" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" :disabled="savingIca" @click="icaOpen = false">Cancelar</Button>
          <Button :disabled="savingIca" @click="saveMunicipio">Guardar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Terceros — la contraparte de cada fila (Fase 1.3) -->
    <Card v-if="info">
      <CardHeader>
        <CardTitle class="flex items-center gap-2"><Users class="size-4 text-muted-foreground" /> Terceros</CardTitle>
        <CardDescription>
          Proveedores y clientes de esta empresa. Se derivan del Excel de la DIAN —el emisor en una
          compra, el receptor en una venta— y de ahí colgarán las reglas de causación y las
          retenciones, que dependen de lo que cada tercero sea ante la DIAN.
        </CardDescription>
        <CardAction>
          <Button size="sm" variant="outline" :disabled="sembrando" @click="sembrarTerceros">
            <Sparkles class="size-3.5" /> Derivar del Excel
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent class="space-y-3">
        <div class="flex flex-wrap items-center gap-x-6 gap-y-1">
          <span class="font-mono text-sm tabular-nums text-foreground">{{ tercerosCounts.total }} terceros</span>
          <span class="font-mono text-sm tabular-nums text-muted-foreground">{{ tercerosCounts.con_rut }} con RUT consultado</span>
          <span v-if="tercerosCounts.sin_rut" class="font-mono text-sm tabular-nums text-muted-foreground">{{ tercerosCounts.sin_rut }} sin consultar</span>
          <Button variant="ghost" size="sm" class="ml-auto" @click="tercerosAbierto = !tercerosAbierto">
            {{ tercerosAbierto ? 'Ocultar' : 'Ver' }} listado
          </Button>
        </div>

        <p v-if="!tercerosCounts.total" class="text-sm text-muted-foreground">
          El catálogo está vacío. <strong>Derivar del Excel</strong> lo llena con las contrapartes de
          las filas ya importadas; no duplica nada si lo corres dos veces.
        </p>

        <template v-if="tercerosAbierto">
          <div class="flex items-center gap-2">
            <Search class="size-4 shrink-0 text-muted-foreground" />
            <Input v-model="tercerosBuscar" placeholder="Buscar por NIT o razón social" class="h-9 max-w-sm" @keyup.enter="reloadTerceros" />
            <Button variant="ghost" size="sm" @click="reloadTerceros">Buscar</Button>
            <Button variant="ghost" size="sm" class="ml-auto" @click="openTercero()"><Plus class="size-3.5" /> Agregar</Button>
          </div>

          <div class="max-h-96 overflow-y-auto rounded-md border border-border">
            <div v-for="t in terceros" :key="t.nit" class="flex items-center gap-3 border-b border-border px-3 py-2 last:border-b-0">
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm text-foreground">{{ t.razon_social || '(sin razón social)' }}</p>
                <p class="font-mono text-[11px] text-muted-foreground">
                  {{ t.nit }}<template v-if="t.dv">-{{ t.dv }}</template>
                  <template v-if="t.ciiu"> · CIIU {{ t.ciiu }}</template>
                  <template v-if="t.municipio"> · {{ t.municipio }}</template>
                </p>
              </div>
              <Badge v-for="r in t.responsabilidades" :key="r" variant="secondary" class="font-mono text-[10px]">{{ r }}</Badge>
              <Badge v-if="t.consultado_at" variant="outline" class="font-mono text-[10px]">RUT</Badge>
              <Button variant="ghost" size="sm" :disabled="consultandoNit === t.nit" @click="consultarRut(t)">
                {{ consultandoNit === t.nit ? 'Consultando…' : 'Consultar RUT' }}
              </Button>
              <Button variant="ghost" size="sm" @click="openTercero(t)"><Pencil class="size-3.5" /></Button>
            </div>
            <p v-if="!terceros.length" class="px-3 py-4 text-sm text-muted-foreground">Ningún tercero coincide.</p>
          </div>

          <p class="text-xs text-muted-foreground">
            <strong>Consultar RUT</strong> trae hoy la razón social y el tipo desde la DIAN. Las
            responsabilidades, el CIIU y el municipio se escriben a mano hasta que una sesión contra
            el portal real confirme de dónde leerlos: no se diseña contra una página que nadie ha visto.
          </p>
        </template>
      </CardContent>
    </Card>

    <!-- Editar un tercero -->
    <Dialog :open="terceroOpen" @update:open="terceroOpen = $event">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Tercero</DialogTitle>
          <DialogDescription>El NIT identifica al tercero; guardar con uno que ya existe lo actualiza.</DialogDescription>
        </DialogHeader>
        <div class="grid gap-3 py-2">
          <div class="grid gap-1.5">
            <Label>NIT</Label>
            <Input v-model="terceroDraft.nit" placeholder="830008686" />
          </div>
          <div class="grid gap-1.5">
            <Label>Razón social</Label>
            <Input v-model="terceroDraft.razon_social" />
          </div>
          <div class="grid gap-2 sm:grid-cols-2">
            <div class="grid gap-1.5">
              <Label>Actividad CIIU</Label>
              <Input v-model="terceroDraft.ciiu" placeholder="4711" maxlength="4" />
            </div>
            <div class="grid gap-1.5">
              <Label>Municipio</Label>
              <Input v-model="terceroDraft.municipio" placeholder="Medellín" />
            </div>
          </div>
          <div class="grid gap-1.5">
            <Label>Responsabilidades</Label>
            <Input v-model="terceroDraft.responsabilidades" placeholder="O-13, O-15, O-23" />
          </div>
          <div class="grid gap-1.5">
            <Label>Notas</Label>
            <Input v-model="terceroDraft.notas" placeholder="Opcional" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" :disabled="savingTercero" @click="terceroOpen = false">Cancelar</Button>
          <Button :disabled="savingTercero" @click="saveTercero">Guardar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Plan de Cuentas (PUC) — a nivel empresa -->
    <Card v-if="info">
      <CardHeader>
        <CardTitle>Plan de Cuentas (PUC)</CardTitle>
        <CardDescription>El catálogo de cuentas contables de esta empresa. Sube el dump de Excel, edítalo, archiva y agrega cuentas.</CardDescription>
        <CardAction>
          <Button size="sm" @click="navigateTo({ path: '/puc', query: { db: dbPath } })">
            <BookText class="size-4" /> Abrir plan de cuentas <ChevronRight class="size-3.5" />
          </Button>
        </CardAction>
      </CardHeader>
    </Card>

    <!-- Pickers de carpeta (soportes por mes + backup) -->
    <DirectoryPicker :open="periodoPickerOpen" :initial-path="''" :title="periodoPickerTarget ? `Carpeta de soportes de ${monthLabel(periodoPickerTarget)}` : 'Carpeta de soportes del mes'" @pick="onPeriodoFolderPicked" @close="periodoPickerOpen = false" />
    <DirectoryPicker :open="backupPickerOpen" :initial-path="''" title="Carpeta donde se guardará el backup (.contab.zip)" @pick="onBackupFolderPicked" @close="backupPickerOpen = false" />

    <!-- Crear mes -->
    <Dialog v-model:open="newMonthOpen">
      <DialogContent class="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Crear mes</DialogTitle>
          <DialogDescription>Elige el mes que vas a trabajar. Luego subes su Excel y eliges su carpeta de soportes.</DialogDescription>
        </DialogHeader>
        <div class="grid grid-cols-2 gap-2">
          <div class="flex flex-col gap-1.5">
            <Label>Mes</Label>
            <Select :model-value="newMonthMes" @update:model-value="newMonthMes = String($event ?? '')">
              <SelectTrigger class="w-full"><SelectValue placeholder="Mes" /></SelectTrigger>
              <SelectContent><SelectItem v-for="m in MESES" :key="m.v" :value="m.v">{{ m.l }}</SelectItem></SelectContent>
            </Select>
          </div>
          <div class="flex flex-col gap-1.5">
            <Label>Año</Label>
            <Select :model-value="newMonthAnio" @update:model-value="newMonthAnio = String($event ?? '')">
              <SelectTrigger class="w-full"><SelectValue placeholder="Año" /></SelectTrigger>
              <SelectContent><SelectItem v-for="y in ANIOS" :key="y" :value="y">{{ y }}</SelectItem></SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="secondary" @click="newMonthOpen = false">Cancelar</Button>
          <Button :disabled="!newMonthValue || creatingMonth" @click="createMonth">{{ creatingMonth ? 'Creando…' : 'Crear mes' }}</Button>
        </DialogFooter>
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
          <DialogDescription>La empresa sale del listado y se guarda en la papelera.</DialogDescription>
        </DialogHeader>
        <div class="flex flex-col gap-3">
          <!-- D-078: ya NO es irreversible. Decir que lo es era mentir al usuario. -->
          <div class="rounded-md border border-status-warning/30 bg-status-warning-bg px-3 py-2 text-sm text-status-warning">
            La empresa se guarda en la <strong>papelera durante 30 días</strong> y después se borra
            definitivamente. Si quieres conservarla más tiempo, archívala o haz un backup.
          </div>
          <div class="flex flex-col gap-1.5">
            <Label for="del-nit">Escribe el NIT <strong class="text-foreground">{{ info?.nit }}</strong> para confirmar:</Label>
            <Input id="del-nit" v-model="deleteConfirmNit" :placeholder="info?.nit" inputmode="numeric" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="secondary" @click="deleteModalOpen = false">Cancelar</Button>
          <Button variant="destructive" :disabled="deleting || deleteConfirmNit.trim() !== info?.nit" @click="confirmDelete">{{ deleting ? 'Eliminando…' : 'Enviar a la papelera' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
