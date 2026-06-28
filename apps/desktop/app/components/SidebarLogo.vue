<script setup lang="ts">
// The sidebar brand mark. Expanded → the lockup "Dandelyon · <app>" (BRAND.md §2.1): "Dandelyon"
// is the constant wordmark; what follows the · is governed by lockupMode:
//   none → just Dandelyon · logo (glyph only) · full (glyph + app name, per naming register).
// The app name follows the register (cósmico/semi/funcional, RFC 0008 Q1). Collapsed rail → "D".
import { useSidebar } from '~/components/ui/sidebar'
import { GLYPHS } from '~/lib/glyphs'
const { state } = useSidebar()
const pg = useBrand()
</script>

<template>
  <!-- expanded: left-aligned lockup (overflow-clip bleed guard); collapsed: centered "P" on the rail -->
  <div class="flex min-w-0 flex-col gap-0.5" :class="state === 'expanded' ? 'max-w-full overflow-hidden' : 'w-full items-center'">
    <div class="flex min-w-0 items-center gap-1" :class="state === 'expanded' ? '' : 'w-full justify-center'">
      <AppLogo class="shrink-0" :variant="state === 'expanded' ? 'navbar' : 'icon'" />
      <!-- sub-brand mark: glyph (logo/full) + name (full only), seated next to the wordmark (no interpunct).
           The nautical GLYPH is ALWAYS the accent (RFC 0008 Q1 — "glyph (acento)"; matches the registry
           lockup + every consuming app); only the sub-NAME text (full mode) follows the subNameAccent knob. -->
      <span v-if="state === 'expanded' && pg.lockupMode !== 'none'"
            class="flex min-w-0 items-center gap-1.5 truncate font-heading text-lg leading-none">
        <component :is="GLYPHS[pg.subGlyph]" v-if="GLYPHS[pg.subGlyph]"
                   class="size-6 shrink-0 text-primary" :stroke-width="1.75" />
        <span v-if="pg.lockupMode === 'full'" class="truncate"
              :class="pg.subNameAccent ? 'text-primary' : 'text-muted-foreground'">{{ pg.subName }}</span>
      </span>
    </div>
    <!-- sublabel (#5): functional name by default, or the full descriptor when descriptorFull is on.
         pl-[7px] left-aligns it under the wordmark's "P" (text starts at x=10 of the 158-wide svg). -->
    <span v-if="state === 'expanded' && pg.subDescriptor && pg.lockupMode !== 'none'"
          class="truncate pl-[7px] font-mono text-[9px] uppercase leading-none tracking-[0.18em] text-muted-foreground">
      {{ pg.descriptorFull ? pg.subBrand.descriptor : pg.subBrand.names.functional }}
    </span>
  </div>
</template>
