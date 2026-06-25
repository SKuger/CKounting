<script setup lang="ts">
type EmpresaSummary = {
  db_path: string
  filename: string
  nit: string | null
  razon_social: string | null
  archived: boolean
}

const route = useRoute()
const dbPathParam = computed(() => (route.query.db as string) || '')

const switcherOpen = ref(false)
const empresas = ref<EmpresaSummary[]>([])
const loadingEmpresas = ref(false)

const activeEmpresa = computed(() =>
  empresas.value.find((e) => e.db_path === dbPathParam.value) || null,
)

const routeHint = computed(() => {
  if (route.path === '/') return 'Inicio'
  if (route.path === '/empresa') return ''
  if (route.path === '/load') return `Carga #${route.query.id ?? ''}`
  return ''
})

async function loadEmpresas() {
  if (loadingEmpresas.value) return
  loadingEmpresas.value = true
  try {
    empresas.value = await rpc<EmpresaSummary[]>('list_empresas', { include_archived: false })
  } catch {
    empresas.value = []
  } finally {
    loadingEmpresas.value = false
  }
}

function toggleSwitcher() {
  switcherOpen.value = !switcherOpen.value
  if (switcherOpen.value && !empresas.value.length) loadEmpresas()
}

function selectEmpresa(e: EmpresaSummary) {
  switcherOpen.value = false
  if (route.path === '/load') {
    navigateTo({ path: '/empresa', query: { db: e.db_path } })
  } else {
    navigateTo({ path: '/empresa', query: { db: e.db_path } })
  }
}

onMounted(() => {
  if (dbPathParam.value && !empresas.value.length) loadEmpresas()
})

watch(dbPathParam, (v) => {
  if (v && !empresas.value.length) loadEmpresas()
})

// Close switcher on Escape.
function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') switcherOpen.value = false
}
onMounted(() => window.addEventListener('keydown', onKeyDown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <NuxtLink to="/" class="logo">Contab</NuxtLink>

      <div class="empresa-switcher">
        <button
          class="switcher-trigger"
          :class="{ active: switcherOpen }"
          @click="toggleSwitcher"
        >
          <span v-if="activeEmpresa" class="switcher-active">
            <span class="switcher-name">{{ activeEmpresa.razon_social || '(sin nombre)' }}</span>
            <span class="muted small mono">{{ activeEmpresa.nit }}</span>
          </span>
          <span v-else class="muted small">Elegir empresa</span>
          <span class="switcher-caret">▾</span>
        </button>

        <div v-if="switcherOpen" class="switcher-panel">
          <div class="switcher-head">
            <span class="muted small">Cambiar empresa</span>
            <NuxtLink to="/" class="muted small" @click="switcherOpen = false">Ver todas →</NuxtLink>
          </div>
          <div v-if="loadingEmpresas" class="empty muted small">Cargando…</div>
          <div v-else-if="!empresas.length" class="empty muted small">Sin empresas. <NuxtLink to="/">Crear una</NuxtLink></div>
          <ul v-else class="switcher-list">
            <li
              v-for="e in empresas"
              :key="e.db_path"
              :class="{ active: e.db_path === dbPathParam }"
              @click="selectEmpresa(e)"
            >
              <div class="switcher-item-name">{{ e.razon_social }}</div>
              <div class="muted mono small">NIT {{ e.nit }}</div>
            </li>
          </ul>
        </div>
      </div>

      <span class="spacer" />

      <span v-if="routeHint" class="crumbs">{{ routeHint }}</span>
    </header>
    <main class="app-main">
      <slot />
    </main>
    <ToastContainer />
  </div>
</template>
