<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

/**
 * SSO/OIDC 回调落地页：后端 /user/sso/callback 登录成功后回跳
 * {frontendRedirectUri}?token=<satoken>，这里落库 satoken → 拉取用户信息 → 路由。
 * token 缺失（如 state 过期/被拒）则回登录页。
 */
onMounted(async () => {
  const token = typeof route.query.token === 'string' ? route.query.token : ''
  if (!token) {
    router.replace({ path: '/login', query: { error: 'sso' } })
    return
  }
  userStore.setToken(token)
  try {
    await userStore.getUserInfo()
    router.replace(userStore.isPending ? '/pending-approval' : '/')
  } catch {
    userStore.clearToken()
    router.replace('/login')
  }
})
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-background p-4">
    <div class="glass-panel rounded-2xl p-7 text-center">
      <p class="text-sm text-muted-foreground">SSO 登录中…</p>
    </div>
  </div>
</template>
