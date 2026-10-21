<script setup lang="ts">
// Tarifas y UVT (Fase 4.1). Son LEY y cambian por decreto: se importan del Excel
// del contador y se editan aquí (D-102). Actualizarlas cada enero es volver a
// subir el archivo, no publicar una versión del programa.
//
// No hay tarifas de ICA: ninguna de las empresas del contador es agente de
// ReteICA, y lo confirmó por escrito. Cuando alguna lo sea, se añade.
import { ArrowLeft, UploadCloud, Plus, Pencil, Archive, ArchiveRestore, Search } from 'lucide-vue-next'

type Concepto = {
  id: number; concepto: string; aplica_a: string; sobre: string
  tarifa: string | null; tarifa_texto: string | null
  base_minima_uvt: string | null; base_minima_pesos?: string | null
  cuenta_puc: string | null; vigencia_desde: string | null
  observaciones: string | null; fuente: string; archivado: number
}
type Uvt = { anio: number; valor: string; norma: string | null; fuente: string }
type Lista = {
  conceptos: Concepto[]; uvt: Uvt[]
  ultima_importacion: { source_name: string; imported_at: string; conceptos: number } | null
}
type Vista = { total_uvt: number; total_conceptos: number; avisos: string[]; source_name: string }

const route = useRoute()
const toast = useToast()
const dbPath = computed(() => (route.query.db as string) || '')

const cargando = ref(false)
const conceptos = ref<Concepto[]>([])
const uvt = ref<Uvt[]>([])
const ultima = ref<Lista['ultima_importacion']>(null)
const razonSocial = ref('')
const busca = ref('')
const verArchivados = ref(false)
const anio = ref(new Date().getFullYear())

const subiendo = ref(false)
const aplicando = ref(false)
const vista = ref<Vista | null>(null)
const vistaRuta = ref('')

const APLICA: Record<string, string> = {
  declarantes: 'Declarantes', no_declarantes: 'No declarantes', ambos: 'Todos',
}
const etiquetaAplica = (a: string) => APLICA[a] || a || '—'

const filtrados = computed(() => {
  const q = busca.value.trim().toLowerCase()
  if (!q) return conceptos.value
  return conceptos.value.filter((c) =>
    `${c.concepto} ${c.cuenta_puc ?? ''} ${c.observaciones ?? ''}`.toLowerCase().includes(q))
})
const sinTarifa = computed(() => conceptos.value.filter((c) => !c.tarifa).length)

function humanError(e: unknown): string {
  // Igual que en `puc.vue`: $fetch deja el mensaje real del sidecar en e.data,
  // y es más útil que el «500» genérico.
  const anyE = e as { data?: { error?: string }; message?: string }
  return String(anyE?.data?.error ?? anyE?.message ?? e).replace(/^Error:\s*/, '')
}

async function cargar() {
  if (!dbPath.value) return
  cargando.value = true
  try {
    const r = await rpc<Lista>('tarifas_list', {
      db_path: dbPath.value, anio: anio.value, incluir_archivados: verArchivados.value,
    })
    conceptos.value = r.conceptos
    uvt.value = r.uvt
    ultima.value = r.ultima_importacion
    const info = await rpc<{ razon_social: string }>('open_empresa', { db_path: dbPath.value })
    razonSocial.value = info.razon_social
  } catch (e) {
    toast.error('No se pudieron cargar las tarifas', humanError(e))
  } finally {
    cargando.value = false
  }
}

async function subir(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  subiendo.value = true
  try {
    const fd = new FormData()
    fd.append('db_path', dbPath.value)
    fd.append('file', file)
    const res = await $fetch<{ ok: boolean; error?: string; result?: Vista; saved_to?: string }>(
      '/api/upload-tarifas', { method: 'POST', body: fd })
    if (!res.ok || !res.result) throw new Error(res.error || 'error al subir')
    vista.value = res.result
    vistaRuta.value = res.saved_to || ''
  } catch (e) {
    toast.error('No se pudo subir el archivo', humanError(e))
  } finally {
    subiendo.value = false
  }
}

