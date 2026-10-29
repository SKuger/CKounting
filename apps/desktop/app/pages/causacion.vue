<script setup lang="ts">
// La bandeja de aprobación (Fase 4.5). La describió el contador el 2026-10-22:
//
//   «Para el primer registro de una factura de un proveedor me muestras en
//   pantalla cómo sería el registro, yo lo valido y en caso de un cambio lo
//   pueda realizar yo; y como por lo general el concepto que factura el
//   proveedor es el mismo, las siguientes facturas se registrarían de esa
//   forma. Pero si en otra factura el concepto cambia, me presentas la nueva
//   propuesta y le doy el visto bueno.»
//
// De ahí las tres cosas que manda esta pantalla: se ve el asiento ENTERO antes
// de aprobar, se puede corregir, y al aprobar **se aprende** — aprobar no es
// marcar una casilla, es enseñarle a Contab lo que él acaba de decidir.
import { ArrowLeft, RefreshCw, Check, Undo2, ChevronRight, Download, FileSpreadsheet, Settings2, UploadCloud, Plus, X, Save, TriangleAlert } from 'lucide-vue-next'

type Linea = {
  id: number; cuenta_puc: string | null; descripcion: string; debito: string; credito: string
  rol: string | null; codigo_siigo: string | null; tercero_nit?: string | null
  base?: string | null; concepto_id?: number | null
}
// `naturaleza` (D-127): compra, venta o doc_soporte. Decide qué líneas lleva,
// quién es el tercero y qué se le pregunta al contador al aprobar.
type Naturaleza = 'compra' | 'venta' | 'doc_soporte'
type Asiento = {
  id: number; cufe: string; tercero_nit: string | null; fecha: string | null
  estado: string; avisos: string[]; aprobado: number; lineas: Linea[]; naturaleza: Naturaleza
  editado?: number
  // Lo que eligió arriba del editor al guardar (JSON): retención, texto, IVA…
  correccion?: string | null
}
type Guardada = {
  cuenta_puc?: string; patron?: string; concepto_retencion_id?: number | string | null
  sin_retencion?: boolean; aprender_regla?: boolean; iva_codigo?: string; retenciones_cliente?: string
}
const ETIQUETA: Record<Naturaleza, string> = { compra: 'Compra', venta: 'Venta', doc_soporte: 'Doc. soporte' }
type Resumen = { total: number; completos: number; revisar: number; aprobados: number; porcentaje_completo: number }

const route = useRoute()
const toast = useToast()
const dbPath = computed(() => (route.query.db as string) || '')
const periodo = computed(() => (route.query.periodo as string) || '')

const cargando = ref(false)
const generando = ref(false)
const asientos = ref<Asiento[]>([])
const resumen = ref<Resumen>({ total: 0, completos: 0, revisar: 0, aprobados: 0, porcentaje_completo: 0 })
const razonSocial = ref('')
// Las cuatro cuentas que Contab no puede deducir, del PUC de ESTA empresa.
const cuentas = reactive({
  cuenta_proveedores: '', cuenta_iva_descontable: '', cuenta_clientes: '', cuenta_iva_generado: '',
})
const abierto = ref<number | null>(null)
const guardando = ref(false)
// Armar la propuesta se pasaba de los 30 s en meses grandes: va como trabajo
// en segundo plano con progreso (D-076).
const trabajo = useJob()

// Los conceptos de retención de la empresa, para elegir uno al aprobar.
type Concepto = { id: number; concepto: string; aplica_a: string; sobre: string }
const conceptos = ref<Concepto[]>([])

// Lo que él corrige de un asiento antes de darle el visto bueno. `retencion`
// es '' (no ha dicho), 'ninguna' (dijo que no se retiene) o el id del concepto.
// Sin esto la regla aprendida no contaba como decisión, y aprobar la primera
// factura de un proveedor no liberaba las siguientes.
const correccion = reactive({ cuenta_puc: '', patron: '', retencion: '' as string, aprender_regla: true, iva_codigo: '' })

const exportOpen = ref(false)
const exportando = ref(false)

// El archivo de Siigo (D-128): lo que el contador sube cada mes. Lo que Siigo
// exige y Contab no deduce —tipos de comprobante, último consecutivo, códigos
// de IVA— vive en `siigo_config`, por empresa, y se edita en este panel.
const siigoOpen = ref(false)
const siigoPanel = ref(false)
const siigoExportando = ref(false)
const siigoGuardando = ref(false)
const CLASES = [
  { clave: 'compra', etiqueta: 'Factura de compra' },
  { clave: 'nc_compra', etiqueta: 'Nota crédito de compra' },
  { clave: 'doc_soporte', etiqueta: 'Documento soporte' },
  { clave: 'venta', etiqueta: 'Factura de venta' },
  { clave: 'nc_venta', etiqueta: 'Nota crédito de venta' },
]
const IVAS = ['19', '5', '0']
const siigo = reactive<Record<string, string>>({})
// Los códigos de IVA del catálogo de Siigo (bienes/servicios, 19/5). Qué IVA
// factura un proveedor es lo único del IVA que el documento no dice; se elige
// al aprobar y la regla lo recuerda.
type Iva = { codigo: string; nombre: string; tarifa: string | null }
const ivas = ref<Iva[]>([])
// En una venta, lo que el cliente le retiene (D-131): una retefuente, un
// ReteIVA y un ReteICA del catálogo. Solo se manda si él lo tocó: si no, la
// regla conserva lo aprendido —incluida una tarifa propia del cliente—.
type RetVenta = { codigo: string; nombre: string; tipo: string; tarifa: string | null }
const retencionesVenta = ref<RetVenta[]>([])
const retPorTipo = (t: string) => retencionesVenta.value.filter((r) => r.tipo === t)
const retCliente = reactive({ retefuente: '', reteiva: '', reteica: '', tocado: false })
const catalogoCargado = ref(false)
const tiposUsados = computed(() => [...new Set(CLASES.map((c) => siigo[`tipo:${c.clave}`]).filter(Boolean))])

async function cargarSiigo() {
  const r = await rpc<{ config: Record<string, string>; ivas: Iva[]; retenciones_venta: RetVenta[]; catalogo_cargado: boolean }>(
    'siigo_config', { db_path: dbPath.value })
  retencionesVenta.value = r.retenciones_venta || []
  for (const k of Object.keys(siigo)) delete siigo[k]
  Object.assign(siigo, r.config)
  ivas.value = r.ivas || []
  catalogoCargado.value = !!r.catalogo_cargado
}

async function guardarSiigo() {
  siigoGuardando.value = true
  try {
    await rpc('siigo_config', { db_path: dbPath.value, valores: { ...siigo } })
    await cargarSiigo()
    siigoPanel.value = false
  } catch (e) {
    toast.error('No se pudo guardar', humanError(e))
  } finally {
    siigoGuardando.value = false
  }
}

