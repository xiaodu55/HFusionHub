<script setup lang="ts">
interface Props {
  title?: string
  message?: string
  showRetry?: boolean
  retryLabel?: string
}

withDefaults(defineProps<Props>(), {
  title: '加载失败',
  message: '数据加载出错，请稍后重试',
  showRetry: true,
  retryLabel: '重新加载',
})

const emit = defineEmits<{
  retry: []
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center py-16 px-4">
    <div class="flex h-20 w-20 items-center justify-center rounded-full bg-destructive/10">
      <svg class="h-10 w-10 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
      </svg>
    </div>
    <h3 class="mt-6 text-lg font-semibold text-foreground">{{ title }}</h3>
    <p class="mt-2 max-w-sm text-center text-sm text-muted-foreground">
      {{ message }}
    </p>
    <button
      v-if="showRetry"
      class="mt-6 inline-flex items-center gap-2 rounded-md border bg-card px-4 py-2 text-sm font-medium hover:bg-accent transition-colors"
      @click="emit('retry')"
    >
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
      </svg>
      {{ retryLabel }}
    </button>
  </div>
</template>
