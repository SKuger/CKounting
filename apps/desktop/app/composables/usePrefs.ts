// usePrefs — REAL, persisted user preferences for the Dandelyon shell (issue #2).
//
// This is the design-system's DEFAULT preferences source: a module-singleton reactive store that
// persists to localStorage AND applies each pref to the DOM so it has actual effect (not decorative).
// A consuming app may ignore this and drive <SidebarUser :preferences> / @update:preferences from its
// own store instead — the component is prop-driven (see SidebarUser.vue).
//
// Effects (all on <html>): theme → .dark (+ follows the OS when "system"); density → data-density
// (existing shell skins); scale → root font-size (rem-based UI scales whole app); reduceMotion →
// data-reduce-motion (kills animations, main.css); highContrast → data-contrast (stronger borders);
// language → lang attr; region/notifications → persisted + read by the app (e.g. number/date format,
// muting the topbar bell).
import { reactive, watch } from 'vue'

export type Theme = 'light' | 'dark' | 'system'
export interface Prefs {
  theme: Theme
  density: 'amplia' | 'media' | 'compacta'
  scale: 'compacta' | 'normal' | 'grande'
  reduceMotion: boolean
  highContrast: boolean
  language: 'es' | 'en'
  region: 'es-CO' | 'es-MX' | 'es-ES' | 'en-US'
  notifications: boolean
}

// Option catalogs (id → label) so the UI and any consumer share one source.
export const PREF_THEMES   = [{ id: 'light', label: 'Claro' }, { id: 'dark', label: 'Oscuro' }, { id: 'system', label: 'Sistema' }] as const
export const PREF_DENSITIES = [{ id: 'amplia', label: 'Amplia' }, { id: 'media', label: 'Media' }, { id: 'compacta', label: 'Compacta' }] as const
export const PREF_SCALES    = [{ id: 'compacta', label: 'Pequeña' }, { id: 'normal', label: 'Normal' }, { id: 'grande', label: 'Grande' }] as const
export const PREF_LANGS      = [{ id: 'es', label: 'Español' }, { id: 'en', label: 'English' }] as const
export const PREF_REGIONS    = [{ id: 'es-CO', label: 'Colombia (es-CO)' }, { id: 'es-MX', label: 'México (es-MX)' }, { id: 'es-ES', label: 'España (es-ES)' }, { id: 'en-US', label: 'US (en-US)' }] as const

const SCALE_PX: Record<Prefs['scale'], string> = { compacta: '15px', normal: '16px', grande: '18px' }

// density default = 'compacta' (el look horneado de Contab; D-055). theme 'system' por defecto.
const DEFAULTS: Prefs = {
  theme: 'system', density: 'compacta', scale: 'normal',
  reduceMotion: false, highContrast: false,
  language: 'es', region: 'es-CO', notifications: true,
}

const PREFS_KEY = 'contab-user-prefs'
const THEME_KEY = 'contab-theme'   // shared with the FOUC guard in nuxt.config so reloads agree

const prefs = reactive<Prefs>({ ...DEFAULTS })
let started = false

function prefersDark() {
  return import.meta.client && window.matchMedia('(prefers-color-scheme: dark)').matches
}
function isDark() {
  return prefs.theme === 'dark' || (prefs.theme === 'system' && prefersDark())
}

function apply() {
  if (!import.meta.client) return
  const el = document.documentElement
  el.classList.toggle('dark', isDark())
  el.dataset.density = prefs.density
  el.dataset.reduceMotion = prefs.reduceMotion ? 'on' : 'off'
  el.dataset.contrast = prefs.highContrast ? 'high' : 'normal'
  el.style.fontSize = SCALE_PX[prefs.scale]
  el.setAttribute('lang', prefs.language)
  // keep the FOUC theme key in sync so a hard reload paints the right theme with no flash
  localStorage.setItem(THEME_KEY, isDark() ? 'dark' : 'light')
}

function persist() {
  if (import.meta.client) localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
}

export function usePrefs() {
  if (import.meta.client && !started) {
    started = true
    try {
      const saved = JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}')
      Object.assign(prefs, DEFAULTS, saved)
    } catch { /* ignore malformed prefs */ }
    apply()
    watch(prefs, () => { apply(); persist() }, { deep: true })
    // re-apply when the OS theme flips while we're following "system"
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (prefs.theme === 'system') apply() })
  }
  function setPref<K extends keyof Prefs>(key: K, value: Prefs[K]) { prefs[key] = value }
  function resetPrefs() { Object.assign(prefs, DEFAULTS) }
  return { prefs, setPref, resetPrefs }
}
