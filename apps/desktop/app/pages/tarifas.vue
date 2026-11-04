<script setup lang="ts">
// Tarifas y UVT (Fase 4.1). Son LEY y cambian por decreto: se importan del Excel
// del contador y se editan aquí (D-102). Actualizarlas cada enero es volver a
// subir el archivo, no publicar una versión del programa.
//
// No hay tarifas de ICA: ninguna de las empresas del contador es agente de
// ReteICA, y lo confirmó por escrito. Cuando alguna lo sea, se añade.
import { ArrowLeft, UploadCloud, Plus, Pencil, Archive, ArchiveRestore, Search, Trash2, X } from 'lucide-vue-next'

type Concepto = {
  id: number; concepto: string; aplica_a: string; sobre: string
  tarifa: string | null; tarifa_texto: string | null
  base_minima_uvt: string | null; base_minima_pesos?: string | null
  cuenta_puc: string | null; codigo_siigo: string | null; vigencia_desde: string | null
  observaciones: string | null; fuente: string; archivado: number
}
type Uvt = { anio: number; valor: string; norma: string | null; fuente: string }
type Lista = {
  conceptos: Concepto[]; uvt: Uvt[]
  ultima_importacion: { source_name: string; imported_at: string; conceptos: number } | null
  conteo?: { total: number; archivados: number }
}
type Vista = { total_uvt: number; total_conceptos: number; avisos: string[]; source_name: string }

const route = useRoute()
const toast = useToast()
const dbPath = computed(() => (route.query.db as string) || '')

const cargando = ref(false)
const conceptos = ref<Concepto[]>([])
const uvt = ref<Uvt[]>([])
const ultima = ref<Lista['ultima_importacion']>(null)
const conteo = ref<{ total: number; archivados: number }>({ total: 0, archivados: 0 })
const razonSocial = ref('')
const busca = ref('')
// Activos o archivados: dos vistas, nunca mezclados (2026-11-04: el contador
// quiere ver solo los archivados y decidir ahí si los saca o los borra).
const soloArchivados = ref(false)
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
const activos = computed(() => conteo.value.total - conteo.value.archivados)
// La lista de activos no cuadra con lo que dice la base: no debería pasar
// nunca, y si pasa hay que decirlo en vez de «todavía no hay tarifas».
const descuadre = computed(() => !soloArchivados.value && conceptos.value.length !== activos.value)
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
      db_path: dbPath.value, anio: anio.value, solo_archivados: soloArchivados.value,
    })
    conceptos.value = r.conceptos
    uvt.value = r.uvt
    ultima.value = r.ultima_importacion
    conteo.value = r.conteo ?? { total: r.conceptos.length, archivados: 0 }
    // Se sacó o se borró el último archivado: no hay nada que ver aquí.
    if (soloArchivados.value && !conteo.value.archivados) soloArchivados.value = false
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
  tarifa: string; base_minima_uvt: string; cuenta_puc: string; codigo_siigo: string
  vigencia_desde: string; observaciones: string
}
const VACIO: Borrador = {
  id: null, concepto: '', aplica_a: 'ambos', sobre: 'base',
  tarifa: '', base_minima_uvt: '', cuenta_puc: '', codigo_siigo: '', vigencia_desde: '', observaciones: '',
}
const borrador = reactive<Borrador>({ ...VACIO })
const borradorUvt = reactive({ anio: new Date().getFullYear(), valor: '', norma: '' })
const guardando = ref(false)

