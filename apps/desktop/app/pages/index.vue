<script setup lang="ts">
// Inicio — la home saluda al usuario y ofrece los módulos como tarjetas. La navegación
// completa vive en el sidebar/topbar; acá orientamos, no repetimos el menú. Estilo inspirado
// en la home del repo hermano admission-patient (mismo design system Órbita).
import { Building2, FileSearch, ArrowRight, Orbit } from 'lucide-vue-next'

const pg = useBrand()
const u = useUser()

const displayName = computed(() => {
  const n = (u.active.value?.name || '').trim()
  return n && n !== 'Mi cuenta' ? n.split(/\s+/)[0] : ''
})
const greeting = ref('Hola')
const today = ref('')
onMounted(() => {
  const now = new Date()
  const h = now.getHours()
  greeting.value = h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches'
  today.value = now.toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
})

const modulos = [
  { to: '/empresas', tour: 'inicio-empresas', icon: Building2, title: 'Empresas', desc: 'Tus libros contables, uno por empresa. Organiza por mes, valida y exporta.' },
  { to: '/consulta-dian', tour: 'inicio-dian', icon: FileSearch, title: 'Consulta DIAN', desc: 'Consulta masiva del RUT de terceros a partir de sus NIT.' },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-5xl flex-col gap-8">
    <!-- Bienvenida -->
    <section class="relative overflow-hidden rounded-lg border border-border bg-card p-6 shadow-sm md:p-8">
      <Orbit class="pointer-events-none absolute -right-8 -top-10 size-48 text-primary/10" />
      <div class="relative">
        <p class="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Dandelyon · {{ pg.subName }}</p>
        <p class="mt-2 font-heading text-3xl font-semibold text-foreground md:text-4xl">
          {{ greeting }}<template v-if="displayName">, {{ displayName }}</template>
        </p>
        <p v-if="today" class="mt-1 text-sm text-muted-foreground first-letter:uppercase">{{ today }}</p>
      </div>
    </section>

    <!-- Módulos -->
    <section>
      <p class="mb-3 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Módulos</p>
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtLink
          v-for="m in modulos"
          :key="m.to"
          :to="m.to"
          :data-tour="m.tour"
          class="group flex items-center gap-4 rounded-lg border border-border bg-card p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
        >
          <span class="grid size-12 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
            <component :is="m.icon" class="size-6" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="text-lg font-semibold leading-tight text-foreground">{{ m.title }}</p>
            <p class="mt-1 text-sm text-muted-foreground">{{ m.desc }}</p>
          </div>
          <ArrowRight class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
        </NuxtLink>
      </div>
    </section>
  </div>
</template>
