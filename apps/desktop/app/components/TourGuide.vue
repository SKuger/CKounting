<script setup lang="ts">
// TourGuide — overlay global del tutorial. Atenúa la pantalla y "enfoca" (spotlight) el elemento
// del paso actual, con una tarjeta que explica y avanza. Se monta una vez en el layout.
import { computed, ref, watch, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { useTour } from '~/composables/useTour'

const { state, next, prev, stop } = useTour()

const rect = ref<DOMRect | null>(null)
const step = computed(() => state.steps[state.index] || null)
const isLast = computed(() => state.index === state.steps.length - 1)
const PAD = 8
const CARD_W = 320

function measure() {
  const s = step.value
  if (!s?.target) { rect.value = null; return }
  const el = document.querySelector(s.target) as HTMLElement | null
  if (!el) { rect.value = null; return }
  el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  requestAnimationFrame(() => {
    const el2 = document.querySelector(s.target!) as HTMLElement | null
    rect.value = el2 ? el2.getBoundingClientRect() : null
  })
}

watch(() => [state.active, state.index], () => {
  if (state.active) nextTick(measure)
  else rect.value = null
})

function onWinChange() { if (state.active) measure() }
function onKey(e: KeyboardEvent) {
  if (!state.active) return
  if (e.key === 'Escape') stop()
  else if (e.key === 'ArrowRight' || e.key === 'Enter') { e.preventDefault(); next() }
  else if (e.key === 'ArrowLeft') prev()
}

onMounted(() => {
  window.addEventListener('resize', onWinChange, { passive: true })
  window.addEventListener('scroll', onWinChange, { passive: true, capture: true })
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onWinChange)
  window.removeEventListener('scroll', onWinChange, true)
  window.removeEventListener('keydown', onKey)
})

const holeStyle = computed(() => {
  const r = rect.value
  if (!r) return null
  return {
    top: `${r.top - PAD}px`,
    left: `${r.left - PAD}px`,
    width: `${r.width + PAD * 2}px`,
    height: `${r.height + PAD * 2}px`,
  }
})

const cardStyle = computed(() => {
  const r = rect.value
  if (!r) return { top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: `${CARD_W}px` }
  const spaceBelow = window.innerHeight - r.bottom
  const top = spaceBelow > 220 ? r.bottom + 14 : Math.max(14, r.top - 14 - 200)
  let left = r.left + r.width / 2 - CARD_W / 2
  left = Math.max(14, Math.min(left, window.innerWidth - CARD_W - 14))
  return { top: `${top}px`, left: `${left}px`, width: `${CARD_W}px` }
})
</script>

<template>
  <Teleport to="body">
    <div v-if="state.active" class="fixed inset-0 z-[100]" aria-live="polite">
      <!-- atenuado + foco -->
      <div v-if="holeStyle" class="tour-hole" :style="holeStyle" />
      <div v-else class="absolute inset-0 bg-black/60" @click="stop" />

      <!-- tarjeta guía -->
      <div class="tour-card rounded-xl border border-border bg-popover p-4 text-popover-foreground shadow-2xl" :style="cardStyle">
        <div class="mb-1 flex items-center justify-between gap-2">
          <span class="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Paso {{ state.index + 1 }} / {{ state.steps.length }}</span>
          <button type="button" class="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground" aria-label="Saltar tutorial" @click="stop">✕</button>
        </div>
        <h3 class="font-heading text-base font-medium tracking-tight">{{ step?.title }}</h3>
        <p class="mt-1 text-sm text-muted-foreground">{{ step?.body }}</p>
        <div class="mt-3 flex items-center justify-between gap-2">
          <button type="button" class="text-sm text-muted-foreground transition-colors hover:text-foreground" @click="stop">Saltar</button>
          <div class="flex gap-2">
            <Button v-if="state.index > 0" variant="secondary" size="sm" @click="prev">Atrás</Button>
            <Button size="sm" @click="next">{{ isLast ? 'Entendido' : 'Siguiente' }}</Button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* El "hueco" de foco: el elemento queda nítido y todo lo demás oscurecido por el box-shadow gigante.
   El scrim es un negro translúcido (como el backdrop de los diálogos), no un color de marca. */
.tour-hole {
  position: absolute;
  border-radius: 10px;
  box-shadow: 0 0 0 9999px rgb(2 6 23 / 0.62), 0 0 0 2px var(--primary);
  transition: top 0.25s ease, left 0.25s ease, width 0.25s ease, height 0.25s ease;
  pointer-events: none;
}
.tour-card { position: absolute; z-index: 101; max-width: calc(100vw - 28px); }
</style>
