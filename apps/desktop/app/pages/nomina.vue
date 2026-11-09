<script setup lang="ts">
// La nómina del mes como comprobante de Siigo (D-134). La fuente es el Excel de
// nómina del contador (hojas 1Q y 2Q), no la DIAN. Una vez por empresa se
// aprende la plantilla comparando ese Excel con el 992 que ya está en Siigo;
// cada mes se sube el Excel, se revisan las dos quincenas y se aprueban. Lo
// aprobado sale en el mismo «Archivo de Siigo» de la bandeja.
import { ArrowLeft, UploadCloud, Check, Undo2, ChevronRight, Plus, Users, ListChecks, Trash2 } from 'lucide-vue-next'

type PorCuenta = { cuenta: string; debito: string; credito: string }
type Comprobante = {
  id: number; quincena: string; fecha: string; empleados: number; avisos: string[]; fuente: string
  aprobado: number; siigo_consecutivo: number | null; debito: string; credito: string; por_cuenta: PorCuenta[]
}
type Aprendido = {
  quincenas: string[]; aprendido: number; cuentas: Record<string, string>; entidades: string[]; faltan: string[]
}

const route = useRoute()
const toast = useToast()
const dbPath = computed(() => (route.query.db as string) || '')
const periodo = computed(() => (route.query.periodo as string) || '')

const comprobantes = ref<Comprobante[]>([])
const tienePlantilla = ref(false)
const razonSocial = ref('')
const abierto = ref<number | null>(null)
const ocupado = ref(false)

const aprender = reactive({ nomina: '', carga: '', nominaNombre: '', cargaNombre: '' })
const vistaAprendido = ref<Aprendido | null>(null)
const verPlantilla = ref(false)

function humanError(e: unknown): string {
  const anyE = e as { data?: { error?: string }; message?: string }
  return String(anyE?.data?.error ?? anyE?.message ?? e).replace(/^Error:\s*/, '')
}
const pesos = (v: string) => Number(v || 0).toLocaleString('es-CO', { maximumFractionDigits: 2 })

// ── Los empleados y sus entidades (D-142) ──────────────────────────────────────
// Cada empleado elige su EPS, sus fondos de pensiones y cesantías y su caja; la
// ARL la designa el empleador, y su tarifa sale de la clase de riesgo de cada uno.
type Entidad = { cuenta: string; nit: string }
const ENTIDADES = [
  { k: 'salud', titulo: 'EPS', conCuenta: true },
  { k: 'pension', titulo: 'Fondo de pensiones', conCuenta: true },
  { k: 'cesantias', titulo: 'Fondo de cesantías', conCuenta: false },
  { k: 'caja', titulo: 'Caja de compensación', conCuenta: true },
] as const
type ClaveEntidad = typeof ENTIDADES[number]['k']
type FilaEmpleado = { id: string; nombre: string; riesgo: string; nuevo?: boolean; sucio?: boolean } & Record<ClaveEntidad, Entidad>
type Empleados = {
  empleados: FilaEmpleado[]; arl: Entidad; por_defecto: Record<ClaveEntidad, Entidad>
  smmlv: Record<string, string>; riesgos: Record<string, string>
  riesgo_por_defecto: string; parametros: Record<string, { smmlv?: string; aux_transporte?: string }>
}
const verEmpleados = ref(false)
const filas = ref<FilaEmpleado[]>([])
const riesgos = ref<Record<string, string>>({})
const empresaNom = reactive({ arl: { cuenta: '', nit: '' } as Entidad, smmlv: '', aux: '', riesgo: '' })
const anio = computed(() => periodo.value.slice(0, 4))
const sinRiesgo = computed(() => empresaNom.riesgo ? 0 : filas.value.filter((f) => !f.nuevo && !f.riesgo).length)

