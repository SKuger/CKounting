<script setup lang="ts">
import { ArrowLeft, Copy, Download, UploadCloud } from 'lucide-vue-next'

type LogEntry = { type: string; msg: string; time: string }
type ServerData = { message?: string; percent?: number; download_url?: string; trace?: string }

// Comando verbatim del original para lanzar Chrome en modo dev (CDP :9222).
const CHROME_CMD = 'google-chrome --remote-debugging-port=9222 --user-data-dir=$HOME/chrome-dian-profile'

const file = ref<File | null>(null)
const dragging = ref(false)
const running = ref(false)
const finished = ref(false)
const percent = ref(0)
const statusMsg = ref('')
const logs = ref<LogEntry[]>([])
const fileId = ref<string | null>(null)
const downloadUrl = ref<string | null>(null)
const browserMode = ref<'unknown' | 'human' | 'auto'>('unknown')
const checking = ref(false)
const copied = ref(false)
const logBox = ref<HTMLElement | null>(null)

let ws: WebSocket | null = null

const partialUrl = computed(() => (fileId.value ? `/api/dian/download/current/${fileId.value}` : null))

const verifyLabel = computed(() => {
  if (checking.value) return 'Verificando…'
  if (browserMode.value === 'human') return '✓ Conectado a Chrome real'
  if (browserMode.value === 'auto') return '🔄 Reintentar conexión'
  return '🔍 Verificar conexión'
})

const modeBadgeClass = computed(() =>
  browserMode.value === 'human'
    ? 'bg-status-success-bg text-status-success'
    : browserMode.value === 'auto'
      ? 'bg-status-error-bg text-status-error'
      : 'bg-muted text-muted-foreground',
)

function logClass(type: string): string {
  if (type === 'error') return 'text-status-error'
  if (type === 'done' || type === 'success') return 'text-status-success'
  if (type === 'progress') return 'text-muted-foreground'
  return 'text-foreground'
}

function appendLog(type: string, msg: string) {
  const time = new Date().toLocaleTimeString('es-CO', { hour12: false })
  logs.value.push({ type, msg, time })
  nextTick(() => {
    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
  })
}

// Backend emite "/download/<archivo>" → lo enrutamos por el proxy.
function rewriteDownload(url: string): string {
  return url.startsWith('/download/') ? url.replace(/^\/download\//, '/api/dian/download/') : url
}

function pickFile(files: FileList | null) {
  if (!files || !files.length) return
  const f = files[0]
  if (!f.name.toLowerCase().endsWith('.xlsx')) {
    appendLog('error', 'Solo se permiten archivos Excel (.xlsx).')
    return
  }
  file.value = f
}

function onDrop(e: DragEvent) {
  dragging.value = false
  pickFile(e.dataTransfer?.files ?? null)
}

async function checkBrowserMode() {
  checking.value = true
  try {
    const r = await $fetch<{ status: string }>('/api/dian/browser-status')
    browserMode.value = r.status === 'human_connected' ? 'human' : 'auto'
  } catch {
    browserMode.value = 'auto'
  } finally {
    checking.value = false
  }
}

async function copyCommand() {
  try {
    await navigator.clipboard.writeText(CHROME_CMD)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    /* clipboard no disponible */
  }
}

function openWs(port: number, clientId: string): Promise<void> {
  return new Promise((resolveOpen) => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${proto}//${window.location.hostname}:${port}/ws/${clientId}`)
    ws.onopen = () => {
      appendLog('info', 'Conexión establecida con el servicio DIAN.')
      resolveOpen()
    }
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data) as { type: string; data: ServerData }
      handleMsg(m.type, m.data)
    }
    ws.onerror = () => appendLog('error', 'Error en la conexión con el servicio DIAN.')
    // No bloquear el upload indefinidamente si onopen tarda.
    setTimeout(resolveOpen, 4000)
  })
}

function handleMsg(type: string, data: ServerData) {
  if (data?.message) {
    appendLog(type, data.message)
    statusMsg.value = data.message
  }
  if (type === 'progress' && data?.percent !== undefined) percent.value = data.percent
  if (type === 'error') running.value = false
  if (type === 'done') {
    percent.value = 100
    finished.value = true
    running.value = false
    if (data?.download_url) downloadUrl.value = rewriteDownload(data.download_url)
    ws?.close()
  }
}

async function start() {
  if (!file.value || running.value) return
  running.value = true
  finished.value = false
  percent.value = 0
  logs.value = []
  downloadUrl.value = null
  fileId.value = null
  statusMsg.value = 'Iniciando…'

  let port: number
  try {
    const s = await $fetch<{ ok: boolean; port: number; error?: string }>('/api/dian/session')
    if (!s.ok) throw new Error(s.error || 'servicio no disponible')
    port = s.port
  } catch (e) {
    appendLog('error', 'No se pudo iniciar el servicio DIAN: ' + String(e))
    running.value = false
    return
  }

  const clientId = crypto.randomUUID()
  await openWs(port, clientId)

  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('client_id', clientId)
  try {
    const res = await fetch('/api/dian/upload', { method: 'POST', body: fd })
    const data = await res.json()
    if (!res.ok) {
      appendLog('error', data.error || 'Error al subir el archivo.')
      statusMsg.value = 'Error'
      running.value = false
      ws?.close()
      return
    }
    if (data.file_id) fileId.value = data.file_id
  } catch {
    appendLog('error', 'Error de red al intentar subir el archivo.')
    running.value = false
    ws?.close()
  }
}

function reset() {
  ws?.close()
  ws = null
  file.value = null
  running.value = false
  finished.value = false
  percent.value = 0
  logs.value = []
  downloadUrl.value = null
  fileId.value = null
  statusMsg.value = ''
}

