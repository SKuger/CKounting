<script setup lang="ts">
import { ArrowLeft, Copy, Download, Globe, UploadCloud } from 'lucide-vue-next'

type LogEntry = { type: string; msg: string; time: string }
type ServerData = { message?: string; percent?: number; download_url?: string; trace?: string }

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
const launching = ref(false)
const launchMsg = ref('')
const copied = ref(false)
const logBox = ref<HTMLElement | null>(null)

let ws: WebSocket | null = null

const partialUrl = computed(() => (fileId.value ? `/api/dian/download/current/${fileId.value}` : null))

const verifyLabel = computed(() => {
  if (checking.value) return 'Verificando…'
  if (browserMode.value === 'human') return '✓ Conectado'
  if (browserMode.value === 'auto') return 'Verificar conexión'
  return 'Verificar conexión'
})

const modeBadgeClass = computed(() =>
  browserMode.value === 'human'
    ? 'bg-status-success-bg text-status-success'
    : browserMode.value === 'auto'
      ? 'bg-status-error-bg text-status-error'
      : 'bg-muted text-muted-foreground',
)

// Comando manual por SO — solo "ayuda avanzada" para quien prefiera hacerlo a mano.
const clientOS = computed<'win' | 'mac' | 'linux' | 'other'>(() => {
  if (!import.meta.client) return 'other'
  const ua = navigator.userAgent
  if (/Windows/i.test(ua)) return 'win'
  if (/Macintosh|Mac OS/i.test(ua)) return 'mac'
  if (/Linux|X11/i.test(ua)) return 'linux'
  return 'other'
})
const manualCommand = computed(() => {
  if (clientOS.value === 'win') return 'chrome.exe --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\\chrome-dian-profile"'
  if (clientOS.value === 'mac') return '"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-dian-profile"'
  return 'google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-dian-profile"'
})

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

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

function browserLabel(b?: string): string {
  if (b === 'edge') return 'Microsoft Edge'
  if (b === 'chromium') return 'Chromium'
  return 'Google Chrome'
}

// El log vive dentro de un <details> colapsado: al abrirlo, saltar al final.
function onLogToggle(e: Event) {
  if ((e.target as HTMLDetailsElement).open) {
    nextTick(() => { if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight })
  }
}

async function pollUntilConnected(maxTries = 15): Promise<boolean> {
  for (let i = 0; i < maxTries; i++) {
    await checkBrowserMode()
    if (browserMode.value === 'human') return true
    await sleep(1500)
  }
  return browserMode.value === 'human'
}

// Abre un Chrome/Edge dedicado en modo depuración, sin terminal.
async function launchBrowser() {
  if (launching.value) return
  launching.value = true
  launchMsg.value = 'Abriendo el navegador…'
  try {
    const r = await $fetch<{ status: string; browser?: string }>('/api/dian/launch-browser', { method: 'POST' })
    if (r.status === 'not_found') {
      launchMsg.value = 'No encontramos Google Chrome ni Microsoft Edge instalado. Instala Chrome, o usa la ayuda avanzada de abajo.'
      return
    }
    launchMsg.value = r.status === 'already_running'
      ? 'El navegador ya estaba abierto. Verificando conexión…'
      : `Abrimos ${browserLabel(r.browser)}. Entra a la página de la DIAN y resuelve el "Soy humano" si aparece.`
    const ok = await pollUntilConnected()
    if (ok) launchMsg.value = '✓ Conectado. Ya puedes consultar los terceros.'
    else launchMsg.value = 'Si el navegador se abrió, espera un momento y pulsa "Verificar conexión".'
  } catch {
    launchMsg.value = 'No se pudo abrir el navegador automáticamente. Usa la ayuda avanzada de abajo.'
  } finally {
    launching.value = false
  }
}

async function copyCommand() {
  try {
    await navigator.clipboard.writeText(manualCommand.value)
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
  <div class="mx-auto flex w-full max-w-5xl flex-col gap-4">
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

    <!-- instrucciones (navegador) | acción (carga/progreso) -->
    <div class="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
      <!-- Navegador para la DIAN (abre Chrome en modo depuración, sin terminal) -->
      <div class="overflow-hidden rounded-lg border border-border bg-card">
        <div class="flex items-center justify-between gap-4 border-b border-border px-4 py-3">
          <span class="font-medium">Navegador para la DIAN</span>
          <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="modeBadgeClass">
            {{ browserMode === 'human' ? '🟢 Conectado' : browserMode === 'auto' ? '🔴 Sin conectar' : '○ verificando…' }}
          </span>
        </div>

        <div class="flex flex-col gap-3 px-4 pb-4 pt-3">
          <p class="text-sm text-muted-foreground">
            Para consultar la DIAN con la máxima efectividad, Contab abre un navegador dedicado.
            Pulsa el botón, entra a la página de la DIAN y resuelve el <strong>"Soy humano"</strong> si aparece.
            No necesitas escribir nada en ninguna consola.
          </p>

          <div class="flex flex-wrap items-center gap-2">
            <Button data-tour="dian-abrir" :disabled="launching || browserMode === 'human'" @click="launchBrowser">
              <Globe class="size-4" /> {{ launching ? 'Abriendo…' : 'Abrir navegador para la DIAN' }}
            </Button>
            <Button data-tour="dian-verificar" variant="secondary" type="button" :disabled="checking" @click="checkBrowserMode">
              {{ verifyLabel }}
            </Button>
          </div>

          <p v-if="launchMsg" class="text-sm" :class="browserMode === 'human' ? 'text-status-success' : 'text-muted-foreground'">
            {{ launchMsg }}
          </p>

          <details class="text-sm">
            <summary class="cursor-pointer select-none text-muted-foreground transition-colors hover:text-foreground">
              Ayuda avanzada (abrir el navegador manualmente)
            </summary>
            <div class="mt-2 flex flex-col gap-1.5">
              <p class="text-xs text-muted-foreground">Si el botón no funciona, abre una terminal/consola y ejecuta:</p>
              <div class="flex items-stretch gap-2">
                <code class="flex-1 overflow-x-auto whitespace-nowrap rounded-md border border-border bg-muted px-2.5 py-2 font-mono text-xs">{{ manualCommand }}</code>
                <Button variant="ghost" size="sm" type="button" @click="copyCommand">
                  <Copy class="size-3.5" /> {{ copied ? '¡Copiado!' : 'Copiar' }}
                </Button>
              </div>
            </div>
          </details>
        </div>
      </div>

      <!-- Paso 1: cargar archivo -->
      <Card v-if="!running && !finished">
        <CardContent class="flex flex-col gap-4">
          <div
            data-tour="dian-archivo"
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
            <Button data-tour="dian-consultar" :disabled="!file" @click="start">Consultar terceros</Button>
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

          <details @toggle="onLogToggle">
            <summary class="cursor-pointer select-none text-xs text-muted-foreground transition-colors hover:text-foreground">
              Ver detalle técnico
            </summary>
            <div ref="logBox" class="mt-1.5 h-52 overflow-auto rounded-md border border-border bg-muted px-3 py-2.5 font-mono text-xs leading-relaxed">
              <div v-for="(l, i) in logs" :key="i" class="whitespace-pre-wrap break-words" :class="logClass(l.type)">
                <span class="text-muted-foreground">[{{ l.time }}]</span> {{ l.msg }}
              </div>
            </div>
          </details>

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
