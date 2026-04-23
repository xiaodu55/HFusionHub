<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BookOpen, Eye, EyeOff, MessageSquare, Sparkles } from 'lucide-vue-next'

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
  <div class="app-shell flex min-h-screen items-stretch">
    <!-- 左侧品牌区（移动端隐藏）— 固定深色背景，浅色主题下也保持可读 -->
    <div class="relative hidden w-[46%] flex-col justify-between overflow-hidden bg-gradient-to-br from-[#0e1512] to-[#060907] p-10 lg:flex xl:p-14">
      <div class="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-emerald-500/15 blur-3xl" />
      <div class="pointer-events-none absolute -bottom-28 -left-16 h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
      <div class="relative z-10">
        <div class="flex items-center gap-3">
          <span class="brand-mark">HF</span>
          <span class="text-left">
            <span class="block text-base font-semibold text-white">HFusionHub</span>
            <span class="block text-xs text-zinc-400">AI Knowledge OS</span>
          </span>
        </div>
      </div>

      <div class="relative z-10 max-w-md">
        <h1 class="text-3xl font-semibold leading-tight tracking-tight text-white xl:text-4xl">
          让 AI 基于<span class="text-emerald-400">你的资料</span>回答问题
        </h1>
        <p class="mt-4 text-sm leading-6 text-zinc-400">
          上传文档、建立知识库，即可获得带来源引用的智能问答；支持 Agent 任务、工具调用与多模型接入。
        </p>
        <ul class="mt-8 space-y-4 text-sm text-zinc-300">
          <li class="flex items-center gap-3">
            <span class="next-step-icon"><BookOpen class="h-4 w-4" /></span>
            知识库驱动的 RAG 问答，回答附带可追溯来源
          </li>
          <li class="flex items-center gap-3">
            <span class="next-step-icon"><MessageSquare class="h-4 w-4" /></span>
            多轮流式对话，支持停止、重试与反馈优化
          </li>
          <li class="flex items-center gap-3">
            <span class="next-step-icon"><Sparkles class="h-4 w-4" /></span>
            DeepSeek / Ollama 多模型，成本用量一目了然
          </li>
        </ul>
      </div>

      <p class="relative z-10 text-xs text-zinc-500">HFusionHub · Java + Python + Vue 企业级 AI Agent 平台</p>
    </div>

    <!-- 右侧登录表单区 -->
    <div class="flex flex-1 items-center justify-center p-4 sm:p-8">
      <div class="w-full max-w-md">
        <div class="mb-8 flex items-center gap-3 lg:hidden">
          <span class="brand-mark">HF</span>
          <span class="text-left">
            <span class="block text-base font-semibold text-foreground">HFusionHub</span>
            <span class="block text-xs text-muted-foreground">AI Knowledge OS</span>
          </span>
        </div>

        <h2 class="text-2xl font-semibold tracking-tight">欢迎回来</h2>
        <p class="mt-1 text-sm text-muted-foreground">登录以继续使用你的知识库与智能助手</p>

        <div v-if="registered" class="mt-5 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.08] px-4 py-3 text-sm text-emerald-600 dark:text-emerald-400">
          注册成功。登录后请联系管理员 admin 分配身份。
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
            <div class="flex items-center justify-between">
              <Label for="password">密码</Label>
            </div>
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

        <div class="mt-6 text-center text-sm text-muted-foreground">
          还没有账号？
          <Button variant="link" class="p-0" :disabled="loading" @click="goToRegister">
            立即注册
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
