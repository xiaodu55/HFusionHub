<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Clock3, LogOut, RefreshCw, ShieldCheck } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

const router = useRouter()
const userStore = useUserStore()
const refreshing = ref(false)
const message = ref('')
const lastChecked = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

async function refreshStatus() {
  refreshing.value = true
  message.value = ''
  try {
    await userStore.getUserInfo()
    if (userStore.isApproved) {
      if (pollTimer) clearInterval(pollTimer)
      await router.replace('/')
      return
    }
    lastChecked.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    message.value = '管理员尚未分配身份，系统每 30 秒自动检查一次。'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '状态刷新失败'
  } finally {
    refreshing.value = false
  }
}

async function logout() {
  if (pollTimer) clearInterval(pollTimer)
  await userStore.logout()
  await router.replace('/login')
}

onMounted(() => {
  pollTimer = setInterval(() => {
    // 静默轮询，避免打断页面
    userStore.getUserInfo().then(() => {
      if (userStore.isApproved) {
        if (pollTimer) clearInterval(pollTimer)
        void router.replace('/')
      }
    }).catch(() => {})
  }, 30000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <main class="flex min-h-screen items-center justify-center bg-background p-4">
    <Card class="w-full max-w-xl border-primary/20">
      <CardHeader class="items-center text-center">
        <div class="mb-3 flex h-14 w-14 items-center justify-center rounded-full border border-amber-400/25 bg-amber-400/10 text-amber-500">
          <Clock3 class="h-7 w-7" />
        </div>
        <CardTitle class="text-2xl">账号等待管理员分配</CardTitle>
        <CardDescription class="max-w-md leading-6">
          您已经登录成功，但当前还没有业务身份。管理员分配完成后，系统会自动开放对应功能。
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="rounded-lg border border-border bg-muted/30 p-4">
          <p class="text-sm font-medium">当前账号</p>
          <p class="mt-1 text-sm text-muted-foreground">{{ userStore.nickname || userStore.username }}（{{ userStore.username }}）</p>
        </div>
        <div class="flex gap-3 rounded-lg border border-primary/20 bg-primary/[0.05] p-4">
          <ShieldCheck class="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div class="text-sm leading-6">
            <p class="font-medium">下一步怎么做</p>
            <p class="text-muted-foreground">联系管理员 <strong class="text-foreground">admin</strong>，提供您的用户名。管理员在“用户与权限”中选择普通用户或 AI 配置员并保存。</p>
          </div>
        </div>
        <p v-if="message" class="text-center text-sm text-muted-foreground">{{ message }}<span v-if="lastChecked" class="block text-xs opacity-80">上次检查：{{ lastChecked }}</span></p>
      </CardContent>
      <CardFooter class="flex flex-col gap-3 sm:flex-row">
        <Button class="w-full gap-2" :disabled="refreshing" @click="refreshStatus">
          <RefreshCw class="h-4 w-4" :class="refreshing && 'animate-spin'" />
          {{ refreshing ? '正在检查...' : '刷新审批状态' }}
        </Button>
        <Button variant="outline" class="w-full gap-2" @click="logout">
          <LogOut class="h-4 w-4" />退出登录
        </Button>
      </CardFooter>
    </Card>
  </main>
</template>
