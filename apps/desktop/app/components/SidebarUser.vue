<script setup lang="ts">
// SidebarUser — bloque del usuario + preferencias + "Salir de Contab".
// Contab es single-user (D-004, sin auth): NO hay gestor multi-cuenta. Se muestra un único perfil,
// editable inline; su persistencia pasa a contab.db (program_save_user) en T2.1. Las preferencias
// viven en usePrefs() (persistidas y aplicadas al DOM).
//
// Sigue siendo dual-source: si el consumidor pasa :user / :preferences (v-model), el componente
// EMITE en vez de mutar; por defecto usa las composables integradas.
//
// variant="sidebar" → bloque completo que colapsa al avatar en el riel · "navbar" → píldora compacta.
import { ref, reactive, computed } from 'vue'
import { ChevronsUpDown, LogOut, Pencil } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '~/components/ui/popover'
import { Switch } from '~/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '~/components/ui/select'
import { Separator } from '~/components/ui/separator'
import { useSidebar } from '~/components/ui/sidebar'
import {
  useUser, usePrefs, initialsOf,
  PREF_THEMES, PREF_DENSITIES, PREF_SCALES, PREF_LANGS, PREF_REGIONS,
  type Profile, type Prefs,
} from '#imports'

const props = withDefaults(defineProps<{
  variant?: 'sidebar' | 'navbar'
  // overrides del consumidor (opcionales). Si se pasan, el componente emite en vez de mutar.
  user?: Profile
  preferences?: Prefs
}>(), { variant: 'sidebar', user: undefined, preferences: undefined })

const emit = defineEmits<{
  'update:user': [Profile]
  'update:preferences': [Prefs]
}>()

const { state } = useSidebar()
const pg = useBrand()

// ── fuente de verdad: props (consumidor) por encima de las composables integradas ──
const u = useUser()
const p = usePrefs()
const active = computed<Profile>(() => props.user ?? u.active.value)
const prefs = computed<Prefs>(() => props.preferences ?? p.prefs)
const controlled = computed(() => props.user != null)
const prefsControlled = computed(() => props.preferences != null)

function setPref<K extends keyof Prefs>(key: K, value: Prefs[K]) {
  if (prefsControlled.value) emit('update:preferences', { ...prefs.value, [key]: value })
  else p.setPref(key, value)
}

// ── editar el perfil (inline) ──
const editing = ref(false)
const draft = reactive({ name: '', email: '', role: '' })
function startEdit() { draft.name = active.value.name; draft.email = active.value.email; draft.role = active.value.role ?? ''; editing.value = true }
function saveEdit() {
  const patch = { name: draft.name.trim() || active.value.name, email: draft.email.trim() || active.value.email, role: draft.role.trim() }
  if (controlled.value) emit('update:user', { ...active.value, ...patch })
  else u.updateActive(patch)
  editing.value = false
}

// ── "Salir de Contab" → cierra el programa (Electron). En navegador dev es no-op. ──
function quitApp() {
  const w = window as unknown as { contab?: { quit?: () => void } }
  if (w.contab?.quit) w.contab.quit()
  else if (import.meta.client) window.close()
}

// alineación del menú + comportamiento colapsado
const menuAlign = computed(() => props.variant === 'navbar' || pg.userPlacement === 'bottom' ? 'end' : 'start')
const showText = computed(() => props.variant === 'navbar' || state.value === 'expanded')

