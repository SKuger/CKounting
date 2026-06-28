<script setup lang="ts">
// ⌘K command palette (solar rail). Tweak #4: live filter, recents (localStorage),
// and contextual actions — "search to jump, navigate by the stars". Esc closes; Enter runs
// the first match. Opens on ⌘K / Ctrl+K or by clicking the topbar search bar.
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Search } from 'lucide-vue-next'
import { Dialog, DialogContent } from '~/components/ui/dialog'

const props = defineProps<{ nav: { label: string; to: string }[] }>()
const open = ref(false)
const query = ref('')
const inputEl = ref<HTMLInputElement | null>(null)
const router = useRouter()
const route = useRoute()
const pg = useBrand()

const RECENTS_KEY = 'dandelyon-pg-recents'
const recents = ref<string[]>([])
function loadRecents() { try { recents.value = JSON.parse(localStorage.getItem(RECENTS_KEY) ?? '[]') } catch { recents.value = [] } }

const actions = computed(() => [
  { label: 'Cambiar tema (claro / oscuro)',  run: () => pg.toggleTheme() },
  { label: 'Sistema: marcar fuera de rango', run: () => pg.setSystemStatus('out') },
  { label: 'Sistema: marcar en orden',       run: () => pg.setSystemStatus('ok') },
])

const q = computed(() => query.value.trim().toLowerCase())
const match = (s: string) => !q.value || s.toLowerCase().includes(q.value)
const pages = computed(() => props.nav.filter(p => match(p.label)))
const acts = computed(() => actions.value.filter(a => match(a.label)))
const recentPages = computed(() => (recents.value
  .map(to => props.nav.find(n => n.to === to))
  .filter(p => p && p.to !== route.path && match(p.label)) as { label: string; to: string }[]))

function onKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); open.value = !open.value }
}
onMounted(() => { window.addEventListener('keydown', onKey); loadRecents() })
onUnmounted(() => window.removeEventListener('keydown', onKey))
watch(open, async (v) => { if (v) { query.value = ''; await nextTick(); inputEl.value?.focus() } })

function go(to: string) {
  recents.value = [to, ...recents.value.filter(t => t !== to)].slice(0, 4)
  localStorage.setItem(RECENTS_KEY, JSON.stringify(recents.value))
  router.push(to); open.value = false
}
function runAction(a: { run: () => void }) { a.run(); open.value = false }
function onEnter() {
  if (pages.value[0]) go(pages.value[0].to)
  else if (acts.value[0]) runAction(acts.value[0])
}
</script>

<template>
  <button type="button" class="flex h-9 w-full max-w-sm items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 text-sm text-muted-foreground transition-colors hover:bg-accent"
    @click="open = true">
    <Search class="size-4 shrink-0" />
    <span>Buscar o navegar…</span>
    <kbd class="ml-auto rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[10px]">⌘K</kbd>
  </button>

  <Dialog v-model:open="open">
    <DialogContent class="gap-0 overflow-hidden p-0 sm:max-w-lg">
      <div class="flex items-center gap-2 border-b border-border px-3">
        <Search class="size-4 shrink-0 text-muted-foreground" />
        <input ref="inputEl" v-model="query" placeholder="Buscar o navegar…"
          class="h-11 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          @keydown.enter.prevent="onEnter" >
      </div>
      <div class="max-h-80 overflow-y-auto p-2">
        <template v-if="recentPages.length">
          <p class="px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Recientes</p>
          <button v-for="item in recentPages" :key="'r' + item.to" type="button" class="flex w-full items-center rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent"
            @click="go(item.to)">{{ item.label }}</button>
        </template>
        <p class="px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Páginas</p>
        <button v-for="item in pages" :key="item.to" type="button" class="flex w-full items-center rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent"
          @click="go(item.to)">{{ item.label }}</button>
        <p class="px-2 pb-1 pt-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Acciones</p>
        <button v-for="(a, i) in acts" :key="'a' + i" type="button" class="flex w-full items-center rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent"
          @click="runAction(a)">{{ a.label }}</button>
        <p v-if="!pages.length && !acts.length && !recentPages.length"
          class="px-2 py-6 text-center text-sm text-muted-foreground">Sin resultados</p>
      </div>
    </DialogContent>
  </Dialog>
</template>
