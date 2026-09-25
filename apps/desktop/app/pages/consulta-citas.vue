<script setup lang="ts">
import { ArrowLeft, CalendarSearch, Square } from 'lucide-vue-next'

type Estado = 'detenido' | 'iniciando' | 'revisando' | 'esperando' | 'hay_cupo' | 'captcha'
type LogLine = { t: string; nivel: 'info' | 'warn' | 'error' | 'ok'; msg: string }
type Status = {
  activo: boolean
  estado: Estado
  intentos: number
  sin_cupo: number
  ultima_revision: string | null
  proxima_revision: string | null
  espera_s: [number, number]
  pantalla: string | null
  detalle: string | null
  hay_captura: boolean
  log: LogLine[]
}

const POLL_MS = 3000

const toast = useToast()
const status = ref<Status | null>(null)
const busy = ref(false)
const errorServicio = ref<string | null>(null)
const capturaUrl = ref<string | null>(null)
const ahora = ref(Date.now())

const encontrado = computed(() => status.value?.estado === 'hay_cupo' || status.value?.estado === 'captcha')
const logReciente = computed(() => [...(status.value?.log ?? [])].reverse())

const faltan = computed(() => {
  const p = status.value?.proxima_revision
  if (!p) return null
  const s = Math.max(0, Math.round((new Date(p).getTime() - ahora.value) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
})

const estadoTexto = computed(() => {
  const s = status.value
  if (!s) return errorServicio.value ? 'Sin conexión con el servicio DIAN' : 'Conectando…'
  switch (s.estado) {
    case 'iniciando': return 'Abriendo el navegador…'
    case 'revisando': return 'Revisando el portal de la DIAN…'
    case 'esperando': return faltan.value ? `Sin cupo. Próxima revisión en ${faltan.value}` : 'Esperando la próxima revisión'
    case 'hay_cupo': return '¡Hay cupo! Termina la reserva en la ventana del navegador'
    case 'captcha': return 'El portal pidió un CAPTCHA: termínalo tú en la ventana del navegador'
    default: return 'Detenido'
  }
})

const estadoClase = computed(() => {
  const e = status.value?.estado
  if (e === 'hay_cupo') return 'bg-status-success-bg text-status-success'
  if (e === 'captcha') return 'bg-status-warning-bg text-status-warning'
  if (e === 'revisando' || e === 'esperando' || e === 'iniciando') return 'bg-status-info-bg text-status-info'
  return 'bg-muted text-muted-foreground'
})

function nivelClase(n: LogLine['nivel']) {
  if (n === 'ok') return 'text-status-success'
  if (n === 'warn') return 'text-status-warning'
  if (n === 'error') return 'text-status-error'
  return 'text-muted-foreground'
}

const hora = (iso: string) => new Date(iso).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

async function cargarCaptura() {
  // Vía $fetch (no <img src>) para que lleve la credencial local en la app instalada (D-089).
  try {
    const blob = await $fetch<Blob>('/api/dian/citas/captura', { responseType: 'blob' })
    if (capturaUrl.value) URL.revokeObjectURL(capturaUrl.value)
    capturaUrl.value = URL.createObjectURL(blob)
  } catch {
    capturaUrl.value = null
  }
}

async function refrescar() {
  try {
    const anterior = status.value?.estado
    const s = await $fetch<Status>('/api/dian/citas/status')
    status.value = s
    errorServicio.value = null
    if ((s.estado === 'hay_cupo' || s.estado === 'captcha') && anterior !== s.estado) {
      if (s.estado === 'hay_cupo') toast.success('¡Hay cupo!', 'Termina la reserva en la ventana del navegador.')
      else toast.warn('La DIAN pidió un CAPTCHA', 'Complétalo tú en la ventana del navegador.')
    }
    if (s.hay_captura && !capturaUrl.value) await cargarCaptura()
  } catch (e) {
    errorServicio.value = String(e)
  }
}

async function buscar() {
  busy.value = true
  try {
    if (capturaUrl.value) URL.revokeObjectURL(capturaUrl.value)
    capturaUrl.value = null
    status.value = await $fetch<Status>('/api/dian/citas/start', { method: 'POST' })
    toast.info('Buscando cita', 'Se abrirá una ventana del navegador; puedes minimizarla, pero no la cierres.')
  } catch (e) {
    toast.error('No se pudo iniciar la búsqueda', String(e))
  } finally {
    busy.value = false
  }
}

async function detener() {
  if (encontrado.value && !confirm('Se cerrará la ventana del navegador. ¿Ya terminaste la reserva?')) return
  busy.value = true
  try {
    status.value = await $fetch<Status>('/api/dian/citas/stop', { method: 'POST' })
  } catch (e) {
    toast.error('No se pudo detener', String(e))
  } finally {
    busy.value = false
  }
}

let poll: ReturnType<typeof setInterval> | undefined
let reloj: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  refrescar()
  poll = setInterval(refrescar, POLL_MS)
  reloj = setInterval(() => { ahora.value = Date.now() }, 1000)
})
onBeforeUnmount(() => {
  clearInterval(poll)
  clearInterval(reloj)
  if (capturaUrl.value) URL.revokeObjectURL(capturaUrl.value)
})
</script>