async function cargarEmpleados() {
  try {
    const r = await rpc<Empleados>('nomina_empleados', { db_path: dbPath.value })
    filas.value = r.empleados
    riesgos.value = r.riesgos
    empresaNom.arl = { ...r.arl }
    // El salario mínimo y el auxilio son de todas las empresas (D-145); el de la
    // empresa, de antes, se muestra mientras no haya uno general.
    empresaNom.smmlv = r.parametros?.[anio.value]?.smmlv || r.smmlv[anio.value] || ''
    empresaNom.aux = r.parametros?.[anio.value]?.aux_transporte || ''
    empresaNom.riesgo = r.riesgo_por_defecto || ''
  } catch (e) {
    toast.error('No se pudieron cargar los empleados', humanError(e))
  }
}
function agregarEmpleado() {
  const vacia = (): Entidad => ({ cuenta: '', nit: '' })
  filas.value.unshift({ id: '', nombre: '', riesgo: '', nuevo: true, sucio: true,
    salud: vacia(), pension: vacia(), cesantias: vacia(), caja: vacia() })
}
async function guardarEmpleado(f: FilaEmpleado) {
  try {
    const r = await rpc<FilaEmpleado>('nomina_empleado_guardar', { db_path: dbPath.value, empleado: f })
    Object.assign(f, r, { nuevo: false, sucio: false })
    toast.success('Empleado guardado', f.nombre || f.id)
  } catch (e) {
    toast.error('No se guardó el empleado', humanError(e))
  }
}
async function guardarEmpresaNom() {
  try {
    await rpc('nomina_empresa_guardar', { db_path: dbPath.value,
      empresa: { arl: empresaNom.arl, riesgo_por_defecto: empresaNom.riesgo,
        smmlv: { [anio.value]: empresaNom.smmlv }, aux_transporte: { [anio.value]: empresaNom.aux } } })
    toast.success('Guardado', 'La ARL y la clase de riesgo de la empresa; el salario mínimo y el auxilio, para todas.')
  } catch (e) {
    toast.error('No se guardó', humanError(e))
  }
}
const tarifaTxt = (t: string) => Number(t).toLocaleString('es-CO', { maximumFractionDigits: 3 })

// ── La tabla de conceptos (D-145) ──────────────────────────────────────────────
// Cada pago o descuento con su cuenta, y si es salarial (base de las
// provisiones) o base de seguridad social (base de los aportes). Lo pidió el
// contador para matricular una vez lo que el Excel trae y no adivinarlo.
type FilaDevengo = { clave: string; nombre: string; cuenta: string; salarial: boolean; base_ss: boolean; propio: boolean; columna: string }
type FilaDeduccion = { clave: string; nombre: string; cuenta: string; propio: boolean; columna: string }
type FilaProvision = { clave: string; nombre: string; cuenta_gasto: string; cuenta_pasivo: string; tarifa: string }
type FilaAporte = { clave: string; nombre: string; cuenta_gasto: string; tarifa: string }
type Conceptos = { devengos: FilaDevengo[]; deducciones: FilaDeduccion[]; provisiones: FilaProvision[]; aportes: FilaAporte[]; neto: { cuenta: string } }
const verConceptos = ref(false)
const tabla = ref<Conceptos | null>(null)
const guardandoConceptos = ref(false)
const nuevo = reactive({ nombre: '', tipo: 'devengo', columna: '', cuenta: '', salarial: false, base_ss: false })
const sinCuenta = computed(() => {
  const t = tabla.value
  if (!t) return 0
  return [...t.devengos.map((f) => f.cuenta), ...t.deducciones.map((f) => f.cuenta),
    ...t.provisiones.flatMap((f) => [f.cuenta_gasto, f.cuenta_pasivo]), ...t.aportes.map((f) => f.cuenta_gasto),
    t.neto.cuenta].filter((c) => !c).length
})

async function cargarConceptos() {
  try {
    tabla.value = await rpc<Conceptos>('nomina_conceptos', { db_path: dbPath.value })
  } catch (e) {
    toast.error('No se pudo cargar la tabla de conceptos', humanError(e))
  }
}
async function guardarConceptos(extra: Record<string, unknown> = {}) {
  if (!tabla.value) return
  guardandoConceptos.value = true
  try {
    tabla.value = await rpc<Conceptos>('nomina_conceptos_guardar', { db_path: dbPath.value,
      conceptos: { ...tabla.value, ...extra } })
    toast.success('Conceptos guardados', 'Vuelva a subir el Excel del mes para rearmar la nómina con ellos.')
    await cargar()
  } catch (e) {
    toast.error('No se guardaron los conceptos', humanError(e))
  } finally {
    guardandoConceptos.value = false
  }
}
async function agregarConcepto() {
  if (!nuevo.nombre.trim()) return
  await guardarConceptos({ nuevos: [{ ...nuevo }] })
  Object.assign(nuevo, { nombre: '', tipo: 'devengo', columna: '', cuenta: '', salarial: false, base_ss: false })
}
async function borrarConcepto(clave: string) {
  await guardarConceptos({ borrar: [clave] })
}

