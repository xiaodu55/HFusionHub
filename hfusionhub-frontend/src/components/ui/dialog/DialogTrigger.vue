<script setup lang="ts">
import { inject } from 'vue'

const dialogOpen = inject<() => void>('dialog-open', () => {})

const handleClick = () => {
  // DialogTrigger 通常用于打开对话框
  // 这里通过父组件的 v-model:open 控制
}
</script>

<template>
  <div @click="handleClick">
    <slot />
  </div>
</template>
