<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import {
  Activity,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  MessageSquare,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Zap,
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

type WorkTask = {
  id: string
  code: string
  title: string
  caption: string
  status: string
  schedule: string
  owner: string
  progress: number
  route: string
  icon: Component
  tone: 'green' | 'cyan' | 'amber' | 'violet'
}

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const loadError = ref(false)
const selectedTaskId = ref('document-index')

const stats = ref<StatCard[]>([
  {
    title: '知识库',
    value: 0,
    caption: '已接入知识空间',
    trend: '+20%',
    path: '/knowledge-base',
    icon: BookOpen,
    dotClass: 'bg-emerald-400',
    iconClass: 'text-emerald-300',
    progressClass: 'bg-emerald-400',
  },
  {
    title: '文档',
    value: 0,
    caption: '解析与索引对象',
    trend: '+18%',
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
    trend: '+9%',
    path: '/chat',
    icon: MessageSquare,
    dotClass: 'bg-violet-400',
    iconClass: 'text-violet-300',
    progressClass: 'bg-violet-400',
  },
  {
    title: 'RAG',
    value: 3,
    caption: '检索链路能力',
    trend: '稳定',
    path: '/rag',
    icon: Activity,
    dotClass: 'bg-amber-400',
    iconClass: 'text-amber-300',
    progressClass: 'bg-amber-400',
  },
])

const clamp = (value: number, min = 8, max = 98) => Math.min(max, Math.max(min, value))

const userName = computed(() => userStore.nickname || userStore.username || 'HFusionHub 用户')

const todayLabel = computed(() =>
  new Date().toLocaleDateString('zh-CN', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
)

const workflowProgress = computed(() => {
  const [kb, docs, conversations] = stats.value
  return clamp(46 + kb.value * 5 + docs.value * 2 + conversations.value)
})

const taskCards = computed<WorkTask[]>(() => {
  const [kb, docs, conversations] = stats.value
  return [
    {
      id: 'knowledge-governance',
      code: 'KB-2026-001',
      title: '知识库治理',
      caption: `${kb.value} 个知识空间待持续维护`,
      status: kb.value > 0 ? '进行中' : '待创建',
      schedule: '今天 10:00',
      owner: 'Knowledge',
      progress: clamp(52 + kb.value * 6),
      route: '/knowledge-base',
      icon: BookOpen,
      tone: 'green',
    },
    {
      id: 'document-index',
      code: 'DOC-2026-024',
      title: '文档解析与索引',
      caption: `${docs.value} 份文档进入检索资产池`,
      status: docs.value > 0 ? '解析中' : '待上传',
      schedule: '今天 14:00',
      owner: 'Index',
      progress: clamp(45 + docs.value * 4),
      route: '/document',
      icon: FileText,
      tone: 'cyan',
    },
    {
      id: 'rag-evaluation',
      code: 'RAG-2026-030',
      title: '检索质量评估',
      caption: '观察召回、重排与回答质量',
      status: '待验证',
      schedule: '明天 09:30',
      owner: 'RAG',
      progress: 64,
      route: '/rag',
      icon: Search,
      tone: 'amber',
    },
    {
      id: 'assistant-chat',
      code: 'CHAT-2026-056',
      title: '智能问答体验',
      caption: `${conversations.value} 个会话沉淀用户反馈`,
      status: conversations.value > 0 ? '已完成' : '待启动',
      schedule: '持续运行',
      owner: 'Agent',
      progress: clamp(58 + conversations.value * 3),
      route: '/chat',
      icon: MessageSquare,
      tone: 'violet',
    },
  ]
})

const activeTask = computed(() =>
  taskCards.value.find((task) => task.id === selectedTaskId.value) || taskCards.value[0]
)

const timeline = computed(() => [
  {
    time: '09:00',
    label: '知识库更新',
    description: `${stats.value[0].value} 个空间可用于检索`,
    tone: 'green',
  },
  {
    time: '10:30',
    label: '文档索引',
    description: `${stats.value[1].value} 份文档等待质量巡检`,
    tone: 'cyan',
  },
  {
    time: '14:00',
    label: 'RAG 验证',
    description: '执行召回率与答案一致性检查',
    tone: 'amber',
  },
])

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
    value: stats.value[2].value > 0 ? '有会话' : '待启动',
    icon: MessageSquare,
    tone: 'text-violet-300',
  },
])

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
    console.error('加载工作台统计失败:', error)
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    await userStore.getUserInfo()
  } catch (error) {
    console.error('加载用户信息失败:', error)
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
        <h2 class="text-3xl font-semibold text-zinc-50 sm:text-4xl">任务管理</h2>
        <p class="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">
          {{ userName }}，{{ todayLabel }}。集中查看知识库、文档索引、智能对话与 RAG 质量状态。
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

    <section
      v-if="loadError"
      class="glass-panel flex items-center justify-between gap-4 p-4 text-sm text-amber-200"
    >
      <span>统计数据加载失败，当前展示为本地占位状态。</span>
      <Button
        class="rounded-lg border border-amber-300/20 bg-amber-300/10 text-amber-100 hover:bg-amber-300/20"
        @click="loadStats"
      >
        重试
      </Button>
    </section>

    <section class="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_23rem]">
      <div class="glass-panel overflow-hidden p-4 sm:p-5">
        <div class="flex flex-col gap-4 border-b border-white/10 pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="text-xs text-zinc-500">当前任务链路</p>
            <h3 class="mt-1 text-xl font-semibold text-zinc-50">知识到回答的工作流</h3>
          </div>
          <div class="flex rounded-lg border border-white/10 bg-black/20 p-1">
            <button type="button" class="rounded-md bg-emerald-400 px-3 py-1.5 text-xs font-medium text-black">
              全部任务
            </button>
            <button type="button" class="rounded-md px-3 py-1.5 text-xs font-medium text-zinc-500 hover:text-zinc-200">
              索引中
            </button>
            <button type="button" class="rounded-md px-3 py-1.5 text-xs font-medium text-zinc-500 hover:text-zinc-200">
              已完成
            </button>
          </div>
        </div>

        <div class="grid gap-6 py-5 lg:grid-cols-[minmax(0,1fr)_19rem] lg:items-center">
          <div class="task-stage">
            <button
              v-for="(task, index) in taskCards"
              :key="task.id"
              type="button"
              :class="[
                'task-stack-card',
                `tone-${task.tone}`,
                selectedTaskId === task.id && 'is-active',
              ]"
              :style="{
                '--stack-index': `${index}`,
                '--stack-progress': `${task.progress}%`,
              }"
              @click="selectedTaskId = task.id"
            >
              <span class="flex items-center justify-between gap-3">
                <span class="task-stack-icon">
                  <component :is="task.icon" class="h-4 w-4" />
                </span>
                <span class="text-xs text-zinc-500">{{ task.code }}</span>
              </span>
              <span class="mt-5 block text-left text-base font-semibold text-zinc-50">
                {{ task.title }}
              </span>
              <span class="mt-2 block text-left text-xs leading-5 text-zinc-500">
                {{ task.caption }}
              </span>
              <span class="mt-5 block h-1.5 overflow-hidden rounded-full bg-white/10">
                <span class="task-stack-progress" />
              </span>
            </button>
          </div>

          <div class="selected-task-panel">
            <div class="flex items-center justify-between">
              <span class="rounded-lg border border-white/10 bg-white/[0.06] px-3 py-1 text-xs text-zinc-400">
                {{ activeTask.code }}
              </span>
              <span class="rounded-lg bg-emerald-400/10 px-3 py-1 text-xs text-emerald-300">
                {{ activeTask.status }}
              </span>
            </div>
            <h4 class="mt-5 text-xl font-semibold text-zinc-50">{{ activeTask.title }}</h4>
            <p class="mt-2 text-sm leading-6 text-zinc-500">{{ activeTask.caption }}</p>
            <div class="mt-5 grid grid-cols-2 gap-3 text-sm">
              <div class="rounded-lg border border-white/10 bg-black/20 p-3">
                <p class="text-xs text-zinc-600">负责人</p>
                <p class="mt-1 text-zinc-200">{{ activeTask.owner }}</p>
              </div>
              <div class="rounded-lg border border-white/10 bg-black/20 p-3">
                <p class="text-xs text-zinc-600">计划时间</p>
                <p class="mt-1 text-zinc-200">{{ activeTask.schedule }}</p>
              </div>
            </div>
            <button
              type="button"
              class="mt-5 inline-flex w-full items-center justify-between rounded-lg bg-emerald-400 px-4 py-3 text-sm font-semibold text-black transition hover:bg-emerald-300"
              @click="router.push(activeTask.route)"
            >
              进入处理
              <ArrowRight class="h-4 w-4" />
            </button>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <button
            v-for="task in taskCards"
            :key="`${task.id}-row`"
            type="button"
            :class="[
              'task-row',
              selectedTaskId === task.id && 'is-selected',
            ]"
            @click="selectedTaskId = task.id"
          >
            <span class="flex items-start gap-3">
              <span :class="['task-row-icon', `tone-${task.tone}`]">
                <component :is="task.icon" class="h-4 w-4" />
              </span>
              <span class="min-w-0 text-left">
                <span class="block truncate text-sm font-medium text-zinc-100">{{ task.title }}</span>
                <span class="mt-1 block truncate text-xs text-zinc-600">{{ task.schedule }} · {{ task.owner }}</span>
              </span>
            </span>
            <span class="text-sm font-semibold text-zinc-300">{{ task.progress }}%</span>
          </button>
        </div>
      </div>

      <aside class="space-y-5">
        <section class="glass-panel p-5">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-xs text-zinc-500">AI 任务建议</p>
              <h3 class="mt-1 text-lg font-semibold text-zinc-50">下一步动作</h3>
            </div>
            <span class="rounded-lg bg-emerald-400/10 p-2 text-emerald-300">
              <Zap class="h-5 w-5" />
            </span>
          </div>
          <div class="mt-5 space-y-3">
            <div class="rounded-lg border border-white/10 bg-white/[0.04] p-4">
              <p class="text-sm font-medium text-zinc-100">优先补齐可检索资产</p>
              <p class="mt-2 text-xs leading-5 text-zinc-500">
                当前文档与知识库规模决定回答覆盖率，建议先维护高频知识源。
              </p>
            </div>
            <div class="rounded-lg border border-white/10 bg-white/[0.04] p-4">
              <p class="text-sm font-medium text-zinc-100">建立 RAG 评估节奏</p>
              <p class="mt-2 text-xs leading-5 text-zinc-500">
                每次批量上传后执行检索观测，关注召回、重排与答案一致性。
              </p>
            </div>
          </div>
        </section>

        <section class="glass-panel p-5">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-xs text-zinc-500">系统健康</p>
              <h3 class="mt-1 text-lg font-semibold text-zinc-50">运行状态</h3>
            </div>
            <CheckCircle2 class="h-5 w-5 text-emerald-300" />
          </div>
          <div class="mt-5 space-y-3">
            <div
              v-for="item in healthItems"
              :key="item.label"
              class="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 p-3"
            >
              <span class="flex items-center gap-3 text-sm text-zinc-400">
                <component :is="item.icon" :class="['h-4 w-4', item.tone]" />
                {{ item.label }}
              </span>
              <span class="text-sm text-zinc-100">{{ item.value }}</span>
            </div>
          </div>
        </section>
      </aside>
    </section>

    <section class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_23rem]">
      <div class="glass-panel p-5">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="text-xs text-zinc-500">项目时间线</p>
            <h3 class="mt-1 text-lg font-semibold text-zinc-50">今日处理窗口</h3>
          </div>
          <span class="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-400">
            <Clock3 class="h-4 w-4 text-emerald-300" />
            自动同步
          </span>
        </div>
        <div class="timeline-track mt-6">
          <div
            v-for="item in timeline"
            :key="item.time"
            :class="['timeline-item', `tone-${item.tone}`]"
          >
            <span class="timeline-dot" />
            <div>
              <p class="text-sm font-medium text-zinc-100">{{ item.time }} · {{ item.label }}</p>
              <p class="mt-1 text-xs text-zinc-500">{{ item.description }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="glass-panel p-5">
        <p class="text-xs text-zinc-500">整体进度</p>
        <div class="mt-4 flex items-end justify-between">
          <span class="text-4xl font-semibold text-zinc-50">{{ workflowProgress }}%</span>
          <span class="text-xs text-emerald-300">工作流可用</span>
        </div>
        <div class="mt-5 h-2 overflow-hidden rounded-full bg-white/10">
          <div
            class="h-full rounded-full bg-gradient-to-r from-emerald-400 via-cyan-300 to-amber-300 transition-all duration-700"
            :style="{ width: `${workflowProgress}%` }"
          />
        </div>
        <p class="mt-4 text-xs leading-5 text-zinc-500">
          从知识导入、文档索引、检索评估到问答反馈形成闭环，适合作为下一阶段工程验收入口。
        </p>
      </div>
    </section>
  </div>
</template>