const ETIQUETA_CLAVE = (k: string) => k.replace('nom:debito:', 'Débito · ').replace('nom:credito:', 'Crédito · ').replaceAll('_', ' ')

async function cargar() {
  if (!dbPath.value || !periodo.value) return
  try {
    const r = await rpc<{ comprobantes: Comprobante[]; plantilla: boolean }>('nomina_list', {
      db_path: dbPath.value, periodo: periodo.value })
    comprobantes.value = r.comprobantes
    tienePlantilla.value = r.plantilla
    await cargarEmpleados()
    await cargarConceptos()
    const info = await rpc<{ razon_social: string }>('open_empresa', { db_path: dbPath.value })
    razonSocial.value = info.razon_social
  } catch (e) {
    toast.error('No se pudo cargar la nómina', humanError(e))
  }
}

async function guardarArchivo(file: File): Promise<string> {
  const fd = new FormData()
  fd.append('db_path', dbPath.value)
  fd.append('accion', 'guardar')
  fd.append('file', file)
  const res = await $fetch<{ ok: boolean; error?: string; saved_to?: string }>('/api/upload-siigo', { method: 'POST', body: fd })
  if (!res.ok || !res.saved_to) throw new Error(res.error || 'no se pudo guardar el archivo')
  return res.saved_to
}

async function elegir(e: Event, cual: 'nomina' | 'carga') {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    aprender[cual] = await guardarArchivo(file)
    aprender[cual === 'nomina' ? 'nominaNombre' : 'cargaNombre'] = file.name
    if (aprender.nomina && aprender.carga) await ensayarAprendizaje()
  } catch (err) {
    toast.error('No se pudo subir el archivo', humanError(err))
  }
}

async function ensayarAprendizaje() {
  ocupado.value = true
  try {
    vistaAprendido.value = await rpc<Aprendido>('nomina_aprender', {
      db_path: dbPath.value, nomina_path: aprender.nomina, carga_path: aprender.carga, periodo: periodo.value, dry_run: true })
  } catch (e) {
    toast.error('No se pudo aprender la plantilla', humanError(e))
  } finally {
    ocupado.value = false
  }
}

async function aplicarAprendizaje() {
  ocupado.value = true
  try {
    const r = await rpc<Aprendido>('nomina_aprender', {
      db_path: dbPath.value, nomina_path: aprender.nomina, carga_path: aprender.carga, periodo: periodo.value, dry_run: false })
    vistaAprendido.value = null
    toast.success('Plantilla de nómina guardada', `${r.aprendido} cuentas y entidades aprendidas`)
    await cargar()
  } catch (e) {
    toast.error('No se pudo guardar la plantilla', humanError(e))
  } finally {
    ocupado.value = false
  }
}

async function subirMes(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  ocupado.value = true
  try {
    const ruta = await guardarArchivo(file)
    await rpc('nomina_generar', { db_path: dbPath.value, periodo: periodo.value, nomina_path: ruta })
    await cargar()
  } catch (err) {
    toast.error('No se pudo armar la nómina', humanError(err))
  } finally {
    ocupado.value = false
  }
}

async function aprobar(c: Comprobante, si: boolean) {
  try {
    await rpc('nomina_aprobar', { db_path: dbPath.value, id: c.id, aprobado: si })
    if (si) toast.success('Nómina aprobada', 'Va en el «Archivo de Siigo» de Causación, junto con los asientos del mes.')
    await cargar()
  } catch (e) {
    toast.error('No se pudo aprobar', humanError(e))
  }
}

