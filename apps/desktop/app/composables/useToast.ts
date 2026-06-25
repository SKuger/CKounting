type ToastKind = 'success' | 'error' | 'info' | 'warn'

export type Toast = {
  id: string
  kind: ToastKind
  message: string
  detail?: string
  createdAt: number
  ttlMs: number
}

const toasts = ref<Toast[]>([])

function makeId(): string {
  return Math.random().toString(36).slice(2, 9) + Date.now().toString(36)
}

function push(kind: ToastKind, message: string, opts: { detail?: string; ttlMs?: number } = {}) {
  if (!message) return
  const ttl = opts.ttlMs ?? (kind === 'error' ? 8000 : 4500)
  const t: Toast = {
    id: makeId(),
    kind,
    message,
    detail: opts.detail,
    createdAt: Date.now(),
    ttlMs: ttl,
  }
  toasts.value.push(t)
  if (ttl > 0) {
    setTimeout(() => dismiss(t.id), ttl)
  }
}

function dismiss(id: string) {
  const idx = toasts.value.findIndex((t) => t.id === id)
  if (idx >= 0) toasts.value.splice(idx, 1)
}

export function useToast() {
  return {
    toasts,
    success: (msg: string, detail?: string) => push('success', msg, { detail }),
    error: (msg: string, detail?: string) => push('error', msg, { detail }),
    info: (msg: string, detail?: string) => push('info', msg, { detail }),
    warn: (msg: string, detail?: string) => push('warn', msg, { detail }),
    push,
    dismiss,
  }
}
