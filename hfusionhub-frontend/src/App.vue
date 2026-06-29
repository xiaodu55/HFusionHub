<script setup lang="ts">
import { onMounted } from 'vue'
import ToastContainer from '@/components/ToastContainer.vue'
import { useTheme } from '@/composables/useTheme'

const { initializeTheme } = useTheme()

// 主题初始化必须在应用入口：MainLayout 只在登录后的页面渲染，
// 放在它里面会导致登录页永远不应用主题偏好（含默认暗色）
onMounted(() => {
  initializeTheme()
})
</script>

<template>
  <router-view />
  <ToastContainer />
</template>
