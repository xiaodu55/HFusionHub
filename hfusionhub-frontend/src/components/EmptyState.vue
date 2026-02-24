<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  /** Icon component from lucide-vue-next */
  icon?: any
  title?: string
  description?: string
  action?: string
  /** Whether to show a "create" action button */
  showAction?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '暂无数据',
  action: '创建',
  showAction: false,
})

const emit = defineEmits<{
  action: []
}>()

const description = computed(() => {
  return props.description || `还没有${props.title}，点击下方按钮${props.action}吧`
})
</script>

<template>
  <div class="flex flex-col items-center justify-center py-16 px-4">
    <div
      v-if="icon"
      class="flex h-20 w-20 items-center justify-center rounded-full bg-muted/50"
    >
      <component
        :is="icon"
        class="h-10 w-10 text-muted-foreground"
        :stroke-width="1.5"
      />
    </div>
    <div v-else class="flex h-20 w-20 items-center justify-center rounded-full bg-muted/50">
      <svg class="h-10 w-10 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
      </svg>
    </div>
    <h3 class="mt-6 text-lg font-semibold text-foreground">{{ title }}</h3>
    <p class="mt-2 max-w-sm text-center text-sm text-muted-foreground">
      {{ description }}
    </p>
    <button
      v-if="showAction"
      class="mt-6 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      @click="emit('action')"
    >
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
      </svg>
      {{ action }}
    </button>
  </div>
</template>