async function aplicar() {
  if (!vistaRuta.value) return
  aplicando.value = true
  try {
    const r = await rpc<{ nuevos: number; actualizados: number }>('tarifas_import', {
      db_path: dbPath.value, source_path: vistaRuta.value, dry_run: false })
    toast.success('Tarifas importadas', `${r.nuevos} nuevas · ${r.actualizados} actualizadas`)
    vista.value = null
    await cargar()
  } catch (e) {
    toast.error('No se pudo importar', humanError(e))
  } finally {
    aplicando.value = false
  }
}

// ── edición a mano, en panel y nunca en modal ──
const panel = ref<'concepto' | 'uvt' | null>(null)
// El borrador guarda TEXTO, no el registro con sus nulos: un `null` en un input
// controlado es un error de tipos, y además el usuario escribe texto.
type Borrador = {
  id: number | null; concepto: string; aplica_a: string; sobre: string
  tarifa: string; base_minima_uvt: string; cuenta_puc: string
  vigencia_desde: string; observaciones: string
}
const VACIO: Borrador = {
  id: null, concepto: '', aplica_a: 'ambos', sobre: 'base',
  tarifa: '', base_minima_uvt: '', cuenta_puc: '', vigencia_desde: '', observaciones: '',
}
const borrador = reactive<Borrador>({ ...VACIO })
const borradorUvt = reactive({ anio: new Date().getFullYear(), valor: '', norma: '' })
const guardando = ref(false)

function abrirConcepto(c?: Concepto) {
  Object.assign(borrador, VACIO, { vigencia_desde: `${anio.value}-01-01` })
  if (c) {
    Object.assign(borrador, {
      id: c.id, concepto: c.concepto, aplica_a: c.aplica_a, sobre: c.sobre,
      tarifa: c.tarifa ?? '', base_minima_uvt: c.base_minima_uvt ?? '',
      cuenta_puc: c.cuenta_puc ?? '', vigencia_desde: c.vigencia_desde ?? '',
      observaciones: c.observaciones ?? '',
    })
  }
  panel.value = 'concepto'
}

async function guardarConcepto() {
  guardando.value = true
  try {
    await rpc('tarifas_guardar_concepto', { db_path: dbPath.value, concepto: { ...borrador } })
    panel.value = null
    await cargar()
  } catch (e) {
    toast.error('No se pudo guardar', humanError(e))
  } finally {
    guardando.value = false
  }
}

async function guardarUvt() {
  guardando.value = true
  try {
    await rpc('tarifas_guardar_uvt', { db_path: dbPath.value, ...borradorUvt })
    panel.value = null
    await cargar()
  } catch (e) {
    toast.error('No se pudo guardar la UVT', humanError(e))
  } finally {
    guardando.value = false
  }
}

async function archivar(c: Concepto) {
  await rpc('tarifas_archivar_concepto', {
    db_path: dbPath.value, id: c.id, archivado: !c.archivado })
  await cargar()
}

