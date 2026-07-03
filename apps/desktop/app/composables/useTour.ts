// useTour — motor de tutoriales interactivos (coach-marks con spotlight). Estado singleton para que
// el overlay global (TourGuide, montado en el layout) y cualquier página compartan el mismo tour.
// Cada paso apunta a un elemento real por selector (usar atributos data-tour="…" en las vistas).
import { reactive } from 'vue'

export type TourStep = {
  target?: string // selector CSS del elemento a resaltar; si falta, el paso va centrado
  title: string
  body: string
}

const state = reactive<{ active: boolean; steps: TourStep[]; index: number; tourId: string | null }>({
  active: false,
  steps: [],
  index: 0,
  tourId: null,
})

const SEEN_PREFIX = 'contab-tour-'

export function useTour() {
  function start(steps: TourStep[], tourId = '') {
    if (!steps.length) return
    state.steps = steps
    state.index = 0
    state.tourId = tourId || null
    state.active = true
  }
  function next() {
    if (state.index < state.steps.length - 1) state.index++
    else stop()
  }
  function prev() {
    if (state.index > 0) state.index--
  }
  function stop() {
    if (state.tourId) {
      try { localStorage.setItem(SEEN_PREFIX + state.tourId, 'done') } catch { /* ignore */ }
    }
    state.active = false
    state.steps = []
    state.index = 0
    state.tourId = null
  }
  function seen(tourId: string): boolean {
    try { return localStorage.getItem(SEEN_PREFIX + tourId) === 'done' } catch { return false }
  }
  return { state, start, next, prev, stop, seen }
}
