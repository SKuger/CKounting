<script setup lang="ts">
// Maker credit, required in every Dandelyon app (dandelyon_brand/BRAND.md §10). Rendered
// MONOCHROME + MUTED (text-muted-foreground, mono, small) — never Interval's orange/
// indigo — so the Dandelyon brand owns the screen. The mark is the REAL Interval icon:
// two brackets (vertical bar + inward feet + a detached top-notch square), framing the
// credit the way the real logo frames a phrase. currentColor → flips in dark.
// Collapsed sidebar → just the brackets [ ].
import { useSidebar } from '~/components/ui/sidebar'
const { state } = useSidebar()
</script>

<template>
  <div class="flex items-center gap-1.5 px-1 text-muted-foreground" :class="state === 'expanded' ? '' : 'justify-center'" aria-label="Hecho por Interval · Tecnología Humana">
    <!-- left bracket -->
    <svg viewBox="0 0 16 40" class="h-3.5 w-auto shrink-0" fill="currentColor" aria-hidden="true">
      <rect x="3" y="7" width="3" height="26" />
      <rect x="3" y="7" width="8" height="3" />
      <rect x="3" y="30" width="8" height="3" />
      <rect x="9.5" y="1" width="3.5" height="3.5" />
    </svg>
    <span v-if="state === 'expanded'"
          class="font-mono text-[10px] leading-tight tracking-wide whitespace-nowrap">
      Interval · Tecnología Humana
    </span>
    <!-- right bracket (mirror) -->
    <svg viewBox="0 0 16 40" class="h-3.5 w-auto shrink-0" fill="currentColor" aria-hidden="true">
      <rect x="10" y="7" width="3" height="26" />
      <rect x="5" y="7" width="8" height="3" />
      <rect x="5" y="30" width="8" height="3" />
      <rect x="2.5" y="1" width="3.5" height="3.5" />
    </svg>
  </div>
</template>
