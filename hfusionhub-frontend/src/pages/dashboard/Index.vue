<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import {
  Activity,
  BookOpen,
  Check,
  CheckCircle2,
  Database,
  FileText,
  MessageSquare,
  Plus,
  Search,
  Sparkles,
  UploadCloud,
} from 'lucide-vue-next'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import * as documentApi from '@/api/document'
import * as conversationApi from '@/api/conversation'

type StatCard = {
  title: string
  value: number
  caption: string
  trend: string
  path: string
  icon: Component
  dotClass: string
  iconClass: string
  progressClass: string
}

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const loadError = ref(false)

const stats = ref<StatCard[]>([
  {
    title: '知识库',
    value: 0,
    caption: '已连接知识空间',
    trend: '--',
    path: '/knowledge-base',
    icon: BookOpen,
    dotClass: 'bg-emerald-400',
    iconClass: 'text-emerald-300',
    progressClass: 'bg-emerald-400',
  },
  {
    title: '文档',
    value: 0,
    caption: '已解析与可检索',
    trend: '--',
    path: '/document',
    icon: FileText,
    dotClass: 'bg-cyan-400',
    iconClass: 'text-cyan-300',
    progressClass: 'bg-cyan-400',
  },
  {
    title: '对话',
    value: 0,
    caption: '多轮问答会话',
    trend: '--',
    path: '/chat',
    icon: MessageSquare,
    dotClass: 'bg-violet-400',
    iconClass: 'text-violet-300',
    progressClass: 'bg-violet-400',
  },
  {
    title: '检索能力',
    value: 3,
    caption: '向量、关键词与图谱',
    trend: '可用',
    path: '/rag',
    icon: Activity,
    dotClass: 'bg-amber-400',
    iconClass: 'text-amber-300',
    progressClass: 'bg-amber-400',
  },
])

const clamp = (value: number, min = 8, max = 98) => Math.min(max, Math.max(min, value))
const userName = computed(() => userStore.nickname || userStore.username || 'HFusionHub 用户')
const todayLabel = computed(() => new Date().toLocaleDateString('zh-CN', {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
}))

const healthItems = computed(() => [
  {
    label: '知识资产',
    value: stats.value[0].value > 0 ? '已接入' : '待接入',
    icon: Database,
    tone: 'text-emerald-300',
  },
  {
    label: '文档索引',
    value: stats.value[1].value > 0 ? '可检索' : '待上传',
    icon: FileText,
    tone: 'text-cyan-300',
  },
  {
    label: '问答通道',
    value: stats.value[2].value > 0 ? '有会话' : '待开始',
    icon: MessageSquare,
    tone: 'text-violet-300',
  },
])

const onboardingSteps = computed(() => [
  {
    number: '01',
    title: '创建知识库',
    description: stats.value[0].value > 0 ? `已创建 ${stats.value[0].value} 个知识库` : '先创建一个用于组织资料的知识库',
    path: '/knowledge-base',
    icon: BookOpen,
    done: stats.value[0].value > 0,
  },
  {
    number: '02',
    title: '上传文档',
    description: stats.value[1].value > 0 ? `已接入 ${stats.value[1].value} 份文档` : '上传 PDF、Word 或 Markdown 文档',
    path: '/document',
    icon: UploadCloud,
    done: stats.value[1].value > 0,
  },
  {
    number: '03',
    title: '开始提问',
    description: stats.value[2].value > 0 ? `已开始 ${stats.value[2].value} 次对话` : '让 AI 基于你的资料回答问题',
    path: '/chat',
    icon: MessageSquare,
    done: stats.value[2].value > 0,
  },
])

const nextStep = computed(() => onboardingSteps.value.find((step) => !step.done) || onboardingSteps.value[2])

const quickActions = [
  { label: '新建知识库', path: '/knowledge-base', icon: Plus },
  { label: '上传文档', path: '/document', icon: UploadCloud },
  { label: '发起对话', path: '/chat', icon: MessageSquare },
]

const loadStats = async () => {
  loading.value = true
  loadError.value = false
  try {
    const [kbRes, docRes, convRes] = await Promise.all([
      knowledgeBaseApi.getMyKnowledgeBaseList({ page: 1, pageSize: 1 }),
      documentApi.getMyDocumentsByKbId(0, { page: 1, pageSize: 1 }),
      conversationApi.getMyConversations({ page: 1, pageSize: 1 }),
    ])
    stats.value[0].value = kbRes.data.total || 0
    stats.value[1].value = docRes.data.total || 0
    stats.value[2].value = convRes.data.total || 0
  } catch (error) {
    console.error('加载工作台统计失败', error)
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    await userStore.getUserInfo()
  } catch (error) {
    console.error('加载用户信息失败', error)
  }
  await loadStats()
})
</script>

