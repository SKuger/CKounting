<script setup lang="ts">
const { toasts, dismiss } = useToast()

const icon = (kind: string) => ({
  success: '✓',
  error: '✕',
  info: 'ℹ',
  warn: '⚠',
}[kind] || 'ℹ')
</script>

<template>
  <Teleport to="body">
    <div class="toast-stack" aria-live="polite">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          :class="['toast', `toast-${t.kind}`]"
          role="status"
        >
          <span class="toast-icon">{{ icon(t.kind) }}</span>
          <div class="toast-body">
            <div class="toast-title">{{ t.message }}</div>
            <div v-if="t.detail" class="toast-detail">{{ t.detail }}</div>
          </div>
          <button class="toast-close" @click="dismiss(t.id)">✕</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>