const segBtn = (on: boolean) =>
  ['rounded px-2 py-1 text-[11px] leading-tight transition-colors',
    on ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'].join(' ')
</script>

<template>
  <Popover>
    <PopoverTrigger
      :class="[
        'flex items-center gap-2 rounded-md text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-sidebar-ring',
        variant === 'navbar' ? 'h-9 px-1.5 hover:bg-accent' : 'w-full p-1.5 hover:bg-sidebar-accent',
        variant === 'sidebar' && state === 'collapsed' ? 'justify-center' : '',
      ]">
      <span class="inline-flex size-8 shrink-0 items-center justify-center rounded-md bg-sidebar-primary font-mono text-xs font-medium text-sidebar-primary-foreground">
        {{ initialsOf(active) }}
      </span>
      <span v-if="showText" class="min-w-0" :class="variant === 'navbar' ? 'hidden flex-1 lg:block' : 'flex-1'">
        <span class="block truncate text-sm font-medium leading-tight" :class="variant === 'navbar' ? 'text-foreground' : 'text-sidebar-foreground'">{{ active.name }}</span>
        <span class="block truncate text-xs leading-tight text-muted-foreground">{{ active.role || active.email }}</span>
      </span>
      <ChevronsUpDown v-if="showText" class="size-4 shrink-0 text-muted-foreground" :class="variant === 'navbar' ? 'hidden lg:block' : ''" />
    </PopoverTrigger>

    <PopoverContent :align="menuAlign" :side="variant === 'navbar' ? 'bottom' : 'right'" :side-offset="8"
      class="flex max-h-[min(78vh,560px)] w-72 flex-col gap-0 overflow-y-auto p-0">
      <!-- header: perfil + editar -->
      <div class="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <span class="inline-flex size-9 shrink-0 items-center justify-center rounded-md bg-sidebar-primary font-mono text-xs text-sidebar-primary-foreground">{{ initialsOf(active) }}</span>
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-medium">{{ active.name }}</div>
          <div class="truncate text-xs text-muted-foreground">{{ active.email }}</div>
        </div>
        <button v-if="!editing" type="button" aria-label="Editar perfil" title="Editar perfil"
          class="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground" @click="startEdit">
          <Pencil class="size-4" />
        </button>
      </div>

      <!-- editar perfil (inline) -->
      <div v-if="editing" class="flex flex-col gap-2 border-b border-border bg-muted/30 px-3 py-2.5">
        <label class="flex flex-col gap-1 text-[11px] text-muted-foreground">Nombre
          <input v-model="draft.name" type="text" class="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" @keydown.enter="saveEdit"></label>
        <label class="flex flex-col gap-1 text-[11px] text-muted-foreground">Correo
          <input v-model="draft.email" type="email" class="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" @keydown.enter="saveEdit"></label>
        <label class="flex flex-col gap-1 text-[11px] text-muted-foreground">Rol
          <input v-model="draft.role" type="text" class="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" @keydown.enter="saveEdit"></label>
        <div class="flex gap-1.5">
          <button type="button" class="flex-1 rounded-md bg-primary px-2 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90" @click="saveEdit">Guardar</button>
          <button type="button" class="rounded-md border border-border px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent" @click="editing = false">Cancelar</button>
        </div>
      </div>

      <!-- preferencias (reales, persistidas, con efecto) -->
      <div class="flex flex-col gap-2.5 px-3 py-2.5">
        <div class="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">Preferencias</div>

        <div class="flex flex-col gap-1">
          <span class="text-[11px] text-muted-foreground">Tema</span>
          <div class="grid grid-cols-3 gap-1 rounded-md border border-border p-1">
            <button v-for="t in PREF_THEMES" :key="t.id" type="button" :class="segBtn(prefs.theme === t.id)" @click="setPref('theme', t.id)">{{ t.label }}</button>
          </div>
        </div>

        <div class="flex flex-col gap-1">
          <span class="text-[11px] text-muted-foreground">Densidad</span>
          <div class="grid grid-cols-3 gap-1 rounded-md border border-border p-1">
            <button v-for="d in PREF_DENSITIES" :key="d.id" type="button" :class="segBtn(prefs.density === d.id)" @click="setPref('density', d.id)">{{ d.label }}</button>
          </div>
        </div>

        <div class="flex flex-col gap-1">
          <span class="text-[11px] text-muted-foreground">Tamaño de la interfaz</span>
          <div class="grid grid-cols-3 gap-1 rounded-md border border-border p-1">
            <button v-for="s in PREF_SCALES" :key="s.id" type="button" :class="segBtn(prefs.scale === s.id)" @click="setPref('scale', s.id)">{{ s.label }}</button>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-2">
          <label class="flex flex-col gap-1 text-[11px] text-muted-foreground">Idioma
            <Select :model-value="prefs.language" @update:model-value="setPref('language', $event as Prefs['language'])">
              <SelectTrigger class="h-8 w-full"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem v-for="l in PREF_LANGS" :key="l.id" :value="l.id">{{ l.label }}</SelectItem></SelectContent>
            </Select>
          </label>
          <label class="flex flex-col gap-1 text-[11px] text-muted-foreground">Formato regional
            <Select :model-value="prefs.region" @update:model-value="setPref('region', $event as Prefs['region'])">
              <SelectTrigger class="h-8 w-full"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem v-for="r in PREF_REGIONS" :key="r.id" :value="r.id">{{ r.label }}</SelectItem></SelectContent>
            </Select>
          </label>
        </div>

        <div class="flex items-center justify-between gap-2 pt-0.5">
          <span class="text-xs">Reducir movimiento</span>
          <Switch :model-value="prefs.reduceMotion" @update:model-value="setPref('reduceMotion', $event)" />
        </div>
        <div class="flex items-center justify-between gap-2">
          <span class="text-xs">Alto contraste</span>
          <Switch :model-value="prefs.highContrast" @update:model-value="setPref('highContrast', $event)" />
        </div>
      </div>

      <Separator />

      <!-- salir -->
      <div class="p-1.5">
        <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-destructive transition-colors hover:bg-destructive/10" @click="quitApp">
          <LogOut class="size-4" /> Salir de Contab
        </button>
      </div>
    </PopoverContent>
  </Popover>
</template>
