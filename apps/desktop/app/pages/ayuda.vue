<script setup lang="ts">
import { Home, Building2, FolderOpen, FileSearch, PlayCircle, LifeBuoy, ArrowRight } from 'lucide-vue-next'
import { TOUR_LIST } from '~/lib/tours'

const ICONS: Record<string, unknown> = { Home, Building2, FolderOpen, FileSearch }

// Los tutoriales de empresa/carga resaltan elementos que solo existen con una empresa abierta:
// desde el hub llevamos al inicio y el botón "?" de esa vista lanza el tutorial en contexto.
const CONTEXTUAL = new Set(['/empresa', '/load'])

function launch(route: string) {
  if (CONTEXTUAL.has(route)) return navigateTo('/empresas')
  return navigateTo({ path: route, query: { tour: '1' } })
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-4xl flex-col gap-5">
    <div class="flex items-center gap-3">
      <span class="inline-flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary"><LifeBuoy class="size-5" /></span>
      <div>
        <h1 class="font-heading text-2xl font-medium tracking-tight">Ayuda</h1>
        <p class="text-sm text-muted-foreground">Elige una pantalla y te guío paso a paso, resaltando dónde hacer clic.</p>
      </div>
    </div>

    <div class="grid gap-3 sm:grid-cols-2">
      <div v-for="t in TOUR_LIST" :key="t.id" class="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
        <div class="flex items-center gap-3">
          <span class="inline-flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <component :is="ICONS[t.icon] || LifeBuoy" class="size-5" />
          </span>
          <div class="min-w-0">
            <div class="font-medium leading-tight">{{ t.label }}</div>
            <div class="text-xs text-muted-foreground">{{ t.steps.length }} pasos</div>
          </div>
        </div>
        <p class="text-sm text-muted-foreground">{{ t.description }}</p>
        <div class="mt-auto flex flex-col gap-1">
          <Button class="w-fit" size="sm" @click="launch(t.route)">
            <component :is="CONTEXTUAL.has(t.route) ? ArrowRight : PlayCircle" class="size-4" />
            {{ CONTEXTUAL.has(t.route) ? 'Ir a Empresas' : 'Ver tutorial' }}
          </Button>
          <p v-if="CONTEXTUAL.has(t.route)" class="text-xs text-muted-foreground">
            Ábrela y pulsa el botón <span class="font-medium text-foreground">?</span> para este tutorial.
          </p>
        </div>
      </div>
    </div>

    <p class="text-xs text-muted-foreground">
      En cualquier pantalla, el botón <span class="font-medium text-foreground">?</span> de la barra superior repite su tutorial.
    </p>
  </div>
</template>
