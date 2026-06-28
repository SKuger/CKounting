<script setup lang="ts">
import { Upload, ChevronRight } from 'lucide-vue-next'

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
  <div class="mx-auto flex w-full max-w-[120rem] flex-col">
    <header>
      <h1 class="font-heading text-2xl font-medium tracking-tight">Empresas</h1>
      <p class="text-sm text-muted-foreground">Cada empresa = un archivo SQLite independiente.</p>
    </header>

    <div class="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <CardTitle>Tus empresas</CardTitle>
          <CardAction class="flex items-center gap-3">
            <label class="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
              <Checkbox v-model="includeArchived" />
              Mostrar archivadas
            </label>
            <Button as-child variant="outline" size="sm" :disabled="restoring">
              <label class="cursor-pointer">
                <input
                  ref="restoreInputRef"
                  type="file"
                  accept=".zip,application/zip"
                  :disabled="restoring"
                  class="hidden"
                  @change="handleRestorePicked"
                >
                <Upload class="size-3.5" />
                Restaurar
              </label>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          <p v-if="loadingList" class="py-8 text-center text-sm text-muted-foreground">Cargando…</p>
          <p v-else-if="!empresas.length" class="py-8 text-center text-sm text-muted-foreground">
            Sin empresas aún. Crea la primera al lado →
          </p>
          <template v-else>
            <ul class="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
              <li v-for="e in activos" :key="e.db_path">
                <button
                  type="button"
                  class="flex w-full items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2.5 text-left transition-colors hover:bg-accent"
                  @click="navigateTo({ path: '/empresa', query: { db: e.db_path } })"
                >
                  <span class="min-w-0">
                    <span class="block truncate font-medium">{{ e.razon_social || '(sin nombre)' }}</span>
                    <span class="block truncate font-mono text-xs text-muted-foreground">{{ e.nit || '—' }} · {{ e.filename }}</span>
                  </span>
                  <ChevronRight class="size-4 shrink-0 text-muted-foreground" />
                </button>
              </li>
            </ul>

            <div v-if="archivados.length && includeArchived" class="mt-4 border-t border-border pt-3">
              <h3 class="mb-2 font-mono text-xs uppercase tracking-wide text-muted-foreground">Archivadas</h3>
              <ul class="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
                <li
                  v-for="e in archivados"
                  :key="e.db_path"
                  class="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2.5 opacity-70 transition-opacity hover:opacity-100"
                >
                  <button type="button" class="min-w-0 flex-1 cursor-pointer text-left" @click="navigateTo({ path: '/empresa', query: { db: e.db_path } })">
                    <span class="flex items-center gap-2">
                      <span class="truncate font-medium">{{ e.razon_social || '(sin nombre)' }}</span>
                      <Badge variant="secondary">archivada</Badge>
                    </span>
                    <span class="block truncate font-mono text-xs text-muted-foreground">{{ e.nit || '—' }} · {{ e.filename }}</span>
                  </button>
                  <Button variant="ghost" size="sm" :disabled="unarchiving === e.db_path" @click.stop="unarchive(e)">
                    {{ unarchiving === e.db_path ? 'Restaurando…' : 'Desarchivar' }}
                  </Button>
                </li>
              </ul>
            </div>
          </template>
          <p v-if="restoring" class="mt-2 text-sm text-muted-foreground">Restaurando empresa…</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Nueva empresa</CardTitle>
        </CardHeader>
        <CardContent class="flex flex-col gap-4">
          <div class="flex flex-col gap-1.5">
            <Label for="new-nit">NIT (sin DV)</Label>
            <Input id="new-nit" v-model="newNit" placeholder="900181831" inputmode="numeric" />
            <p v-if="dvHint?.valid" class="text-sm text-muted-foreground">
              DV calculado: <strong class="text-foreground">{{ dvHint.computed_dv }}</strong>
            </p>
          </div>
          <div class="flex flex-col gap-1.5">
            <Label for="new-rs">Razón social</Label>
            <Input id="new-rs" v-model="newRazonSocial" placeholder="REAL Seguros Ltda." />
          </div>
          <Button :disabled="!newNit || !newRazonSocial || creating" @click="crearEmpresa">
            {{ creating ? 'Creando…' : 'Crear empresa' }}
          </Button>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
