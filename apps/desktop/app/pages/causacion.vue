<script setup lang="ts">
// La bandeja de aprobación (Fase 4.5). La describió el contador el 2026-10-22:
//
//   «Para el primer registro de una factura de un proveedor me muestras en
//   pantalla cómo sería el registro, yo lo valido y en caso de un cambio lo
//   pueda realizar yo; y como por lo general el concepto que factura el
//   proveedor es el mismo, las siguientes facturas se registrarían de esa
//   forma. Pero si en otra factura el concepto cambia, me presentas la nueva
//   propuesta y le doy el visto bueno.»
//
// De ahí las tres cosas que manda esta pantalla: se ve el asiento ENTERO antes
// de aprobar, se puede corregir, y al aprobar **se aprende** — aprobar no es
// marcar una casilla, es enseñarle a Contab lo que él acaba de decidir.
import { ArrowLeft, RefreshCw, Check, Undo2, ChevronRight, Download } from 'lucide-vue-next'

type Linea = { id: number; cuenta_puc: string | null; descripcion: string; debito: string; credito: string }
type Asiento = {
  id: number; cufe: string; tercero_nit: string | null; fecha: string | null
  estado: string; avisos: string[]; aprobado: number; lineas: Linea[]
}
type Resumen = { total: number; completos: number; revisar: number; aprobados: number; porcentaje_completo: number }

const route = useRoute()
const toast = useToast()
const dbPath = computed(() => (route.query.db as string) || '')
const periodo = computed(() => (route.query.periodo as string) || '')

const cargando = ref(false)
const generando = ref(false)
const asientos = ref<Asiento[]>([])
const resumen = ref<Resumen>({ total: 0, completos: 0, revisar: 0, aprobados: 0, porcentaje_completo: 0 })
const razonSocial = ref('')
const cuentas = reactive({ cuenta_proveedores: '', cuenta_iva_descontable: '' })
const abierto = ref<number | null>(null)
const guardando = ref(false)
// Armar la propuesta se pasaba de los 30 s en meses grandes: va como trabajo
// en segundo plano con progreso (D-076).
const trabajo = useJob()

// Los conceptos de retención de la empresa, para elegir uno al aprobar.
type Concepto = { id: number; concepto: string; aplica_a: string; sobre: string }
const conceptos = ref<Concepto[]>([])

// Lo que él corrige de un asiento antes de darle el visto bueno. `retencion`
// es '' (no ha dicho), 'ninguna' (dijo que no se retiene) o el id del concepto.
// Sin esto la regla aprendida no contaba como decisión, y aprobar la primera
// factura de un proveedor no liberaba las siguientes.
const correccion = reactive({ cuenta_puc: '', patron: '', retencion: '' as string, aprender_regla: true })

const exportOpen = ref(false)
const exportando = ref(false)

function humanError(e: unknown): string {
  const anyE = e as { data?: { error?: string }; message?: string }
  return String(anyE?.data?.error ?? anyE?.message ?? e).replace(/^Error:\s*/, '')
}

const pendientes = computed(() => asientos.value.filter((a) => !a.aprobado && a.estado !== 'completo'))
const listos = computed(() => asientos.value.filter((a) => !a.aprobado && a.estado === 'completo'))
const aprobados = computed(() => asientos.value.filter((a) => a.aprobado))

const faltanCuentas = computed(() => !cuentas.cuenta_proveedores)

async function cargar() {
  if (!dbPath.value || !periodo.value) return
  cargando.value = true
  try {
    const r = await rpc<{ asientos: Asiento[]; resumen: Resumen }>('asiento_list', {
      db_path: dbPath.value, periodo: periodo.value,
    })
    asientos.value = r.asientos
    resumen.value = r.resumen
    const t = await rpc<{ conceptos: Concepto[] }>('tarifas_list', { db_path: dbPath.value })
    conceptos.value = t.conceptos.filter((c) => c.sobre !== 'iva')
    const c = await rpc<typeof cuentas>('cuentas_empresa', { db_path: dbPath.value })
    cuentas.cuenta_proveedores = c.cuenta_proveedores || ''
    cuentas.cuenta_iva_descontable = c.cuenta_iva_descontable || ''
    const info = await rpc<{ razon_social: string }>('open_empresa', { db_path: dbPath.value })
    razonSocial.value = info.razon_social
  } catch (e) {
    toast.error('No se pudo cargar la causación', humanError(e))
  } finally {
    cargando.value = false
  }
}

