<script setup lang="ts">
type Empresa = {
  db_path: string
  filename: string
  nit: string | null
  razon_social: string | null
  archived: boolean
}

type RestoreResult = {
  db_path: string
  excels_folder: string | null
  pdfs_folder: string | null
  excels_restored: number
  pdfs_restored: number
  conflict_action: string | null
  meta: { nit: string; razon_social: string; created_at?: string }
}

const toast = useToast()
const empresas = ref<Empresa[]>([])
const loadingList = ref(false)
const includeArchived = ref(false)
const newNit = ref('')
const newRazonSocial = ref('')
const dvHint = ref<{ valid: boolean; computed_dv?: string | null } | null>(null)
const creating = ref(false)

const restoring = ref(false)
const restoreInputRef = ref<HTMLInputElement | null>(null)

const unarchiving = ref<string | null>(null)

const activos = computed(() => empresas.value.filter((e) => !e.archived))
const archivados = computed(() => empresas.value.filter((e) => e.archived))

async function refresh() {
  loadingList.value = true
  try {
    empresas.value = await rpc<Empresa[]>('list_empresas', {
      include_archived: includeArchived.value,
    })
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    loadingList.value = false
  }
}

watch(includeArchived, refresh)

let dvDebounce: ReturnType<typeof setTimeout> | null = null
watch(newNit, (raw) => {
  if (dvDebounce) clearTimeout(dvDebounce)
  dvDebounce = setTimeout(async () => {
    const digits = (raw || '').replace(/\D/g, '')
    if (!digits) {
      dvHint.value = null
      return
    }
    try {
      dvHint.value = await rpc<{ valid: boolean; computed_dv?: string }>('validate_nit', { nit: digits })
    } catch {
      dvHint.value = null
    }
  }, 250)
})

async function crearEmpresa() {
  creating.value = true
  try {
    const result = await rpc<Empresa>('create_empresa', {
      nit: newNit.value.trim(),
      razon_social: newRazonSocial.value.trim(),
    })
    newNit.value = ''
    newRazonSocial.value = ''
    dvHint.value = null
    await refresh()
    await navigateTo({ path: '/empresa', query: { db: result.db_path } })
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    creating.value = false
  }
}

async function unarchive(e: Empresa) {
  unarchiving.value = e.db_path
  try {
    await rpc('unarchive_empresa', { db_path: e.db_path })
    await refresh()
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    unarchiving.value = null
  }
}

async function handleRestorePicked(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  restoring.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await $fetch<{ ok: boolean; result?: RestoreResult; error?: string }>(
      '/api/upload-restore', { method: 'POST', body: fd },
    )
    if (!res.ok || !res.result) throw new Error(res.error || 'restore falló')
    const r = res.result
    const detail = `${r.excels_restored} Excels, ${r.pdfs_restored} PDFs.` +
      (r.conflict_action ? ` ${r.conflict_action}` : '')
    toast.success(`Restaurada ${r.meta.razon_social} (NIT ${r.meta.nit})`, detail)
    await refresh()
  } catch (exc) {
    toast.error('Algo falló', String(exc))
  } finally {
    restoring.value = false
    if (restoreInputRef.value) restoreInputRef.value.value = ''
  }
}

onMounted(refresh)
</script>

<template>
  <div class="home-page">
    <header class="home-hero">
      <h1>Empresas</h1>
      <div class="muted small">Cada empresa = un archivo SQLite independiente.</div>
    </header>

    <div class="home-grid">
      <section class="card panel">
        <div class="panel-head">
          <h2>Tus empresas</h2>
          <div class="row" style="gap: 0.5rem">
            <label class="muted small" style="display: flex; align-items: center; gap: 0.3rem">
              <input v-model="includeArchived" type="checkbox" />
              Mostrar archivadas
            </label>
            <label class="file-picker">
              <input
                ref="restoreInputRef"
                type="file"
                accept=".zip,application/zip"
                :disabled="restoring"
                @change="handleRestorePicked"
                style="display: none"
              />
              <span class="button-like" style="padding: 0.32rem 0.7rem; font-size: 0.78rem">
                ⤴ Restaurar
              </span>
            </label>
          </div>
        </div>

        <div v-if="loadingList" class="empty muted">Cargando…</div>
        <div v-else-if="!empresas.length" class="empty muted">
          Sin empresas aún. Crea la primera al lado →
        </div>
        <template v-else>
          <ul class="empresa-list">
            <li
              v-for="e in activos"
              :key="e.db_path"
              class="empresa-item"
              @click="navigateTo({ path: '/empresa', query: { db: e.db_path } })"
            >
              <div>
                <div style="font-weight: 600">{{ e.razon_social || '(sin nombre)' }}</div>
                <div class="muted mono small">{{ e.nit || '—' }} · {{ e.filename }}</div>
              </div>
              <span class="muted small mono">→</span>
            </li>
          </ul>
          <div v-if="archivados.length && includeArchived" class="archived-section">
            <h3>Archivadas</h3>
            <ul class="empresa-list">
              <li
                v-for="e in archivados"
                :key="e.db_path"
                class="empresa-item archived"
              >
                <div @click="navigateTo({ path: '/empresa', query: { db: e.db_path } })" style="flex:1; cursor: pointer">
                  <div style="font-weight: 600">
                    {{ e.razon_social || '(sin nombre)' }}
                    <span class="chip warn">archivada</span>
                  </div>
                  <div class="muted mono small">{{ e.nit || '—' }} · {{ e.filename }}</div>
                </div>
                <button
                  class="ghost"
                  :disabled="unarchiving === e.db_path"
                  @click.stop="unarchive(e)"
                >
                  {{ unarchiving === e.db_path ? 'Restaurando…' : 'Desarchivar' }}
                </button>
              </li>
            </ul>
          </div>
        </template>
        <div v-if="restoring" class="muted small" style="margin-top: 0.4rem">Restaurando empresa…</div>
      </section>

      <section class="card panel">
        <div class="panel-head">
          <h2>Nueva empresa</h2>
        </div>
        <div class="form-grid">
          <div class="form-field">
            <label>NIT (sin DV)</label>
            <input v-model="newNit" placeholder="900181831" inputmode="numeric" />
            <div v-if="dvHint?.valid" class="muted small">
              DV calculado: <strong style="color: var(--text)">{{ dvHint.computed_dv }}</strong>
            </div>
          </div>
          <div class="form-field">
            <label>Razón social</label>
            <input v-model="newRazonSocial" placeholder="REAL Seguros Ltda." />
          </div>
          <button
            :disabled="!newNit || !newRazonSocial || creating"
            @click="crearEmpresa"
          >
            {{ creating ? 'Creando…' : 'Crear empresa' }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.home-page { display: flex; flex-direction: column; gap: 1rem; max-width: 1100px; margin: 0 auto; }
.home-hero { padding: 0.2rem 0.2rem 0.5rem; }
.home-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: 0.95rem;
}
@media (max-width: 800px) { .home-grid { grid-template-columns: 1fr; } }
.form-grid { display: flex; flex-direction: column; gap: 0.7rem; }
.form-field { display: flex; flex-direction: column; gap: 0.3rem; }
.form-field label { font-size: 0.78rem; color: var(--muted); }
.archived-section { margin-top: 1rem; padding-top: 0.7rem; border-top: 1px dashed var(--border); }
.archived-section h3 { font-size: 0.78rem; color: var(--muted); margin-bottom: 0.5rem; }
.empresa-item.archived { opacity: 0.7; }
.empresa-item.archived:hover { opacity: 1; }
</style>
