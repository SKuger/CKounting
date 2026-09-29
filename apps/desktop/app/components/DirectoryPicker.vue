<script setup lang="ts">
import { ArrowUp, House, Folder, Check, X } from 'lucide-vue-next'

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
  <!-- Panel, no ventana superpuesta (norma 2026-09-28). Quien lo usa decide dónde
       ponerlo; el componente solo se dibuja cuando `open` es verdadero. -->
  <section v-if="open" class="flex max-h-[60vh] flex-col overflow-hidden rounded-lg border border-primary/40 bg-card">
    <div class="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-2.5">
      <h2 class="text-sm font-semibold">{{ title }}</h2>
      <Button variant="ghost" size="icon-sm" aria-label="Cerrar" @click="emit('close')"><X class="size-4" /></Button>
    </div>

    <div class="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2">
      <Button variant="secondary" size="sm" :disabled="!parent" @click="goParent"><ArrowUp class="size-4" /> Subir</Button>
      <Button variant="secondary" size="sm" @click="goHome"><House class="size-4" /> Inicio</Button>
      <label class="flex cursor-pointer items-center gap-1.5 text-sm text-muted-foreground">
        <input v-model="showHidden" type="checkbox" class="size-3.5 accent-primary"> Ocultas
      </label>
    </div>

    <div class="flex shrink-0 flex-wrap items-center gap-1 border-b border-border px-4 py-2 text-xs">
      <template v-for="(c, i) in breadcrumbs" :key="i">
        <button type="button" class="rounded px-1.5 py-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground" @click="loadPath(c.path)">{{ c.label || 'raíz' }}</button>
        <span v-if="i < breadcrumbs.length - 1" class="text-muted-foreground">{{ separator }}</span>
      </template>
    </div>

    <div class="min-h-0 flex-1 overflow-auto px-3 py-2">
      <p v-if="loading" class="px-1 py-2 text-sm text-muted-foreground">Cargando…</p>
      <div v-else-if="errorMsg" class="rounded-md border border-status-error/30 bg-status-error-bg px-3 py-2 text-sm text-status-error">{{ errorMsg }}</div>
      <p v-else-if="!entries.length" class="px-1 py-2 text-sm text-muted-foreground">Sin subcarpetas.</p>
      <ul v-else class="grid gap-0.5 sm:grid-cols-2 lg:grid-cols-3">
        <li
          v-for="e in entries"
          :key="e.name"
          class="flex cursor-pointer select-none items-center gap-2 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-accent"
          @dblclick="enter(e.name)"
          @click="enter(e.name)"
        >
          <Folder class="size-4 shrink-0 text-muted-foreground" /> <span class="truncate">{{ e.name }}</span>
        </li>
      </ul>
    </div>

    <div class="flex shrink-0 flex-wrap items-center gap-2 border-t border-border px-4 py-2.5">
      <div class="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">{{ currentPath || '—' }}</div>
      <Button variant="secondary" size="sm" @click="emit('close')">Cancelar</Button>
      <Button size="sm" :disabled="!currentPath" @click="pick"><Check class="size-4" /> Seleccionar esta carpeta</Button>
    </div>
  </section>
</template>
