<script setup lang="ts">
// Creator credit for every Dandelyon app: «Creado por: SKuger · V<version>». Rendered
// MONOCHROME + MUTED (text-muted-foreground, mono, small) and CENTRED, so the app's own
// brand owns the screen. No brackets/logo — the credit is plain text.
//   • author  → SKuger, the creator of the design system (constant; prop default).
//   • version → the live release version (useAppVersion → /api/version → CONTAB_VERSION).
//     An explicit `version` prop still overrides it; otherwise it tracks the installed app.
// Collapsed rail → just «V<version>».
import { useSidebar } from '~/components/ui/sidebar'
const props = withDefaults(defineProps<{ version?: string; author?: string }>(), {
  author: 'SKuger',
})
const { state } = useSidebar()
const appVersion = useAppVersion()
const shown = computed(() => props.version ?? (appVersion.value || ''))
</script>

<template>
  <div class="flex w-full items-center justify-center px-1 font-mono text-[10px] leading-tight tracking-wide text-muted-foreground"
       :aria-label="`Creado por ${props.author}${shown ? ` · versión ${shown}` : ''}`">
    <span v-if="state === 'expanded'" class="whitespace-nowrap">Creado por: {{ props.author }}<template v-if="shown"> · V{{ shown }}</template></span>
    <span v-else-if="shown" class="whitespace-nowrap">V{{ shown }}</span>
  </div>
</template>
