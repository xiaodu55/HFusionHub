<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="flex flex-col items-center justify-center py-16 px-4">
    <div class="flex h-20 w-20 items-center justify-center rounded-full bg-muted">
      <svg class="h-10 w-10 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          d="M12 21a9 9 0 100-18 9 9 0 000 18zm0 0v-4m0 0h.01M9 9.5c0-1 .9-2 2.2-2 1.2 0 2.3.7 2.3 1.9 0 1.9-2.5 1.7-2.5 3.4"
        />
      </svg>
    </div>
    <h3 class="mt-6 text-lg font-semibold text-foreground">页面不存在</h3>
    <p class="mt-2 max-w-sm text-center text-sm text-muted-foreground">
      你访问的地址不存在或已被移动，请检查链接是否正确。
    </p>
    <button
      class="mt-6 inline-flex items-center gap-2 rounded-md border bg-card px-4 py-2 text-sm font-medium hover:bg-accent transition-colors"
      @click="router.push('/')"
    >
      返回首页
    </button>
  </div>
</template>
