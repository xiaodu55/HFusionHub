<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

/**
 * SSO/OIDC 回调落地页：后端 /user/sso/callback 登录成功后回跳
 * {frontendRedirectUri}#token=<satoken>，这里落库 satoken → 拉取用户信息 → 路由。
 * token 缺失（如 state 过期/被拒）则回登录页。
 */
onMounted(async () => {
  // 后端 302 以 fragment（#token=...）携带会话令牌——fragment 不进浏览器历史、
  // 代理日志与 Referer；query.token 仅作灰度期旧链接兜底。
  let token = ''
  const hash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : ''
  if (hash.includes('token=')) {
    token = new URLSearchParams(hash).get('token') ?? ''
    // 从地址栏/历史中立即清除令牌
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }
  if (!token && typeof route.query.token === 'string') {
    token = route.query.token
  }
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
