<script setup lang="ts">
type DirEntry = { name: string; is_dir: true }
type DirResponse = {
  ok: boolean
  path: string
  parent: string | null
  separator: string
  home: string
  entries: DirEntry[]
  error?: string
}

const props = withDefaults(defineProps<{
  open: boolean
  initialPath?: string
  title?: string
}>(), {
  title: 'Elegir carpeta',
})

const emit = defineEmits<{
  pick: [path: string]
  close: []
}>()

const currentPath = ref('')
const parent = ref<string | null>(null)
const separator = ref('/')
const home = ref('')
const entries = ref<DirEntry[]>([])
const loading = ref(false)
const errorMsg = ref('')
const showHidden = ref(false)

async function loadPath(target: string) {
  loading.value = true
  errorMsg.value = ''
  try {
    const params = new URLSearchParams()
    if (target) params.set('path', target)
    if (showHidden.value) params.set('show_hidden', '1')
    const res = await $fetch<DirResponse>(`/api/list-dir?${params.toString()}`)
    if (!res.ok) {
      errorMsg.value = res.error || 'No se pudo leer la carpeta'
      return
    }
    currentPath.value = res.path
    parent.value = res.parent
    separator.value = res.separator
    home.value = res.home
    entries.value = res.entries
  } catch (exc) {
    errorMsg.value = String(exc)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      loadPath(props.initialPath || '')
    }
  },
  { immediate: true },
)

watch(showHidden, () => {
  if (props.open) loadPath(currentPath.value)
})

const breadcrumbs = computed(() => {
  const parts: { label: string; path: string }[] = []
  if (!currentPath.value) return parts
  const sep = separator.value
  const isWindows = sep === '\\'
  const root = isWindows
    ? (currentPath.value.match(/^[A-Z]:\\?/i)?.[0] ?? '\\')
    : '/'
  parts.push({ label: root, path: root })
  const trimmed = currentPath.value.slice(root.length)
  if (!trimmed) return parts
  const segments = trimmed.split(sep).filter(Boolean)
  let accum = root
  for (const seg of segments) {
    accum = accum.endsWith(sep) ? accum + seg : accum + sep + seg
    parts.push({ label: seg, path: accum })
  }
  return parts
})

function enter(name: string) {
  const sep = separator.value
  const base = currentPath.value.endsWith(sep)
    ? currentPath.value
    : currentPath.value + sep
  loadPath(base + name)
}

function goParent() {
  if (parent.value) loadPath(parent.value)
}

function goHome() {
  loadPath(home.value)
}

function pick() {
  emit('pick', currentPath.value)
  emit('close')
}
</script>

<template>
  <div v-if="open" class="modal-backdrop" @click.self="emit('close')">
    <div class="modal">
      <header class="modal-header">
        <h2 style="margin: 0">{{ title }}</h2>
        <button class="ghost" style="padding: 0.3rem 0.6rem" @click="emit('close')">✕</button>
      </header>

      <div class="modal-toolbar">
        <button class="secondary" :disabled="!parent" @click="goParent">↑ Subir</button>
        <button class="secondary" @click="goHome">🏠 Inicio</button>
        <label class="muted" style="display: flex; align-items: center; gap: 0.3rem">
          <input v-model="showHidden" type="checkbox" /> Ocultas
        </label>
        <span class="spacer" />
      </div>

      <div class="breadcrumbs">
        <template v-for="(c, i) in breadcrumbs" :key="i">
          <button class="ghost crumb" @click="loadPath(c.path)">{{ c.label || 'raíz' }}</button>
          <span v-if="i < breadcrumbs.length - 1" class="muted">{{ separator }}</span>
        </template>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="muted">Cargando…</div>
        <div v-else-if="errorMsg" class="alert error">{{ errorMsg }}</div>
        <div v-else-if="!entries.length" class="muted">Sin subcarpetas.</div>
        <ul v-else class="dir-list">
          <li
            v-for="e in entries"
            :key="e.name"
            class="dir-item"
            @dblclick="enter(e.name)"
            @click="enter(e.name)"
          >
            📁 {{ e.name }}
          </li>
        </ul>
      </div>

      <footer class="modal-footer">
        <div class="muted mono" style="font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis">
          {{ currentPath || '—' }}
        </div>
        <span class="spacer" />
        <button class="secondary" @click="emit('close')">Cancelar</button>
        <button :disabled="!currentPath" @click="pick">Seleccionar esta carpeta</button>
      </footer>
    </div>
  </div>
</template>
