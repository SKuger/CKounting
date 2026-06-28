<script setup lang="ts">
// Live system-health beacon (tweaks #1 + #6) — "vigilamos lo invisible" made literal.
// Uses the accent-INDEPENDENT status palette (RFC 0008 Q4), NOT the brand accent, so it
// never shifts when a sub-brand re-accents. 'ok' is the calm rest/all-clear state
// (steady, no pulse); 'drift' and 'out' pulse with rising urgency.
import { computed } from 'vue'
const pg = useBrand()

const MAP: Record<string, { label: string; dot: string; text: string }> = {
  ok:    { label: 'En orden',       dot: 'bg-status-success', text: 'text-status-success' },
  drift: { label: 'Derivando',      dot: 'bg-status-warning', text: 'text-status-warning' },
  out:   { label: 'Fuera de rango', dot: 'bg-status-error',   text: 'text-status-error' },
}
const s = computed(() => MAP[pg.systemStatus] ?? MAP.ok)
const alert = computed(() => pg.systemStatus !== 'ok')
</script>

<template>
  <span class="hidden items-center gap-2 lg:inline-flex" :title="`Sistema: ${s.label}`" aria-live="polite">
    <span class="relative flex size-2">
      <span v-if="alert" class="absolute inline-flex size-full animate-ping rounded-full opacity-60" :class="s.dot" />
      <span class="relative inline-flex size-2 rounded-full" :class="s.dot" />
    </span>
    <span class="font-mono text-[11px] uppercase tracking-wide" :class="s.text">{{ s.label }}</span>
  </span>
</template>
