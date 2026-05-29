<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { getSsoProviders } from '@/api/user'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BookOpen, CheckCircle2, Eye, EyeOff, MessageSquare, Sparkles } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const form = ref({
  username: '',
  password: '',
})
const showPassword = ref(false)
const loading = ref(false)
const error = ref('')
const registered = computed(() => route.query.registered === '1')

// SSO/OIDC —— 后端未启用或不可达时静默隐藏入口
const ssoEnabled = ref(false)
const ssoProviderName = ref('')

onMounted(async () => {
  try {
    const res = await getSsoProviders()
    ssoEnabled.value = Boolean(res.data?.enabled)
    ssoProviderName.value = res.data?.providerName || ''
  } catch {
    ssoEnabled.value = false
  }
})

const startSso = () => {
  // 整页跳转到后端 /user/sso/authorize（经 Vite/网关代理到 Java），
  // 由后端 302 至 IdP；登录完成后再回跳 /sso/callback?token=...
  window.location.href = '/api/user/sso/authorize'
}

const handleLogin = async () => {
  if (!form.value.username || !form.value.password) {
    error.value = '请输入用户名和密码'
    return
  }

  loading.value = true
  error.value = ''

  try {
    await userStore.login(form.value.username, form.value.password)
    router.push('/')
  } catch (e: any) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}

const goToRegister = () => {
  router.push('/register')
}
</script>

<template>
  <!-- 统一主题：背景渐变 + 光晕，玻璃卡片自动适配深浅色，无生硬分栏 -->
  <div class="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-4">
    <!-- 背景光晕与网格纹理 -->
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="absolute -top-32 left-1/2 h-80 w-[36rem] -translate-x-1/2 rounded-full bg-primary/15 blur-3xl" />
      <div class="absolute -bottom-40 -left-24 h-80 w-80 rounded-full bg-cyan-500/10 blur-3xl" />
      <div class="absolute -bottom-32 -right-24 h-72 w-72 rounded-full bg-emerald-500/10 blur-3xl" />
      <div class="absolute inset-0 opacity-[0.35] [background-image:linear-gradient(rgba(120,140,130,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(120,140,130,0.08)_1px,transparent_1px)] [background-size:56px_56px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,black,transparent)]" />
    </div>

    <div class="relative z-10 w-full max-w-md">
      <!-- 玻璃卡片（glass-panel 自动适配深浅主题） -->
      <div class="glass-panel rounded-2xl p-7 sm:p-9">
        <!-- 品牌 -->
        <div class="flex flex-col items-center text-center">
          <span class="brand-mark h-12 w-12 text-lg">HF</span>
          <h1 class="mt-4 text-xl font-semibold tracking-tight">HFusionHub</h1>
          <p class="mt-0.5 text-xs tracking-[0.18em] text-muted-foreground">AI KNOWLEDGE OS</p>
        </div>

        <h2 class="mt-7 text-center text-2xl font-semibold tracking-tight">欢迎回来</h2>
        <p class="mt-1.5 text-center text-sm text-muted-foreground">登录以继续使用你的知识库与智能助手</p>

        <div
          v-if="registered"
          class="mt-5 flex items-start gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.08] px-4 py-3 text-sm text-emerald-600 dark:text-emerald-400"
        >
          <CheckCircle2 class="mt-0.5 h-4 w-4 shrink-0" />
          <span>注册成功。登录后请联系管理员 admin 分配身份。</span>
        </div>

        <form class="mt-6 space-y-4" @submit.prevent="handleLogin">
          <div class="space-y-2">
            <Label for="username">用户名</Label>
            <Input
              id="username"
              v-model="form.username"
              placeholder="请输入用户名"
              autocomplete="username"
              :disabled="loading"
              @keyup.enter="handleLogin"
            />
          </div>
          <div class="space-y-2">
            <Label for="password">密码</Label>
            <div class="relative">
              <Input
                id="password"
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="请输入密码"
                autocomplete="current-password"
                :disabled="loading"
                class="pr-10"
                @keyup.enter="handleLogin"
              />
              <button
                type="button"
                class="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                :title="showPassword ? '隐藏密码' : '显示密码'"
                @click="showPassword = !showPassword"
              >
                <EyeOff v-if="showPassword" class="h-4 w-4" />
                <Eye v-else class="h-4 w-4" />
              </button>
            </div>
          </div>

          <div v-if="error" class="rounded-xl border border-destructive/25 bg-destructive/[0.08] px-4 py-3 text-sm text-destructive">
            {{ error }}
          </div>

          <Button class="w-full" type="submit" :disabled="loading">
            {{ loading ? '登录中...' : '登录' }}
          </Button>
        </form>

        <div v-if="ssoEnabled" class="mt-4">
          <div class="mb-3 flex items-center gap-3 text-xs text-muted-foreground">
            <span class="h-px flex-1 bg-border" />
            或使用 SSO 登录
            <span class="h-px flex-1 bg-border" />
          </div>
          <Button type="button" variant="outline" class="w-full" :disabled="loading" @click="startSso">
            {{ ssoProviderName || '企业身份' }} 单点登录
          </Button>
        </div>

        <div class="mt-6 text-center text-sm text-muted-foreground">
          还没有账号？
          <Button variant="link" class="p-0" :disabled="loading" @click="goToRegister">
            立即注册
          </Button>
        </div>
      </div>

      <!-- 轻量特性提示 -->
      <div class="mt-6 grid grid-cols-3 gap-2 text-center text-[11px] text-muted-foreground/80">
        <span class="flex items-center justify-center gap-1"><BookOpen class="h-3.5 w-3.5 text-primary/70" />知识库问答</span>
        <span class="flex items-center justify-center gap-1"><MessageSquare class="h-3.5 w-3.5 text-primary/70" />流式对话</span>
        <span class="flex items-center justify-center gap-1"><Sparkles class="h-3.5 w-3.5 text-primary/70" />多模型接入</span>
      </div>
    </div>
  </div>
</template>
