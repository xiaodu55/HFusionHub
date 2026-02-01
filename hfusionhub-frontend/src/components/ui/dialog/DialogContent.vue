<script setup lang="ts">
import { inject, computed } from 'vue'
import { cn } from '@/lib/utils'
import { X } from 'lucide-vue-next'

interface Props {
  class?: string
}

const props = defineProps<Props>()

const dialogClose = inject<() => void>('dialog-close', () => {})

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <div
    :class="cn(
      'relative z-50 w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg',
      props.class
    )"
    v-bind="delegatedProps"
  >
    <slot />
    <button
      class="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
      @click="dialogClose"
    >
      <X class="h-4 w-4" />
      <span class="sr-only">关闭</span>
    </button>
  </div>
</template>