onMounted(cargar)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-3 overflow-auto p-4">
    <header class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
      <NuxtLink :to="{ path: '/causacion', query: { db: dbPath, periodo } }"
        class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft class="size-3.5" /> {{ razonSocial || 'Empresa' }} · causación
      </NuxtLink>
      <span class="text-border">/</span>
      <h1 class="font-heading text-xl font-medium tracking-tight">Nómina de {{ periodo }}</h1>
    </header>

    <p class="max-w-3xl text-xs text-muted-foreground">
      La nómina sale de su Excel de liquidación (hojas «1Q» y «2Q»), no de la DIAN. Contab arma un comprobante por
      quincena, como el que usted sube hoy a Siigo, y lo aprobado va en el mismo «Archivo de Siigo» de la bandeja.
    </p>

    <!-- la plantilla: una vez por empresa -->
    <section class="rounded-lg border border-border bg-card p-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-sm font-semibold">
          Plantilla de nómina
          <span class="ml-1 text-xs font-normal" :class="tienePlantilla ? 'text-status-success' : 'text-status-warning'">
            {{ tienePlantilla ? 'aprendida' : 'falta: se aprende una vez' }}
          </span>
        </h2>
        <Button size="sm" variant="ghost" @click="verPlantilla = !verPlantilla">
          {{ verPlantilla ? 'Cerrar' : (tienePlantilla ? 'Volver a aprender' : 'Aprender') }}
        </Button>
      </div>
      <div v-if="verPlantilla || !tienePlantilla" class="mt-2 grid gap-2">
        <p class="text-xs text-muted-foreground">
          Suba el Excel de nómina de un mes que ya esté en Siigo, y el archivo de carga o el movimiento contable
          de Siigo que tenga el comprobante de nómina de ese mes. Contab los compara línea por línea y aprende a qué cuenta va cada
          concepto y cuál es la EPS, el fondo, la caja y la ARL de cada empleado.
        </p>
        <div class="flex flex-wrap gap-2">
          <Button as="label" size="sm" variant="outline" :disabled="ocupado">
            <UploadCloud class="size-3.5" /> {{ aprender.nominaNombre || 'Excel de nómina' }}
            <input type="file" accept=".xlsx,.xlsm,.ods" class="hidden" @change="elegir($event, 'nomina')">
          </Button>
          <Button as="label" size="sm" variant="outline" :disabled="ocupado">
            <UploadCloud class="size-3.5" /> {{ aprender.cargaNombre || 'Carga o movimiento de Siigo' }}
            <input type="file" accept=".xlsx,.xlsm,.ods" class="hidden" @change="elegir($event, 'carga')">
          </Button>
        </div>
        <div v-if="vistaAprendido" class="rounded-md border border-border bg-muted/30 p-3 text-xs">
          <p>Quincenas emparejadas: <strong>{{ vistaAprendido.quincenas.join(' · ') }}</strong> ·
            {{ vistaAprendido.aprendido }} valores aprendidos.</p>
          <div class="mt-2 grid gap-x-6 gap-y-0.5 sm:grid-cols-2">
            <div v-for="(v, k) in vistaAprendido.cuentas" :key="k" class="flex justify-between gap-2">
              <span class="text-muted-foreground">{{ ETIQUETA_CLAVE(String(k)) }}</span><span class="font-mono">{{ v }}</span>
            </div>
          </div>
          <p class="mt-2 text-muted-foreground">Entidades (cuenta | NIT): <span class="font-mono">{{ vistaAprendido.entidades.join(' · ') }}</span></p>
          <p v-if="vistaAprendido.faltan.length" class="mt-2 text-status-warning">
            Falta: {{ vistaAprendido.faltan.join(', ') }}
          </p>
          <div class="mt-3 flex gap-2">
            <Button size="sm" :disabled="ocupado" @click="aplicarAprendizaje">Guardar la plantilla</Button>
            <Button size="sm" variant="ghost" :disabled="ocupado" @click="vistaAprendido = null">Cancelar</Button>
          </div>
        </div>
      </div>
    </section>

    <!-- la tabla de conceptos: cuenta y si es base de cada cosa -->
    <section class="rounded-lg border border-border bg-card p-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="flex items-center gap-1.5 text-sm font-semibold">
          <ListChecks class="size-4" /> Conceptos y cuentas
          <span v-if="sinCuenta" class="text-xs font-normal text-muted-foreground">· {{ sinCuenta }} sin cuenta: solo hacen falta si el Excel los trae</span>
        </h2>
        <Button size="sm" variant="ghost" @click="verConceptos = !verConceptos">{{ verConceptos ? 'Cerrar' : 'Abrir' }}</Button>
      </div>
      <div v-if="verConceptos && tabla" class="mt-3 grid gap-4 text-xs">
        <p class="max-w-3xl text-muted-foreground">
          A qué cuenta va cada concepto. En los pagos, «salarial» quiere decir que entra en la base de las provisiones
          (prima, cesantías, intereses y vacaciones), y «base de seguridad social», en la de pensión, caja y ARL.
          Lo que el Excel traiga y no esté aquí se puede matricular abajo.
        </p>

        <div class="overflow-x-auto">
          <table class="w-full min-w-[640px]">
            <thead><tr class="text-left text-[10px] uppercase text-muted-foreground">
              <th class="py-1 pr-2 font-normal">Pagos al empleado</th><th class="py-1 pr-2 font-normal">Cuenta</th>
              <th class="py-1 pr-2 text-center font-normal">Salarial</th><th class="py-1 pr-2 text-center font-normal">Base seguridad social</th><th />
            </tr></thead>
            <tbody>
              <tr v-for="f in tabla.devengos" :key="f.clave" class="border-t border-border/50">
                <td class="py-1 pr-2">{{ f.nombre }}<span v-if="f.propio" class="ml-1 text-muted-foreground">· columna «{{ f.columna }}»</span></td>
                <td class="py-1 pr-2"><Input v-model="f.cuenta" class="h-7 w-28 font-mono text-xs" /></td>
                <td class="py-1 pr-2 text-center"><input v-model="f.salarial" type="checkbox"></td>
                <td class="py-1 pr-2 text-center"><input v-model="f.base_ss" type="checkbox"></td>
                <td class="py-1 text-right">
                  <Button v-if="f.propio" variant="ghost" size="icon-sm" title="Quitar este concepto" @click="borrarConcepto(f.clave)"><Trash2 class="size-3.5" /></Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full min-w-[480px]">
            <thead><tr class="text-left text-[10px] uppercase text-muted-foreground">
              <th class="py-1 pr-2 font-normal">Descuentos al empleado</th><th class="py-1 pr-2 font-normal">Cuenta (con el NIT del empleado)</th><th />
            </tr></thead>
            <tbody>
              <tr v-for="f in tabla.deducciones" :key="f.clave" class="border-t border-border/50">
                <td class="py-1 pr-2">{{ f.nombre }}<span v-if="f.propio" class="ml-1 text-muted-foreground">· columna «{{ f.columna }}»</span></td>
                <td class="py-1 pr-2"><Input v-model="f.cuenta" class="h-7 w-28 font-mono text-xs" /></td>
                <td class="py-1 text-right">
                  <Button v-if="f.propio" variant="ghost" size="icon-sm" title="Quitar este concepto" @click="borrarConcepto(f.clave)"><Trash2 class="size-3.5" /></Button>
                </td>
              </tr>
              <tr class="border-t border-border/50 text-muted-foreground">
                <td class="py-1 pr-2" colspan="3">Salud, pensión y fondo de solidaridad van a la entidad de cada empleado (en Empleados).</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="grid gap-4 lg:grid-cols-2">
          <table class="w-full">
            <thead><tr class="text-left text-[10px] uppercase text-muted-foreground">
              <th class="py-1 pr-2 font-normal">Provisiones</th><th class="py-1 pr-2 font-normal">Gasto</th><th class="py-1 pr-2 font-normal">Pasivo</th><th class="py-1 pr-2 font-normal">Tarifa %</th>
            </tr></thead>
            <tbody>
              <tr v-for="f in tabla.provisiones" :key="f.clave" class="border-t border-border/50">
                <td class="py-1 pr-2">{{ f.nombre }}</td>
                <td class="py-1 pr-2"><Input v-model="f.cuenta_gasto" class="h-7 w-24 font-mono text-xs" :class="f.cuenta_gasto ? '' : 'border-status-warning'" /></td>
                <td class="py-1 pr-2"><Input v-model="f.cuenta_pasivo" class="h-7 w-24 font-mono text-xs" :class="f.cuenta_pasivo ? '' : 'border-status-warning'" /></td>
                <td class="py-1 pr-2"><Input v-model="f.tarifa" class="h-7 w-20 font-mono text-xs" /></td>
              </tr>
            </tbody>
          </table>
          <table class="w-full">
            <thead><tr class="text-left text-[10px] uppercase text-muted-foreground">
              <th class="py-1 pr-2 font-normal">Aportes del empleador</th><th class="py-1 pr-2 font-normal">Gasto</th><th class="py-1 pr-2 font-normal">Tarifa %</th>
            </tr></thead>
            <tbody>
              <tr v-for="f in tabla.aportes" :key="f.clave" class="border-t border-border/50">
                <td class="py-1 pr-2">{{ f.nombre }}</td>
                <td class="py-1 pr-2"><Input v-model="f.cuenta_gasto" class="h-7 w-24 font-mono text-xs" :class="f.cuenta_gasto ? '' : 'border-status-warning'" /></td>
                <td class="py-1 pr-2">
                  <Input v-if="f.clave !== 'arl'" v-model="f.tarifa" class="h-7 w-20 font-mono text-xs" />
                  <span v-else class="text-muted-foreground">según la clase de riesgo</span>
                </td>
              </tr>
              <tr class="border-t border-border/50">
                <td class="py-1 pr-2">Neto a pagar</td>
                <td class="py-1 pr-2" colspan="2"><Input v-model="tabla.neto.cuenta" class="h-7 w-24 font-mono text-xs" :class="tabla.neto.cuenta ? '' : 'border-status-warning'" /></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="flex flex-wrap items-end gap-2 rounded-md border border-border bg-muted/30 p-3">
          <div class="grid gap-1"><Label class="text-xs">Concepto nuevo</Label><Input v-model="nuevo.nombre" class="h-8 w-48 text-xs" placeholder="Bonificación" /></div>
          <div class="grid gap-1">
            <Label class="text-xs">Es un</Label>
            <select v-model="nuevo.tipo" class="h-8 rounded-md border border-border bg-background px-2 text-xs">
              <option value="devengo">Pago</option><option value="deduccion">Descuento</option>
            </select>
          </div>
          <div class="grid gap-1"><Label class="text-xs">Columna del Excel</Label><Input v-model="nuevo.columna" class="h-8 w-44 text-xs" :placeholder="nuevo.nombre || 'como dice el Excel'" /></div>
          <div class="grid gap-1"><Label class="text-xs">Cuenta</Label><Input v-model="nuevo.cuenta" class="h-8 w-28 font-mono text-xs" /></div>
          <template v-if="nuevo.tipo === 'devengo'">
            <label class="flex h-8 items-center gap-1"><input v-model="nuevo.salarial" type="checkbox"> Salarial</label>
            <label class="flex h-8 items-center gap-1"><input v-model="nuevo.base_ss" type="checkbox"> Base seguridad social</label>
          </template>
          <Button size="sm" variant="outline" :disabled="!nuevo.nombre.trim() || guardandoConceptos" @click="agregarConcepto"><Plus class="size-3.5" /> Agregar</Button>
        </div>

        <div><Button size="sm" :disabled="guardandoConceptos" @click="guardarConceptos()">{{ guardandoConceptos ? 'Guardando…' : 'Guardar los conceptos' }}</Button></div>
      </div>
    </section>

    <!-- los empleados: sus entidades y su clase de riesgo -->
    <section class="rounded-lg border border-border bg-card p-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="flex items-center gap-1.5 text-sm font-semibold">
          <Users class="size-4" /> Empleados
          <span class="text-xs font-normal text-muted-foreground">{{ filas.length }}</span>
          <span v-if="sinRiesgo" class="text-xs font-normal text-status-warning">· {{ sinRiesgo }} sin clase de riesgo</span>
          <span v-if="!empresaNom.smmlv" class="text-xs font-normal text-status-warning">· falta el salario mínimo de {{ anio }}</span>
        </h2>
        <Button size="sm" variant="ghost" @click="verEmpleados = !verEmpleados">{{ verEmpleados ? 'Cerrar' : 'Abrir' }}</Button>
      </div>
      <div v-if="verEmpleados" class="mt-3 grid gap-3">
        <p class="max-w-3xl text-xs text-muted-foreground">
          Cada empleado elige su EPS, sus fondos y su caja; la ARL la designa la empresa y su tarifa sale de la clase de
          riesgo de cada uno. La salud y la pensión del empleado se toman del Excel y se revisan contra el 4 %; con el
          salario mínimo se revisan el fondo de solidaridad (desde 4) y la exoneración (hasta 10).
        </p>
        <div class="flex flex-wrap items-end gap-3 rounded-md border border-border bg-muted/30 p-3">
          <div class="grid gap-1">
            <Label class="text-xs">ARL de la empresa · NIT</Label>
            <Input v-model="empresaNom.arl.nit" class="h-8 w-36 font-mono" />
          </div>
          <div class="grid gap-1">
            <Label class="text-xs">Cuenta</Label>
            <Input v-model="empresaNom.arl.cuenta" class="h-8 w-28 font-mono" />
          </div>
          <div class="grid gap-1">
            <Label class="text-xs">Clase de riesgo por defecto</Label>
            <select v-model="empresaNom.riesgo" class="h-8 rounded-md border border-border bg-background px-2 text-xs">
              <option value="">— ninguna —</option>
              <option v-for="(t, c) in riesgos" :key="c" :value="c">{{ c }} · {{ tarifaTxt(t) }} %</option>
            </select>
          </div>
          <div class="grid gap-1">
            <Label class="text-xs">Salario mínimo {{ anio }} <span class="text-muted-foreground">(todas las empresas)</span></Label>
            <Input v-model="empresaNom.smmlv" class="h-8 w-36 font-mono" inputmode="numeric" />
          </div>
          <div class="grid gap-1">
            <Label class="text-xs">Auxilio de transporte {{ anio }} <span class="text-muted-foreground">(todas)</span></Label>
            <Input v-model="empresaNom.aux" class="h-8 w-32 font-mono" inputmode="numeric" />
          </div>
          <Button size="sm" @click="guardarEmpresaNom">Guardar</Button>
          <span class="text-[11px] text-muted-foreground">
            Clases de riesgo: {{ Object.entries(riesgos).map(([c, t]) => `${c} ${tarifaTxt(t)} %`).join(' · ') }}
          </span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[980px] text-xs">
            <thead>
              <tr class="text-left text-[10px] uppercase text-muted-foreground">
                <th class="py-1 pr-2 font-normal">Cédula · nombre</th>
                <th class="py-1 pr-2 font-normal">Riesgo ARL</th>
                <th v-for="e in ENTIDADES" :key="e.k" class="py-1 pr-2 font-normal">{{ e.titulo }} <span class="normal-case">(NIT{{ e.conCuenta ? ' · cuenta' : '' }})</span></th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr v-for="(f, i) in filas" :key="f.id || `nuevo-${i}`" class="border-t border-border/50 align-top">
                <td class="py-1.5 pr-2">
                  <Input v-if="f.nuevo" v-model="f.id" class="h-7 w-32 font-mono text-xs" placeholder="Cédula" />
                  <span v-else class="font-mono">{{ f.id }}</span>
                  <Input v-model="f.nombre" class="mt-1 h-7 w-60 text-xs" placeholder="Nombre" @input="f.sucio = true" />
                </td>
                <td class="py-1.5 pr-2">
                  <select v-model="f.riesgo" class="h-7 rounded-md border bg-background px-1.5 text-xs"
                    :class="f.riesgo ? 'border-border' : 'border-status-warning'" @change="f.sucio = true">
                    <option value="">— elegir —</option>
                    <option v-for="(t, c) in riesgos" :key="c" :value="c">{{ c }} · {{ tarifaTxt(t) }} %</option>
                  </select>
                </td>
                <td v-for="e in ENTIDADES" :key="e.k" class="py-1.5 pr-2">
                  <Input v-model="f[e.k].nit" class="h-7 w-28 font-mono text-xs" placeholder="NIT" @input="f.sucio = true" />
                  <Input v-if="e.conCuenta" v-model="f[e.k].cuenta" class="mt-1 h-7 w-28 font-mono text-xs" placeholder="Cuenta" @input="f.sucio = true" />
                </td>
                <td class="py-1.5">
                  <Button v-if="f.sucio" size="sm" @click="guardarEmpleado(f)">Guardar</Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div>
          <Button size="sm" variant="outline" @click="agregarEmpleado"><Plus class="size-3.5" /> Agregar empleado</Button>
          <span class="ml-2 text-[11px] text-muted-foreground">Los empleados del Excel se agregan solos al subir la nómina del mes.</span>
        </div>
      </div>
    </section>

    <!-- el mes -->
    <section class="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-2">
      <Button as="label" size="sm" :disabled="ocupado || !tienePlantilla"
        :title="tienePlantilla ? '' : 'Primero la plantilla'">
        <UploadCloud class="size-3.5" /> {{ ocupado ? 'Armando…' : `Subir el Excel de nómina de ${periodo}` }}
        <input type="file" accept=".xlsx,.xlsm,.ods" class="hidden" @change="subirMes">
      </Button>
      <span class="text-xs text-muted-foreground">Se puede volver a subir: lo aprobado no se toca. La nómina aprobada sale en el «Archivo de Siigo» de Causación.</span>
    </section>

    <section class="rounded-lg border border-border bg-card">
      <p v-if="!comprobantes.length" class="px-3 py-8 text-center text-sm text-muted-foreground">
        Todavía no hay nómina para {{ periodo }}.
      </p>
      <template v-for="c in comprobantes" :key="c.id">
        <div class="flex cursor-pointer items-center gap-3 border-b border-border/60 px-3 py-2 text-sm hover:bg-accent/40"
          @click="abierto = abierto === c.id ? null : c.id">
          <ChevronRight class="size-3.5 text-muted-foreground transition-transform" :class="abierto === c.id ? 'rotate-90' : ''" />
          <span class="font-medium">{{ c.quincena === '1Q' ? 'Primera quincena' : 'Segunda quincena' }}</span>
          <span class="font-mono text-xs text-muted-foreground">{{ c.fecha }}</span>
          <span class="text-xs text-muted-foreground">{{ c.empleados }} empleados</span>
          <span class="flex-1" />
          <span class="font-mono text-xs">{{ pesos(c.debito) }}</span>
          <span class="text-xs" :class="c.debito === c.credito ? 'text-status-success' : 'text-status-error'">
            {{ c.debito === c.credito ? 'cuadra' : 'no cuadra' }}
          </span>
          <span v-if="c.aprobado" class="text-xs text-status-success">aprobada<template v-if="c.siigo_consecutivo"> · {{ c.siigo_consecutivo }}</template></span>
          <Button v-if="!c.aprobado" size="sm" :disabled="c.debito !== c.credito" @click.stop="aprobar(c, true)">
            <Check class="size-3.5" /> Aprobar
          </Button>
          <Button v-else variant="ghost" size="icon-sm" title="Deshacer la aprobación" @click.stop="aprobar(c, false)">
            <Undo2 class="size-3.5" />
          </Button>
        </div>
        <div v-if="abierto === c.id" class="border-b border-border bg-muted/30 px-3 py-3">
          <ul v-if="c.avisos.length" class="mb-2 space-y-0.5">
            <li v-for="(a, i) in c.avisos" :key="i" class="text-xs text-status-warning">· {{ a }}</li>
          </ul>
          <table class="w-full max-w-xl text-xs">
            <thead><tr class="text-left text-[10px] uppercase text-muted-foreground">
              <th class="py-1 font-normal">Cuenta</th><th class="py-1 text-right font-normal">Débito</th><th class="py-1 text-right font-normal">Crédito</th>
            </tr></thead>
            <tbody>
              <tr v-for="x in c.por_cuenta" :key="x.cuenta" class="border-t border-border/50">
                <td class="py-1 font-mono" :class="x.cuenta === 'falta' ? 'text-status-error' : ''">{{ x.cuenta }}</td>
                <td class="py-1 text-right font-mono">{{ Number(x.debito) ? pesos(x.debito) : '' }}</td>
                <td class="py-1 text-right font-mono">{{ Number(x.credito) ? pesos(x.credito) : '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>
  </div>
</template>
