<script setup lang="ts">
import { ArrowLeft, CalendarCheck, CalendarSearch, Pencil, Play, RotateCcw, Square, Trash2, UserPlus } from 'lucide-vue-next'

type Estado = 'detenido' | 'iniciando' | 'revisando' | 'esperando' | 'hay_cupo' | 'captcha'
type LogLine = { t: string; nivel: 'info' | 'warn' | 'error' | 'ok'; msg: string }
type Status = {
  activo: boolean
  estado: Estado
  pausado: boolean
  intentos: number
  sin_cupo: number
  ultima_revision: string | null
  proxima_revision: string | null
  espera_s: [number, number]
  pantalla: string | null
  detalle: string | null
  persona: { id: number; cedula: string; nombre: string | null } | null
  hay_captura: boolean
  log: LogLine[]
}
type EstadoPersona = 'pendiente' | 'en_curso' | 'agendada'
type Persona = {
  id: number
  cedula: string
  nombre: string | null
  correo: string | null
  celular: string | null
  autoriza_tratamiento: boolean
  estado: EstadoPersona
  detalle: string | null
  agendada_at: string | null
}
type Formulario = { id: number | null; cedula: string; nombre: string; correo: string; celular: string; autoriza_tratamiento: boolean }

const POLL_MS = 3000

const toast = useToast()
const status = ref<Status | null>(null)
const busy = ref(false)
const errorServicio = ref<string | null>(null)
const capturaUrl = ref<string | null>(null)
const ahora = ref(Date.now())

const personas = ref<Persona[]>([])
const vacio = (): Formulario => ({ id: null, cedula: '', nombre: '', correo: '', celular: '', autoriza_tratamiento: false })
const form = ref<Formulario>(vacio())
const guardando = ref(false)

const pendientes = computed(() => personas.value.filter(p => p.estado === 'pendiente').length)
const enCurso = computed(() => personas.value.filter(p => p.estado === 'en_curso').length)
const agendadas = computed(() => personas.value.filter(p => p.estado === 'agendada').length)
const personaActual = computed(() => personas.value.find(p => p.id === status.value?.persona?.id) ?? null)

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
    case 'hay_cupo': return '¡Hay cupo! En pausa: termina la reserva en la ventana del navegador'
    case 'captcha': return 'El portal pidió un CAPTCHA. En pausa: termínalo tú en la ventana del navegador'
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

function personaBadge(e: EstadoPersona) {
  if (e === 'agendada') return 'bg-status-success-bg text-status-success'
  if (e === 'en_curso') return 'bg-status-warning-bg text-status-warning'
  return 'bg-muted text-muted-foreground'
}
const personaLabel = (e: EstadoPersona) => (e === 'agendada' ? 'Agendada' : e === 'en_curso' ? 'En curso' : 'Pendiente')

const hora = (iso: string) => new Date(iso).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

// ─── personas ───────────────────────────────────────────────────────────────

async function cargarPersonas() {
  try {
    personas.value = await rpc<Persona[]>('citas_list')
  } catch (e) {
    toast.error('No se pudo leer la lista de personas', String(e))
  }
}

async function guardarPersona() {
  if (!form.value.cedula.trim()) { toast.warn('La cédula es obligatoria'); return }
  guardando.value = true
  try {
    const { id, ...resto } = form.value
    await rpc<Persona>('citas_save_persona', { persona: id ? { id, ...resto } : resto })
    toast.success(id ? 'Persona actualizada' : 'Persona agregada a la lista')
    form.value = vacio()
    await cargarPersonas()
  } catch (e) {
    toast.error('No se pudo guardar', String(e))
  } finally {
    guardando.value = false
  }
}

function editar(p: Persona) {
  form.value = { id: p.id, cedula: p.cedula, nombre: p.nombre ?? '', correo: p.correo ?? '', celular: p.celular ?? '', autoriza_tratamiento: p.autoriza_tratamiento }
}

async function borrar(p: Persona) {
  if (!confirm(`¿Quitar a ${p.nombre || p.cedula} de la lista?`)) return
  try {
    await rpc('citas_delete_persona', { id: p.id })
    await cargarPersonas()
  } catch (e) {
    toast.error('No se pudo quitar', String(e))
  }
}

