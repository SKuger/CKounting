<script setup lang="ts">
// Las reglas de causación de la empresa. Hasta la 0.16 no había dónde verlas:
// nacían al aprobar y vivían escondidas. Con la siembra desde los históricos de
// Siigo (D-130) llegan 240 de golpe, y el contador tiene que poder revisarlas,
// corregir una cuenta y archivar las que sobren. Panel, no modal.
import { ArrowLeft, Pencil, Archive, ArchiveRestore, Search } from 'lucide-vue-next'

type Naturaleza = 'compra' | 'venta' | 'doc_soporte'
type Regla = {
  id: number; tercero_nit: string | null; tercero_nombre: string | null; patron: string | null
  cuenta_puc: string; concepto_retencion_id: number | null; sin_retencion: number
  naturaleza: Naturaleza; iva_codigo: string | null; retenciones_cliente: string | null
  origen: string; veces_usada: number; archivada: number
}
type Concepto = { id: number; concepto: string; sobre: string }
type Iva = { codigo: string; nombre: string }

const route = useRoute()
const toast = useToast()
const dbPath = computed(() => (route.query.db as string) || '')

const reglas = ref<Regla[]>([])
const conceptos = ref<Concepto[]>([])
const ivas = ref<Iva[]>([])
const razonSocial = ref('')
const cargando = ref(false)
const busca = ref('')
const naturaleza = ref<'' | Naturaleza>('')
const verArchivadas = ref(false)

const ETIQUETA: Record<Naturaleza, string> = { compra: 'Compra', venta: 'Venta', doc_soporte: 'Doc. soporte' }
const ORIGEN: Record<string, string> = { historico: 'De Siigo', aprendida: 'Al aprobar', manual: 'A mano' }

function humanError(e: unknown): string {
  const anyE = e as { data?: { error?: string }; message?: string }
  return String(anyE?.data?.error ?? anyE?.message ?? e).replace(/^Error:\s*/, '')
}

const nombreConcepto = (id: number | null) => conceptos.value.find((c) => c.id === id)?.concepto || ''

function retencion(r: Regla): string {
  if (r.naturaleza === 'venta') {
    if (r.retenciones_cliente === null) return 'no se sabe'
    return r.retenciones_cliente === 'ninguna' ? 'Ninguna' : r.retenciones_cliente.replaceAll(',', ' · ')
  }
  if (r.sin_retencion) return 'Ninguna'
  return nombreConcepto(r.concepto_retencion_id) || '—'
}

const filtradas = computed(() => {
  const q = busca.value.trim().toLowerCase()
  return reglas.value.filter((r) =>
    (!naturaleza.value || r.naturaleza === naturaleza.value)
    && (!q || `${r.tercero_nit ?? ''} ${r.tercero_nombre ?? ''} ${r.patron ?? ''} ${r.cuenta_puc}`.toLowerCase().includes(q)))
})
const conteo = computed(() => {
  const c: Record<string, number> = {}
  for (const r of reglas.value) c[r.naturaleza] = (c[r.naturaleza] || 0) + 1
  return c
})

async function cargar() {
  if (!dbPath.value) return
  cargando.value = true
  try {
    const r = await rpc<{ reglas: Regla[] }>('reglas_list', {
      db_path: dbPath.value, incluir_archivadas: verArchivadas.value })
    reglas.value = r.reglas
    const t = await rpc<{ conceptos: Concepto[] }>('tarifas_list', { db_path: dbPath.value })
    conceptos.value = t.conceptos.filter((c) => c.sobre !== 'iva')
    const s = await rpc<{ ivas: Iva[] }>('siigo_config', { db_path: dbPath.value })
    ivas.value = s.ivas || []
    const info = await rpc<{ razon_social: string }>('open_empresa', { db_path: dbPath.value })
    razonSocial.value = info.razon_social
  } catch (e) {
    toast.error('No se pudieron cargar las reglas', humanError(e))
  } finally {
    cargando.value = false
  }
}

