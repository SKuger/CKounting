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
import { ArrowLeft, RefreshCw, Check, Undo2, ChevronRight, Download, FileSpreadsheet, Settings2, UploadCloud } from 'lucide-vue-next'

type Linea = {
  id: number; cuenta_puc: string | null; descripcion: string; debito: string; credito: string
  rol: string | null; codigo_siigo: string | null
}
// `naturaleza` (D-127): compra, venta o doc_soporte. Decide qué líneas lleva,
// quién es el tercero y qué se le pregunta al contador al aprobar.
type Naturaleza = 'compra' | 'venta' | 'doc_soporte'
type Asiento = {
  id: number; cufe: string; tercero_nit: string | null; fecha: string | null
  estado: string; avisos: string[]; aprobado: number; lineas: Linea[]; naturaleza: Naturaleza
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
    const r = await rpc<{ path: string; comprobantes: number; lineas: number; cuadra: boolean; faltan: string[] }>(
      'siigo_exportar', { db_path: dbPath.value, periodo: periodo.value, output_dir: ruta })
    await cargarSiigo()
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

function abrir(a: Asiento) {
  if (abierto.value === a.id) { abierto.value = null; return }
  abierto.value = a.id
  correccion.cuenta_puc = lineaDecidida(a)?.cuenta_puc || ''
  correccion.patron = ''
  correccion.retencion = ''
  correccion.aprender_regla = true
  correccion.iva_codigo = a.lineas.find((l) => l.rol === 'iva')?.codigo_siigo || ''
  const codigos = a.lineas.filter((l) => l.rol === 'retencion').map((l) => l.codigo_siigo || '')
  for (const t of ['retefuente', 'reteiva', 'reteica'] as const)
    retCliente[t] = retPorTipo(t).find((r) => codigos.includes(r.codigo))?.codigo || ''
  retCliente.tocado = false
}

async function aprobar(a: Asiento) {
  guardando.value = true
  try {
    await rpc('asiento_aprobar', {
      db_path: dbPath.value, id: a.id,
      cuenta_puc: correccion.cuenta_puc,
      patron: correccion.patron,
      concepto_retencion_id: correccion.retencion && correccion.retencion !== 'ninguna' ? correccion.retencion : '',
      sin_retencion: correccion.retencion === 'ninguna',
      aprender_regla: correccion.aprender_regla,
      iva_codigo: correccion.iva_codigo,
      retenciones_cliente: a.naturaleza === 'venta' && retCliente.tocado
        ? ([retCliente.retefuente, retCliente.reteiva, retCliente.reteica].filter(Boolean).join(',') || 'ninguna')
        : '',
      ...cuentas,
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
        <ul v-if="catalogoVista.sin_cruce.length" class="mt-2 space-y-0.5 text-xs text-status-warning">
          <li v-for="c in catalogoVista.sin_cruce" :key="c.codigo">
            · <span class="font-mono">{{ c.codigo }}</span> {{ c.nombre }}: {{ c.motivo }}
          </li>
        </ul>
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
          <h2 class="sticky top-0 z-10 border-b border-border bg-card px-3 py-1.5 text-xs font-semibold uppercase"
            :class="grupo.clase">
            {{ grupo.titulo }} · {{ grupo.filas.length }}
          </h2>
          <template v-for="a in grupo.filas" :key="a.id">
            <div class="flex cursor-pointer items-center gap-2 border-b border-border/60 px-3 py-2 text-sm hover:bg-accent/40"
              @click="abrir(a)">
              <ChevronRight class="size-3.5 shrink-0 text-muted-foreground transition-transform"
                :class="abierto === a.id ? 'rotate-90' : ''" />
              <span class="w-20 shrink-0 font-mono text-xs text-muted-foreground">{{ a.fecha }}</span>
              <span class="w-24 shrink-0 font-mono text-xs">{{ a.tercero_nit }}</span>
              <span v-if="a.naturaleza !== 'compra'"
                class="shrink-0 rounded border border-border px-1.5 py-px text-[10px] uppercase text-muted-foreground">
                {{ ETIQUETA[a.naturaleza] }}
              </span>
              <span class="min-w-0 flex-1 truncate">{{ lineaDecidida(a)?.descripcion }}</span>
              <span class="shrink-0 font-mono text-xs">{{ pesos(a.lineas[0]?.debito || '0') }}</span>
              <Button v-if="a.aprobado" variant="ghost" size="icon-sm" title="Deshacer la aprobación"
                @click.stop="deshacer(a)"><Undo2 class="size-3.5" /></Button>
            </div>

            <div v-if="abierto === a.id" class="border-b border-border bg-muted/30 px-3 py-3">
              <ul v-if="a.avisos.length" class="mb-3 space-y-1">
                <li v-for="(x, i) in a.avisos" :key="i" class="text-xs text-status-warning">· {{ x }}</li>
              </ul>

              <table class="w-full text-xs">
                <thead>
                  <tr class="text-left text-[10px] uppercase text-muted-foreground">
                    <th class="py-1 font-normal">Cuenta</th>
                    <th class="py-1 font-normal">Concepto</th>
                    <th class="py-1 text-right font-normal">Débito</th>
                    <th class="py-1 text-right font-normal">Crédito</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="ln in a.lineas" :key="ln.id" class="border-t border-border/50">
                    <td class="py-1 pr-2 font-mono" :class="ln.cuenta_puc ? '' : 'text-status-error'">
                      {{ ln.cuenta_puc || 'falta' }}
                    </td>
                    <td class="py-1 pr-2">{{ ln.descripcion }}</td>
                    <td class="py-1 text-right font-mono">{{ Number(ln.debito) ? pesos(ln.debito) : '' }}</td>
                    <td class="py-1 text-right font-mono">{{ Number(ln.credito) ? pesos(ln.credito) : '' }}</td>
                  </tr>
                </tbody>
              </table>

              <div v-if="!a.aprobado" class="mt-3 flex flex-wrap items-end gap-3">
                <div class="grid gap-1">
                  <Label class="text-xs">{{ a.naturaleza === 'venta' ? 'Cuenta del ingreso' : 'Cuenta del gasto' }}</Label>
                  <Input v-model="correccion.cuenta_puc" class="h-8 w-32 font-mono"
                    :placeholder="a.naturaleza === 'venta' ? '413505' : '519530'" />
                </div>
                <div v-if="a.naturaleza !== 'venta'" class="grid gap-1">
                  <Label class="text-xs">Retención en la fuente</Label>
                  <select v-model="correccion.retencion" class="h-8 rounded-md border border-border bg-background px-2 text-xs">
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
                      @change="retCliente.tocado = true">
                      <option value="">Nada</option>
                      <option v-for="r in retPorTipo(t)" :key="r.codigo" :value="r.codigo">{{ r.codigo }} · {{ r.nombre }}</option>
                    </select>
                  </div>
                </template>
                <div v-if="ivas.length && a.lineas.some((l) => l.rol === 'iva')" class="grid gap-1">
                  <Label class="text-xs">IVA (código de Siigo)</Label>
                  <select v-model="correccion.iva_codigo" class="h-8 rounded-md border border-border bg-background px-2 text-xs">
                    <option value="">— el de la tarifa —</option>
                    <option v-for="i in ivas" :key="i.codigo" :value="i.codigo">{{ i.codigo }} · {{ i.nombre }}</option>
                  </select>
                </div>
                <div class="grid gap-1">
                  <Label class="text-xs">Recordarlo cuando la factura diga…</Label>
                  <Input v-model="correccion.patron" class="h-8 w-56" placeholder="monitoreo de alarma" />
                </div>
                <label class="flex items-center gap-1.5 pb-1.5 text-xs text-muted-foreground">
                  <input v-model="correccion.aprender_regla" type="checkbox"> Recordar para las próximas
                </label>
                <Button size="sm" :disabled="guardando" @click="aprobar(a)">
                  <Check class="size-3.5" /> Aprobar
                </Button>
              </div>
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