async function cambiarEstado(p: Persona, estado: EstadoPersona) {
  try {
    await rpc<Persona>('citas_set_estado', { id: p.id, estado })
    if (estado === 'agendada') toast.success(`${p.nombre || p.cedula}: agendada`, status.value?.activo ? 'El bot sigue con la siguiente persona.' : undefined)
    await cargarPersonas()
  } catch (e) {
    toast.error('No se pudo cambiar el estado', String(e))
  }
}

// ─── bot ────────────────────────────────────────────────────────────────────

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
    if (!s.hay_captura && capturaUrl.value) { URL.revokeObjectURL(capturaUrl.value); capturaUrl.value = null }
  } catch (e) {
    errorServicio.value = String(e)
  }
  // El bot cambia estados en contab.db (pendiente → en curso); la tabla se mantiene al día.
  await cargarPersonas()
}

async function buscar() {
  busy.value = true
  try {
    if (capturaUrl.value) URL.revokeObjectURL(capturaUrl.value)
    capturaUrl.value = null
    status.value = await $fetch<Status>('/api/dian/citas/start', { method: 'POST' })
    toast.info('Buscando citas', 'Se abrirá una ventana del navegador; puedes minimizarla, pero no la cierres.')
  } catch (e) {
    toast.error('No se pudo iniciar la búsqueda', String(e))
  } finally {
    busy.value = false
  }
}

