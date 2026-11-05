<script setup lang="ts">
// La nómina del mes como comprobante de Siigo (D-134). La fuente es el Excel de
// nómina del contador (hojas 1Q y 2Q), no la DIAN. Una vez por empresa se
// aprende la plantilla comparando ese Excel con el 992 que ya está en Siigo;
// cada mes se sube el Excel, se revisan las dos quincenas y se aprueban. Lo
// aprobado sale en el mismo «Archivo de Siigo» de la bandeja.
import { ArrowLeft, UploadCloud, Check, Undo2, ChevronRight, Plus, Users } from 'lucide-vue-next'

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
}
const verEmpleados = ref(false)
const filas = ref<FilaEmpleado[]>([])
const riesgos = ref<Record<string, string>>({})
const empresaNom = reactive({ arl: { cuenta: '', nit: '' } as Entidad, smmlv: '' })
const anio = computed(() => periodo.value.slice(0, 4))
const sinRiesgo = computed(() => filas.value.filter((f) => !f.nuevo && !f.riesgo).length)

async function cargarEmpleados() {
  try {
    const r = await rpc<Empleados>('nomina_empleados', { db_path: dbPath.value })
    filas.value = r.empleados
    riesgos.value = r.riesgos
    empresaNom.arl = { ...r.arl }
    empresaNom.smmlv = r.smmlv[anio.value] || ''
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
      empresa: { arl: empresaNom.arl, smmlv: { [anio.value]: empresaNom.smmlv } } })
    toast.success('Guardado', 'La ARL de la empresa y el salario mínimo.')
  } catch (e) {
    toast.error('No se guardó', humanError(e))
  }
}
const tarifaTxt = (t: string) => Number(t).toLocaleString('es-CO', { maximumFractionDigits: 3 })

const ETIQUETA_CLAVE = (k: string) => k.replace('nom:debito:', 'Débito · ').replace('nom:credito:', 'Crédito · ').replaceAll('_', ' ')

async function cargar() {
  if (!dbPath.value || !periodo.value) return
  try {
    const r = await rpc<{ comprobantes: Comprobante[]; plantilla: boolean }>('nomina_list', {
      db_path: dbPath.value, periodo: periodo.value })
    comprobantes.value = r.comprobantes
    tienePlantilla.value = r.plantilla
    await cargarEmpleados()
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
      db_path: dbPath.value, nomina_path: aprender.nomina, carga_path: aprender.carga, dry_run: true })
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
      db_path: dbPath.value, nomina_path: aprender.nomina, carga_path: aprender.carga, dry_run: false })
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
          Suba el Excel de nómina de un mes que ya esté en Siigo, y el archivo de carga de Siigo que tenga el
          comprobante de nómina de ese mes. Contab los compara línea por línea y aprende a qué cuenta va cada
          concepto y cuál es la EPS, el fondo, la caja y la ARL de cada empleado.
        </p>
        <div class="flex flex-wrap gap-2">
          <Button as="label" size="sm" variant="outline" :disabled="ocupado">
            <UploadCloud class="size-3.5" /> {{ aprender.nominaNombre || 'Excel de nómina' }}
            <input type="file" accept=".xlsx,.xlsm,.ods" class="hidden" @change="elegir($event, 'nomina')">
          </Button>
          <Button as="label" size="sm" variant="outline" :disabled="ocupado">
            <UploadCloud class="size-3.5" /> {{ aprender.cargaNombre || 'Archivo de carga de Siigo' }}
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
            <Label class="text-xs">Salario mínimo {{ anio }}</Label>
            <Input v-model="empresaNom.smmlv" class="h-8 w-36 font-mono" inputmode="numeric" />
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