function abrirConcepto(c?: Concepto) {
  Object.assign(borrador, VACIO, { vigencia_desde: `${anio.value}-01-01` })
  if (c) {
    Object.assign(borrador, {
      id: c.id, concepto: c.concepto, aplica_a: c.aplica_a, sobre: c.sobre,
      // Number(): una tarifa guardada como «1.100» antes de normalizarla se
      // leería «mil cien» en el campo.
      tarifa: c.tarifa ? String(Number(c.tarifa)) : '',
      base_minima_uvt: c.base_minima_uvt ? String(Number(c.base_minima_uvt)) : '',
      cuenta_puc: c.cuenta_puc ?? '', codigo_siigo: c.codigo_siigo ?? '', vigencia_desde: c.vigencia_desde ?? '',
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

const desarchivando = ref(false)
async function desarchivarTodos() {
  desarchivando.value = true
  try {
    const r = await rpc<{ desarchivados: number }>('tarifas_desarchivar_todos', { db_path: dbPath.value })
    toast.success('Conceptos fuera del archivo', `${r.desarchivados} vuelven a la lista`)
    soloArchivados.value = false
    await cargar()
  } catch (e) {
    toast.error('No se pudieron sacar del archivo', humanError(e))
  } finally {
    desarchivando.value = false
  }
}

// Borrar es para siempre: pide una segunda confirmación en la misma fila o en
// la misma barra, nunca en un modal.
const confirmarFila = ref<number | null>(null)
const confirmarTodos = ref(false)
const borrando = ref(false)
async function borrar(ids?: number[]) {
  borrando.value = true
  try {
    const r = await rpc<{ borrados: number; en_uso: string[] }>('tarifas_borrar_archivados', {
      db_path: dbPath.value, ...(ids ? { ids } : {}) })
    toast.success(r.borrados === 1 ? 'Concepto borrado' : `${r.borrados} conceptos borrados`)
    if (r.en_uso.length) {
      toast.warn(
        r.en_uso.length === 1 ? 'Uno no se borró' : `${r.en_uso.length} no se borraron`,
        `Los usa una regla de causación: ${r.en_uso.join(', ')}. Cambie la regla y vuelva a intentarlo.`)
    }
  } catch (e) {
    toast.error('No se pudo borrar', humanError(e))
  } finally {
    borrando.value = false
    confirmarFila.value = null
    confirmarTodos.value = false
    await cargar()
  }
}

watch(soloArchivados, () => { confirmarFila.value = null; confirmarTodos.value = false })
watch([anio, soloArchivados], cargar)
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
        <template v-if="soloArchivados">
          <strong class="text-foreground">{{ conteo.archivados }}</strong> archivados
        </template>
        <template v-else>
          <strong class="text-foreground">{{ conceptos.length }}</strong> conceptos
        </template>
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
      <div v-if="conteo.archivados || soloArchivados" class="inline-flex rounded-md border border-border p-0.5 text-sm">
        <button type="button" class="rounded px-2.5 py-1 transition-colors"
          :class="!soloArchivados ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'"
          @click="soloArchivados = false">
          Activos <span class="font-mono text-xs">{{ activos }}</span>
        </button>
        <button type="button" class="rounded px-2.5 py-1 transition-colors"
          :class="soloArchivados ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'"
          @click="soloArchivados = true">
          Archivados <span class="font-mono text-xs">{{ conteo.archivados }}</span>
        </button>
      </div>
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
        <div class="grid gap-1.5">
          <Label>Código en Siigo</Label>
          <Input v-model="borrador.codigo_siigo" placeholder="14" />
          <p class="text-[11px] text-muted-foreground">El código de este impuesto en el catálogo de Siigo de la empresa. Va en el archivo que se importa.</p>
        </div>
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

    <!-- vista de archivados: aquí, y solo aquí, se decide qué hacer con ellos -->
    <section v-if="soloArchivados && conteo.archivados"
      class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border bg-card px-3 py-2 text-sm">
      <template v-if="!confirmarTodos">
        <span class="text-muted-foreground">
          Los archivados no se usan para causar. Puede sacarlos del archivo o borrarlos.
        </span>
        <span class="flex-1" />
        <Button size="sm" variant="outline" :disabled="desarchivando || borrando" @click="desarchivarTodos">
          <ArchiveRestore class="size-3.5" /> {{ desarchivando ? 'Sacando…' : 'Sacarlos todos del archivo' }}
        </Button>
        <Button size="sm" variant="outline" class="text-destructive" :disabled="desarchivando || borrando"
          @click="confirmarTodos = true">
          <Trash2 class="size-3.5" /> Borrarlos todos
        </Button>
      </template>
      <template v-else>
        <span>
          ¿Borrar los <strong>{{ conteo.archivados }}</strong> archivados para siempre? Esto no se puede deshacer.
        </span>
        <span class="flex-1" />
        <Button size="sm" variant="destructive" :disabled="borrando" @click="borrar()">
          {{ borrando ? 'Borrando…' : `Sí, borrar los ${conteo.archivados}` }}
        </Button>
        <Button size="sm" variant="ghost" :disabled="borrando" @click="confirmarTodos = false">Cancelar</Button>
      </template>
    </section>

    <section v-if="!cargando && descuadre"
      class="shrink-0 rounded-lg border border-status-warning/40 bg-status-warning-bg px-3 py-2 text-sm text-status-warning">
      Hay <strong>{{ activos }}</strong> conceptos guardados en esta empresa, pero la lista no los está mostrando.
      Cierre esta pantalla y vuelva a entrar; si sigue igual, avísele a quien le da soporte.
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
            <th class="px-2 py-2 font-normal" title="Código del impuesto en el catálogo de Siigo">Siigo</th>
            <th class="px-2 py-2 font-normal">Desde</th>
            <th class="px-2 py-2 font-normal">Observaciones</th>
            <th class="px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in filtrados" :key="c.id"
            class="cursor-pointer border-b border-border/60 align-top hover:bg-muted/40"
            :class="borrador.id === c.id && panel === 'concepto' ? 'bg-primary/5' : ''"
            title="Clic para editar"
            @click="abrirConcepto(c)">
            <td class="px-3 py-1.5">
              {{ c.concepto }}
              <span v-if="c.fuente === 'manual'" class="ml-1 rounded bg-muted px-1 text-[10px] uppercase">manual</span>
            </td>
            <td class="px-2 py-1.5 text-muted-foreground">{{ etiquetaAplica(c.aplica_a) }}</td>
            <td class="px-2 py-1.5 text-right font-mono">
              <span v-if="c.tarifa">{{ Number(c.tarifa) }}%</span>
              <span v-else class="text-status-warning" :title="c.tarifa_texto || ''">{{ c.tarifa_texto || '—' }}</span>
            </td>
            <td class="whitespace-nowrap px-2 py-1.5 text-xs text-muted-foreground">
              {{ c.sobre === 'iva' ? 'el IVA' : 'la base' }}
            </td>
            <td class="whitespace-nowrap px-2 py-1.5 text-right font-mono text-xs">
              <template v-if="c.base_minima_uvt">
                {{ Number(c.base_minima_uvt) }} UVT
                <span v-if="c.base_minima_pesos" class="text-muted-foreground">
                  · ${{ Number(c.base_minima_pesos).toLocaleString('es-CO') }}
                </span>
              </template>
              <span v-else class="text-muted-foreground">sin mínimo</span>
            </td>
            <td class="px-2 py-1.5 font-mono text-xs">{{ c.cuenta_puc }}</td>
            <td class="px-2 py-1.5 font-mono text-xs" :class="c.codigo_siigo ? '' : 'text-status-warning'">{{ c.codigo_siigo || 'falta' }}</td>
            <td class="whitespace-nowrap px-2 py-1.5 font-mono text-xs text-muted-foreground">{{ c.vigencia_desde }}</td>
            <td class="min-w-48 max-w-80 px-2 py-1.5 text-xs text-muted-foreground">{{ c.observaciones }}</td>
            <td class="whitespace-nowrap px-2 py-1.5 text-right">
              <Button variant="ghost" size="icon-sm" title="Editar" @click.stop="abrirConcepto(c)"><Pencil class="size-3.5" /></Button>
              <template v-if="confirmarFila === c.id">
                <Button variant="destructive" size="sm" class="h-7" :disabled="borrando" @click.stop="borrar([c.id])">
                  ¿Borrar?
                </Button>
                <Button variant="ghost" size="icon-sm" title="No borrar" @click.stop="confirmarFila = null"><X class="size-3.5" /></Button>
              </template>
              <template v-else>
                <Button variant="ghost" size="icon-sm" :title="c.archivado ? 'Sacar del archivo' : 'Archivar'" @click.stop="archivar(c)">
                  <ArchiveRestore v-if="c.archivado" class="size-3.5" />
                  <Archive v-else class="size-3.5" />
                </Button>
                <Button v-if="c.archivado" variant="ghost" size="icon-sm" title="Borrar para siempre"
                  class="text-destructive" @click.stop="confirmarFila = c.id">
                  <Trash2 class="size-3.5" />
                </Button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!cargando && !filtrados.length && busca.trim() && conceptos.length"
        class="px-3 py-8 text-center text-sm text-muted-foreground">
        Ningún concepto coincide con «{{ busca.trim() }}».
      </p>
      <div v-else-if="!cargando && !filtrados.length && !soloArchivados && conteo.archivados && !activos"
        class="flex flex-col items-center gap-2 px-3 py-8 text-center text-sm text-muted-foreground">
        Todos los conceptos de esta empresa están archivados.
        <Button size="sm" variant="outline" @click="soloArchivados = true">Ver los {{ conteo.archivados }} archivados</Button>
      </div>
      <p v-else-if="!cargando && !filtrados.length && !conteo.total"
        class="px-3 py-8 text-center text-sm text-muted-foreground">
        Todavía no hay tarifas. Suba el Excel del contador con el botón de arriba.
      </p>
    </section>
  </div>
</template>