// Reanudar es un acto deliberado: mientras esté en pausa, la ventana se queda en
// la pantalla del cupo y el bot no vuelve a navegar.
async function continuar() {
  busy.value = true
  try {
    const s = await $fetch<Status & { reanudado: boolean; motivo?: string }>('/api/dian/citas/continuar', { method: 'POST' })
    status.value = s
    if (s.reanudado) toast.success('Sigo buscando', 'La búsqueda se reanudó.')
    else toast.error('No se reanudó', s.motivo || 'La búsqueda no estaba en pausa.')
  } catch (e) {
    toast.error('No se pudo reanudar', String(e))
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
        Agrega a las personas que necesitan cita de devoluciones y pulsa <strong>Buscar citas</strong>. El bot revisa
        el portal cada 1–2 minutos y las atiende una a una: cuando aparece el trámite de Medellín elige la fecha más
        cercana y la primera hora, llena la cédula (si la persona autorizó el tratamiento de datos) y se detiene para
        que termines. Al marcarla como <strong>agendada</strong>, sigue con la siguiente. No resuelve CAPTCHAs.
      </p>
    </div>

    <!-- Personas -->
    <Card>
      <CardContent class="flex flex-col gap-4">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <p class="font-medium">Personas</p>
          <p class="text-sm text-muted-foreground">
            {{ pendientes }} pendiente{{ pendientes === 1 ? '' : 's' }} ·
            <span :class="enCurso ? 'text-status-warning' : ''">{{ enCurso }} en curso</span> ·
            <span class="text-status-success">{{ agendadas }} agendada{{ agendadas === 1 ? '' : 's' }}</span>
          </p>
        </div>

        <form class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" @submit.prevent="guardarPersona">
          <label class="flex flex-col gap-1 text-sm">Cédula *
            <Input v-model="form.cedula" inputmode="numeric" placeholder="Solo números" />
          </label>
          <label class="flex flex-col gap-1 text-sm">Nombre
            <Input v-model="form.nombre" />
          </label>
          <label class="flex flex-col gap-1 text-sm">Correo
            <Input v-model="form.correo" type="email" />
          </label>
          <label class="flex flex-col gap-1 text-sm">Celular
            <Input v-model="form.celular" inputmode="tel" />
          </label>
          <label class="flex items-start gap-2 text-sm sm:col-span-2 lg:col-span-3">
            <input v-model="form.autoriza_tratamiento" type="checkbox" class="mt-0.5 size-4 accent-primary">
            <span>Esta persona autorizó el tratamiento de sus datos personales ante la DIAN (el bot lo aceptará en su nombre).</span>
          </label>
          <div class="flex gap-2 lg:justify-end">
            <Button type="submit" :disabled="guardando">
              <UserPlus class="size-4" /> {{ form.id ? 'Guardar cambios' : 'Agregar' }}
            </Button>
            <Button v-if="form.id" type="button" variant="ghost" @click="form = vacio()">Cancelar</Button>
          </div>
        </form>

        <div v-if="personas.length" class="max-h-[40vh] overflow-auto border-t border-border">
          <table class="w-full text-sm">
            <thead class="sticky top-0 bg-card">
              <tr class="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th class="px-3 py-2 font-medium">Cédula</th>
                <th class="px-3 py-2 font-medium">Nombre</th>
                <th class="px-3 py-2 font-medium">Estado</th>
                <th class="px-3 py-2 font-medium">Detalle</th>
                <th class="px-3 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in personas" :key="p.id" class="border-b border-border/60 last:border-0" :class="p.id === status?.persona?.id && status?.activo ? 'bg-primary/5' : ''">
                <td class="px-3 py-1.5 font-mono tabular-nums">{{ p.cedula }}</td>
                <td class="px-3 py-1.5">
                  {{ p.nombre || '—' }}
                  <span v-if="!p.autoriza_tratamiento" class="block text-xs text-muted-foreground">sin autorización de datos</span>
                </td>
                <td class="px-3 py-1.5">
                  <span class="inline-flex rounded-full px-2 py-0.5 text-xs font-medium" :class="personaBadge(p.estado)">{{ personaLabel(p.estado) }}</span>
                </td>
                <td class="max-w-xs px-3 py-1.5 text-xs text-muted-foreground">{{ p.detalle || '—' }}</td>
                <td class="whitespace-nowrap px-3 py-1.5 text-right">
                  <Button v-if="p.estado !== 'agendada'" size="sm" variant="ghost" title="Marcar agendada" @click="cambiarEstado(p, 'agendada')"><CalendarCheck class="size-4" /></Button>
                  <Button v-if="p.estado !== 'pendiente'" size="sm" variant="ghost" title="Volver a pendiente" @click="cambiarEstado(p, 'pendiente')"><RotateCcw class="size-4" /></Button>
                  <Button size="sm" variant="ghost" title="Editar" @click="editar(p)"><Pencil class="size-4" /></Button>
                  <Button size="sm" variant="ghost" title="Quitar" @click="borrar(p)"><Trash2 class="size-4" /></Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>

    <!-- Bot -->
    <Card>
      <CardContent class="flex flex-col gap-4">
        <div class="flex flex-wrap gap-2 text-xs">
          <span v-for="c in ['Persona natural', 'Videoatención', 'Devoluciones', 'Solo Medellín']" :key="c" class="rounded-full bg-muted px-2.5 py-1 text-muted-foreground">
            {{ c }}
          </span>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <Button v-if="!status?.activo" size="lg" :disabled="busy || !!errorServicio || !pendientes" @click="buscar">
            <CalendarSearch class="size-4" /> Buscar citas
          </Button>
          <Button v-else size="lg" variant="secondary" :disabled="busy" @click="detener">
            <Square class="size-4" /> Detener
          </Button>
          <span class="inline-flex rounded-full px-3 py-1 text-sm font-medium" :class="estadoClase">
            {{ estadoTexto }}
          </span>
        </div>
        <p v-if="!status?.activo && !pendientes" class="text-sm text-muted-foreground">Agrega al menos una persona pendiente para buscar.</p>

        <p v-if="status?.activo && status.persona" class="text-sm">
          Buscando para <strong>{{ status.persona.nombre || 'sin nombre' }}</strong> (CC {{ status.persona.cedula }})
        </p>
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
          <strong class="text-foreground">La búsqueda está detenida</strong> y la ventana del navegador se queda
          justo en esta pantalla: haz ahí el trámite con calma. El bot no vuelve a navegar hasta que tú se lo digas.
        </p>
        <p v-if="status?.detalle" class="text-sm font-medium">{{ status.detalle }}</p>

        <div class="flex flex-wrap gap-2">
          <Button v-if="personaActual && personaActual.estado === 'en_curso'" @click="cambiarEstado(personaActual, 'agendada')">
            <CalendarCheck class="size-4" /> Marcar agendada y seguir
          </Button>
          <Button :disabled="busy || !status?.pausado" variant="secondary" @click="continuar">
            <Play class="size-4" /> Continuar buscando
          </Button>
          <Button v-if="personaActual && personaActual.estado === 'en_curso'" variant="ghost" @click="cambiarEstado(personaActual, 'pendiente')">
            <RotateCcw class="size-4" /> No se pudo: volver a pendiente
          </Button>
        </div>
        <p class="text-xs text-muted-foreground">
          «Continuar» reanuda la búsqueda sin tocar a la persona; «Marcar agendada» la cierra y sigue con la
          siguiente. Si no pulsas ninguno, el bot se queda quieto — que es lo que debe hacer.
        </p>
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
