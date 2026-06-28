<script setup lang="ts">
// "Sistema solar" (2.5D) — the WHOLE system seen at a tilt at the foot of the sidebar. The
// Dandelyon sun sits at the centre; planets travel along FORESHORTENED elliptical orbits (CSS
// offset-path), so the plane reads as top-down-at-an-angle: a planet is big/bright on the near
// side (front) and small/dim on the far side (back). A quiet starfield drifts behind, and a
// Star-Trek-style starship flies THROUGH the system, scaling near→far. Everything is currentColor
// (tinted by data-ocean-tint: mono | cyan | accent) and lives in a fixed 260×96 .cosmos-stage
// centred in the band (sun at stage 130,48). Speeds follow the system status (CSS). Tunable:
// band height (data-swell), nebula glow (oceanFoam), starship (oceanBoat). Replaces the old sea.
const pg = useBrand()

// orbits: foreshortened ellipses centred on the sun (130,48). rx/ry → the ring div size + the
// planet's offset-path. delay phases the planets so they don't line up. (ry ≈ 0.31·rx = the tilt.)
const ORBITS = [
  { n: 1, rx: 24, ry: 7,  delay: '-3s',  ring: false, type: 'rocky'  }, // small rocky world
  { n: 2, rx: 44, ry: 13, delay: '-10s', ring: false, type: 'earth'  }, // Earth (oceans + the Americas)
  { n: 3, rx: 66, ry: 20, delay: '-25s', ring: false, type: 'mars'   }, // Mars (red + polar cap)
  { n: 4, rx: 90, ry: 28, delay: '-46s', ring: true,  type: 'saturn' }, // ringed gas giant
]

// occasional shooting stars (mostly off-screen between passes). Each enters from a DIFFERENT side
// at a different angle/time (--ang sets travel direction; the CSS carries it head-first so the tail
// trails). Mixed sides + coprime durations → they don't always come from the same place.
const METEORS = [
  { left: '82%', top: '2px', ang: '150deg', dur: '64s', delay: '-6s'  }, // from right → down-left
  { left: '2%',  top: '8px', ang: '32deg',  dur: '93s', delay: '-48s' }, // from left  → down-right
]
// elliptical path starting at the BOTTOM (front) so the depth keyframes line up (0% = near).
const orbitPath = (rx: number, ry: number) => {
  const cx = 120, cy = 40
  return `path("M ${cx} ${cy + ry} A ${rx} ${ry} 0 1 1 ${cx} ${cy - ry} A ${rx} ${ry} 0 1 1 ${cx} ${cy + ry}")`
}

// quiet starfield — fixed positions in the 240×80 stage, kept off the bright centre.
const STARS = [
  { x: 12,  y: 10, s: 1.6, d: '3.1s', delay: '0s'   },
  { x: 36,  y: 60, s: 1.2, d: '4.2s', delay: '0.6s' },
  { x: 60,  y: 14, s: 1.8, d: '3.6s', delay: '1.2s' },
  { x: 26,  y: 38, s: 1.2, d: '5.0s', delay: '0.3s' },
  { x: 196, y: 12, s: 1.8, d: '4.4s', delay: '1.8s' },
  { x: 220, y: 56, s: 1.4, d: '3.3s', delay: '0.9s' },
  { x: 230, y: 26, s: 1.6, d: '4.8s', delay: '2.2s' },
  { x: 176, y: 68, s: 1.2, d: '3.9s', delay: '0.4s' },
  { x: 8,   y: 70, s: 1.4, d: '4.1s', delay: '1.5s' },
  { x: 112, y: 4,  s: 1.4, d: '5.2s', delay: '0.8s' },
  { x: 140, y: 74, s: 1.2, d: '3.7s', delay: '2.6s' },
  { x: 92,  y: 72, s: 1.4, d: '4.6s', delay: '1.1s' },
]
</script>