async function onSiigoFolder(ruta: string) {
  siigoOpen.value = false
  siigoExportando.value = true
  try {
    const r = await rpc<{ path: string; comprobantes: number; lineas: number; cuadra: boolean; faltan: string[]
      no_salen: { numero: string | null; fecha: string | null; tercero_nit: string | null; diferencia: string; sin_cuenta: boolean }[] }>(
      'siigo_exportar', { db_path: dbPath.value, periodo: periodo.value, output_dir: ruta })
    await cargarSiigo()
    if (r.no_salen?.length) {
      toast.error(`${r.no_salen.length} aprobados no salieron en el archivo`,
        'No cuadran o les falta una cuenta: '
        + r.no_salen.map((x) => `${x.numero || x.fecha} (${x.tercero_nit})`).join(', ')
        + '. Deshaz su aprobación con la flecha, corrígelos y vuelve a armar el archivo.')
    }
    if (r.faltan.length) {
      toast.error(`${r.comprobantes} comprobantes, pero faltan datos`,
        'Celdas vacías en el archivo: ' + r.faltan.map(etiquetaFalta).join(', ') + '. Complétalos en «Siigo» o en Tarifas y vuelve a exportar.')
    } else {
      toast.success(`${r.comprobantes} comprobantes · ${r.lineas} líneas`,
        (r.cuadra ? 'El archivo cuadra. ' : 'OJO: el archivo NO cuadra. ') + r.path)
    }
  } catch (e) {
    toast.error('No se pudo armar el archivo de Siigo', humanError(e))
  } finally {
    siigoExportando.value = false
  }
}

// El catálogo de Siigo desde el Excel de la empresa: hoja «Impuestos» y hoja
// «Comprobantes». Se enseña qué cruzó y qué no ANTES de escribir nada.
type VistaCatalogo = {
  source_name: string
  conceptos_cruzados: { codigo: string; nombre: string; concepto: string }[]
  sin_cruce: { codigo: string; nombre: string; motivo: string }[]
  config: Record<string, string>
  avisos: string[]
}
const catalogoSubiendo = ref(false)
const catalogoAplicando = ref(false)
const catalogoVista = ref<VistaCatalogo | null>(null)
const catalogoRuta = ref('')

async function subirCatalogo(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  catalogoSubiendo.value = true
  try {
    const fd = new FormData()
    fd.append('db_path', dbPath.value)
    fd.append('file', file)
    const res = await $fetch<{ ok: boolean; error?: string; result?: VistaCatalogo; saved_to?: string }>(
      '/api/upload-siigo', { method: 'POST', body: fd })
    if (!res.ok || !res.result) throw new Error(res.error || 'error al subir')
    catalogoVista.value = res.result
    catalogoRuta.value = res.saved_to || ''
    siigoPanel.value = true
  } catch (e) {
    toast.error('No se pudo leer el catálogo', humanError(e))
  } finally {
    catalogoSubiendo.value = false
  }
}

async function aplicarCatalogo() {
  if (!catalogoRuta.value) return
  catalogoAplicando.value = true
  try {
    const r = await rpc<VistaCatalogo>('siigo_importar', {
      db_path: dbPath.value, source_path: catalogoRuta.value, dry_run: false })
    toast.success('Catálogo de Siigo cargado',
      `${r.conceptos_cruzados.length} conceptos con código · ${Object.keys(r.config).length} valores de configuración`)
    catalogoVista.value = null
    await cargarSiigo()
  } catch (e) {
    toast.error('No se pudo aplicar el catálogo', humanError(e))
  } finally {
    catalogoAplicando.value = false
  }
}

// Las reglas por tercero, sembradas desde la hoja de históricos del archivo de
// carga de Siigo (D-130). Lo que ya decidió en la bandeja no se toca.
type VistaSiembra = {
  source_name: string; nuevas: number; por_clase: Record<string, number>; con_retencion: number
  ya_existian: number; ambiguos: { tercero_nit: string; naturaleza: string; cuentas: string[] }[]
  comprobantes_ignorados: number
}
const siembraSubiendo = ref(false)
const siembraAplicando = ref(false)
const siembraVista = ref<VistaSiembra | null>(null)
const siembraRuta = ref('')

async function subirHistoricos(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  siembraSubiendo.value = true
  try {
    const fd = new FormData()
    fd.append('db_path', dbPath.value)
    fd.append('accion', 'historicos')
    fd.append('file', file)
    const res = await $fetch<{ ok: boolean; error?: string; result?: VistaSiembra; saved_to?: string }>(
      '/api/upload-siigo', { method: 'POST', body: fd })
    if (!res.ok || !res.result) throw new Error(res.error || 'error al subir')
    siembraVista.value = res.result
    siembraRuta.value = res.saved_to || ''
    siigoPanel.value = true
  } catch (e) {
    toast.error('No se pudieron leer los históricos', humanError(e))
  } finally {
    siembraSubiendo.value = false
  }
}

async function aplicarSiembra() {
  if (!siembraRuta.value) return
  siembraAplicando.value = true
  try {
    const r = await rpc<VistaSiembra>('siigo_sembrar', {
      db_path: dbPath.value, source_path: siembraRuta.value, dry_run: false })
    siembraVista.value = null
    toast.success(`${r.nuevas} reglas creadas desde Siigo`,
      'Pulse «Armar la propuesta del mes» para que las use.')
  } catch (e) {
    toast.error('No se pudieron crear las reglas', humanError(e))
  } finally {
    siembraAplicando.value = false
  }
}

const NATURALEZA_TXT: Record<string, string> = { compra: 'compras', venta: 'ventas', doc_soporte: 'documentos soporte' }

function etiquetaFalta(f: string): string {
  const [k, v] = f.split(':')
  if (k === 'tipo') return `tipo de comprobante de ${CLASES.find((c) => c.clave === v)?.etiqueta.toLowerCase() ?? v}`
  if (k === 'iva') return `código de IVA ${v}%`
  if (k === 'concepto') return 'código de Siigo de un concepto de retención (en Tarifas)'
  return f
}

function humanError(e: unknown): string {
  const anyE = e as { data?: { error?: string }; message?: string }
  return String(anyE?.data?.error ?? anyE?.message ?? e).replace(/^Error:\s*/, '')
}

const pendientes = computed(() => asientos.value.filter((a) => !a.aprobado && a.estado !== 'completo'))
const listos = computed(() => asientos.value.filter((a) => !a.aprobado && a.estado === 'completo'))
const aprobados = computed(() => asientos.value.filter((a) => a.aprobado))

const hayVentas = computed(() => asientos.value.some((a) => a.naturaleza === 'venta'))
const hayCompras = computed(() => asientos.value.some((a) => a.naturaleza !== 'venta'))
const faltanCuentas = computed(() =>
  (hayCompras.value && !cuentas.cuenta_proveedores) || (hayVentas.value && !cuentas.cuenta_clientes))

// En una venta la cuenta que él decide es la del ingreso (la segunda línea);
// en lo demás, la del gasto (la primera).
const lineaDecidida = (a: Asiento) => (a.naturaleza === 'venta' ? a.lineas[1] : a.lineas[0])

