<script setup lang="ts">
import { X } from 'lucide-vue-next'

const { toasts, dismiss } = useToast()

const icon = (kind: string) => ({ success: '✓', error: '✕', info: 'ℹ', warn: '⚠' }[kind] || 'ℹ')

const borderClass = (kind: string) => ({
  success: 'border-l-2 border-l-status-success',
  error: 'border-l-2 border-l-status-error',
  warn: 'border-l-2 border-l-status-warning',
  info: 'border-l-2 border-l-status-info',
}[kind] || 'border-l-2 border-l-status-info')

const iconClass = (kind: string) => ({
  success: 'bg-status-success-bg text-status-success',
  error: 'bg-status-error-bg text-status-error',
  warn: 'bg-status-warning-bg text-status-warning',
  info: 'bg-status-info-bg text-status-info',
}[kind] || 'bg-status-info-bg text-status-info')
</script>

<template>
  <Teleport to="body">
    <div class="pointer-events-none fixed right-4 top-4 z-[70] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          role="status"
          class="pointer-events-auto grid grid-cols-[auto_1fr_auto] items-start gap-2.5 rounded-lg border border-border bg-popover px-3 py-2.5 text-sm text-popover-foreground shadow-lg"
          :class="borderClass(t.kind)"
        >
          <span class="inline-flex size-6 items-center justify-center rounded-full text-sm font-bold" :class="iconClass(t.kind)">{{ icon(t.kind) }}</span>
          <div class="min-w-0 leading-snug">
            <div class="font-medium">{{ t.message }}</div>
            <div v-if="t.detail" class="mt-0.5 break-words text-xs text-muted-foreground">{{ t.detail }}</div>
          </div>
          <button class="text-muted-foreground transition-colors hover:text-foreground" @click="dismiss(t.id)"><X class="size-4" /></button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-from { opacity: 0; transform: translateX(20px); }
.toast-enter-active, .toast-leave-active { transition: transform 0.18s ease, opacity 0.18s ease; }
.toast-leave-to { opacity: 0; transform: translateX(20px); }
</style>
