<script setup lang="ts">
// Inicio — el tablero. La unidad de trabajo del contador no es una empresa, es
// «mis N empresas este mes», y hasta la Fase 1.5 no había una sola pantalla que lo
// respondiera: había que entrar una por una a ver en qué iba cada una.
import { Building2, FileSearch, ArrowRight, Orbit, RefreshCw, ChevronLeft, ChevronRight, CircleAlert } from 'lucide-vue-next'

type EmpresaTablero = {
  db_path: string; nit: string; dv: string | null; razon_social: string
  archived: boolean; mes_creado: boolean; pdfs_folder: string | null
  cargas: number; filas: number; soportes: number; soportes_con_cufe: number
  validado_at: string | null; no_conformes: number | null
  perfil_fiscal: boolean; terceros: number; terceros_sin_rut: number
  error: string | null
}
type Resumen = {
  empresas: number; con_excel: number; validadas: number
  con_perfil: number; no_conformes: number; ilegibles: number
}

const pg = useBrand()
const u = useUser()
const toast = useToast()

const displayName = computed(() => {
  const n = (u.active.value?.name || '').trim()
  return n && n !== 'Mi cuenta' ? n.split(/\s+/)[0] : ''
})
const greeting = ref('Hola')
const today = ref('')

function periodoDe(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
const periodo = ref(periodoDe(new Date()))
const empresas = ref<EmpresaTablero[]>([])
const resumen = ref<Resumen | null>(null)
const cargando = ref(false)

const mesLargo = computed(() => {
  const [y, m] = periodo.value.split('-').map(Number)
  if (!y || !m) return periodo.value
  return new Date(y, m - 1, 1).toLocaleDateString('es-CO', { month: 'long', year: 'numeric' })
})

function moverMes(delta: number) {
  const [y, m] = periodo.value.split('-').map(Number)
  if (!y || !m) return
  periodo.value = periodoDe(new Date(y, m - 1 + delta, 1))
  cargar()
}

async function cargar() {
  cargando.value = true
  try {
    const r = await rpc<{ periodo: string; resumen: Resumen; empresas: EmpresaTablero[] }>(
      'tablero', { periodo: periodo.value },
    )
    empresas.value = r.empresas
    resumen.value = r.resumen
  } catch (exc) {
    toast.error('No se pudo cargar el tablero', exc instanceof Error ? exc.message : String(exc))
  } finally {
    cargando.value = false
  }
}

// El estado que se muestra en cada fila. El orden importa: es el orden real del
// trabajo, y la primera etapa sin cumplir es lo que le falta a esa empresa.
function etapas(e: EmpresaTablero) {
  const soportesListos = e.soportes > 0 && e.soportes_con_cufe === e.soportes
  return [
    { k: 'perfil', label: 'Perfil', ok: e.perfil_fiscal, detalle: e.perfil_fiscal ? 'Perfil fiscal configurado' : 'Sin perfil fiscal: no se pueden calcular retenciones' },
    { k: 'excel', label: 'Excel', ok: e.cargas > 0, detalle: e.cargas > 0 ? `${e.cargas} carga(s) · ${e.filas} filas` : 'Sin Excel de la DIAN este mes' },
    { k: 'soportes', label: 'Soportes', ok: soportesListos, parcial: e.soportes > 0 && !soportesListos, detalle: e.pdfs_folder ? `${e.soportes_con_cufe} de ${e.soportes} con CUFE` : 'Sin carpeta de soportes' },
    { k: 'validado', label: 'Validado', ok: !!e.validado_at, detalle: e.validado_at ? `Última validación: ${e.validado_at}` : 'Sin validar' },
  ]
}

// Lo que le falta a esa empresa, en texto. Las etiquetas solas obligaban a pasar
// el mouse para saber qué significaba una apagada, y el estado de una empresa
// tiene que leerse de un vistazo: son veinte filas, no una.
function siguientePaso(e: EmpresaTablero): { texto: string; pendiente: boolean } {
  if (e.error) return { texto: 'No se pudo leer', pendiente: true }
  const primera = etapas(e).find((et) => !et.ok)
  if (!primera) return { texto: 'Al día', pendiente: false }
  return {
    texto: {
      perfil: 'Sin perfil fiscal',
      excel: 'Sin cargar',
      soportes: e.pdfs_folder ? 'Faltan soportes' : 'Sin carpeta de soportes',
      validado: 'Sin validar',
    }[primera.k] ?? 'Pendiente',
    pendiente: true,
  }
}

const modulos = [
  { to: '/empresas', tour: 'inicio-empresas', icon: Building2, title: 'Empresas', desc: 'Tus libros contables, uno por empresa.' },
  { to: '/consulta-dian', tour: 'inicio-dian', icon: FileSearch, title: 'Consulta DIAN', desc: 'Consulta masiva del RUT de terceros a partir de sus NIT.' },
]

onMounted(() => {
  const now = new Date()
  const h = now.getHours()
  greeting.value = h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches'
  today.value = now.toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  cargar()
})
</script>

<template>
  <div class="mx-auto flex w-full max-w-6xl flex-col gap-8">
    <!-- Bienvenida -->
    <section class="relative overflow-hidden rounded-lg border border-border bg-card p-6 shadow-sm md:p-8">
      <Orbit class="pointer-events-none absolute -right-8 -top-10 size-48 text-primary/10" />
      <div class="relative">
        <p class="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Dandelyon · {{ pg.subName }}</p>
        <p class="mt-2 font-heading text-3xl font-semibold text-foreground md:text-4xl">
          {{ greeting }}<template v-if="displayName">, {{ displayName }}</template>
        </p>
        <p v-if="today" class="mt-1 text-sm text-muted-foreground first-letter:uppercase">{{ today }}</p>
      </div>
    </section>

    <!-- Tablero del mes -->
    <section>
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <p class="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">El mes</p>
          <Button variant="ghost" size="sm" aria-label="Mes anterior" @click="moverMes(-1)"><ChevronLeft class="size-4" /></Button>
          <span class="min-w-40 text-center text-sm font-semibold capitalize text-foreground">{{ mesLargo }}</span>
          <Button variant="ghost" size="sm" aria-label="Mes siguiente" @click="moverMes(1)"><ChevronRight class="size-4" /></Button>
        </div>
        <Button variant="outline" size="sm" :disabled="cargando" @click="cargar">
          <RefreshCw class="size-3.5" :class="cargando && 'animate-spin'" /> Actualizar
        </Button>
      </div>

      <!-- Marcador -->
      <div v-if="resumen" class="mb-3 flex flex-wrap gap-x-8 gap-y-2 rounded-lg border border-border bg-card px-5 py-4">
        <div>
          <p class="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Empresas</p>
          <p class="font-mono text-xl tabular-nums text-foreground">{{ resumen.empresas }}</p>
        </div>
        <div>
          <p class="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Con Excel</p>
          <p class="font-mono text-xl tabular-nums text-foreground">{{ resumen.con_excel }}</p>
        </div>
        <div>
          <p class="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Validadas</p>
          <p class="font-mono text-xl tabular-nums text-foreground">{{ resumen.validadas }}</p>
        </div>
        <div>
          <p class="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">No conformes</p>
          <p class="font-mono text-xl tabular-nums" :class="resumen.no_conformes ? 'text-destructive' : 'text-muted-foreground'">{{ resumen.no_conformes }}</p>
        </div>
        <div v-if="resumen.ilegibles">
          <p class="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Ilegibles</p>
          <p class="font-mono text-xl tabular-nums text-destructive">{{ resumen.ilegibles }}</p>
        </div>
      </div>

      <!-- Filas -->
      <div class="overflow-hidden rounded-lg border border-border bg-card">
        <p v-if="!cargando && !empresas.length" class="p-6 text-sm text-muted-foreground">
          Todavía no hay empresas. Crea la primera desde
          <NuxtLink to="/empresas" class="underline underline-offset-4">Empresas</NuxtLink>.
        </p>

        <NuxtLink
          v-for="e in empresas"
          :key="e.db_path"
          :to="{ path: '/empresa', query: { db: e.db_path } }"
          class="flex items-center gap-4 border-b border-border px-5 py-3.5 last:border-b-0 hover:bg-muted/40"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate font-medium text-foreground">{{ e.razon_social }}</p>
            <p class="font-mono text-[11px] text-muted-foreground">
              {{ e.nit }}<template v-if="e.dv">-{{ e.dv }}</template>
              <template v-if="e.terceros"> · {{ e.terceros }} terceros</template>
            </p>
          </div>

          <p
            class="hidden shrink-0 text-sm sm:block"
            :class="siguientePaso(e).pendiente ? 'text-muted-foreground' : 'text-primary'"
          >{{ siguientePaso(e).texto }}</p>

          <p v-if="e.error" class="flex items-center gap-1.5 text-sm text-destructive">
            <CircleAlert class="size-4 shrink-0" />
          </p>

          <div v-else class="flex flex-wrap items-center gap-1.5">
            <span
              v-for="et in etapas(e)"
              :key="et.k"
              :title="et.detalle"
              class="rounded-md border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide"
              :class="et.ok
                ? 'border-primary/40 bg-primary/10 text-primary'
                : et.parcial
                  ? 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400'
                  : 'border-border text-muted-foreground'"
            >{{ et.label }}</span>
            <span
              v-if="e.no_conformes"
              :title="`${e.no_conformes} filas no conformes en la última validación`"
              class="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-0.5 font-mono text-[10px] tabular-nums text-destructive"
            >{{ e.no_conformes }} NC</span>
          </div>

          <ArrowRight class="size-4 shrink-0 text-muted-foreground" />
        </NuxtLink>
      </div>

      <p class="mt-2 text-xs text-muted-foreground">
        Las etiquetas van en el orden real del trabajo, y el texto a su izquierda nombra la primera que falta: eso es lo que le toca a esa empresa este mes.
      </p>
    </section>

    <!-- Módulos -->
    <section>
      <p class="mb-3 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Módulos</p>
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtLink
          v-for="m in modulos"
          :key="m.to"
          :to="m.to"
          :data-tour="m.tour"
          class="group flex items-center gap-4 rounded-lg border border-border bg-card p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
        >
          <span class="grid size-12 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
            <component :is="m.icon" class="size-6" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="text-lg font-semibold leading-tight text-foreground">{{ m.title }}</p>
            <p class="mt-1 text-sm text-muted-foreground">{{ m.desc }}</p>
          </div>
          <ArrowRight class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
        </NuxtLink>
      </div>
    </section>
  </div>
</template>