// Lo que se eligió arriba del editor, leído de las líneas: un aprobado no tiene
// editor, pero él quiere ver con qué quedó (el contador, 2026-10-29).
function loElegido(a: Asiento) {
  const principales = a.lineas.filter((l) => l.rol === (a.naturaleza === 'venta' ? 'ingreso' : 'gasto'))
  const cuentas = [...new Set(principales.map((l) => l.cuenta_puc).filter(Boolean))]
  const retenciones = a.lineas.filter((l) => l.rol === 'retencion').map((l) => l.descripcion)
  const codigos = [...new Set(a.lineas.filter((l) => l.rol === 'iva').map((l) => l.codigo_siigo).filter(Boolean))]
  return {
    cuenta: cuentas.join(' · ') || lineaDecidida(a)?.cuenta_puc || '—',
    retencion: retenciones.join(' · ') || 'Ninguna',
    iva: codigos.map((c) => {
      const nombre = ivas.value.find((i) => i.codigo === c)?.nombre
      return nombre ? `${c} · ${nombre}` : c
    }).join(', '),
  }
}

// ── El editor de líneas (observaciones del contador, 2026-10-28) ──────────────
// Lo que se ve en el panel abierto es un BORRADOR: él cambia cuentas, valores y
// el tercero de cada línea, agrega o quita líneas, y lo guarda sin aprobar o lo
// aprueba. Cambiar la retención o el IVA de arriba rehace las líneas de
// impuestos y la cartera; su reparto del gasto o del ingreso se respeta.
type Borrador = {
  cuenta_puc: string; descripcion: string; debito: string; credito: string
  tercero_nit: string; rol: string | null; codigo_siigo: string | null
  base: string | null; concepto_id: number | null
}
const borrador = ref<Borrador[]>([])
const previsualizando = ref(false)
// Tocó las líneas a mano: rehacer ya no puede reemplazarlas enteras.
const sucio = ref(false)
const ROLES_DE_REGLA = ['iva', 'retencion', 'cartera']

const aBorrador = (ls: Linea[]): Borrador[] => ls.map((l) => ({
  cuenta_puc: l.cuenta_puc || '', descripcion: l.descripcion || '',
  debito: Number(l.debito) ? String(l.debito) : '', credito: Number(l.credito) ? String(l.credito) : '',
  tercero_nit: l.tercero_nit || '', rol: l.rol, codigo_siigo: l.codigo_siigo,
  base: l.base ?? null, concepto_id: l.concepto_id ?? null,
}))

// En centavos, para que la suma no la descuadre el punto flotante.
const centavos = (v: string) => Math.round(Number(String(v || '0').replace(/,/g, '')) * 100) || 0
const sumaDebito = computed(() => borrador.value.reduce((t, l) => t + centavos(l.debito), 0))
const sumaCredito = computed(() => borrador.value.reduce((t, l) => t + centavos(l.credito), 0))
const diferencia = computed(() => sumaDebito.value - sumaCredito.value)
const sinCuenta = computed(() => borrador.value.filter((l) => (l.debito || l.credito) && !l.cuenta_puc.trim()).length)
const sePuedeAprobar = computed(() => diferencia.value === 0 && sinCuenta.value === 0 && borrador.value.length > 0)
const deCentavos = (c: number) => (c / 100).toLocaleString('es-CO', { maximumFractionDigits: 2 })

function agregarLinea() {
  sucio.value = true
  borrador.value.push({ cuenta_puc: '', descripcion: '', debito: '', credito: '', tercero_nit: '',
    rol: null, codigo_siigo: null, base: null, concepto_id: null })
}
function quitarLinea(i: number) { borrador.value.splice(i, 1); sucio.value = true }
// La diferencia a esta línea, al lado que le falte: lo normal al repartir.
function cuadrarCon(i: number) {
  const l = borrador.value[i]
  if (!l) return
  const d = diferencia.value
  if (centavos(l.debito) || (!centavos(l.credito) && d < 0)) l.debito = String((centavos(l.debito) - d) / 100)
  else l.credito = String((centavos(l.credito) + d) / 100)
}

function correccionParams(a: Asiento) {
  return {
    cuenta_puc: correccion.cuenta_puc,
    patron: correccion.patron,
    concepto_retencion_id: correccion.retencion && correccion.retencion !== 'ninguna' ? correccion.retencion : '',
    sin_retencion: correccion.retencion === 'ninguna',
    aprender_regla: correccion.aprender_regla,
    iva_codigo: correccion.iva_codigo,
    retenciones_cliente: a.naturaleza === 'venta' && retCliente.tocado
      ? ([retCliente.retefuente, retCliente.reteiva, retCliente.reteica].filter(Boolean).join(',') || 'ninguna')
      : '',
  }
}

async function rehacerBorrador(a: Asiento) {
  previsualizando.value = true
  try {
    const r = await rpc<{ lineas: Linea[] }>('asiento_previsualizar', {
      db_path: dbPath.value, id: a.id, ...correccionParams(a), ...cuentas })
    const nuevas = aBorrador(r.lineas)
    if (!sucio.value) { borrador.value = nuevas; return }
    // Lo suyo (gasto, ingreso, parte sin IVA, líneas agregadas) se queda; los
    // impuestos y la cartera vienen recalculados, con el tercero que él puso.
    const suyas = borrador.value.filter((l) => !ROLES_DE_REGLA.includes(l.rol || ''))
    const principal = suyas.find((l) => l.rol === 'gasto' || l.rol === 'ingreso')
    if (principal && correccion.cuenta_puc.trim()) principal.cuenta_puc = correccion.cuenta_puc.trim()
    const terceroCartera = borrador.value.find((l) => l.rol === 'cartera')?.tercero_nit || ''
    for (const l of nuevas) if (l.rol === 'cartera' && terceroCartera) l.tercero_nit = terceroCartera
    borrador.value = [...suyas, ...nuevas.filter((l) => ROLES_DE_REGLA.includes(l.rol || ''))]
  } catch (e) {
    toast.error('No se pudo rehacer el asiento', humanError(e))
  } finally {
    previsualizando.value = false
  }
}

async function guardarAsiento(a: Asiento) {
  guardando.value = true
  try {
    const r = await rpc<Asiento>('asiento_guardar', {
      db_path: dbPath.value, id: a.id, lineas: borrador.value, ...correccionParams(a), ...cuentas })
    await cargar()
    abierto.value = r.id
    borrador.value = aBorrador(r.lineas)
    toast.success('Guardado', r.estado === 'completo'
      ? 'Queda listo para aprobar.' : 'Queda por decidir: ' + (r.avisos[0] || ''))
  } catch (e) {
    toast.error('No se pudo guardar', humanError(e))
  } finally {
    guardando.value = false
  }
}

