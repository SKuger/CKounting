<script setup lang="ts">
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
const logBox = ref<HTMLElement | null>(null)

let ws: WebSocket | null = null

const partialUrl = computed(() => (fileId.value ? `/api/dian/download/current/${fileId.value}` : null))

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
  try {
    const r = await $fetch<{ status: string }>('/api/dian/browser-status')
    browserMode.value = r.status === 'human_connected' ? 'human' : 'auto'
  } catch {
    browserMode.value = 'auto'
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
  <div class="dian-page col">
    <NuxtLink to="/" class="back-link">← Empresas</NuxtLink>

    <div class="panel-head">
      <div>
        <h1>Consulta DIAN · Terceros</h1>
        <p class="muted small">
          Sube un Excel con la columna <span class="mono">NIT</span> y consulta el RUT de cada tercero
          en el portal de la DIAN. El resultado se descarga como Excel con los datos combinados.
        </p>
      </div>
      <span
        class="badge"
        :class="browserMode === 'human' ? 'ok' : browserMode === 'auto' ? 'warn' : ''"
        :title="browserMode === 'human' ? 'Conectado a un Chrome real (modo humano)' : 'Modo automático (fallback)'"
      >
        {{ browserMode === 'human' ? '● chrome real' : browserMode === 'auto' ? '● modo automático' : '○ verificando…' }}
      </span>
    </div>

    <!-- Paso 1: cargar archivo -->
    <div v-if="!running && !finished" class="card col">
      <div
        class="drop-area"
        :class="{ dragover: dragging }"
        @dragenter.prevent="dragging = true"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <p v-if="file">Archivo cargado: <span class="mono">{{ file.name }}</span></p>
        <p v-else class="muted">Arrastra aquí tu Excel <span class="mono">.xlsx</span> o selecciónalo</p>
        <label class="file-picker">
          <span class="button-like">Elegir archivo</span>
          <input type="file" accept=".xlsx" hidden @change="pickFile(($event.target as HTMLInputElement).files)" />
        </label>
      </div>
      <div class="row">
        <button :disabled="!file" @click="start">Consultar terceros</button>
        <a class="muted small" href="/api/dian/template" download>Descargar plantilla</a>
      </div>
    </div>

    <!-- Paso 2/3: progreso + resultado -->
    <div v-else class="card col">
      <div class="progress-wrap">
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: percent + '%' }" />
        </div>
        <span class="mono small">{{ percent }}%</span>
      </div>
      <p class="small" :class="finished ? 'ok-text' : 'muted'">{{ statusMsg }}</p>

      <div ref="logBox" class="log-terminal mono">
        <div v-for="(l, i) in logs" :key="i" class="log-line" :class="'log-' + l.type">
          <span class="muted">[{{ l.time }}]</span> {{ l.msg }}
        </div>
      </div>

      <div class="row">
        <a v-if="downloadUrl" class="file-picker" :href="downloadUrl" download>
          <span class="button-like">Descargar resultado</span>
        </a>
        <a v-else-if="partialUrl" :href="partialUrl" download>
          <button class="secondary" type="button">Descargar avance parcial</button>
        </a>
        <button v-if="finished" class="ghost" @click="reset">Nueva consulta</button>
        <button v-else-if="!running" class="ghost" @click="reset">Cancelar</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dian-page { max-width: 860px; }

.drop-area {
  border: 1.5px dashed var(--border-strong);
  border-radius: var(--radius);
  padding: 1.6rem 1rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.7rem;
  transition: border-color 0.15s, background 0.15s;
}
.drop-area.dragover { border-color: var(--accent); background: var(--accent-soft); }

.progress-wrap { display: flex; align-items: center; gap: 0.6rem; }
.progress-track {
  flex: 1;
  height: 8px;
  background: var(--panel-3);
  border-radius: 999px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #7480e0, var(--accent));
  transition: width 0.25s ease;
}
.ok-text { color: var(--ok); }

.log-terminal {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.6rem 0.75rem;
  height: 240px;
  overflow: auto;
  font-size: 0.75rem;
  line-height: 1.6;
}
.log-line { white-space: pre-wrap; word-break: break-word; }
.log-error { color: var(--danger); }
.log-done { color: var(--ok); }
.log-info { color: var(--text-soft); }
.log-progress { color: var(--muted); }
</style>