onMounted(checkBrowserMode)
onBeforeUnmount(() => ws?.close())
</script>

<template>
  <div class="mx-auto flex w-full max-w-5xl flex-col">
    <NuxtLink to="/" class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
      <ArrowLeft class="size-3.5" /> Empresas
    </NuxtLink>

    <div>
      <h1 class="font-heading text-2xl font-medium tracking-tight">Consulta DIAN · Terceros</h1>
      <p class="text-sm text-muted-foreground">
        Sube un Excel con la columna <span class="font-mono">NIT</span> y consulta el RUT de cada tercero
        en el portal de la DIAN. El resultado se descarga como Excel con los datos combinados.
      </p>
    </div>

    <!-- instrucciones (modo) | acción (carga/progreso) -->
    <div class="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
    <!-- Modo Navegador Humano (CDP :9222) -->
    <details class="overflow-hidden rounded-lg border border-border bg-card" :open="browserMode !== 'human'">
      <summary class="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 select-none [&::-webkit-details-marker]:hidden">
        <span class="font-medium">Modo Navegador Humano</span>
        <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="modeBadgeClass">
          {{ browserMode === 'human' ? '🟢 Conectado a Chrome real' : browserMode === 'auto' ? '🔴 Modo Automático' : '○ verificando…' }}
        </span>
      </summary>

      <div class="border-t border-border px-4 pb-4 pt-3">
        <p class="text-sm text-muted-foreground">
          Conecta tu navegador Chrome real para evadir los bloqueos de Cloudflare con un 100 % de efectividad.
          El scraper se "pega" a tu Chrome por el puerto de depuración (9222) y reutiliza tu sesión de la DIAN.
        </p>

        <ol class="my-3 flex list-decimal flex-col gap-2 pl-5 text-sm">
          <li>Abre la aplicación <strong>"Terminal"</strong> o <strong>"Consola"</strong> de tu computador.</li>
          <li>
            Copia y pega este comando, y presiona <strong>ENTER</strong>:
            <div class="mt-1.5 flex items-stretch gap-2">
              <code class="flex-1 overflow-x-auto whitespace-nowrap rounded-md border border-border bg-muted px-2.5 py-2 font-mono text-xs">{{ CHROME_CMD }}</code>
              <Button variant="ghost" size="sm" type="button" @click="copyCommand">
                <Copy class="size-3.5" /> {{ copied ? '¡Copiado!' : 'Copiar' }}
              </Button>
            </div>
          </li>
          <li>Se abrirá Chrome. Entra a la página de la <strong>DIAN</strong> allí, resuelve el "Soy humano" y déjala abierta.</li>
          <li>Haz clic en <strong>"Verificar conexión"</strong>.</li>
        </ol>

        <Button variant="secondary" type="button" :disabled="checking" @click="checkBrowserMode">
          {{ verifyLabel }}
        </Button>
      </div>
    </details>

    <!-- Paso 1: cargar archivo -->
    <Card v-if="!running && !finished">
      <CardContent class="flex flex-col gap-4">
        <div
          class="flex flex-col items-center gap-2 rounded-lg border-[1.5px] border-dashed px-4 py-5 text-center transition-colors"
          :class="dragging ? 'border-primary bg-primary/5' : 'border-input'"
          @dragenter.prevent="dragging = true"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <UploadCloud class="size-6 text-muted-foreground" />
          <p v-if="file">Archivo cargado: <span class="font-mono">{{ file.name }}</span></p>
          <p v-else class="text-muted-foreground">Arrastra aquí tu Excel <span class="font-mono">.xlsx</span> o selecciónalo</p>
          <Button as-child variant="outline" size="sm">
            <label class="cursor-pointer">
              Elegir archivo
              <input type="file" accept=".xlsx" hidden @change="pickFile(($event.target as HTMLInputElement).files)">
            </label>
          </Button>
        </div>
        <div class="flex items-center gap-3">
          <Button :disabled="!file" @click="start">Consultar terceros</Button>
          <a class="text-sm text-muted-foreground hover:text-foreground hover:underline" href="/api/dian/template" download>Descargar plantilla</a>
        </div>
      </CardContent>
    </Card>

    <!-- Paso 2/3: progreso + resultado -->
    <Card v-else>
      <CardContent class="flex flex-col gap-3">
        <div class="flex items-center gap-3">
          <div class="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div class="h-full bg-primary transition-[width] duration-300" :style="{ width: percent + '%' }" />
          </div>
          <span class="font-mono text-sm">{{ percent }}%</span>
        </div>
        <p class="text-sm" :class="finished ? 'text-status-success' : 'text-muted-foreground'">{{ statusMsg }}</p>

        <div ref="logBox" class="h-60 overflow-auto rounded-md border border-border bg-muted px-3 py-2.5 font-mono text-xs leading-relaxed">
          <div v-for="(l, i) in logs" :key="i" class="whitespace-pre-wrap break-words" :class="logClass(l.type)">
            <span class="text-muted-foreground">[{{ l.time }}]</span> {{ l.msg }}
          </div>
        </div>

        <div class="flex items-center gap-3">
          <Button v-if="downloadUrl" as-child>
            <a :href="downloadUrl" download><Download class="size-4" /> Descargar resultado</a>
          </Button>
          <Button v-else-if="partialUrl" as-child variant="secondary">
            <a :href="partialUrl" download><Download class="size-4" /> Descargar avance parcial</a>
          </Button>
          <Button v-if="finished" variant="ghost" @click="reset">Nueva consulta</Button>
          <Button v-else-if="!running" variant="ghost" @click="reset">Cancelar</Button>
        </div>
      </CardContent>
    </Card>
    </div>
  </div>
</template>
