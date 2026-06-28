import { reactive } from 'vue'

// Minimal baked-brand composable — the consumer-side replacement for the playground's
// `usePlayground()` store (consume-plan §3.2 / §5). It exposes ONLY the slice of the store
// API that the copied brand components read, with the Dandelyon · Órbita (Contabilidad)
// decisions baked in (RFC 0008, playground export 2026-06-28). No knobs, no Pinia.
export type SystemStatus = 'ok' | 'drift' | 'out'

// Singleton reactive state so a status change anywhere reflects everywhere (e.g. the ⌘K palette
// flips the beacon). Constants are baked; only systemStatus is mutable here. Theme/density/scale
// live in usePrefs() (issue #2) — the single source of truth for user preferences.
const brand = reactive({
  // ── Sub-brand lockup (Dandelyon · Órbita — Contabilidad) ──
  // Lockup = "Solo logo" → the glyph shows, the sub-NAME text is hidden (lockupMode 'logo').
  subGlyph: 'Orbit',
  subName: 'Órbita',
  subBrand: {
    descriptor: 'Contabilidad · libros y cierres',
    names: { functional: 'Contabilidad' },
  },
  lockupMode: 'logo' as 'none' | 'logo' | 'full',
  subNameAccent: false,
  subDescriptor: true,   // show the sublabel under the wordmark
  descriptorFull: true,  // sublabel = the full descriptor ("Contabilidad · libros y cierres")

  // ── Session block placement (Usuario · Sidebar · abajo) ──
  userPlacement: 'bottom' as 'bottom' | 'top',

  // ── Cosmos scene (Motivo cósmico: sí — nebulosa sí, nave sí) ──
  ocean: true,
  oceanFoam: true,
  oceanBoat: true,

  // ── Live system-health beacon (accent-independent status palette) ──
  systemStatus: 'ok' as SystemStatus,

  setSystemStatus(s: SystemStatus) {
    brand.systemStatus = s
    if (import.meta.client) document.documentElement.setAttribute('data-status', s)
  },
})

export function useBrand() {
  return brand
}
