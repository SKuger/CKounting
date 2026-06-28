// useUser — the design-system's DEFAULT account source for <SidebarUser> (issue #2).
//
// Multi-account: a list of saved profiles + the active one, switchable and editable, persisted to
// localStorage. A consuming app can ignore this and pass <SidebarUser :user :profiles> from its own
// auth/session instead (the component is prop-driven; this is just the standalone fallback).
import { reactive, computed, watch } from 'vue'

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

// Contab es single-user sin auth (D-004): no hay backend de sesión, así que este localStorage ES
// la fuente real. Sembramos UNA cuenta neutra editable (sin personas demo del DS); el usuario la
// edita y puede añadir/eliminar más desde el panel de SidebarUser.
const DEFAULT_PROFILES: Profile[] = [
  { id: 'principal', name: 'Mi cuenta', email: '', role: 'Contabilidad' },
]

const KEY = 'contab-user-accounts'

const state = reactive<{ profiles: Profile[]; activeId: string }>({
  profiles: DEFAULT_PROFILES.map(p => ({ ...p })),
  activeId: DEFAULT_PROFILES[0].id,
})
let started = false

function slugify(s: string) {
  return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}
function persist() { if (import.meta.client) localStorage.setItem(KEY, JSON.stringify({ profiles: state.profiles, activeId: state.activeId })) }

export function useUser() {
  if (import.meta.client && !started) {
    started = true
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) ?? 'null')
      if (saved && Array.isArray(saved.profiles) && saved.profiles.length) {
        state.profiles = saved.profiles
        state.activeId = saved.profiles.some((p: Profile) => p.id === saved.activeId) ? saved.activeId : saved.profiles[0].id
      }
    } catch { /* ignore */ }
    watch(state, persist, { deep: true })
  }

  const active = computed<Profile>(() => state.profiles.find(p => p.id === state.activeId) ?? state.profiles[0])

  function setActive(id: string) { if (state.profiles.some(p => p.id === id)) state.activeId = id }

  // edit the active profile in place (name/email/role)
  function updateActive(patch: Partial<Omit<Profile, 'id'>>) {
    const p = state.profiles.find(x => x.id === state.activeId)
    if (p) Object.assign(p, patch)
  }

  // add a new account (and switch to it). id is slugged from the email/name with a collision suffix.
  function addAccount(input: { name: string; email: string; role?: string }) {
    const name = (input.name ?? '').trim()
    const email = (input.email ?? '').trim()
    if (!email) return null
    const base = `acct-${slugify(email.split('@')[0] || name) || 'user'}`
    const taken = new Set(state.profiles.map(p => p.id))
    let id = base, n = 2
    while (taken.has(id)) id = `${base}-${n++}`
    state.profiles.push({ id, name: name || email.split('@')[0], email, role: input.role })
    state.activeId = id
    return id
  }

  function removeAccount(id: string) {
    if (state.profiles.length <= 1) return            // never remove the last account
    state.profiles = state.profiles.filter(p => p.id !== id)
    if (state.activeId === id) state.activeId = state.profiles[0].id
  }

  return { profiles: computed(() => state.profiles), active, activeId: computed(() => state.activeId), setActive, updateActive, addAccount, removeAccount }
}
