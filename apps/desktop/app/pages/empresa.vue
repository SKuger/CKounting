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

// ── paneles ──
const panelActivo = computed(() => {
  if (terceroOpen.value) return 'tercero'
  if (tercerosVerOpen.value) return 'terceros'
  if (dianOpen.value) return 'dian'
  if (newMonthOpen.value) return 'mes'
  if (moveTarget.value) return 'mover'
  if (deleteMonthTarget.value) return 'borrarMes'
  if (archiveModalOpen.value) return 'archivar'
  if (deleteModalOpen.value) return 'borrarEmpresa'
  if (periodoPickerOpen.value || backupPickerOpen.value) return 'carpeta'
  return null
})
const TITULOS_PANEL: Record<string, string> = {
  tercero: 'Tercero', terceros: 'Terceros', dian: 'Traer de la DIAN',
  mes: 'Crear mes', mover: 'Mover el Excel de mes', borrarMes: 'Borrar mes',
  archivar: 'Archivar empresa', borrarEmpresa: 'Enviar la empresa a la papelera',
  carpeta: 'Elegir carpeta',
}
function cerrarPaneles() {
  dianOpen.value = false; tercerosVerOpen.value = false; terceroOpen.value = false
  newMonthOpen.value = false; moveTarget.value = null; deleteMonthTarget.value = null
  archiveModalOpen.value = false; deleteModalOpen.value = false
  periodoPickerOpen.value = false; backupPickerOpen.value = false
}
function alternarPanel(cual: 'dian' | 'terceros' | 'mes') {
  const abierto = panelActivo.value === cual
  cerrarPaneles()
  if (abierto) return
  if (cual === 'dian') dianOpen.value = true
  else if (cual === 'terceros') tercerosVerOpen.value = true
  else newMonthOpen.value = true
}

// El mes vigente es el que se trabaja; el resto es historial. Darles el mismo peso
// visual hacía que buscar el de este mes costara lo mismo que buscar uno de hace
// un año, y no es lo mismo que se hace cada día.
function abrirPickerMes(periodo: string) { cerrarPaneles(); _openPeriodoPickerOriginal(periodo) }

