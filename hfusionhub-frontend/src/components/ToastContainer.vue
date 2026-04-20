<template>
  <div class="fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm" role="status" aria-live="polite" aria-atomic="true">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        :class="[
          'px-4 py-3 rounded-lg shadow-lg text-sm text-white flex items-center gap-2',
          toast.type === 'success' && 'bg-green-600',
          toast.type === 'error' && 'bg-red-600',
          toast.type === 'warning' && 'bg-yellow-600 text-yellow-900',
          toast.type === 'info' && 'bg-blue-600',
        ]"
      >
        <span>{{ toast.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
import { useToast } from '@/composables/useToast'

const { toasts } = useToast()
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
