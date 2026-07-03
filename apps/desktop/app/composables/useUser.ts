// useUser — perfil ÚNICO de Contab (D-004, sin auth), persistido en la BD del programa (contab.db)
// vía program_get_user / program_save_user (T2.1). contab.db es la fuente de verdad y sobrevive al
// cierre del programa; localStorage es solo una caché para pintar al instante antes de que responda
// el sidecar. La sub-marca del design system usa <SidebarUser :user> para inyectar su propia sesión.
import { reactive, computed, watch } from 'vue'
import { rpc } from './useRpc'

export interface Profile {
  id: string
  name: string
  email: string
  role?: string
}

// initials from a name ("Carlos Kuger" → "CK"); falls back to the email's first letter.
export function initialsOf(p: Pick<Profile, 'name' | 'email'>) {
  const parts = (p.name || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  if (parts.length === 1 && parts[0]) return parts[0].slice(0, 2).toUpperCase()
  return (p.email || '?').slice(0, 2).toUpperCase()
}

const CACHE_KEY = 'contab-user'
const DEFAULT: Profile = { id: 'principal', name: 'Mi cuenta', email: '', role: 'Contabilidad' }

const state = reactive<Profile>({ ...DEFAULT })
let started = false

function cache() {
  if (import.meta.client) localStorage.setItem(CACHE_KEY, JSON.stringify(state))
}

async function loadFromDb() {
  try {
    const r = await rpc<{ user: { name: string; email: string } | null }>('program_get_user')
    if (r?.user) {
      if (r.user.name) state.name = r.user.name
      state.email = r.user.email ?? state.email
      cache()
    }
  } catch {
    /* el sidecar aún no responde: seguimos con la caché/el default */
  }
}

export function useUser() {
  if (import.meta.client && !started) {
    started = true
    try {
      const c = JSON.parse(localStorage.getItem(CACHE_KEY) ?? 'null')
      if (c && typeof c === 'object') Object.assign(state, c)
    } catch { /* caché malformada: ignorar */ }
    loadFromDb()
    watch(state, cache, { deep: true })
  }

  const active = computed<Profile>(() => state)

  // Edita el perfil y lo persiste en contab.db (name/email). `role` es local (cosmético).
  function updateActive(patch: Partial<Omit<Profile, 'id'>>) {
    Object.assign(state, patch)
    cache()
    if (import.meta.client) rpc('program_save_user', { name: state.name, email: state.email }).catch(() => {})
  }

  return { active, updateActive }
}