const mesVigente = computed(() => periodos.value[0] ?? null)
const historialMeses = computed(() => periodos.value.slice(1))
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
// Paneles expansibles, nunca modales (norma 2026-09-28): uno abierto a la vez, y
// el mismo botón que lo abre lo cierra. Un modal tapa el contexto justo cuando se
// necesita — configurar el perfil mientras miras el mes, pegar el enlace mientras
// ves qué mes falta.
const dianOpen = ref(false)
const tercerosVerOpen = ref(false)
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
    const faltantes = await rpc<{ carpeta: string | null; faltan: { cufe: string; nit: string }[]; total: number; meses_con_carpeta: string[] }>(
      'documentos_sin_soporte', { db_path: dbPath.value, periodo },
    )
    if (!faltantes.carpeta) {
      // Decir «no se puede» a secas parece un fallo del programa; lo que falta es
      // un dato, y el mensaje tiene que decir cuál y dónde ponerlo.
      const otros = faltantes.meses_con_carpeta?.length
        ? ` Los meses con carpeta son: ${faltantes.meses_con_carpeta.join(', ')}.`
        : ' Ningún mes tiene carpeta todavía.'
      throw new Error(
        `${periodo} no tiene carpeta de soportes en esta empresa.${otros} `
        + 'Elígela con «Cambiar soportes» en la lista de meses, o cambia el mes de arriba.',
      )
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
  dianEstado.value = 'corriendo'
  dianMensaje.value = 'Validando…'
  dianResultado.value = null
  try {
    // El core valida el enlace y calcula el rango del mes; si algo está mal, se
    // sabe ANTES de abrir un navegador contra la DIAN.
    // El core valida y además decide dónde cae el archivo: es un intermedio.
    const plan = await rpc<Record<string, unknown>>(
      'preparar_descarga_dian', { db_path: dbPath.value, periodo: dianPeriodo.value, enlace: dianEnlace.value },
    )
    dianMensaje.value = 'Abriendo el portal…'
    const inicio = await $fetch<{ id: string }>('/api/dian/portal/descargar', {
      method: 'POST', body: plan,
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
function _openPeriodoPickerOriginal(periodo: string) { periodoPickerTarget.value = periodo; periodoPickerOpen.value = true }
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
  <div class="flex h-full min-h-0 w-full flex-col gap-3 p-4">

    <!-- ── identidad y acciones ── -->
    <header v-if="info" class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2">
      <NuxtLink to="/" class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft class="size-4" />
      </NuxtLink>
      <div class="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
        <template v-if="editingRazon">
          <Input v-model="razonDraft" :disabled="savingRazon" class="h-9 w-72" @keyup.enter="saveRazon" @keyup.escape="editingRazon = false" />
          <Button size="sm" variant="secondary" :disabled="savingRazon || !razonDraft.trim()" @click="saveRazon">Guardar</Button>
          <Button size="sm" variant="ghost" :disabled="savingRazon" @click="editingRazon = false">Cancelar</Button>
        </template>
        <template v-else>
          <h1 class="truncate font-heading text-xl font-medium tracking-tight">{{ info.razon_social }}</h1>
          <span class="font-mono text-xs text-muted-foreground">{{ info.nit }}<template v-if="info.dv">-{{ info.dv }}</template></span>
          <Button variant="ghost" size="icon-sm" title="Editar razón social" @click="startEditingRazon"><Pencil class="size-3.5" /></Button>
        </template>
      </div>

      <div class="ml-auto flex shrink-0 items-center gap-2">
        <Button size="sm" data-tour="empresa-crear-mes" :variant="panelActivo === 'mes' ? 'secondary' : 'outline'" @click="alternarPanel('mes')">
          <CalendarPlus class="size-4" /> Crear mes
        </Button>
        <Button size="sm" :variant="panelActivo === 'dian' ? 'secondary' : 'default'" @click="alternarPanel('dian')">
          <CloudDownload class="size-4" /> Traer de la DIAN
        </Button>
        <Popover>
          <PopoverTrigger as-child>
            <Button variant="outline" size="icon-sm" aria-label="Más acciones"><EllipsisVertical class="size-4" /></Button>
          </PopoverTrigger>
          <PopoverContent align="end" :side-offset="6" class="w-56 p-1">
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent disabled:opacity-50" :disabled="backingUp" @click="backupPickerOpen = true">
              <Download class="size-4" /> {{ backingUp ? 'Generando…' : 'Hacer backup' }}
            </button>
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent disabled:opacity-50" :disabled="archiving" @click="cerrarPaneles(); archiveModalOpen = true">
              <Archive class="size-4" /> Archivar
            </button>
            <div class="my-1 h-px bg-border" />
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-destructive transition-colors hover:bg-accent" @click="cerrarPaneles(); openDeleteModal()">
              <Trash2 class="size-4" /> Enviar a la papelera
            </button>
          </PopoverContent>
        </Popover>
      </div>
    </header>

    <Card v-else-if="loading" class="shrink-0"><CardContent class="py-10 text-center text-muted-foreground">Cargando empresa…</CardContent></Card>
    <Card v-else class="shrink-0"><CardContent class="py-6"><div class="rounded-md border border-status-error/30 bg-status-error-bg px-3 py-2 text-sm text-status-error">Empresa no encontrada. <NuxtLink to="/" class="underline">Volver</NuxtLink></div></CardContent></Card>

    <!-- ══════════ el panel expansible: nunca un modal ══════════ -->
    <!-- el selector de carpetas trae su propio marco -->
    <DirectoryPicker
      v-if="panelActivo === 'carpeta'"
      class="shrink-0"
      :open="periodoPickerOpen || backupPickerOpen"
      :initial-path="''"
      :title="periodoPickerOpen
        ? (periodoPickerTarget ? `Carpeta de soportes de ${monthLabel(periodoPickerTarget)}` : 'Carpeta de soportes del mes')
        : 'Carpeta donde se guardará el backup (.contab.zip)'"
      @pick="(ruta: string) => periodoPickerOpen ? onPeriodoFolderPicked(ruta) : onBackupFolderPicked(ruta)"
      @close="cerrarPaneles"
    />

    <section v-if="panelActivo && panelActivo !== 'carpeta'" class="max-h-[62vh] shrink-0 overflow-y-auto rounded-lg border border-primary/40 bg-card">
      <div class="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-border bg-card px-4 py-2.5">
        <h2 class="text-sm font-semibold">{{ TITULOS_PANEL[panelActivo] }}</h2>
        <Button variant="ghost" size="icon-sm" aria-label="Cerrar" @click="cerrarPaneles"><X class="size-4" /></Button>
      </div>

      <div class="p-4">
        <!-- ───────── traer de la DIAN ───────── -->
        <template v-if="panelActivo === 'dian'">
          <p class="mb-3 max-w-prose text-sm text-muted-foreground">
            Pega el enlace que la DIAN manda al correo y elige el mes. Contab entra al portal, pide
            el listado, espera a que lo generen y lo baja. Nada entra a la contabilidad hasta que lo apruebes.
          </p>
          <div class="grid gap-4 lg:grid-cols-2">
            <div class="flex flex-col gap-3">
              <template v-if="dianEstado === 'inactivo'">
                <div class="grid gap-1.5">
                  <Label for="dian-enlace">Enlace de acceso</Label>
                  <Input id="dian-enlace" v-model="dianEnlace" type="password" autocomplete="off" placeholder="https://catalogo-vpfe.dian.gov.co/User/AuthToken?…" />
                  <p class="text-xs text-muted-foreground">No se guarda en ningún lado: se usa para esta descarga y se descarta.</p>
                </div>
                <div class="flex flex-wrap items-end gap-2">
                  <div class="grid gap-1.5">
                    <Label>Mes</Label>
                    <Select v-model="dianMes">
                      <SelectTrigger class="w-36"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem v-for="m in MESES" :key="m.v" :value="m.v">{{ m.l }}</SelectItem></SelectContent>
                    </Select>
                  </div>
                  <div class="grid gap-1.5">
                    <Label>Año</Label>
                    <Select v-model="dianAnio">
                      <SelectTrigger class="w-28"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem v-for="a in ANIOS" :key="a" :value="a">{{ a }}</SelectItem></SelectContent>
                    </Select>
                  </div>
                  <Button :disabled="!dianEnlace || !dianPeriodo" @click="bajarDeLaDian"><CloudDownload class="size-4" /> Bajar</Button>
                </div>
              </template>

              <template v-else-if="dianEstado === 'corriendo'">
                <div class="flex items-center gap-3 text-sm text-muted-foreground">
                  <Loader2 class="size-4 shrink-0 animate-spin" /><span>{{ dianMensaje }}</span>
                </div>
                <p class="text-xs text-muted-foreground">Se abrió una ventana del navegador: el portal no acepta conexiones sin ventana. Se cierra sola al terminar.</p>
              </template>

              <template v-else-if="dianEstado === 'listo'">
                <div class="rounded-md border border-primary/40 bg-primary/5 p-3">
                  <p class="text-sm">
                    Listo<template v-if="dianResultado?.empresa">, como <strong>{{ dianResultado.empresa }}</strong></template>.
                    El listado de <strong>{{ dianPeriodo }}</strong> está descargado y <strong>todavía no se importó</strong>.
                  </p>
                  <div class="mt-3 flex flex-wrap gap-2">
                    <Button :disabled="dianImportando" @click="importarDescarga">{{ dianImportando ? 'Importando…' : `Importar a ${dianPeriodo}` }}</Button>
                    <Button variant="ghost" :disabled="dianImportando" @click="dianEstado = 'inactivo'; dianResultado = null">Descartar</Button>
                  </div>
                </div>
              </template>

              <template v-else>
                <div class="rounded-md border border-destructive/40 bg-destructive/5 p-3">
                  <p class="text-sm">{{ dianMensaje }}</p>
                  <Button variant="outline" size="sm" class="mt-2" @click="dianEstado = 'inactivo'">Volver a intentar</Button>
                </div>
              </template>
            </div>

            <div class="rounded-md border border-border p-3">
              <div class="text-sm font-medium">Soportes oficiales</div>
              <p class="mt-1 text-xs text-muted-foreground">
                La DIAN entrega el soporte de cualquier documento con solo el CUFE y el NIT, sin
                credenciales. En vez de esperar a que el cliente los mande, los bajamos nosotros.
              </p>
              <Button variant="outline" size="sm" class="mt-2" :disabled="soportesEstado === 'corriendo' || !dianPeriodo" @click="bajarSoportes(dianPeriodo)">
                <CloudDownload class="size-3.5" /> Bajar los de {{ dianPeriodo }}
              </Button>
              <p v-if="soportesEstado === 'corriendo'" class="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 class="size-3.5 shrink-0 animate-spin" /> {{ soportesMensaje }}
              </p>
              <p v-else-if="soportesEstado === 'listo' && soportesResumen" class="mt-2 text-sm">
                {{ soportesResumen.bajados }} bajados<template v-if="soportesResumen.sin_encontrar"> · {{ soportesResumen.sin_encontrar }} que la DIAN no tiene</template><template v-if="soportesResumen.fallidos"> · {{ soportesResumen.fallidos }} fallidos</template>.
              </p>
            </div>
          </div>
        </template>

        <!-- ───────── listado de terceros ───────── -->
        <template v-else-if="panelActivo === 'terceros'">
          <div class="flex items-center gap-2">
            <Search class="size-4 shrink-0 text-muted-foreground" />
            <Input v-model="tercerosBuscar" placeholder="Buscar por NIT o razón social" class="h-9 max-w-sm" @keyup.enter="reloadTerceros" />
            <Button variant="ghost" size="sm" @click="reloadTerceros">Buscar</Button>
            <Button variant="ghost" size="sm" class="ml-auto" @click="openTercero()"><Plus class="size-3.5" /> Agregar</Button>
          </div>
          <div class="mt-2 rounded-md border border-border">
            <div v-for="t in terceros" :key="t.nit" class="flex items-center gap-3 border-b border-border px-3 py-2 last:border-b-0">
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm">{{ t.razon_social || '(sin razón social)' }}</p>
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
              <Button variant="ghost" size="icon-sm" @click="openTercero(t)"><Pencil class="size-3.5" /></Button>
            </div>
            <p v-if="!terceros.length" class="px-3 py-4 text-sm text-muted-foreground">Ningún tercero coincide.</p>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">
            <strong>Consultar RUT</strong> trae hoy la razón social y el tipo. Las responsabilidades y
            el CIIU se escriben a mano hasta que se confirme de dónde leerlos en el portal.
          </p>
        </template>

        <!-- ───────── ficha de un tercero ───────── -->
        <template v-else-if="panelActivo === 'tercero'">
          <div class="grid max-w-3xl gap-3 sm:grid-cols-2">
            <div class="grid gap-1.5"><Label>NIT</Label><Input v-model="terceroDraft.nit" placeholder="830008686" /></div>
            <div class="grid gap-1.5"><Label>Razón social</Label><Input v-model="terceroDraft.razon_social" /></div>
            <div class="grid gap-1.5"><Label>Actividad CIIU</Label><Input v-model="terceroDraft.ciiu" placeholder="4711" maxlength="4" /></div>
            <div class="grid gap-1.5"><Label>Municipio</Label><Input v-model="terceroDraft.municipio" placeholder="Medellín" /></div>
            <div class="grid gap-1.5"><Label>Responsabilidades</Label><Input v-model="terceroDraft.responsabilidades" placeholder="O-13, O-15, O-23" /></div>
            <div class="grid gap-1.5"><Label>Notas</Label><Input v-model="terceroDraft.notas" placeholder="Opcional" /></div>
          </div>
          <div class="mt-3 flex gap-2">
            <Button :disabled="savingTercero" @click="saveTercero">Guardar</Button>
            <Button variant="ghost" :disabled="savingTercero" @click="terceroOpen = false">Cancelar</Button>
          </div>
        </template>

        <!-- ───────── crear mes ───────── -->
        <template v-else-if="panelActivo === 'mes'">
          <p class="mb-3 text-sm text-muted-foreground">Elige el mes que vas a trabajar. Luego subes su Excel y eliges su carpeta de soportes.</p>
          <div class="flex flex-wrap items-end gap-2">
            <div class="grid gap-1.5">
              <Label>Mes</Label>
              <Select :model-value="newMonthMes" @update:model-value="newMonthMes = String($event ?? '')">
                <SelectTrigger class="w-40"><SelectValue placeholder="Mes" /></SelectTrigger>
                <SelectContent><SelectItem v-for="m in MESES" :key="m.v" :value="m.v">{{ m.l }}</SelectItem></SelectContent>
              </Select>
            </div>
            <div class="grid gap-1.5">
              <Label>Año</Label>
              <Select :model-value="newMonthAnio" @update:model-value="newMonthAnio = String($event ?? '')">
                <SelectTrigger class="w-28"><SelectValue placeholder="Año" /></SelectTrigger>
                <SelectContent><SelectItem v-for="y in ANIOS" :key="y" :value="y">{{ y }}</SelectItem></SelectContent>
              </Select>
            </div>
            <Button :disabled="!newMonthValue || creatingMonth" @click="createMonth">{{ creatingMonth ? 'Creando…' : 'Crear mes' }}</Button>
          </div>
        </template>

        <!-- ───────── mover el Excel ───────── -->
        <template v-else-if="panelActivo === 'mover'">
          <p class="mb-3 text-sm text-muted-foreground">Elige el mes destino para «{{ moveTarget?.source_name }}».</p>
          <div class="flex flex-wrap items-end gap-2">
            <div class="grid gap-1.5">
              <Label>Mes destino</Label>
              <Select :model-value="moveDestino" @update:model-value="moveDestino = String($event ?? '')">
                <SelectTrigger class="w-64"><SelectValue placeholder="Elegir mes…" /></SelectTrigger>
                <SelectContent><SelectItem v-for="p in periodos" :key="p.periodo" :value="p.periodo">{{ monthLabel(p.periodo) }} ({{ p.periodo }})</SelectItem></SelectContent>
              </Select>
            </div>
            <Button :disabled="!moveDestino || busy" @click="confirmMove">Mover</Button>
            <Button variant="ghost" @click="moveTarget = null">Cancelar</Button>
          </div>
        </template>

        <!-- ───────── borrar mes ───────── -->
        <template v-else-if="panelActivo === 'borrarMes'">
          <p class="mb-3 max-w-prose text-sm text-muted-foreground">
            Se elimina el mes <strong class="text-foreground">{{ deleteMonthTarget }}</strong> y el Excel que tenga cargado.
            Los soportes en disco no se tocan. Esta acción no se puede deshacer.
          </p>
          <div class="flex gap-2">
            <Button variant="destructive" :disabled="busy" @click="confirmDeleteMonth">Borrar mes</Button>
            <Button variant="ghost" @click="deleteMonthTarget = null">Cancelar</Button>
          </div>
        </template>

        <!-- ───────── archivar ───────── -->
        <template v-else-if="panelActivo === 'archivar'">
          <p class="mb-3 max-w-prose text-sm text-muted-foreground">
            Quedará oculta de la lista principal, pero sus datos se conservan y puedes desarchivarla cuando quieras.
          </p>
          <div class="flex gap-2">
            <Button :disabled="archiving" @click="confirmArchive">{{ archiving ? 'Archivando…' : 'Archivar' }}</Button>
            <Button variant="ghost" @click="archiveModalOpen = false">Cancelar</Button>
          </div>
        </template>

        <!-- ───────── enviar la empresa a la papelera ───────── -->
        <template v-else-if="panelActivo === 'borrarEmpresa'">
          <div class="max-w-prose">
            <!-- D-078: ya NO es irreversible. Decir que lo es era mentir al usuario. -->
            <div class="rounded-md border border-status-warning/30 bg-status-warning-bg px-3 py-2 text-sm text-status-warning">
              La empresa se guarda en la <strong>papelera durante 30 días</strong> y después se borra
              definitivamente. Si quieres conservarla más tiempo, archívala o haz un backup.
            </div>
            <div class="mt-3 grid gap-1.5">
              <Label for="del-nit">Escribe el NIT <strong class="text-foreground">{{ info?.nit }}</strong> para confirmar:</Label>
              <Input id="del-nit" v-model="deleteConfirmNit" :placeholder="info?.nit" inputmode="numeric" class="max-w-xs" />
            </div>
            <div class="mt-3 flex gap-2">
              <Button variant="destructive" :disabled="deleting || deleteConfirmNit.trim() !== info?.nit" @click="confirmDelete">{{ deleting ? 'Eliminando…' : 'Enviar a la papelera' }}</Button>
              <Button variant="ghost" @click="deleteModalOpen = false">Cancelar</Button>
            </div>
          </div>
        </template>
      </div>
    </section>

    <!-- ══════════ el espacio de trabajo ══════════ -->
    <div v-if="info" class="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_340px]">

      <div class="flex min-h-0 flex-col gap-3">
        <!-- EL MES VIGENTE: lo que se trabaja hoy -->
        <section v-if="mesVigente" data-tour="empresa-periodos" class="shrink-0 rounded-lg border border-border bg-card p-4">
          <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span class="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">El mes</span>
            <h2 class="font-heading text-2xl font-medium first-letter:uppercase">{{ monthLabel(mesVigente.periodo) }}</h2>
            <span class="font-mono text-xs text-muted-foreground">{{ mesVigente.periodo }}</span>
          </div>

          <div class="mt-3 flex flex-wrap gap-x-8 gap-y-2">
            <div>
              <div class="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">Filas</div>
              <div class="font-mono text-lg tabular-nums">{{ mesVigente.row_count }}</div>
            </div>
            <div>
              <div class="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">CUFE indexados</div>
              <div class="font-mono text-lg tabular-nums" :class="mesVigente.indexed_cufe_count ? '' : 'text-muted-foreground'">{{ mesVigente.indexed_cufe_count }}</div>
            </div>
            <div class="min-w-0">
              <div class="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">Soportes</div>
              <div class="truncate text-sm" :title="mesVigente.pdfs_folder || ''">
                <span v-if="mesVigente.pdfs_folder">{{ folderName(mesVigente.pdfs_folder) }}</span>
                <span v-else class="text-amber-600 dark:text-amber-400">sin carpeta</span>
              </div>
            </div>
          </div>

          <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-dashed border-border pt-3">
            <template v-if="activeLoadsByPeriodo.get(mesVigente.periodo)?.length">
              <div v-for="c in activeLoadsByPeriodo.get(mesVigente.periodo)" :key="c.id" class="flex w-full flex-wrap items-center gap-2">
                <FileSpreadsheet class="size-4 shrink-0 text-muted-foreground" />
                <span class="min-w-0 flex-1 truncate text-sm">{{ c.source_name }}</span>
                <Button size="sm" @click="navigateTo({ path: '/load', query: { db: dbPath, id: c.id } })">Abrir y validar <ChevronRight class="size-3.5" /></Button>
                <Button variant="ghost" size="sm" :disabled="busy" @click="cerrarPaneles(); moveTarget = c">Mover</Button>
                <Button variant="ghost" size="icon-sm" title="Enviar a papelera" :disabled="busy" @click="trashLoad(c)"><Trash2 class="size-3.5" /></Button>
              </div>
            </template>
            <template v-else>
              <span class="text-sm text-muted-foreground">Sin Excel en este mes.</span>
              <Button as-child variant="outline" size="sm" :disabled="busy">
                <label class="cursor-pointer">
                  <UploadCloud class="size-4" /> Cargar Excel
                  <input type="file" accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel" hidden @change="onExcelPicked($event, mesVigente.periodo)">
                </label>
              </Button>
              <Button variant="outline" size="sm" @click="alternarPanel('dian')"><CloudDownload class="size-4" /> Traerlo de la DIAN</Button>
            </template>
            <div class="ml-auto flex items-center gap-1">
              <Button variant="ghost" size="sm" :disabled="busy" @click="abrirPickerMes(mesVigente.periodo)">
                <FolderOpen class="size-3.5" /> {{ mesVigente.pdfs_folder ? 'Cambiar carpeta' : 'Elegir carpeta' }}
              </Button>
              <Button variant="ghost" size="icon-sm" title="Borrar mes" :disabled="busy" @click="cerrarPaneles(); deleteMonthTarget = mesVigente.periodo"><Trash2 class="size-3.5" /></Button>
            </div>
          </div>
        </section>

        <p v-else class="rounded-lg border border-dashed border-border py-10 text-center text-sm text-muted-foreground">
          Aún no hay meses. Crea el primero con <strong class="text-foreground">«Crear mes»</strong>, o tráelo de la DIAN.
        </p>

        <!-- HISTORIAL -->
        <section class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-card">
          <div class="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-2">
            <h2 class="text-sm font-semibold">Historial</h2>
            <Button v-if="trashedLoads.length" variant="ghost" size="sm" :class="showTrash ? 'text-foreground' : ''" @click="showTrash = !showTrash">
              <RotateCcw class="size-3.5" /> Papelera ({{ trashedLoads.length }})
            </Button>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto">
            <p v-if="!historialMeses.length" class="px-4 py-6 text-sm text-muted-foreground">
              Todavía no hay meses anteriores.
            </p>
            <div
              v-for="p in historialMeses" :key="p.periodo"
              class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-4 py-2 last:border-b-0 hover:bg-muted/40"
            >
              <span class="w-36 shrink-0 text-sm first-letter:uppercase">{{ monthLabel(p.periodo) }}</span>
              <span class="font-mono text-[11px] text-muted-foreground">{{ p.row_count }} filas · {{ p.indexed_cufe_count }} CUFE</span>
              <span class="truncate text-xs text-muted-foreground" :title="p.pdfs_folder || ''">
                {{ p.pdfs_folder ? folderName(p.pdfs_folder) : 'sin carpeta' }}
              </span>
              <div class="ml-auto flex items-center gap-1">
                <Button
                  v-for="c in activeLoadsByPeriodo.get(p.periodo) || []" :key="c.id"
                  variant="ghost" size="sm"
                  @click="navigateTo({ path: '/load', query: { db: dbPath, id: c.id } })"
                >Abrir <ChevronRight class="size-3.5" /></Button>
                <Button variant="ghost" size="sm" :disabled="busy" @click="abrirPickerMes(p.periodo)"><FolderOpen class="size-3.5" /></Button>
                <Button variant="ghost" size="icon-sm" title="Borrar mes" :disabled="busy" @click="cerrarPaneles(); deleteMonthTarget = p.periodo"><Trash2 class="size-3.5" /></Button>
              </div>
            </div>

            <div v-if="showTrash && trashedLoads.length" class="border-t border-dashed border-border bg-muted/30 px-4 py-2">
              <div class="mb-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Papelera</div>
              <div v-for="c in trashedLoads" :key="c.id" class="flex items-center gap-2 py-1">
                <FileSpreadsheet class="size-4 shrink-0 text-muted-foreground opacity-70" />
                <span class="min-w-0 flex-1 truncate text-sm text-muted-foreground">{{ c.source_name }} <span v-if="c.periodo" class="font-mono">· {{ c.periodo }}</span></span>
                <Button variant="ghost" size="sm" :disabled="busy" @click="restoreLoad(c)"><RotateCcw class="size-3.5" /> Restaurar</Button>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- panel lateral: lo que se configura una vez -->
      <aside class="flex min-h-0 flex-col gap-3 overflow-y-auto">

        <!-- perfil fiscal, con su formulario expandible EN SITIO -->
        <div class="rounded-lg border border-border bg-card p-3">
          <div class="mb-2 flex items-center justify-between gap-2">
            <h3 class="flex items-center gap-1.5 text-sm font-semibold"><Landmark class="size-3.5 text-muted-foreground" /> Perfil fiscal</h3>
            <Button size="sm" :variant="perfilOpen ? 'secondary' : (perfil ? 'ghost' : 'default')" @click="perfilOpen ? (perfilOpen = false) : openPerfil()">
              {{ perfilOpen ? 'Cerrar' : (perfil ? 'Editar' : 'Configurar') }}
            </Button>
          </div>

          <template v-if="!perfilOpen">
            <p v-if="!perfil" class="text-xs text-muted-foreground">
              Sin configurar. Hasta que esté, no se puede calcular ninguna retención.
            </p>
            <template v-else>
              <p class="text-sm first-letter:uppercase">
                {{ perfil.regimen }}
                <span class="text-muted-foreground">
                  · IVA <template v-if="perfil.responsable_iva">{{ perfil.periodicidad_iva }}</template><template v-else>no responsable</template>
                </span>
              </p>
              <div class="mt-1.5 flex flex-wrap gap-1">
                <Badge v-for="b in banderasActivas" :key="b.key" variant="secondary" class="text-[10px]">{{ b.label }}</Badge>
                <Badge v-for="m in municipiosIca" :key="m.id" variant="outline" class="font-mono text-[10px]">{{ m.municipio }} {{ m.tarifa_por_mil }}‰</Badge>
              </div>
              <p class="mt-1.5 font-mono text-[10px] text-muted-foreground">desde {{ perfil.vigencia_desde }}</p>
            </template>
            <Button variant="ghost" size="sm" class="mt-1 h-7 px-1 text-xs" @click="icaOpen = !icaOpen">
              <Plus class="size-3" /> Municipio de ICA
            </Button>
          </template>

          <!-- formulario del perfil -->
          <div v-if="perfilOpen" class="grid gap-3 border-t border-border pt-3">
            <div class="grid gap-1.5">
              <Label>Vigente desde</Label>
              <Input v-model="perfilDraft.vigencia_desde" type="date" />
              <p class="text-[11px] text-muted-foreground">
                Una fecha nueva crea otra versión y deja intacta la anterior.
              </p>
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
            <div class="grid gap-1.5">
              <div v-for="b in BANDERAS_PERFIL" :key="b.key" class="flex items-center gap-2">
                <Checkbox :id="b.key" v-model="perfilDraft[b.key]" />
                <Label :for="b.key" class="text-sm font-normal">{{ b.label }}</Label>
              </div>
            </div>
            <div class="grid gap-1.5"><Label>Actividad CIIU</Label><Input v-model="perfilDraft.ciiu" placeholder="6201" maxlength="4" /></div>
            <div class="grid gap-1.5"><Label>Notas</Label><Input v-model="perfilDraft.notas" placeholder="Opcional" /></div>
            <div class="flex gap-2">
              <Button size="sm" :disabled="savingPerfil" @click="savePerfil">Guardar</Button>
              <Button size="sm" variant="ghost" :disabled="savingPerfil" @click="perfilOpen = false">Cancelar</Button>
            </div>

            <div v-if="perfiles.length > 1" class="border-t border-border pt-2">
              <Button variant="ghost" size="sm" class="h-7 px-1 text-xs" @click="perfilHistorial = !perfilHistorial">
                {{ perfilHistorial ? 'Ocultar' : 'Ver' }} historial ({{ perfiles.length }})
              </Button>
              <div v-if="perfilHistorial" class="mt-1">
                <div v-for="v in perfiles" :key="v.vigencia_desde" class="flex items-center gap-1 py-0.5 text-xs text-muted-foreground">
                  <span class="min-w-0 flex-1 truncate"><span class="font-mono">{{ v.vigencia_desde }}</span> · {{ v.regimen }}</span>
                  <Button variant="ghost" size="icon-sm" @click="openPerfil(v)"><Pencil class="size-3" /></Button>
                  <Button variant="ghost" size="icon-sm" @click="deletePerfilVersion(v.vigencia_desde)"><Trash2 class="size-3" /></Button>
                </div>
              </div>
            </div>
          </div>

          <!-- municipio de ICA, también en sitio -->
          <div v-if="icaOpen" class="mt-3 grid gap-2 border-t border-border pt-3">
            <div class="grid gap-1.5"><Label>Municipio</Label><Input v-model="icaDraft.municipio" placeholder="Medellín" /></div>
            <div class="grid grid-cols-2 gap-2">
              <div class="grid gap-1.5"><Label>DANE</Label><Input v-model="icaDraft.codigo_dane" placeholder="05001" maxlength="5" /></div>
              <div class="grid gap-1.5"><Label>Por mil</Label><Input v-model="icaDraft.tarifa_por_mil" placeholder="6,9" /></div>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div class="grid gap-1.5"><Label>Actividad</Label><Input v-model="icaDraft.actividad" placeholder="Opcional" /></div>
              <div class="grid gap-1.5"><Label>Desde</Label><Input v-model="icaDraft.vigencia_desde" type="date" /></div>
            </div>
            <div class="flex gap-2">
              <Button size="sm" :disabled="savingIca" @click="saveMunicipio">Guardar</Button>
              <Button size="sm" variant="ghost" :disabled="savingIca" @click="icaOpen = false">Cancelar</Button>
            </div>
            <div v-for="m in municipiosIca" :key="m.id" class="flex items-center gap-1 text-xs text-muted-foreground">
              <span class="min-w-0 flex-1 truncate">{{ m.municipio }} · {{ m.tarifa_por_mil }}‰ · desde {{ m.vigencia_desde }}</span>
              <Button variant="ghost" size="icon-sm" @click="deleteMunicipio(m.id)"><X class="size-3" /></Button>
            </div>
          </div>
        </div>

        <!-- terceros -->
        <div class="rounded-lg border border-border bg-card p-3">
          <div class="mb-2 flex items-center justify-between gap-2">
            <h3 class="flex items-center gap-1.5 text-sm font-semibold"><Users class="size-3.5 text-muted-foreground" /> Terceros</h3>
            <span class="font-mono text-sm tabular-nums">{{ tercerosCounts.total }}</span>
          </div>
          <p class="text-xs text-muted-foreground">
            <template v-if="tercerosCounts.total">{{ tercerosCounts.con_rut }} con RUT · {{ tercerosCounts.sin_rut }} sin consultar</template>
            <template v-else>Vacío. «Derivar» los saca de las filas del Excel ya importadas.</template>
          </p>
          <div class="mt-2 flex flex-wrap gap-1.5">
            <Button variant="outline" size="sm" :disabled="sembrando" @click="sembrarTerceros"><Sparkles class="size-3.5" /> Derivar</Button>
            <Button v-if="tercerosCounts.total" size="sm" :variant="panelActivo === 'terceros' ? 'secondary' : 'ghost'" @click="alternarPanel('terceros')">
              {{ panelActivo === 'terceros' ? 'Cerrar listado' : 'Ver listado' }}
            </Button>
          </div>
        </div>

        <!-- plan de cuentas -->
        <div class="flex items-center justify-between gap-2 rounded-lg border border-border bg-card p-3">
          <div class="min-w-0">
            <h3 class="flex items-center gap-1.5 text-sm font-semibold"><BookText class="size-3.5 text-muted-foreground" /> Plan de cuentas</h3>
            <p class="text-xs text-muted-foreground">El catálogo contable de esta empresa.</p>
          </div>
          <Button variant="outline" size="sm" @click="navigateTo({ path: '/puc', query: { db: dbPath } })">Abrir <ChevronRight class="size-3.5" /></Button>
        </div>

        <!-- bitácora -->
        <div v-if="ingestas.length" class="rounded-lg border border-border bg-card p-3">
          <h3 class="mb-1.5 text-sm font-semibold">Últimas corridas</h3>
          <div v-for="g in ingestas" :key="g.id" class="flex items-start gap-2 py-0.5 text-xs">
            <span class="mt-1.5 size-1.5 shrink-0 rounded-full" :class="g.estado === 'ok' ? 'bg-primary' : 'bg-destructive'" />
            <span class="min-w-0 flex-1">
              <span class="font-mono text-muted-foreground">{{ g.corrio_at?.slice(0, 16) }}</span> · {{ g.periodo }}
              <template v-if="g.estado === 'ok'"> · {{ g.documentos }} docs</template>
              <span v-else class="text-muted-foreground"> · {{ g.error }}</span>
            </span>
          </div>
        </div>
      </aside>
    </div>

  </div>
</template>