// El panel de edición guarda TEXTO; `retencion` es '' (no dicho), 'ninguna' o el id.
const abierta = ref<number | null>(null)
const borrador = reactive({ cuenta_puc: '', patron: '', iva_codigo: '', retencion: '', retenciones_cliente: '' })
const guardando = ref(false)

function editar(r: Regla) {
  if (abierta.value === r.id) { abierta.value = null; return }
  abierta.value = r.id
  Object.assign(borrador, {
    cuenta_puc: r.cuenta_puc, patron: r.patron || '', iva_codigo: r.iva_codigo || '',
    retencion: r.sin_retencion ? 'ninguna' : (r.concepto_retencion_id ? String(r.concepto_retencion_id) : ''),
    retenciones_cliente: r.retenciones_cliente || '',
  })
}

async function guardar(r: Regla) {
  guardando.value = true
  try {
    await rpc('regla_guardar', {
      db_path: dbPath.value,
      regla: {
        ...r, cuenta_puc: borrador.cuenta_puc, patron: borrador.patron,
        iva_codigo: borrador.iva_codigo,
        sin_retencion: borrador.retencion === 'ninguna',
        concepto_retencion_id: borrador.retencion && borrador.retencion !== 'ninguna' ? Number(borrador.retencion) : null,
        retenciones_cliente: borrador.retenciones_cliente,
      },
    })
    abierta.value = null
    await cargar()
  } catch (e) {
    toast.error('No se pudo guardar la regla', humanError(e))
  } finally {
    guardando.value = false
  }
}

async function archivar(r: Regla) {
  try {
    await rpc('regla_archivar', { db_path: dbPath.value, id: r.id, archivada: !r.archivada })
    await cargar()
  } catch (e) {
    toast.error('No se pudo archivar', humanError(e))
  }
}