async function generar() {
  generando.value = true
  try {
    const r = await trabajo.correr<{ total: number; completos: number; revisar: number; sin_xml: number }>(
      'asiento_generar', { db_path: dbPath.value, periodo: periodo.value })
    await cargar()
    toast.success(`${r.total} documentos`,
      `${r.completos} listos para aprobar · ${r.revisar} por decidir`
      + (r.sin_xml ? ` · ${r.sin_xml} sin XML` : ''))
  } catch (e) {
    toast.error('No se pudo armar la propuesta', humanError(e))
  } finally {
    generando.value = false
  }
}

function abrir(a: Asiento) {
  if (abierto.value === a.id) { abierto.value = null; return }
  abierto.value = a.id
  const gasto = a.lineas[0]
  correccion.cuenta_puc = gasto?.cuenta_puc || ''
  correccion.patron = ''
  correccion.retencion = ''
  correccion.aprender_regla = true
}

async function aprobar(a: Asiento) {
  guardando.value = true
  try {
    await rpc('asiento_aprobar', {
      db_path: dbPath.value, id: a.id,
      cuenta_puc: correccion.cuenta_puc,
      patron: correccion.patron,
      concepto_retencion_id: correccion.retencion && correccion.retencion !== 'ninguna' ? correccion.retencion : '',
      sin_retencion: correccion.retencion === 'ninguna',
      aprender_regla: correccion.aprender_regla,
      cuenta_proveedores: cuentas.cuenta_proveedores,
      cuenta_iva_descontable: cuentas.cuenta_iva_descontable,
    })
    abierto.value = null
    await cargar()
  } catch (e) {
    toast.error('No se pudo aprobar', humanError(e))
  } finally {
    guardando.value = false
  }
}

async function aprobarTodos() {
  guardando.value = true
  try {
    const r = await rpc<{ aprobados: number }>('asiento_aprobar_lote', {
      db_path: dbPath.value, periodo: periodo.value })
    await cargar()
    toast.success(`${r.aprobados} aprobados`, 'Los que había que mirar siguen esperando.')
  } catch (e) {
    toast.error('No se pudo aprobar en lote', humanError(e))
  } finally {
    guardando.value = false
  }
}

async function onExportFolder(ruta: string) {
  exportOpen.value = false
  exportando.value = true
  try {
    const r = await rpc<{ path: string; asientos: number; lineas: number; cuadra: boolean }>(
      'asiento_exportar', { db_path: dbPath.value, periodo: periodo.value, output_dir: ruta })
    toast.success(`${r.asientos} asientos exportados`,
      (r.cuadra ? 'El archivo cuadra. ' : 'OJO: el archivo NO cuadra. ') + r.path)
  } catch (e) {
    toast.error('No se pudo exportar', humanError(e))
  } finally {
    exportando.value = false
  }
}

async function deshacer(a: Asiento) {
  await rpc('asiento_desaprobar', { db_path: dbPath.value, id: a.id })
  await cargar()
}

