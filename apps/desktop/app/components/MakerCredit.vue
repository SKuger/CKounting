<script setup lang="ts">
// Creator credit for every Dandelyon app: «Creado por: SKuger · V<version>». Rendered
// MONOCHROME + MUTED (text-muted-foreground, mono, small) and CENTRED, so the app's own
// brand owns the screen. No brackets/logo — the credit is plain text.
//   • author  → SKuger, the creator of the design system (constant; prop default).
//   • version → per consuming app: each app passes its own `version` (default 1.0.0) and
//     bumps it as the app improves.
// Collapsed rail → just «V<version>».
import { useSidebar } from '~/components/ui/sidebar'
const props = withDefaults(defineProps<{ version?: string; author?: string }>(), {
  version: '1.0.0',
  author: 'SKuger',
})
const { state } = useSidebar()
</script>

<template>
  <div class="flex w-full items-center justify-center px-1 font-mono text-[10px] leading-tight tracking-wide text-muted-foreground"
       :aria-label="`Creado por ${props.author} · versión ${props.version}`">
    <span v-if="state === 'expanded'" class="whitespace-nowrap">Creado por: {{ props.author }} · V{{ props.version }}</span>
    <span v-else class="whitespace-nowrap">V{{ props.version }}</span>
  </div>
</template>