async function descartar(a: Asiento) {
  guardando.value = true
  try {
    const r = await rpc<Asiento>('asiento_descartar', { db_path: dbPath.value, id: a.id })
    await cargar()
    const nuevo = asientos.value.find((x) => x.id === r.id)
    if (nuevo) { abierto.value = null; abrir(nuevo) }
  } catch (e) {
    toast.error('No se pudo descartar', humanError(e))
  } finally {
    guardando.value = false
  }
}

// Los marcados para aprobar en bloque. Solo entra lo que está listo; lo que
// falta decidir el servidor lo salta y lo dice.
const marcados = ref<Set<number>>(new Set())
function marcar(id: number, si: boolean) {
  const s = new Set(marcados.value)
  if (si) s.add(id); else s.delete(id)
  marcados.value = s
}
function marcarGrupo(filas: Asiento[], si: boolean) {
  const s = new Set(marcados.value)
  for (const a of filas) { if (si) s.add(a.id); else s.delete(a.id) }
  marcados.value = s
}
const marcadosListos = computed(() => listos.value.filter((a) => marcados.value.has(a.id)).length)

async function aprobarMarcados() {
  guardando.value = true
  try {
    const r = await rpc<{ aprobados: number; omitidos: number }>('asiento_aprobar_lote', {
      db_path: dbPath.value, periodo: periodo.value, ids: [...marcados.value] })
    marcados.value = new Set()
    await cargar()
    toast.success(`${r.aprobados} aprobados`,
      r.omitidos ? `${r.omitidos} marcados no estaban listos y siguen esperando.` : 'Todos los marcados.')
  } catch (e) {
    toast.error('No se pudo aprobar en bloque', humanError(e))
  } finally {
    guardando.value = false
  }
}

async function cargar() {
  if (!dbPath.value || !periodo.value) return
  cargando.value = true
  try {
    const r = await rpc<{ asientos: Asiento[]; resumen: Resumen }>('asiento_list', {
      db_path: dbPath.value, periodo: periodo.value,
    })
    asientos.value = r.asientos
    resumen.value = r.resumen
    const t = await rpc<{ conceptos: Concepto[] }>('tarifas_list', { db_path: dbPath.value })
    conceptos.value = t.conceptos.filter((c) => c.sobre !== 'iva')
    const c = await rpc<typeof cuentas>('cuentas_empresa', { db_path: dbPath.value })
    for (const k of Object.keys(cuentas) as (keyof typeof cuentas)[]) cuentas[k] = c[k] || ''
    const info = await rpc<{ razon_social: string }>('open_empresa', { db_path: dbPath.value })
    razonSocial.value = info.razon_social
    await cargarSiigo()
  } catch (e) {
    toast.error('No se pudo cargar la causación', humanError(e))
  } finally {
    cargando.value = false
  }
}

async function generar() {
  generando.value = true
  try {
    const r = await trabajo.correr<{ total: number; completos: number; revisar: number; sin_xml: number }>(
      'asiento_generar', { db_path: dbPath.value, periodo: periodo.value })
    await cargar()
    toast.success(`${r.total} documentos`,
      `${r.completos} listos para aprobar · ${r.revisar} por decidir`
      + (r.sin_xml ? ` · ${r.sin_xml} sin XML` : ''))
  } catch (e) {
    toast.error('No se pudo armar la propuesta', humanError(e))
  } finally {
    generando.value = false
  }
}

function guardadaDe(a: Asiento): Guardada {
  try { return a.correccion ? JSON.parse(a.correccion) as Guardada : {} } catch { return {} }
}

function abrir(a: Asiento) {
  if (abierto.value === a.id) { abierto.value = null; return }
  abierto.value = a.id
  // Lo que guardó vuelve como lo dejó (Carlos, 0.18.0: se perdían la retención
  // y el «recordarlo cuando diga»). Sin nada guardado, lo que dicen las líneas.
  const g = guardadaDe(a)
  const conceptoDeLinea = a.lineas.find((l) => l.rol === 'retencion' && l.concepto_id)?.concepto_id
  correccion.cuenta_puc = g.cuenta_puc || lineaDecidida(a)?.cuenta_puc || ''
  correccion.patron = g.patron || ''
  borrador.value = aBorrador(a.lineas)
  sucio.value = !!a.editado
  correccion.retencion = g.sin_retencion ? 'ninguna'
    : g.concepto_retencion_id ? String(g.concepto_retencion_id)
      : conceptoDeLinea ? String(conceptoDeLinea) : ''
  correccion.aprender_regla = g.aprender_regla ?? true
  correccion.iva_codigo = g.iva_codigo || a.lineas.find((l) => l.rol === 'iva')?.codigo_siigo || ''
  const codigos = g.retenciones_cliente
    ? g.retenciones_cliente.split(',').map((c) => c.trim())
    : a.lineas.filter((l) => l.rol === 'retencion').map((l) => l.codigo_siigo || '')
  for (const t of ['retefuente', 'reteiva', 'reteica'] as const)
    retCliente[t] = retPorTipo(t).find((r) => codigos.includes(r.codigo))?.codigo || ''
  retCliente.tocado = !!g.retenciones_cliente
}

// Cuánto no cuadra lo guardado, para señalarlo en la lista sin abrir la fila.
function descuadreDe(a: Asiento): number {
  return a.lineas.reduce((t, l) => t + centavos(l.debito) - centavos(l.credito), 0)
}

async function aprobar(a: Asiento) {
  guardando.value = true
  try {
    // Se aprueba lo que está en el editor, tal cual lo dejó.
    await rpc('asiento_aprobar', {
      db_path: dbPath.value, id: a.id, ...correccionParams(a), ...cuentas, lineas: borrador.value,
    })
    abierto.value = null
    await cargar()
  } catch (e) {
    toast.error('No se pudo aprobar', humanError(e))
  } finally {
    guardando.value = false
  }
}

async function aprobarTodos() {
  guardando.value = true
  try {
    const r = await rpc<{ aprobados: number }>('asiento_aprobar_lote', {
      db_path: dbPath.value, periodo: periodo.value })
    await cargar()
    toast.success(`${r.aprobados} aprobados`, 'Los que había que mirar siguen esperando.')
  } catch (e) {
    toast.error('No se pudo aprobar en lote', humanError(e))
  } finally {
    guardando.value = false
  }
}

async function onExportFolder(ruta: string) {
  exportOpen.value = false
  exportando.value = true
  try {
    const r = await rpc<{ path: string; asientos: number; lineas: number; cuadra: boolean }>(
      'asiento_exportar', { db_path: dbPath.value, periodo: periodo.value, output_dir: ruta })
    toast.success(`${r.asientos} asientos exportados`,
      (r.cuadra ? 'El archivo cuadra. ' : 'OJO: el archivo NO cuadra. ') + r.path)
  } catch (e) {
    toast.error('No se pudo exportar', humanError(e))
  } finally {
    exportando.value = false
  }
}

async function deshacer(a: Asiento) {
  await rpc('asiento_desaprobar', { db_path: dbPath.value, id: a.id })
  await cargar()
}