<template>
  <div class="mx-auto flex w-full max-w-5xl flex-col gap-4">
    <NuxtLink to="/consulta-dian" class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
      <ArrowLeft class="size-3.5" /> Consultas DIAN
    </NuxtLink>

    <div>
      <h1 class="font-heading text-2xl font-medium tracking-tight">Consulta DIAN · Citas</h1>
      <p class="text-sm text-muted-foreground">
        Busca cita en el portal de agendamiento de la DIAN cada 1–2 minutos, hasta encontrar cupo.
        Cuando aparece el trámite de Medellín, lo elige, toma el primer día disponible, se detiene en la
        pantalla siguiente y te avisa para que termines la reserva. No resuelve CAPTCHAs: si aparece uno, te avisa.
      </p>
    </div>

    <Card>
      <CardContent class="flex flex-col gap-4">
        <div class="flex flex-wrap gap-2 text-xs">
          <span v-for="c in ['Persona natural', 'Videoatención', 'Devoluciones', 'Solo Medellín']" :key="c" class="rounded-full bg-muted px-2.5 py-1 text-muted-foreground">
            {{ c }}
          </span>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <Button v-if="!status?.activo" size="lg" :disabled="busy || !!errorServicio" @click="buscar">
            <CalendarSearch class="size-4" /> Buscar cita
          </Button>
          <Button v-else size="lg" variant="secondary" :disabled="busy" @click="detener">
            <Square class="size-4" /> Detener
          </Button>
          <span class="inline-flex rounded-full px-3 py-1 text-sm font-medium" :class="estadoClase">
            {{ estadoTexto }}
          </span>
        </div>

        <p v-if="status && status.intentos" class="text-sm text-muted-foreground">
          {{ status.intentos }} revisión{{ status.intentos === 1 ? '' : 'es' }} · {{ status.sin_cupo }} sin cupo
          <template v-if="status.ultima_revision"> · última a las {{ hora(status.ultima_revision) }}</template>
        </p>
        <p v-if="errorServicio" class="text-sm text-status-error">
          No pude conectar con el servicio DIAN: {{ errorServicio }}
        </p>
      </CardContent>
    </Card>

    <Card v-if="encontrado || capturaUrl" :class="encontrado ? 'border-status-success' : ''">
      <CardContent class="flex flex-col gap-3">
        <p class="font-medium" :class="status?.estado === 'captcha' ? 'text-status-warning' : 'text-status-success'">
          {{ status?.estado === 'captcha' ? 'El portal pidió un CAPTCHA' : 'Pantalla donde encontró cupo' }}
        </p>
        <p class="text-sm text-muted-foreground">
          La ventana del navegador quedó abierta en esta pantalla: termina la reserva ahí y luego pulsa <strong>Detener</strong>.
        </p>
        <p v-if="status?.detalle" class="text-sm font-medium">{{ status.detalle }}</p>
        <pre v-if="status?.pantalla" class="max-h-60 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">{{ status.pantalla }}</pre>
        <img v-if="capturaUrl" :src="capturaUrl" alt="Captura del portal de la DIAN" class="rounded-md border border-border">
      </CardContent>
    </Card>

    <Card v-if="logReciente.length">
      <CardContent class="p-0">
        <div class="max-h-[40vh] overflow-auto">
          <ul class="divide-y divide-border/60 text-sm">
            <li v-for="(l, i) in logReciente" :key="i" class="flex gap-3 px-3 py-1.5">
              <span class="font-mono tabular-nums text-muted-foreground">{{ hora(l.t) }}</span>
              <span :class="nivelClase(l.nivel)">{{ l.msg }}</span>
            </li>
          </ul>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
