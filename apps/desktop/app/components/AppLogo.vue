<script setup lang="ts">
// Inline SVG (NOT <img src>): the wordmark uses the page's real Fraunces.
//
// Brand rules (Dandelyon = the dandelion-as-sun):
//  • wordmark is ALWAYS Fraunces — never the display picker's font, never substituted;
//  • wordmark colour is cosmos-ink #1E1B4B (light) / #FFFFFF (dark) — the shared family
//    constant, NEVER a sub-brand accent and never `currentColor`;
//  • the brand mark = the favicon: a black tile + blue "D" (#4F8DF7) cradling a blue sun in
//    its counter. The sun's core is the one live beacon (.dandelyon-sun — dims/brightens +
//    pulses faster with system health), here tinted blue via an inline --pg-sun.
//    NAVBAR (expanded sidebar) = the clean Fraunces "Dandelyon" wordmark, no mark; the
//    mark appears only in the favicon + the collapsed-rail ICON (where the word can't fit).
const props = withDefaults(defineProps<{ variant?: 'navbar' | 'icon' }>(), { variant: 'navbar' })

// stout rays radiating from the sun core (the dandelion's light): a stem r1→r2.
// Start at -90° so a ray points straight up.
function rays(cx: number, cy: number, r1: number, r2: number, n = 8) {
  return Array.from({ length: n }, (_, i) => {
    const a = (-90 + i * 360 / n) * Math.PI / 180
    return { x1: cx + Math.cos(a) * r1, y1: cy + Math.sin(a) * r1, x2: cx + Math.cos(a) * r2, y2: cy + Math.sin(a) * r2 }
  })
}
// the sun's rays seated in the "D" counter centre (31, 31.5). Shared by the navbar tile
// mark and the collapsed-rail icon — both reuse the favicon's "D + sun" letter-mark.
const counterRays = rays(31, 31.5, 5.5, 8.5)
</script>

<template>
  <!-- navbar (expanded sidebar): the clean "Dandelyon" wordmark in Fraunces — no mark beside
       it (the D+sun mark lives in the favicon and the collapsed rail). -->
  <svg v-if="props.variant === 'navbar'" class="h-10 w-auto" viewBox="0 0 200 60"
       role="img" aria-label="Dandelyon" fill="none">
    <text x="6" y="45" font-family="Fraunces, 'Times New Roman', serif"
          font-size="33" letter-spacing="-0.4" class="fill-dandelyon-indigo dark:fill-white">Dandelyon</text>
  </svg>

  <!-- icon (collapsed rail): the brand mark, identical to the favicon — a black tile + blue
       "D" cradling a blue sun in its counter. The core stays the live .dandelyon-sun beacon
       (still breathes), tinted blue via an inline --pg-sun so it matches the mark. -->
  <svg v-else class="h-9 w-9" viewBox="0 0 64 64"
       role="img" aria-label="Dandelyon" fill="none">
    <rect x="2" y="2" width="60" height="60" rx="15" fill="#000000" />
    <path d="M14,11 H31 A20.5,20.5 0 0 1 31,52 H14 Z M22,19 H30 A12.5,12.5 0 0 1 30,44 H22 Z"
          fill="#4F8DF7" fill-rule="evenodd" />
    <g stroke="#4F8DF7" stroke-width="1.6" stroke-linecap="round">
      <line v-for="(r, i) in counterRays" :key="i" :x1="r.x1" :y1="r.y1" :x2="r.x2" :y2="r.y2" />
    </g>
    <circle class="dandelyon-sun" cx="31" cy="31.5" r="4.5" style="--pg-sun:#4F8DF7" />
  </svg>
</template>