const pesos = (v: string) => Number(v || 0).toLocaleString('es-CO')
onMounted(cargar)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-3 p-4">
    <DirectoryPicker v-if="exportOpen" :open="exportOpen" :initial-path="''"
      title="Carpeta donde guardar el Excel de asientos"
      @pick="onExportFolder" @close="exportOpen = false" />
    <DirectoryPicker v-if="siigoOpen" :open="siigoOpen" :initial-path="''"
      title="Carpeta donde guardar el archivo para Siigo"
      @pick="onSiigoFolder" @close="siigoOpen = false" />
    <header class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
      <NuxtLink :to="{ path: '/empresa', query: { db: dbPath } }"
        class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft class="size-3.5" /> {{ razonSocial || 'Empresa' }}
      </NuxtLink>
      <span class="text-border">/</span>
      <h1 class="font-heading text-xl font-medium tracking-tight">Causación de {{ periodo }}</h1>
      <p class="text-sm text-muted-foreground">
        <strong class="text-foreground">{{ resumen.total }}</strong> documentos ·
        <span class="text-status-success">{{ listos.length }} listos</span> ·
        <span class="text-status-warning">{{ pendientes.length }} por decidir</span> ·
        {{ aprobados.length }} aprobados
      </p>
    </header>

    <section class="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-2">
      <Button size="sm" variant="outline" :disabled="generando" @click="generar">
        <RefreshCw class="size-3.5" :class="generando ? 'animate-spin' : ''" />
        {{ generando ? 'Armando…' : 'Armar la propuesta del mes' }}
      </Button>
      <Button size="sm" :disabled="guardando || !listos.length" @click="aprobarTodos">
        <Check class="size-3.5" /> Aprobar los {{ listos.length }} listos
      </Button>
      <Button size="sm" variant="outline" :disabled="guardando || !marcados.size" @click="aprobarMarcados"
        title="Aprueba solo los que marcó; los que falta decidir se saltan">
        <Check class="size-3.5" /> Aprobar {{ marcados.size }} marcados
      </Button>
      <Button size="sm" variant="outline" :disabled="exportando || !aprobados.length"
        title="Los asientos aprobados a un Excel, una fila por línea, para llevarlos a Siigo"
        @click="exportOpen = true">
        <Download class="size-3.5" /> Exportar {{ aprobados.length }} aprobados
      </Button>
      <Button size="sm" variant="outline" :disabled="siigoExportando || !aprobados.length"
        title="Los asientos aprobados en el formato de importación de comprobantes de Siigo"
        @click="siigoOpen = true">
        <FileSpreadsheet class="size-3.5" /> Archivo de Siigo
      </Button>
      <Button size="sm" variant="ghost" title="La nómina del mes, desde su Excel de liquidación"
        @click="navigateTo({ path: '/nomina', query: { db: dbPath, periodo } })">
        Nómina
      </Button>
      <Button size="sm" variant="ghost" title="Ver y corregir las reglas de esta empresa"
        @click="navigateTo({ path: '/reglas', query: { db: dbPath } })">
        Reglas
      </Button>
      <Button size="sm" variant="ghost" :title="siigoPanel ? 'Cerrar' : 'Tipos de comprobante y consecutivos de Siigo'"
        @click="siigoPanel = !siigoPanel">
        <Settings2 class="size-3.5" /> Siigo
      </Button>
      <span v-if="trabajo.corriendo.value" class="text-xs text-muted-foreground">{{ trabajo.etiqueta.value }}</span>
      <span class="flex-1" />
      <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
        Proveedores
        <Input v-model="cuentas.cuenta_proveedores" class="h-8 w-24 font-mono" placeholder="220505" />
      </label>
      <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
        IVA descontable
        <Input v-model="cuentas.cuenta_iva_descontable" class="h-8 w-24 font-mono" placeholder="240810" />
      </label>
      <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
        Clientes
        <Input v-model="cuentas.cuenta_clientes" class="h-8 w-24 font-mono" placeholder="130505" />
      </label>
      <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
        IVA generado
        <Input v-model="cuentas.cuenta_iva_generado" class="h-8 w-24 font-mono" placeholder="240805" />
      </label>
    </section>

    <!-- panel de Siigo: nunca un modal -->
    <section v-if="siigoPanel" class="shrink-0 rounded-lg border border-primary/40 bg-card p-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-sm font-semibold">Lo que Siigo exige y Contab no puede adivinar</h2>
        <div class="flex flex-wrap gap-2">
          <Button as="label" size="sm" variant="outline" :disabled="catalogoSubiendo">
            <UploadCloud class="size-3.5" /> {{ catalogoSubiendo ? 'Leyendo…' : 'Subir el catálogo (Excel)' }}
            <input type="file" accept=".xlsx,.xlsm,.ods" class="hidden" @change="subirCatalogo">
          </Button>
          <Button as="label" size="sm" variant="outline" :disabled="siembraSubiendo || !catalogoCargado"
            :title="catalogoCargado ? 'El archivo de carga de Siigo con su hoja de históricos' : 'Primero el catálogo'">
            <UploadCloud class="size-3.5" /> {{ siembraSubiendo ? 'Leyendo…' : 'Reglas desde los históricos' }}
            <input type="file" accept=".xlsx,.xlsm,.ods" class="hidden" @change="subirHistoricos">
          </Button>
        </div>
      </div>
      <p class="mb-3 text-xs text-muted-foreground">
        Son del catálogo de <strong>esta empresa</strong> en Siigo. El tipo de comprobante es el número con que
        la empresa registra cada clase de documento; el último consecutivo es el del último comprobante de ese
        tipo que ya está en Siigo — Contab sigue desde ahí y lo va anotando. Puede escribirlos aquí o subir el
        Excel con las hojas «Impuestos» y «Comprobantes»: Contab le enseña qué leyó antes de guardar.
      </p>

      <!-- vista previa de la siembra, antes de crear ninguna regla -->
      <div v-if="siembraVista" class="mb-3 rounded-md border border-border bg-muted/30 p-3">
        <h3 class="text-xs font-semibold">{{ siembraVista.source_name }}</h3>
        <p class="mt-1 text-xs text-muted-foreground">
          Se crearían <strong class="text-foreground">{{ siembraVista.nuevas }}</strong> reglas
          (<template v-for="(n, k, i) in siembraVista.por_clase" :key="k">{{ i ? ', ' : '' }}{{ n }} de {{ NATURALEZA_TXT[k] || k }}</template>),
          <strong class="text-foreground">{{ siembraVista.con_retencion }}</strong> con su concepto de retención.
          <template v-if="siembraVista.ya_existian">{{ siembraVista.ya_existian }} terceros ya tenían regla y no se tocan.</template>
        </p>
        <p v-if="siembraVista.ambiguos.length" class="mt-2 text-xs text-status-warning">
          {{ siembraVista.ambiguos.length }} terceros fueron a cuentas distintas sin una que domine; se deciden en la bandeja:
          <span class="font-mono">{{ siembraVista.ambiguos.slice(0, 6).map((a) => a.tercero_nit).join(', ') }}</span><template v-if="siembraVista.ambiguos.length > 6">…</template>
        </p>
        <div class="mt-3 flex gap-2">
          <Button size="sm" :disabled="siembraAplicando || !siembraVista.nuevas" @click="aplicarSiembra">
            {{ siembraAplicando ? 'Creando…' : `Crear ${siembraVista.nuevas} reglas` }}
          </Button>
          <Button size="sm" variant="ghost" :disabled="siembraAplicando" @click="siembraVista = null">Cancelar</Button>
        </div>
      </div>

      <!-- vista previa del catálogo, antes de escribir nada -->
      <div v-if="catalogoVista" class="mb-3 rounded-md border border-border bg-muted/30 p-3">
        <h3 class="text-xs font-semibold">{{ catalogoVista.source_name }}</h3>
        <p class="mt-1 text-xs text-muted-foreground">
          <strong class="text-foreground">{{ catalogoVista.conceptos_cruzados.length }}</strong> conceptos de retención reciben su código ·
          <strong class="text-foreground">{{ Object.keys(catalogoVista.config).length }}</strong> valores (tipos, consecutivos, IVA).
        </p>
        <ul v-if="catalogoVista.conceptos_cruzados.length" class="mt-2 space-y-0.5 text-xs">
          <li v-for="c in catalogoVista.conceptos_cruzados" :key="c.codigo">
            <span class="font-mono">{{ c.codigo }}</span> {{ c.nombre }} → <strong>{{ c.concepto }}</strong>
          </li>
        </ul>
        <!-- Un catálogo de Siigo trae decenas de códigos y la empresa usa unos
             pocos: los que no cruzan no son un error, y en ámbar parecían uno. -->
        <details v-if="catalogoVista.sin_cruce.length" class="mt-2 text-xs">
          <summary class="cursor-pointer text-muted-foreground">
            {{ catalogoVista.sin_cruce.length }} códigos del catálogo no tienen concepto en Tarifas — es normal si
            esta empresa no los usa. Ver cuáles
          </summary>
          <ul class="mt-1 space-y-0.5 text-muted-foreground">
            <li v-for="c in catalogoVista.sin_cruce" :key="c.codigo">
              · <span class="font-mono">{{ c.codigo }}</span> {{ c.nombre }}: {{ c.motivo }}
            </li>
          </ul>
        </details>
        <ul v-if="catalogoVista.avisos.length" class="mt-2 space-y-0.5 text-xs text-status-warning">
          <li v-for="(a, i) in catalogoVista.avisos" :key="i">· {{ a }}</li>
        </ul>
        <div class="mt-3 flex gap-2">
          <Button size="sm" :disabled="catalogoAplicando" @click="aplicarCatalogo">
            {{ catalogoAplicando ? 'Guardando…' : 'Aplicar' }}
          </Button>
          <Button size="sm" variant="ghost" :disabled="catalogoAplicando" @click="catalogoVista = null">Cancelar</Button>
        </div>
      </div>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div v-for="c in CLASES" :key="c.clave" class="grid gap-1">
          <Label class="text-xs">{{ c.etiqueta }} · tipo</Label>
          <Input v-model="siigo[`tipo:${c.clave}`]" class="h-8 w-24 font-mono" placeholder="11" />
        </div>
      </div>
      <div v-if="tiposUsados.length" class="mt-3 grid gap-3 sm:grid-cols-3">
        <div v-for="t in tiposUsados" :key="t" class="grid gap-1">
          <Label class="text-xs">Último consecutivo del tipo {{ t }}</Label>
          <Input v-model="siigo[`ultimo:${t}`]" class="h-8 w-28 font-mono" placeholder="0" />
        </div>
      </div>
      <p v-if="catalogoCargado" class="mt-3 text-xs text-status-success">
        Catálogo de impuestos cargado: la cuenta del IVA y de cada retención sale de él según el comprobante
        (venta, compra o devolución). Las cuentas de arriba quedan de respaldo.
      </p>
      <div class="mt-3 grid gap-3 sm:grid-cols-4">
        <div v-for="t in IVAS" :key="t" class="grid gap-1">
          <Label class="text-xs">Código de IVA {{ t }}%</Label>
          <Input v-model="siigo[`iva:${t}`]" class="h-8 w-20 font-mono" placeholder="02" />
        </div>
        <div class="grid gap-1">
          <Label class="text-xs">Vencimiento (días)</Label>
          <Input v-model="siigo['vencimiento_dias']" class="h-8 w-20 font-mono" placeholder="30" />
        </div>
      </div>
      <p class="mt-2 text-xs text-muted-foreground">
        El código de Siigo de cada <strong>concepto de retención</strong> se pone en Tarifas y UVT, junto a su cuenta.
      </p>
      <div class="mt-3 flex gap-2">
        <Button size="sm" :disabled="siigoGuardando" @click="guardarSiigo">Guardar</Button>
        <Button size="sm" variant="ghost" :disabled="siigoGuardando" @click="siigoPanel = false">Cancelar</Button>
      </div>
    </section>

    <p v-if="faltanCuentas" class="shrink-0 rounded-md border border-status-warning/40 bg-status-warning-bg px-3 py-2 text-sm">
      Falta decir a qué cuenta va
      <template v-if="hayCompras && !cuentas.cuenta_proveedores"><strong>el pasivo con el proveedor</strong></template>
      <template v-if="hayCompras && !cuentas.cuenta_proveedores && hayVentas && !cuentas.cuenta_clientes"> y </template>
      <template v-if="hayVentas && !cuentas.cuenta_clientes"><strong>la cuenta por cobrar a clientes</strong></template>
      en esta empresa. Escríbela arriba: se guarda al aprobar el primer asiento, y solo para esta empresa.
    </p>

    <section class="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-card">
      <p v-if="!cargando && !asientos.length" class="px-3 py-10 text-center text-sm text-muted-foreground">
        Todavía no hay propuesta para {{ periodo }}. Pulsa «Armar la propuesta del mes».
      </p>

      <template v-for="grupo in [
        { titulo: 'Por decidir', filas: pendientes, clase: 'text-status-warning' },
        { titulo: 'Listos para aprobar', filas: listos, clase: 'text-status-success' },
        { titulo: 'Aprobados', filas: aprobados, clase: 'text-muted-foreground' },
      ]" :key="grupo.titulo">
        <div v-if="grupo.filas.length">
          <h2 class="sticky top-0 z-10 flex items-center gap-2 border-b border-border bg-card px-3 py-1.5 text-xs font-semibold uppercase"
            :class="grupo.clase">
            <input v-if="grupo.titulo !== 'Aprobados'" type="checkbox" class="size-3.5"
              :title="`Marcar los ${grupo.filas.length}`"
              :checked="grupo.filas.every((a) => marcados.has(a.id))"
              @change="marcarGrupo(grupo.filas, ($event.target as HTMLInputElement).checked)">
            {{ grupo.titulo }} · {{ grupo.filas.length }}
          </h2>
          <template v-for="a in grupo.filas" :key="a.id">
            <div class="flex cursor-pointer items-center gap-2 border-b border-border/60 px-3 py-2 text-sm hover:bg-accent/40"
              @click="abrir(a)">
              <input v-if="!a.aprobado" type="checkbox" class="size-3.5 shrink-0" title="Marcar para aprobar en bloque"
                :checked="marcados.has(a.id)" @click.stop
                @change="marcar(a.id, ($event.target as HTMLInputElement).checked)">
              <ChevronRight class="size-3.5 shrink-0 text-muted-foreground transition-transform"
                :class="abierto === a.id ? 'rotate-90' : ''" />
              <span class="w-20 shrink-0 font-mono text-xs text-muted-foreground">{{ a.fecha }}</span>
              <span class="w-24 shrink-0 font-mono text-xs">{{ a.tercero_nit }}</span>
              <span v-if="a.naturaleza !== 'compra'"
                class="shrink-0 rounded border border-border px-1.5 py-px text-[10px] uppercase text-muted-foreground">
                {{ ETIQUETA[a.naturaleza] }}
              </span>
              <span v-if="a.editado && !a.aprobado" title="Guardado a mano: armar la propuesta no lo cambia"
                class="shrink-0 rounded border border-primary/40 px-1.5 py-px text-[10px] uppercase text-primary">
                Guardado
              </span>
              <span v-if="!a.aprobado && descuadreDe(a)" title="El débito y el crédito no son iguales: no se puede aprobar"
                class="shrink-0 rounded border border-status-error bg-status-error-bg px-1.5 py-px text-[10px] font-semibold uppercase text-status-error">
                No cuadra
              </span>
              <span class="min-w-0 flex-1 truncate">{{ lineaDecidida(a)?.descripcion }}</span>
              <span class="shrink-0 font-mono text-xs">{{ pesos(String(a.lineas.reduce((t, l) => t + Number(l.debito || 0), 0))) }}</span>
              <Button v-if="a.aprobado" variant="ghost" size="icon-sm" title="Deshacer la aprobación"
                @click.stop="deshacer(a)"><Undo2 class="size-3.5" /></Button>
            </div>

            <div v-if="abierto === a.id" class="border-b border-border bg-muted/30 px-3 py-3">
              <ul v-if="a.avisos.length" class="mb-3 space-y-1">
                <li v-for="(x, i) in a.avisos" :key="i" class="text-xs"
                  :class="/no cuadra/i.test(x) ? 'font-semibold text-status-error' : 'text-status-warning'">· {{ x }}</li>
              </ul>

              <!-- aprobado: solo se mira -->
              <div v-if="a.aprobado" class="mb-3 flex flex-wrap items-end gap-x-6 gap-y-2 text-xs">
                <div class="grid gap-0.5">
                  <span class="text-muted-foreground">{{ a.naturaleza === 'venta' ? 'Cuenta del ingreso' : 'Cuenta del gasto' }}</span>
                  <span class="font-mono">{{ loElegido(a).cuenta }}</span>
                </div>
                <div v-if="a.naturaleza !== 'venta'" class="grid gap-0.5">
                  <span class="text-muted-foreground">Retención en la fuente</span>
                  <span>{{ loElegido(a).retencion }}</span>
                </div>
                <div v-if="loElegido(a).iva" class="grid gap-0.5">
                  <span class="text-muted-foreground">IVA (código de Siigo)</span>
                  <span>{{ loElegido(a).iva }}</span>
                </div>
                <span class="text-muted-foreground">Aprobado: para cambiarlo, deshaz la aprobación (↶).</span>
              </div>
              <table v-if="a.aprobado" class="w-full text-xs">
                <thead>
                  <tr class="text-left text-[10px] uppercase text-muted-foreground">
                    <th class="py-1 font-normal">Cuenta</th>
                    <th class="py-1 font-normal">Concepto</th>
                    <th class="py-1 font-normal">Tercero</th>
                    <th class="py-1 text-right font-normal">Débito</th>
                    <th class="py-1 text-right font-normal">Crédito</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="ln in a.lineas" :key="ln.id" class="border-t border-border/50">
                    <td class="py-1 pr-2 font-mono">{{ ln.cuenta_puc }}</td>
                    <td class="py-1 pr-2">{{ ln.descripcion }}</td>
                    <td class="py-1 pr-2 font-mono" :class="ln.tercero_nit ? 'text-primary' : 'text-muted-foreground'">
                      {{ ln.tercero_nit || a.tercero_nit }}
                    </td>
                    <td class="py-1 text-right font-mono">{{ Number(ln.debito) ? pesos(ln.debito) : '' }}</td>
                    <td class="py-1 text-right font-mono">{{ Number(ln.credito) ? pesos(ln.credito) : '' }}</td>
                  </tr>
                </tbody>
              </table>

              <template v-else>
                <!-- lo que rehace el asiento desde las reglas -->
                <div class="mb-3 flex flex-wrap items-end gap-3">
                  <div class="grid gap-1">
                    <Label class="text-xs">{{ a.naturaleza === 'venta' ? 'Cuenta del ingreso' : 'Cuenta del gasto' }}</Label>
                    <Input v-model="correccion.cuenta_puc" class="h-8 w-32 font-mono"
                      :placeholder="a.naturaleza === 'venta' ? '413505' : '519530'" @change="rehacerBorrador(a)" />
                  </div>
                  <div v-if="a.naturaleza !== 'venta'" class="grid gap-1">
                    <Label class="text-xs">Retención en la fuente</Label>
                    <select v-model="correccion.retencion" class="h-8 rounded-md border border-border bg-background px-2 text-xs"
                      @change="rehacerBorrador(a)">
                      <option value="">— elegir —</option>
                      <option value="ninguna">Ninguna: a este proveedor no se le retiene</option>
                      <option v-for="c in conceptos" :key="c.id" :value="String(c.id)">
                        {{ c.concepto }}<template v-if="c.aplica_a && c.aplica_a !== 'ambos'"> · {{ c.aplica_a === 'declarantes' ? 'declarantes' : 'no declarantes' }}</template>
                      </option>
                    </select>
                  </div>
                  <template v-if="a.naturaleza === 'venta' && retencionesVenta.length">
                    <div v-for="t in (['retefuente', 'reteiva', 'reteica'] as const)" :key="t" class="grid gap-1">
                      <Label class="text-xs">{{ { retefuente: 'Le retiene en la fuente', reteiva: 'Le retiene IVA', reteica: 'Le retiene ICA' }[t] }}</Label>
                      <select v-model="retCliente[t]" class="h-8 rounded-md border border-border bg-background px-2 text-xs"
                        @change="retCliente.tocado = true; rehacerBorrador(a)">
                        <option value="">Nada</option>
                        <option v-for="r in retPorTipo(t)" :key="r.codigo" :value="r.codigo">{{ r.codigo }} · {{ r.nombre }}</option>
                      </select>
                    </div>
                  </template>
                  <div v-if="ivas.length && a.lineas.some((l) => l.rol === 'iva')" class="grid gap-1">
                    <Label class="text-xs">IVA (código de Siigo)</Label>
                    <select v-model="correccion.iva_codigo" class="h-8 rounded-md border border-border bg-background px-2 text-xs"
                      @change="rehacerBorrador(a)">
                      <option value="">— el de la tarifa —</option>
                      <option v-for="i in ivas" :key="i.codigo" :value="i.codigo">{{ i.codigo }} · {{ i.nombre }}</option>
                    </select>
                  </div>
                  <span class="pb-2 text-xs text-muted-foreground">
                    {{ previsualizando ? 'Rehaciendo…' : (sucio ? 'Cambiar esto rehace impuestos y cartera; su reparto se queda.' : 'Cambiar esto rehace las líneas de abajo.') }}
                  </span>
                </div>

                <!-- el editor: cada línea se cambia, se agrega o se quita -->
                <div class="overflow-x-auto">
                  <table class="w-full min-w-[720px] text-xs">
                    <thead>
                      <tr class="text-left text-[10px] uppercase text-muted-foreground">
                        <th class="py-1 font-normal">Cuenta</th>
                        <th class="py-1 font-normal">Concepto</th>
                        <th class="py-1 font-normal" title="Vacío = el tercero del documento">Tercero</th>
                        <th class="py-1 text-right font-normal">Débito</th>
                        <th class="py-1 text-right font-normal">Crédito</th>
                        <th class="w-14" />
                      </tr>
                    </thead>
                    <tbody @input="sucio = true">
                      <tr v-for="(ln, i) in borrador" :key="i" class="border-t border-border/50">
                        <td class="py-1 pr-1">
                          <Input v-model="ln.cuenta_puc" class="h-7 w-28 font-mono text-xs"
                            :class="(ln.debito || ln.credito) && !ln.cuenta_puc.trim() ? 'border-status-error' : ''"
                            placeholder="falta" />
                        </td>
                        <td class="py-1 pr-1"><Input v-model="ln.descripcion" class="h-7 min-w-40 text-xs" /></td>
                        <td class="py-1 pr-1">
                          <Input v-model="ln.tercero_nit" class="h-7 w-28 font-mono text-xs"
                            :class="ln.tercero_nit ? 'text-primary' : ''" :placeholder="a.tercero_nit || ''" />
                        </td>
                        <td class="py-1 pr-1"><Input v-model="ln.debito" class="h-7 w-32 text-right font-mono text-xs" inputmode="decimal" /></td>
                        <td class="py-1 pr-1"><Input v-model="ln.credito" class="h-7 w-32 text-right font-mono text-xs" inputmode="decimal" /></td>
                        <td class="py-1 text-right whitespace-nowrap">
                          <Button v-if="diferencia" variant="ghost" size="icon-sm" title="Llevar la diferencia a esta línea"
                            @click="cuadrarCon(i)">=</Button>
                          <Button variant="ghost" size="icon-sm" title="Quitar la línea" @click="quitarLinea(i)"><X class="size-3.5" /></Button>
                        </td>
                      </tr>
                    </tbody>
                    <tfoot>
                      <tr class="border-t border-border">
                        <td colspan="3" class="py-1.5">
                          <Button variant="ghost" size="sm" class="h-7" @click="agregarLinea"><Plus class="size-3.5" /> Agregar línea</Button>
                        </td>
                        <td class="py-1.5 pr-1 text-right font-mono" :class="diferencia ? 'font-semibold text-status-error' : ''">{{ deCentavos(sumaDebito) }}</td>
                        <td class="py-1.5 pr-1 text-right font-mono" :class="diferencia ? 'font-semibold text-status-error' : ''">{{ deCentavos(sumaCredito) }}</td>
                        <td />
                      </tr>
                    </tfoot>
                  </table>
                </div>
                <!-- Un descuadre no puede pasar desapercibido (Carlos, 0.18.0). -->
                <div v-if="diferencia" role="alert"
                  class="mt-2 flex items-center gap-2 rounded-md border border-status-error bg-status-error-bg px-3 py-2 text-sm font-semibold text-status-error">
                  <TriangleAlert class="size-4 shrink-0" />
                  No cuadra: sobran {{ deCentavos(Math.abs(diferencia)) }} pesos en el {{ diferencia > 0 ? 'débito' : 'crédito' }}.
                  <span class="font-normal">Usa «=» en la línea que deba llevar la diferencia.</span>
                </div>
                <p v-if="sinCuenta || sePuedeAprobar" class="mt-1 text-xs" :class="sePuedeAprobar ? 'text-status-success' : 'text-status-warning'">
                  <template v-if="sinCuenta">{{ sinCuenta }} línea{{ sinCuenta > 1 ? 's' : '' }} sin cuenta.</template>
                  <template v-if="sePuedeAprobar">Cuadra.</template>
                </p>

                <div class="mt-3 flex flex-wrap items-end gap-3">
                  <div class="grid gap-1">
                    <Label class="text-xs">Recordarlo cuando la factura diga…</Label>
                    <Input v-model="correccion.patron" class="h-8 w-56" placeholder="monitoreo de alarma" />
                  </div>
                  <label class="flex items-center gap-1.5 pb-1.5 text-xs text-muted-foreground">
                    <input v-model="correccion.aprender_regla" type="checkbox"> Recordar para las próximas
                  </label>
                  <span class="flex-1" />
                  <Button v-if="a.editado" size="sm" variant="ghost" :disabled="guardando"
                    title="Olvida lo guardado y vuelve a lo que dicen las reglas" @click="descartar(a)">
                    Descartar cambios
                  </Button>
                  <Button size="sm" variant="outline" :disabled="guardando" @click="guardarAsiento(a)"
                    title="Guarda las líneas sin aprobar; armar la propuesta del mes no las cambia">
                    <Save class="size-3.5" /> Guardar
                  </Button>
                  <Button size="sm" :disabled="guardando || !sePuedeAprobar" @click="aprobar(a)">
                    <Check class="size-3.5" /> Aprobar
                  </Button>
                </div>
              </template>
              <p v-if="!a.aprobado && a.naturaleza !== 'venta' && !correccion.retencion" class="mt-2 text-xs text-status-warning">
                Elige la retención —o «ninguna»—: sin eso, las próximas facturas de este proveedor
                volverán a pedir revisión aunque apruebes esta.
              </p>
              <p v-if="!a.aprobado" class="mt-2 text-xs text-muted-foreground">
                Si dejas vacío «recordarlo cuando la factura diga», la regla se guarda para
                <strong>todo</strong> lo que {{ a.naturaleza === 'venta' ? 'se le facture a este cliente' : 'facture este proveedor' }}.
                Si lo llenas, solo para ese concepto — y cuando diga otra cosa te lo vuelvo a preguntar.
              </p>
            </div>
          </template>
        </div>
      </template>
    </section>
  </div>
</template>
