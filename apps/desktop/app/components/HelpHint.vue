<script setup lang="ts">
// HelpHint — un botón "?" que abre un Popover con una explicación en lenguaje llano.
// Se coloca junto a la jerga (CUFE, V1/V2/V3, NIT/DV, papelera…) para que un usuario NO técnico
// entienda sin salir de la pantalla. Contenido por slot; `title` opcional como encabezado.
import { HelpCircle } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '~/components/ui/popover'

defineProps<{ title?: string }>()
</script>

<template>
  <Popover>
    <PopoverTrigger
      class="inline-flex size-4 shrink-0 items-center justify-center rounded-full align-middle text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
      :aria-label="title ? `Ayuda: ${title}` : 'Ayuda'"
      @click.stop.prevent
    >
      <HelpCircle class="size-3.5" />
    </PopoverTrigger>
    <PopoverContent :side-offset="6" class="w-72 text-sm">
      <p v-if="title" class="mb-1 font-medium">{{ title }}</p>
      <div class="text-muted-foreground [&_strong]:text-foreground"><slot /></div>
    </PopoverContent>
  </Popover>
</template>
