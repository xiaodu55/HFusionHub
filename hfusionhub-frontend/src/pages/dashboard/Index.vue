<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import { useToast } from '@/composables/useToast'
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
  Cpu,
  Wrench,
  Fingerprint,
  User,
  StickyNote,
  DollarSign,
  Cable,
  Rocket,
  GitBranch,
  Megaphone,
  Package,
} from 'lucide-vue-next'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import * as documentApi from '@/api/document'
import * as conversationApi from '@/api/conversation'
import { getAiHealth } from '@/api/system'
import SetupChecklist from '@/components/setup/SetupChecklist.vue'

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
const route = useRoute()
const userStore = useUserStore()
const toast = useToast()
const loading = ref(false)
const loadError = ref(false)
const loadErrorMessage = ref('')
const aiReady = ref<boolean | null>(null)

const stats = ref<StatCard[]>([
  {
    title: '知识库',
    value: 0,
    caption: '已连接知识空间',
    trend: '--',
    path: '/knowledge-base',
    icon: BookOpen,
    dotClass: 'bg-emerald-400',
    iconClass: 'text-emerald-700 dark:text-emerald-700 dark:text-emerald-300',
    progressClass: 'bg-emerald-400',
  },
  {
    title: '文档',
    value: 0,
    caption: '名下文档（含待解析）',
    trend: '--',
    path: '/document',
    icon: FileText,
    dotClass: 'bg-cyan-400',
    iconClass: 'text-cyan-700 dark:text-cyan-300',
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
    iconClass: 'text-violet-700 dark:text-violet-300',
    progressClass: 'bg-violet-400',
  },
  {
    title: '检索能力',
    // 检索架构常量：P5 混合检索 = 向量 + 关键词共 2 条通道（GraphRAG 已移除）
    value: 2,
    caption: '向量与关键词混合通道（默认开启）',
    trend: '—',
    path: '/rag',
    icon: Activity,
    dotClass: 'bg-amber-400',
    iconClass: 'text-amber-700 dark:text-amber-300',
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
    label: 'AI 服务',
    value: aiReady.value === null ? '检测中…' : aiReady.value ? '已连接' : '未连接',
    icon: Sparkles,
    tone: aiReady.value === true ? 'text-emerald-700 dark:text-emerald-700 dark:text-emerald-300' : aiReady.value === false ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground',
  },
  {
    label: '知识资产',
    value: stats.value[0].value > 0 ? '已接入' : '待接入',
    icon: Database,
    tone: 'text-emerald-700 dark:text-emerald-700 dark:text-emerald-300',
  },
  {
    label: '文档索引',
    value: stats.value[1].value > 0 ? '已上传' : '待上传',
    icon: FileText,
    tone: 'text-cyan-700 dark:text-cyan-300',
  },
  {
    label: '问答通道',
    value: stats.value[2].value > 0 ? '有会话' : '待开始',
    icon: MessageSquare,
    tone: 'text-violet-700 dark:text-violet-300',
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

const moreLinks = [
  { label: '我的模型', path: '/builder/models', icon: Cpu },
  { label: 'AI 能力', path: '/builder/tools', icon: Wrench },
  { label: 'MCP 服务', path: '/builder/mcp', icon: Cable },
  { label: '应用发布', path: '/builder/apps', icon: Rocket },
  { label: '运行记录', path: '/agent', icon: Sparkles },
  { label: '待确认操作', path: '/approvals', icon: Fingerprint },
  { label: '我的记忆', path: '/memory', icon: User },
  { label: '我的笔记', path: '/notes', icon: StickyNote },
  { label: '模型用量', path: '/cost', icon: DollarSign },
  { label: '问题分流', path: '/admin/intent-tree', icon: GitBranch },
  { label: '公告管理', path: '/admin/notices', icon: Megaphone },
  { label: '套餐管理', path: '/admin/plans', icon: Package },
]

// 六色柔和渐变循环:每个功能磁贴有专属色调,呼应统计卡的彩色圆点
const TILE_TINTS = [
  "from-emerald-500/20 to-emerald-500/5 text-emerald-600 dark:text-emerald-300",
  "from-sky-500/20 to-sky-500/5 text-sky-600 dark:text-sky-300",
  "from-violet-500/20 to-violet-500/5 text-violet-600 dark:text-violet-300",
  "from-amber-500/20 to-amber-500/5 text-amber-600 dark:text-amber-300",
  "from-rose-500/20 to-rose-500/5 text-rose-600 dark:text-rose-300",
  "from-cyan-500/20 to-cyan-500/5 text-cyan-600 dark:text-cyan-300",
]
const tileTint = (i: number) => TILE_TINTS[i % TILE_TINTS.length]

const quickActions = [
  { label: '新建知识库', path: '/knowledge-base', icon: Plus },
  { label: '上传文档', path: '/document', icon: UploadCloud },
  { label: '发起对话', path: '/chat', icon: MessageSquare },
]

const loadStats = async () => {
  loading.value = true
  loadError.value = false
  try {
    const [kbRes, docRes, convRes, healthRes] = await Promise.all([
      knowledgeBaseApi.getMyKnowledgeBaseList({ page: 1, pageSize: 1 }),
      documentApi.getMyDocumentsByKbId(0, { page: 1, pageSize: 1 }),
      conversationApi.getMyConversations({ page: 1, pageSize: 1 }),
      getAiHealth().catch(() => null),
    ])
    stats.value[0].value = kbRes.data.total || 0
    stats.value[1].value = docRes.data.total || 0
    stats.value[2].value = convRes.data.total || 0
    aiReady.value = healthRes ? !!healthRes.data.ready : false
  } catch (error) {
    console.error('加载工作台统计失败', error)
    loadError.value = true
    loadErrorMessage.value = error instanceof Error ? error.message : '网络或服务异常'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (route.query.access === 'denied') {
    toast.error('当前账号没有访问该页面的权限')
  }
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
    <SetupChecklist />

    <section class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div class="min-w-0">
        <h2 class="text-3xl font-semibold text-foreground sm:text-4xl">欢迎回来，{{ userName }}</h2>
        <p class="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          {{ todayLabel }}。从资料管理开始，让 AI 更准确地理解和回答你的问题。
        </p>
      </div>

      <div class="flex flex-wrap gap-2">
        <Button
          v-for="action in quickActions"
          :key="action.label"
          class="h-10 rounded-lg border border-border bg-card px-3 text-foreground hover:bg-accent"
          @click="router.push(action.path)"
        >
          <component :is="action.icon" class="mr-2 h-4 w-4" />
          {{ action.label }}
        </Button>
      </div>
    </section>

    <section class="glass-panel-soft rounded-2xl p-5">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="flex items-center gap-2 text-sm font-medium text-foreground">
          <span class="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400/50" />
          更多功能
        </h3>
        <span class="rounded-full bg-foreground/5 px-2.5 py-0.5 text-xs text-muted-foreground">
          {{ moreLinks.length }} 项
        </span>
      </div>
      <div class="grid grid-cols-3 gap-2.5 sm:grid-cols-4 lg:grid-cols-6">
        <router-link
          v-for="(link, i) in moreLinks"
          :key="link.path"
          :to="link.path"
          class="group flex flex-col items-center gap-2.5 rounded-2xl border border-border/40 bg-card/50 px-2 py-4 text-muted-foreground shadow-sm backdrop-blur-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-border hover:bg-card hover:text-foreground hover:shadow-lg hover:shadow-foreground/5"
        >
          <span
            :class="[
              'flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br shadow-sm transition-transform duration-300 group-hover:scale-110',
              tileTint(i),
            ]"
          >
            <component :is="link.icon" class="h-[18px] w-[18px]" />
          </span>
          <span class="text-center text-xs font-medium leading-none">{{ link.label }}</span>
        </router-link>
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
          <span class="flex items-center gap-2 text-sm text-muted-foreground">
            <span :class="['h-2 w-2 rounded-full shadow-lg', stat.dotClass]" />
            {{ stat.title }}
          </span>
          <component :is="stat.icon" :class="['h-5 w-5', stat.iconClass]" />
        </span>
        <span class="mt-5 block text-3xl font-semibold tabular-nums tracking-tight text-foreground">
          {{ loading ? '--' : stat.value.toLocaleString() }}
        </span>
        <span class="mt-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>{{ stat.caption }}</span>
          <span class="text-emerald-700 dark:text-emerald-300">{{ stat.trend }}</span>
        </span>
        <span class="mt-4 block h-1.5 overflow-hidden rounded-full bg-foreground/10">
          <span
            :class="['block h-full rounded-full transition-all duration-700', stat.progressClass]"
            :style="{ width: `${clamp(28 + stat.value * 8)}%` }"
          />
        </span>
      </button>
    </section>

    <section v-if="loadError" class="glass-panel flex flex-col gap-3 p-4 text-sm text-amber-800 dark:text-amber-200 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <p>统计数据读取失败，下方数字可能不是最新的。</p>
        <p v-if="loadErrorMessage" class="mt-1 truncate text-xs text-amber-800/70 dark:text-amber-200/70">原因：{{ loadErrorMessage }}</p>
      </div>
      <Button class="shrink-0 rounded-lg border border-amber-300/20 bg-amber-300/10 text-amber-800 hover:bg-amber-300/20 dark:text-amber-100" :disabled="loading" @click="loadStats">
        {{ loading ? '正在重试…' : '重试' }}
      </Button>
    </section>

    <section class="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_23rem]">
      <div class="glass-panel p-5 sm:p-6">
        <div class="flex flex-col gap-2 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p class="text-xs font-medium uppercase tracking-[0.16em] text-emerald-700/80 dark:text-emerald-300/80">Getting started</p>
            <h3 class="mt-1 text-xl font-semibold text-foreground">三步开始使用</h3>
          </div>
          <p class="text-sm text-muted-foreground">把资料接入后，就可以开始问答。</p>
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
              <span v-else class="text-xs font-semibold tracking-widest text-muted-foreground/70">{{ step.number }}</span>
            </span>
            <span class="mt-6 block text-left text-base font-semibold text-foreground">{{ step.title }}</span>
            <span class="mt-2 block text-left text-xs leading-5 text-muted-foreground">{{ step.description }}</span>
            <span class="mt-5 block text-left text-xs font-medium" :class="step.done ? 'text-emerald-700 dark:text-emerald-300' : 'text-muted-foreground'">
              {{ step.done ? '已完成 · 查看' : '开始设置' }}
            </span>
          </button>
        </div>

        <div class="next-step-panel flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div class="flex items-start gap-3">
            <span class="next-step-icon"><Search class="h-5 w-5" /></span>
            <div>
              <p class="text-xs text-muted-foreground">推荐下一步</p>
              <p class="mt-1 text-sm font-semibold text-foreground">{{ nextStep.title }}</p>
              <p class="mt-1 text-xs text-muted-foreground">{{ nextStep.description }}</p>
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
              <p class="text-xs text-muted-foreground">资料准备情况</p>
              <h3 class="mt-1 text-lg font-semibold text-foreground">当前概况</h3>
            </div>
            <CheckCircle2 class="h-5 w-5 text-emerald-700 dark:text-emerald-300" />
          </div>
          <div class="mt-5 space-y-2">
            <div v-for="item in healthItems" :key="item.label" class="health-row">
              <span class="flex items-center gap-3 text-sm text-muted-foreground">
                <component :is="item.icon" :class="['h-4 w-4', item.tone]" />
                {{ item.label }}
              </span>
              <span class="text-sm text-foreground">{{ item.value }}</span>
            </div>
          </div>
        </section>

        <section class="glass-panel p-5">
          <p class="text-xs text-muted-foreground">你可以做什么</p>
          <h3 class="mt-1 text-lg font-semibold text-foreground">从资料到答案</h3>
          <p class="mt-3 text-sm leading-6 text-muted-foreground">上传资料后，系统会自动解析并建立索引。你可以在对话中追问，并查看答案引用来源。</p>
          <button type="button" class="mt-4 inline-flex items-center text-sm font-medium text-emerald-700 hover:text-emerald-600 dark:text-emerald-300 dark:hover:text-emerald-200" @click="router.push('/chat')">
            去提问 <span class="ml-1" aria-hidden="true">→</span>
          </button>
        </section>
      </aside>
    </section>
  </div>
</template>