watch(verArchivadas, cargar)
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
      <h1 class="font-heading text-xl font-medium tracking-tight">Reglas de causación</h1>
      <p class="text-sm text-muted-foreground">
        <strong class="text-foreground">{{ reglas.length }}</strong> reglas ·
        {{ conteo.compra || 0 }} de compras · {{ conteo.venta || 0 }} de ventas · {{ conteo.doc_soporte || 0 }} de soportes
      </p>
    </header>

    <p class="max-w-3xl text-xs text-muted-foreground">
      Cada regla dice a qué cuenta va lo que factura un tercero y qué retención lleva. Nacen al aprobar en la bandeja,
      o desde los históricos de Siigo. Corregir una aquí cambia la próxima propuesta, no lo ya aprobado.
    </p>

    <section class="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-2">
      <div class="relative min-w-48 flex-1">
        <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="busca" class="pl-8" placeholder="NIT, nombre, texto o cuenta…" />
      </div>
      <select v-model="naturaleza" class="h-9 rounded-md border border-border bg-background px-2 text-sm">
        <option value="">Todas</option>
        <option value="compra">Compras</option>
        <option value="venta">Ventas</option>
        <option value="doc_soporte">Documentos soporte</option>
      </select>
      <label class="flex items-center gap-1.5 text-sm text-muted-foreground">
        <input v-model="verArchivadas" type="checkbox"> Ver archivadas
      </label>
    </section>

    <section class="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-card">
      <p v-if="!cargando && !reglas.length" class="px-3 py-10 text-center text-sm text-muted-foreground">
        Todavía no hay reglas. Nacen al aprobar en la bandeja, o en «Siigo» → «Reglas desde los históricos».
      </p>
      <table v-else class="w-full text-sm">
        <thead class="sticky top-0 bg-card text-left text-[11px] uppercase text-muted-foreground">
          <tr>
            <th class="px-3 py-2 font-normal">Tercero</th>
            <th class="px-2 py-2 font-normal">Tipo</th>
            <th class="px-2 py-2 font-normal">Cuando dice</th>
            <th class="px-2 py-2 font-normal">Cuenta</th>
            <th class="px-2 py-2 font-normal">IVA</th>
            <th class="px-2 py-2 font-normal">Retención</th>
            <th class="px-2 py-2 font-normal">Origen</th>
            <th class="px-2 py-2 text-right font-normal">Usada</th>
            <th class="px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          <template v-for="r in filtradas" :key="r.id">
            <tr class="border-t border-border/60" :class="r.archivada ? 'opacity-50' : ''">
              <td class="px-3 py-1.5">
                <span class="font-mono text-xs">{{ r.tercero_nit || '—' }}</span>
                <span v-if="r.tercero_nombre" class="ml-1.5 text-muted-foreground">{{ r.tercero_nombre }}</span>
              </td>
              <td class="px-2 py-1.5 text-xs text-muted-foreground">{{ ETIQUETA[r.naturaleza] }}</td>
              <td class="px-2 py-1.5 text-xs">{{ r.patron || 'siempre' }}</td>
              <td class="px-2 py-1.5 font-mono text-xs">{{ r.cuenta_puc }}</td>
              <td class="px-2 py-1.5 font-mono text-xs">{{ r.iva_codigo || '' }}</td>
              <td class="px-2 py-1.5 text-xs" :class="retencion(r) === 'no se sabe' || retencion(r) === '—' ? 'text-status-warning' : ''">
                {{ retencion(r) }}
              </td>
              <td class="px-2 py-1.5 text-xs text-muted-foreground">{{ ORIGEN[r.origen] || r.origen }}</td>
              <td class="px-2 py-1.5 text-right font-mono text-xs">{{ r.veces_usada }}</td>
              <td class="whitespace-nowrap px-2 py-1.5 text-right">
                <Button variant="ghost" size="icon-sm" title="Editar" @click="editar(r)"><Pencil class="size-3.5" /></Button>
                <Button variant="ghost" size="icon-sm" :title="r.archivada ? 'Restaurar' : 'Archivar'" @click="archivar(r)">
                  <ArchiveRestore v-if="r.archivada" class="size-3.5" /><Archive v-else class="size-3.5" />
                </Button>
              </td>
            </tr>
            <tr v-if="abierta === r.id" class="border-t border-border bg-muted/30">
              <td colspan="9" class="px-3 py-3">
                <div class="flex flex-wrap items-end gap-3">
                  <div class="grid gap-1">
                    <Label class="text-xs">{{ r.naturaleza === 'venta' ? 'Cuenta del ingreso' : 'Cuenta del gasto' }}</Label>
                    <Input v-model="borrador.cuenta_puc" class="h-8 w-32 font-mono" />
                  </div>
                  <div class="grid gap-1">
                    <Label class="text-xs">Solo cuando la factura diga…</Label>
                    <Input v-model="borrador.patron" class="h-8 w-56" placeholder="vacío = siempre" />
                  </div>
                  <div v-if="ivas.length" class="grid gap-1">
                    <Label class="text-xs">IVA (código de Siigo)</Label>
                    <select v-model="borrador.iva_codigo" class="h-8 rounded-md border border-border bg-background px-2 text-xs">
                      <option value="">— el de la tarifa —</option>
                      <option v-for="i in ivas" :key="i.codigo" :value="i.codigo">{{ i.codigo }} · {{ i.nombre }}</option>
                    </select>
                  </div>
                  <div v-if="r.naturaleza !== 'venta'" class="grid gap-1">
                    <Label class="text-xs">Retención en la fuente</Label>
                    <select v-model="borrador.retencion" class="h-8 rounded-md border border-border bg-background px-2 text-xs">
                      <option value="">— preguntar al aprobar —</option>
                      <option value="ninguna">Ninguna</option>
                      <option v-for="c in conceptos" :key="c.id" :value="String(c.id)">{{ c.concepto }}</option>
                    </select>
                  </div>
                  <div v-else class="grid gap-1">
                    <Label class="text-xs">Le retiene (códigos de Siigo)</Label>
                    <Input v-model="borrador.retenciones_cliente" class="h-8 w-40 font-mono" placeholder="05,07,11 · ninguna" />
                  </div>
                  <Button size="sm" :disabled="guardando" @click="guardar(r)">Guardar</Button>
                  <Button size="sm" variant="ghost" :disabled="guardando" @click="abierta = null">Cancelar</Button>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </section>
  </div>
</template>