<template>
  <div v-if="pg.ocean"
       class="pg-cosmos pointer-events-none absolute inset-0 z-0 overflow-hidden"
       aria-hidden="true">
    <div class="cosmos-stage">
      <!-- starfield -->
      <span v-for="(st, i) in STARS" :key="'s' + i" class="cosmos-star"
            :style="{ left: st.x + 'px', top: st.y + 'px', width: st.s + 'px', height: st.s + 'px', animationDuration: st.d, animationDelay: st.delay }" />

      <!-- occasional shooting stars with trailing tails (the "Estrellas fugaces" toggle = oceanFoam) -->
      <template v-if="pg.oceanFoam">
        <span v-for="(m, i) in METEORS" :key="'m' + i" class="cosmos-meteor"
              :style="{ left: m.left, top: m.top, '--ang': m.ang, animationDuration: m.dur, animationDelay: m.delay }" />
      </template>

      <!-- orbit rings (foreshortened ellipses) -->
      <span v-for="o in ORBITS" :key="'o' + o.n" class="cosmos-orbit"
            :style="{ width: o.rx * 2 + 'px', height: o.ry * 2 + 'px' }" />

      <!-- the Dandelyon sun: corona + core -->
      <span class="cosmos-sun-glow" />
      <span class="cosmos-sun-core" />

      <!-- planets travelling the elliptical orbits (Earth + Mars are detailed; Saturn is ringed) -->
      <span v-for="o in ORBITS" :key="'p' + o.n" class="cosmos-planet"
            :class="['orbit-' + o.n, { ringed: o.ring, 'has-svg': o.type === 'earth' || o.type === 'mars' }]"
            :style="{ offsetPath: orbitPath(o.rx, o.ry), animationDelay: o.delay + ', ' + o.delay }">
        <!-- Earth: blue oceans + the Americas (North · Central · South), atmosphere rim + 3D shade -->
        <svg v-if="o.type === 'earth'" class="planet-svg" viewBox="0 0 100 100" aria-hidden="true">
          <defs>
            <clipPath id="dl-earth-clip"><circle cx="50" cy="50" r="50" /></clipPath>
            <radialGradient id="dl-earth-shade" cx="35%" cy="30%" r="78%">
              <stop offset="0" stop-color="#ffffff" stop-opacity="0.45" />
              <stop offset="42%" stop-color="#ffffff" stop-opacity="0" />
              <stop offset="100%" stop-color="#04060f" stop-opacity="0.5" />
            </radialGradient>
          </defs>
          <g clip-path="url(#dl-earth-clip)">
            <rect width="100" height="100" fill="#1a6fc6" />
            <!-- North America -->
            <path d="M30 16 Q47 12 53 25 Q57 35 46 41 Q40 43 34 42 Q23 41 20 31 Q17 20 30 16 Z" fill="#3f9d4d" />
            <!-- Central America -->
            <path d="M45 42 Q49 46 46 52 L41 50 Q40 45 45 42 Z" fill="#46a653" />
            <!-- South America (the tapering wedge) -->
            <path d="M46 52 Q56 54 54 64 Q51 79 43 88 Q39 79 38 67 Q38 56 46 52 Z" fill="#46a653" />
            <!-- a hint of land on the far side (Africa edge) -->
            <path d="M72 54 Q82 56 80 68 Q77 78 70 76 Q66 66 68 58 Q69 54 72 54 Z" fill="#3f9d4d" opacity="0.55" />
            <!-- wisps of cloud -->
            <ellipse cx="60" cy="30" rx="13" ry="4" fill="#ffffff" opacity="0.22" />
            <ellipse cx="34" cy="64" rx="11" ry="3.5" fill="#ffffff" opacity="0.18" />
          </g>
          <circle cx="50" cy="50" r="50" fill="url(#dl-earth-shade)" />
          <circle cx="50" cy="50" r="48.5" fill="none" stroke="#bfe2ff" stroke-width="2" opacity="0.4" />
        </svg>
        <!-- Mars: rust surface + darker maria + a white polar cap + 3D shade -->
        <svg v-else-if="o.type === 'mars'" class="planet-svg" viewBox="0 0 100 100" aria-hidden="true">
          <defs>
            <clipPath id="dl-mars-clip"><circle cx="50" cy="50" r="50" /></clipPath>
            <radialGradient id="dl-mars-shade" cx="35%" cy="30%" r="78%">
              <stop offset="0" stop-color="#ffffff" stop-opacity="0.4" />
              <stop offset="42%" stop-color="#ffffff" stop-opacity="0" />
              <stop offset="100%" stop-color="#1a0805" stop-opacity="0.5" />
            </radialGradient>
          </defs>
          <g clip-path="url(#dl-mars-clip)">
            <rect width="100" height="100" fill="#c0512e" />
            <ellipse cx="38" cy="46" rx="20" ry="11" fill="#9b3a20" opacity="0.7" />
            <ellipse cx="68" cy="66" rx="15" ry="9" fill="#9b3a20" opacity="0.6" />
            <ellipse cx="62" cy="30" rx="10" ry="6" fill="#a8442a" opacity="0.6" />
            <!-- polar ice cap -->
            <ellipse cx="50" cy="6" rx="18" ry="9" fill="#f4ede2" />
          </g>
          <circle cx="50" cy="50" r="50" fill="url(#dl-mars-shade)" />
        </svg>
      </span>
    </div>

    <!-- the starship, flying through the system (front of the scene; kept crisp + glowing so it
         stands out, with blinking lights, a graded warp trail, and an occasional warp jump) -->
    <div v-if="pg.oceanBoat" class="pg-ship">
      <!-- full-HD starship: hi-res viewBox (crisp), saucer with sheen + rim + bridge, neck,
           engineering hull + deflector, nacelle with grille + glowing bussard cap, graded trail -->
      <svg class="pg-ship-hull" width="50" height="18" viewBox="0 0 100 36" fill="currentColor" aria-hidden="true">
        <defs>
          <linearGradient id="dl-warp-trail" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stop-color="currentColor" stop-opacity="0.6" />
            <stop offset="1" stop-color="currentColor" stop-opacity="0" />
          </linearGradient>
          <!-- shade overlay → gives each hull part a lit top-left + shadowed bottom-right (3D) -->
          <radialGradient id="dl-shade" cx="34%" cy="26%" r="80%">
            <stop offset="0" stop-color="#ffffff" stop-opacity="0.55" />
            <stop offset="40%" stop-color="#ffffff" stop-opacity="0" />
            <stop offset="100%" stop-color="#000000" stop-opacity="0.4" />
          </radialGradient>
        </defs>
        <!-- warp trail (behind, to the right) -->
        <rect x="76" y="20.4" width="24" height="3" rx="1.5" fill="url(#dl-warp-trail)" />
        <!-- nacelle strut + nacelle (solid + 3D shade) + grille + glowing bussard cap -->
        <path d="M60 18 L72 10" stroke="currentColor" stroke-width="2.4" opacity="0.7" />
        <rect x="58" y="6.5" width="40" height="6" rx="3" />
        <rect x="58" y="6.5" width="40" height="6" rx="3" fill="url(#dl-shade)" />
        <rect x="62" y="8" width="28" height="1" rx="0.5" fill="#ffffff" opacity="0.2" />
        <circle class="ship-light" cx="60" cy="9.5" r="2.8" fill="#ffffff" style="animation-delay: .3s" />
        <!-- engineering hull (solid + 3D shade) + deflector dish -->
        <ellipse cx="60" cy="22" rx="20" ry="6" />
        <ellipse cx="60" cy="22" rx="20" ry="6" fill="url(#dl-shade)" />
        <circle class="ship-light" cx="42" cy="22" r="2.2" fill="#ffffff" style="animation-delay: .9s" />
        <!-- neck -->
        <path d="M34 15 L44 12 L50 20 L40 22 Z" opacity="0.85" />
        <!-- saucer (solid + 3D shade) + rim line + bridge dome (solid + shade) -->
        <ellipse cx="26" cy="12" rx="24" ry="7" />
        <ellipse cx="26" cy="12" rx="24" ry="7" fill="url(#dl-shade)" />
        <ellipse cx="26" cy="12" rx="24" ry="7" fill="none" stroke="currentColor" stroke-width="0.7" opacity="0.4" />
        <ellipse cx="26" cy="8" rx="5.5" ry="2.4" />
        <ellipse cx="26" cy="8" rx="5.5" ry="2.4" fill="url(#dl-shade)" />
        <!-- lucecitas (blink, staggered): bridge · two windows -->
        <circle class="ship-light" cx="26" cy="12"   r="2"   fill="#ffffff" style="animation-delay: 0s" />
        <circle class="ship-light" cx="15" cy="11.5" r="1.3" fill="#ffffff" style="animation-delay: 1.2s" />
        <circle class="ship-light" cx="36" cy="11.5" r="1.3" fill="#ffffff" style="animation-delay: 1.7s" />
      </svg>
    </div>
  </div>
</template>