<template>
  <div class="dashboard-workbench space-y-5">
    <section class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div class="min-w-0">
        <div class="mb-3 inline-flex items-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-xs font-medium text-emerald-300">
          <Sparkles class="h-3.5 w-3.5" />
          AI 工作台
        </div>
        <h2 class="text-3xl font-semibold text-zinc-50 sm:text-4xl">欢迎回来，{{ userName }}</h2>
        <p class="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">
          {{ todayLabel }}。从资料管理开始，让 AI 更准确地理解和回答你的问题。
        </p>
      </div>

      <div class="flex flex-wrap gap-2">
        <Button
          v-for="action in quickActions"
          :key="action.label"
          class="h-10 rounded-lg border border-white/10 bg-white/[0.06] px-3 text-zinc-100 hover:bg-white/[0.1]"
          @click="router.push(action.path)"
        >
          <component :is="action.icon" class="mr-2 h-4 w-4" />
          {{ action.label }}
        </Button>
      </div>
    </section>

    <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <button
        v-for="stat in stats"
        :key="stat.title"
        type="button"
        class="metric-card glass-panel-soft group text-left"
        @click="router.push(stat.path)"
      >
        <span class="flex items-center justify-between">
          <span class="flex items-center gap-2 text-sm text-zinc-400">
            <span :class="['h-2 w-2 rounded-full shadow-lg', stat.dotClass]" />
            {{ stat.title }}
          </span>
          <component :is="stat.icon" :class="['h-5 w-5', stat.iconClass]" />
        </span>
        <span class="mt-5 block text-3xl font-semibold text-zinc-50">
          {{ loading ? '--' : stat.value.toLocaleString() }}
        </span>
        <span class="mt-2 flex items-center justify-between text-xs text-zinc-500">
          <span>{{ stat.caption }}</span>
          <span class="text-emerald-300">{{ stat.trend }}</span>
        </span>
        <span class="mt-4 block h-1.5 overflow-hidden rounded-full bg-white/10">
          <span
            :class="['block h-full rounded-full transition-all duration-700', stat.progressClass]"
            :style="{ width: `${clamp(28 + stat.value * 8)}%` }"
          />
        </span>
      </button>
    </section>

    <section v-if="loadError" class="glass-panel flex items-center justify-between gap-4 p-4 text-sm text-amber-200">
      <span>统计数据加载失败，当前展示为占位状态。</span>
      <Button class="rounded-lg border border-amber-300/20 bg-amber-300/10 text-amber-100 hover:bg-amber-300/20" @click="loadStats">
        重试
      </Button>
    </section>

    <section class="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_23rem]">
      <div class="glass-panel p-5 sm:p-6">
        <div class="flex flex-col gap-2 border-b border-white/10 pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p class="text-xs font-medium uppercase tracking-[0.16em] text-emerald-300/80">Getting started</p>
            <h3 class="mt-1 text-xl font-semibold text-zinc-50">三步开始使用</h3>
          </div>
          <p class="text-sm text-zinc-500">把资料接入后，就可以开始问答。</p>
        </div>

        <div class="grid gap-3 py-5 md:grid-cols-3">
          <button
            v-for="step in onboardingSteps"
            :key="step.number"
            type="button"
            :class="['onboarding-step', step.done && 'is-done']"
            @click="router.push(step.path)"
          >
            <span class="flex items-center justify-between">
              <span class="onboarding-icon"><component :is="step.icon" class="h-5 w-5" /></span>
              <span v-if="step.done" class="onboarding-check"><Check class="h-3.5 w-3.5" /></span>
              <span v-else class="text-xs font-semibold tracking-widest text-zinc-600">{{ step.number }}</span>
            </span>
            <span class="mt-6 block text-left text-base font-semibold text-zinc-100">{{ step.title }}</span>
            <span class="mt-2 block text-left text-xs leading-5 text-zinc-500">{{ step.description }}</span>
            <span class="mt-5 block text-left text-xs font-medium" :class="step.done ? 'text-emerald-300' : 'text-zinc-400'">
              {{ step.done ? '已完成 · 查看' : '开始设置' }}
            </span>
          </button>
        </div>

        <div class="next-step-panel flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div class="flex items-start gap-3">
            <span class="next-step-icon"><Search class="h-5 w-5" /></span>
            <div>
              <p class="text-xs text-zinc-500">推荐下一步</p>
              <p class="mt-1 text-sm font-semibold text-zinc-100">{{ nextStep.title }}</p>
              <p class="mt-1 text-xs text-zinc-500">{{ nextStep.description }}</p>
            </div>
          </div>
          <Button class="shrink-0 rounded-lg bg-emerald-400 text-black hover:bg-emerald-300" @click="router.push(nextStep.path)">
            继续
          </Button>
        </div>
      </div>

      <aside class="space-y-5">
        <section class="glass-panel p-5">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-xs text-zinc-500">资料准备情况</p>
              <h3 class="mt-1 text-lg font-semibold text-zinc-50">当前概况</h3>
            </div>
            <CheckCircle2 class="h-5 w-5 text-emerald-300" />
          </div>
          <div class="mt-5 space-y-2">
            <div v-for="item in healthItems" :key="item.label" class="health-row">
              <span class="flex items-center gap-3 text-sm text-zinc-400">
                <component :is="item.icon" :class="['h-4 w-4', item.tone]" />
                {{ item.label }}
              </span>
              <span class="text-sm text-zinc-100">{{ item.value }}</span>
            </div>
          </div>
        </section>

        <section class="glass-panel p-5">
          <p class="text-xs text-zinc-500">你可以做什么</p>
          <h3 class="mt-1 text-lg font-semibold text-zinc-50">从资料到答案</h3>
          <p class="mt-3 text-sm leading-6 text-zinc-500">上传资料后，系统会自动解析并建立索引。你可以在对话中追问，并查看答案引用来源。</p>
          <button type="button" class="mt-4 inline-flex items-center text-sm font-medium text-emerald-300 hover:text-emerald-200" @click="router.push('/chat')">
            去提问 <span class="ml-1" aria-hidden="true">→</span>
          </button>
        </section>
      </aside>
    </section>
  </div>
</template>