const pesos = (v: string) => Number(v || 0).toLocaleString('es-CO')
onMounted(cargar)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-3 p-4">
    <DirectoryPicker v-if="exportOpen" :open="exportOpen" :initial-path="''"
      title="Carpeta donde guardar el Excel de asientos"
      @pick="onExportFolder" @close="exportOpen = false" />
    <header class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
      <NuxtLink :to="{ path: '/empresa', query: { db: dbPath } }"
        class="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft class="size-3.5" /> {{ razonSocial || 'Empresa' }}
      </NuxtLink>
      <span class="text-border">/</span>
      <h1 class="font-heading text-xl font-medium tracking-tight">Causación de {{ periodo }}</h1>
      <p class="text-sm text-muted-foreground">
        <strong class="text-foreground">{{ resumen.total }}</strong> documentos ·
        <span class="text-status-success">{{ listos.length }} listos</span> ·
        <span class="text-status-warning">{{ pendientes.length }} por decidir</span> ·
        {{ aprobados.length }} aprobados
      </p>
    </header>

    <section class="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-2">
      <Button size="sm" variant="outline" :disabled="generando" @click="generar">
        <RefreshCw class="size-3.5" :class="generando ? 'animate-spin' : ''" />
        {{ generando ? 'Armando…' : 'Armar la propuesta del mes' }}
      </Button>
      <Button size="sm" :disabled="guardando || !listos.length" @click="aprobarTodos">
        <Check class="size-3.5" /> Aprobar los {{ listos.length }} listos
      </Button>
      <Button size="sm" variant="outline" :disabled="exportando || !aprobados.length"
        title="Los asientos aprobados a un Excel, una fila por línea, para llevarlos a Siigo"
        @click="exportOpen = true">
        <Download class="size-3.5" /> Exportar {{ aprobados.length }} aprobados
      </Button>
      <span v-if="trabajo.corriendo.value" class="text-xs text-muted-foreground">{{ trabajo.etiqueta.value }}</span>
      <span class="flex-1" />
      <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
        Cuenta de proveedores
        <Input v-model="cuentas.cuenta_proveedores" class="h-8 w-28 font-mono" placeholder="220505" />
      </label>
      <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
        IVA descontable
        <Input v-model="cuentas.cuenta_iva_descontable" class="h-8 w-28 font-mono" placeholder="240810" />
      </label>
    </section>

    <p v-if="faltanCuentas" class="shrink-0 rounded-md border border-status-warning/40 bg-status-warning-bg px-3 py-2 text-sm">
      Falta decir a qué cuenta va <strong>el pasivo con el proveedor</strong> en esta empresa.
      Escríbela arriba: se guarda al aprobar el primer asiento, y solo para esta empresa.
    </p>

    <section class="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-card">
      <p v-if="!cargando && !asientos.length" class="px-3 py-10 text-center text-sm text-muted-foreground">
        Todavía no hay propuesta para {{ periodo }}. Pulsa «Armar la propuesta del mes».
      </p>

      <template v-for="grupo in [
        { titulo: 'Por decidir', filas: pendientes, clase: 'text-status-warning' },
        { titulo: 'Listos para aprobar', filas: listos, clase: 'text-status-success' },
        { titulo: 'Aprobados', filas: aprobados, clase: 'text-muted-foreground' },
      ]" :key="grupo.titulo">
        <div v-if="grupo.filas.length">
          <h2 class="sticky top-0 z-10 border-b border-border bg-card px-3 py-1.5 text-xs font-semibold uppercase"
            :class="grupo.clase">
            {{ grupo.titulo }} · {{ grupo.filas.length }}
          </h2>
          <template v-for="a in grupo.filas" :key="a.id">
            <div class="flex cursor-pointer items-center gap-2 border-b border-border/60 px-3 py-2 text-sm hover:bg-accent/40"
              @click="abrir(a)">
              <ChevronRight class="size-3.5 shrink-0 text-muted-foreground transition-transform"
                :class="abierto === a.id ? 'rotate-90' : ''" />
              <span class="w-20 shrink-0 font-mono text-xs text-muted-foreground">{{ a.fecha }}</span>
              <span class="w-24 shrink-0 font-mono text-xs">{{ a.tercero_nit }}</span>
              <span class="min-w-0 flex-1 truncate">{{ a.lineas[0]?.descripcion }}</span>
              <span class="shrink-0 font-mono text-xs">{{ pesos(a.lineas[0]?.debito || '0') }}</span>
              <Button v-if="a.aprobado" variant="ghost" size="icon-sm" title="Deshacer la aprobación"
                @click.stop="deshacer(a)"><Undo2 class="size-3.5" /></Button>
            </div>

            <div v-if="abierto === a.id" class="border-b border-border bg-muted/30 px-3 py-3">
              <ul v-if="a.avisos.length" class="mb-3 space-y-1">
                <li v-for="(x, i) in a.avisos" :key="i" class="text-xs text-status-warning">· {{ x }}</li>
              </ul>

              <table class="w-full text-xs">
                <thead>
                  <tr class="text-left text-[10px] uppercase text-muted-foreground">
                    <th class="py-1 font-normal">Cuenta</th>
                    <th class="py-1 font-normal">Concepto</th>
                    <th class="py-1 text-right font-normal">Débito</th>
                    <th class="py-1 text-right font-normal">Crédito</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="ln in a.lineas" :key="ln.id" class="border-t border-border/50">
                    <td class="py-1 pr-2 font-mono" :class="ln.cuenta_puc ? '' : 'text-status-error'">
                      {{ ln.cuenta_puc || 'falta' }}
                    </td>
                    <td class="py-1 pr-2">{{ ln.descripcion }}</td>
                    <td class="py-1 text-right font-mono">{{ Number(ln.debito) ? pesos(ln.debito) : '' }}</td>
                    <td class="py-1 text-right font-mono">{{ Number(ln.credito) ? pesos(ln.credito) : '' }}</td>
                  </tr>
                </tbody>
              </table>

              <div v-if="!a.aprobado" class="mt-3 flex flex-wrap items-end gap-3">
                <div class="grid gap-1">
                  <Label class="text-xs">Cuenta del gasto</Label>
                  <Input v-model="correccion.cuenta_puc" class="h-8 w-32 font-mono" placeholder="519530" />
                </div>
                <div class="grid gap-1">
                  <Label class="text-xs">Retención en la fuente</Label>
                  <select v-model="correccion.retencion" class="h-8 rounded-md border border-border bg-background px-2 text-xs">
                    <option value="">— elegir —</option>
                    <option value="ninguna">Ninguna: a este proveedor no se le retiene</option>
                    <option v-for="c in conceptos" :key="c.id" :value="String(c.id)">
                      {{ c.concepto }}<template v-if="c.aplica_a && c.aplica_a !== 'ambos'"> · {{ c.aplica_a === 'declarantes' ? 'declarantes' : 'no declarantes' }}</template>
                    </option>
                  </select>
                </div>
                <div class="grid gap-1">
                  <Label class="text-xs">Recordarlo cuando la factura diga…</Label>
                  <Input v-model="correccion.patron" class="h-8 w-56" placeholder="monitoreo de alarma" />
                </div>
                <label class="flex items-center gap-1.5 pb-1.5 text-xs text-muted-foreground">
                  <input v-model="correccion.aprender_regla" type="checkbox"> Recordar para las próximas
                </label>
                <Button size="sm" :disabled="guardando" @click="aprobar(a)">
                  <Check class="size-3.5" /> Aprobar
                </Button>
              </div>
              <p v-if="!a.aprobado && !correccion.retencion" class="mt-2 text-xs text-status-warning">
                Elige la retención —o «ninguna»—: sin eso, las próximas facturas de este proveedor
                volverán a pedir revisión aunque apruebes esta.
              </p>
              <p v-if="!a.aprobado" class="mt-2 text-xs text-muted-foreground">
                Si dejas vacío «recordarlo cuando la factura diga», la regla se guarda para
                <strong>todo</strong> lo que facture este proveedor. Si lo llenas, solo para
                ese concepto — y cuando facture otra cosa te lo vuelvo a preguntar.
              </p>
            </div>
          </template>
        </div>
      </template>
    </section>
  </div>
</template>