watch([anio, verArchivados], cargar)
onMounted(cargar)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-3 p-4">
    <header class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
      <NuxtLink :to="{ path: '/empresa', query: { db: dbPath } }"
        class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft class="size-3.5" /> {{ razonSocial || 'Empresa' }}
      </NuxtLink>
      <span class="text-border">/</span>
      <h1 class="font-heading text-xl font-medium tracking-tight">Tarifas y UVT</h1>
      <p class="text-sm text-muted-foreground">
        <strong class="text-foreground">{{ conceptos.length }}</strong> conceptos
        · {{ uvt.length }} años de UVT
        <template v-if="sinTarifa"> · <span class="text-status-warning">{{ sinTarifa }} sin tarifa numérica</span></template>
        <template v-if="ultima"> · último archivo: {{ ultima.source_name }}</template>
      </p>
    </header>

    <section class="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-2">
      <div class="relative min-w-48 flex-1">
        <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="busca" class="pl-8" placeholder="Buscar concepto o cuenta…" />
      </div>
      <label class="flex items-center gap-1.5 text-sm text-muted-foreground">
        Año
        <Input v-model.number="anio" type="number" class="w-24" />
      </label>
      <label class="flex items-center gap-1.5 text-sm text-muted-foreground">
        <input v-model="verArchivados" type="checkbox"> Ver archivados
      </label>
      <Button variant="outline" size="sm" @click="abrirConcepto()"><Plus class="size-3.5" /> Concepto</Button>
      <Button variant="outline" size="sm" @click="panel = 'uvt'">UVT</Button>
      <Button as="label" size="sm" :disabled="subiendo">
        <UploadCloud class="size-3.5" /> {{ subiendo ? 'Subiendo…' : 'Subir el Excel' }}
        <input type="file" accept=".xlsx,.xlsm" class="hidden" @change="subir">
      </Button>
    </section>

    <!-- vista previa antes de escribir nada -->
    <section v-if="vista" class="shrink-0 rounded-lg border border-primary/40 bg-card p-3">
      <h2 class="text-sm font-semibold">{{ vista.source_name }}</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Se leyeron <strong class="text-foreground">{{ vista.total_conceptos }}</strong> conceptos
        y <strong class="text-foreground">{{ vista.total_uvt }}</strong> años de UVT.
        Volver a subirlo fusiona: lo que usted escribió a mano no se pierde.
      </p>
      <ul v-if="vista.avisos.length" class="mt-2 space-y-1">
        <li v-for="(a, i) in vista.avisos" :key="i" class="text-xs text-status-warning">· {{ a }}</li>
      </ul>
      <div class="mt-3 flex gap-2">
        <Button size="sm" :disabled="aplicando" @click="aplicar">
          {{ aplicando ? 'Importando…' : 'Importar' }}
        </Button>
        <Button size="sm" variant="ghost" :disabled="aplicando" @click="vista = null">Cancelar</Button>
      </div>
    </section>

    <!-- panel de edición: nunca un modal -->
    <section v-if="panel === 'concepto'" class="shrink-0 rounded-lg border border-primary/40 bg-card p-3">
      <h2 class="mb-2 text-sm font-semibold">{{ borrador.id ? 'Editar concepto' : 'Nuevo concepto' }}</h2>
      <div class="grid max-w-4xl gap-3 sm:grid-cols-3">
        <div class="grid gap-1.5 sm:col-span-2"><Label>Concepto</Label><Input v-model="borrador.concepto" /></div>
        <div class="grid gap-1.5"><Label>Cuenta PUC</Label><Input v-model="borrador.cuenta_puc" placeholder="23651503" /></div>
        <div class="grid gap-1.5"><Label>Tarifa (%)</Label><Input v-model="borrador.tarifa" placeholder="11" /></div>
        <div class="grid gap-1.5"><Label>Base mínima (UVT)</Label><Input v-model="borrador.base_minima_uvt" placeholder="vacío = sin mínimo" /></div>
        <div class="grid gap-1.5">
          <Label>Se aplica sobre</Label>
          <select v-model="borrador.sobre" class="h-9 rounded-md border border-border bg-background px-2 text-sm">
            <option value="base">La base gravable (retefuente)</option>
            <option value="iva">El IVA facturado (ReteIVA)</option>
          </select>
        </div>
        <div class="grid gap-1.5">
          <Label>Aplica a</Label>
          <select v-model="borrador.aplica_a" class="h-9 rounded-md border border-border bg-background px-2 text-sm">
            <option value="ambos">Todos</option>
            <option value="declarantes">Declarantes</option>
            <option value="no_declarantes">No declarantes</option>
          </select>
        </div>
        <div class="grid gap-1.5"><Label>Rige desde</Label><Input v-model="borrador.vigencia_desde" placeholder="2026-01-01" /></div>
        <div class="grid gap-1.5"><Label>Observaciones</Label><Input v-model="borrador.observaciones" /></div>
      </div>
      <div class="mt-3 flex gap-2">
        <Button size="sm" :disabled="guardando" @click="guardarConcepto">Guardar</Button>
        <Button size="sm" variant="ghost" :disabled="guardando" @click="panel = null">Cancelar</Button>
      </div>
    </section>

    <section v-if="panel === 'uvt'" class="shrink-0 rounded-lg border border-primary/40 bg-card p-3">
      <h2 class="mb-2 text-sm font-semibold">Valor de la UVT</h2>
      <div class="grid max-w-2xl gap-3 sm:grid-cols-3">
        <div class="grid gap-1.5"><Label>Año</Label><Input v-model.number="borradorUvt.anio" type="number" /></div>
        <div class="grid gap-1.5"><Label>Valor (pesos)</Label><Input v-model="borradorUvt.valor" placeholder="52374" /></div>
        <div class="grid gap-1.5"><Label>Norma</Label><Input v-model="borradorUvt.norma" placeholder="Resolución DIAN…" /></div>
      </div>
      <div class="mt-2 flex flex-wrap gap-2">
        <span v-for="u in uvt" :key="u.anio" class="rounded border border-border px-2 py-0.5 font-mono text-xs"
          :title="u.norma || ''">{{ u.anio }}: {{ u.valor }}</span>
      </div>
      <div class="mt-3 flex gap-2">
        <Button size="sm" :disabled="guardando" @click="guardarUvt">Guardar</Button>
        <Button size="sm" variant="ghost" :disabled="guardando" @click="panel = null">Cerrar</Button>
      </div>
    </section>

    <section class="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-card">
      <table class="w-full text-sm">
        <thead class="sticky top-0 bg-card">
          <tr class="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th class="px-3 py-2 font-normal">Concepto</th>
            <th class="px-2 py-2 font-normal">Aplica a</th>
            <th class="px-2 py-2 text-right font-normal">Tarifa</th>
            <th class="px-2 py-2 font-normal">Sobre</th>
            <th class="px-2 py-2 text-right font-normal">Base mínima</th>
            <th class="px-2 py-2 font-normal">Cuenta</th>
            <th class="px-2 py-2 font-normal">Desde</th>
            <th class="px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in filtrados" :key="c.id" class="border-b border-border/60"
            :class="c.archivado ? 'opacity-50' : ''">
            <td class="px-3 py-1.5">
              {{ c.concepto }}
              <span v-if="c.fuente === 'manual'" class="ml-1 rounded bg-muted px-1 text-[10px] uppercase">manual</span>
            </td>
            <td class="px-2 py-1.5 text-muted-foreground">{{ etiquetaAplica(c.aplica_a) }}</td>
            <td class="px-2 py-1.5 text-right font-mono">
              <span v-if="c.tarifa">{{ Number(c.tarifa) }}%</span>
              <span v-else class="text-status-warning" :title="c.tarifa_texto || ''">{{ c.tarifa_texto || '—' }}</span>
            </td>
            <td class="px-2 py-1.5 text-xs text-muted-foreground">
              {{ c.sobre === 'iva' ? 'el IVA' : 'la base' }}
            </td>
            <td class="px-2 py-1.5 text-right font-mono text-xs">
              <template v-if="c.base_minima_uvt">
                {{ Number(c.base_minima_uvt) }} UVT
                <span v-if="c.base_minima_pesos" class="text-muted-foreground">
                  · ${{ Number(c.base_minima_pesos).toLocaleString('es-CO') }}
                </span>
              </template>
              <span v-else class="text-muted-foreground">sin mínimo</span>
            </td>
            <td class="px-2 py-1.5 font-mono text-xs">{{ c.cuenta_puc }}</td>
            <td class="px-2 py-1.5 font-mono text-xs text-muted-foreground">{{ c.vigencia_desde }}</td>
            <td class="whitespace-nowrap px-2 py-1.5 text-right">
              <Button variant="ghost" size="icon-sm" @click="abrirConcepto(c)"><Pencil class="size-3.5" /></Button>
              <Button variant="ghost" size="icon-sm" @click="archivar(c)">
                <ArchiveRestore v-if="c.archivado" class="size-3.5" />
                <Archive v-else class="size-3.5" />
              </Button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!cargando && !filtrados.length" class="px-3 py-8 text-center text-sm text-muted-foreground">
        Todavía no hay tarifas. Suba el Excel del contador con el botón de arriba.
      </p>
    </section>
  </div>
</template>
