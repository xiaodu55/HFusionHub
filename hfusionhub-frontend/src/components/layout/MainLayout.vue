<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { get } from '@/api/request'
import type { ApiResponse } from '@/api/types'
import * as agentApi from '@/api/agent'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useTheme } from '@/composables/useTheme'
import {
  Activity,
  Bell,
  BookOpen,
  Cpu,
  FileText,
  Home,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  PenLine,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  User,
  X,
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const { isDarkMode, initializeTheme, toggleTheme } = useTheme()

const isSidebarOpen = ref(true)
const globalSearchQuery = ref('')
const serviceDialogOpen = ref(false)
const notificationsDialogOpen = ref(false)
const serviceState = ref<'checking' | 'online' | 'offline'>('checking')
const serviceCheckedAt = ref('')
const serviceMessage = ref('正在检查应用服务…')
const notificationsLoading = ref(false)
const notificationsError = ref('')
const notifications = ref<agentApi.AgentAlertEvent[]>([])

const menuItems: Array<{
  path: string
  label: string
  description: string
  icon: Component
}> = [
  { path: '/builder/prompts', label: 'Prompt 工作台', description: '模板与发布', icon: PenLine },
  { path: '/builder/models', label: '模型中心', description: '模型与运行状态', icon: Cpu },
  { path: '/', label: '任务总览', description: '工作台', icon: Home },
  { path: '/knowledge-base', label: '知识库', description: '知识治理', icon: BookOpen },
  { path: '/document', label: '文档管理', description: '解析与索引', icon: FileText },
  { path: '/chat', label: '智能对话', description: '多轮问答', icon: MessageSquare },
  { path: '/agent', label: 'Agent 任务', description: '执行与恢复', icon: Sparkles },
  { path: '/memory', label: '长期记忆', description: 'Agent 用户记忆', icon: User },
  { path: '/rag', label: 'RAG 观测', description: '检索评估', icon: Activity },
  { path: '/admin/flags', label: '高级能力', description: '配置说明', icon: ShieldCheck },
]

const menuGroups = [
  { label: '工作区', items: menuItems.filter((item) => ['/', '/knowledge-base', '/document', '/chat'].includes(item.path)) },
  { label: '构建', items: menuItems.filter((item) => ['/builder/prompts', '/builder/models', '/agent'].includes(item.path)) },
  { label: '运营', items: menuItems.filter((item) => ['/rag', '/memory'].includes(item.path)) },
  { label: '管理', items: menuItems.filter((item) => item.path === '/admin/flags') },
]

const commandRoutes = [
  { keywords: ['model', '模型', 'llm', 'embedding', '向量'], path: '/builder/models' },
  { keywords: ['prompt', '提示词', '模板'], path: '/builder/prompts' },
  { keywords: ['知识', '知识库', 'kb'], path: '/knowledge-base' },
  { keywords: ['文档', '文件', '索引', 'doc'], path: '/document' },
  { keywords: ['对话', '聊天', 'chat'], path: '/chat' },
  { keywords: ['rag', '观测', '调试', '评估'], path: '/rag' },
  { keywords: ['开关', 'flag', '灰度'], path: '/admin/flags' },
  { keywords: ['设置', '主题', '账户'], path: '/settings' },
]

const isActive = (path: string) => {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(path)
}

const currentItem = computed(() => menuItems.find((item) => isActive(item.path)))
const userDisplayName = computed(() => userStore.nickname || userStore.username || 'HFusionHub 用户')
const userInitial = computed(() => userDisplayName.value.trim().slice(0, 1).toUpperCase() || 'H')
const unreadNotificationCount = computed(() => notifications.value.length)
const serviceLabel = computed(() => ({ checking: '检查中', online: '服务在线', offline: '服务异常' }[serviceState.value]))
const serviceClass = computed(() => ({
  checking: 'border-amber-400/20 bg-amber-400/10 text-amber-200',
  online: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
  offline: 'border-rose-400/20 bg-rose-400/10 text-rose-200',
}[serviceState.value]))
const logoutButtonClass = computed(() =>
  [
    'w-full rounded-lg text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100',
    isSidebarOpen.value ? 'justify-start gap-3' : 'justify-center px-0',
  ].join(' ')
)

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value
}

const refreshServiceHealth = async () => {
  serviceState.value = 'checking'
  serviceMessage.value = '正在检查应用服务…'
  try {
    const response = await get<ApiResponse<{ status: string; timestamp?: string }>>('/health')
    serviceState.value = response.data.status === 'UP' ? 'online' : 'offline'
    serviceCheckedAt.value = response.data.timestamp || new Date().toISOString()
    serviceMessage.value = serviceState.value === 'online' ? '应用服务响应正常。' : '应用服务返回了异常状态。'
  } catch (error) {
    serviceState.value = 'offline'
    serviceCheckedAt.value = new Date().toISOString()
    serviceMessage.value = error instanceof Error ? error.message : '无法连接到应用服务。'
  }
}

const loadNotifications = async () => {
  notificationsLoading.value = true
  notificationsError.value = ''
  try {
    notifications.value = (await agentApi.getUnresolvedAlerts()).data
  } catch (error) {
    notificationsError.value = error instanceof Error ? error.message : '暂时无法加载通知'
  } finally {
    notificationsLoading.value = false
  }
}

const openNotifications = async () => {
  notificationsDialogOpen.value = true
  await loadNotifications()
}

const resolveNotification = async (alertId: number) => {
  try {
    await agentApi.resolveAlert(alertId)
    notifications.value = notifications.value.filter(alert => alert.id !== alertId)
  } catch (error) {
    notificationsError.value = error instanceof Error ? error.message : '无法解除该通知'
  }
}

const formatDateTime = (value?: string) => value ? value.replace('T', ' ').slice(0, 16) : '刚刚'
const severityLabel = (severity?: string) => ({ critical: '需要立即处理', warning: '需要关注', info: '提示' }[severity || ''] || '提示')
const severityClass = (severity?: string) => ({
  critical: 'border-rose-400/25 bg-rose-400/10 text-rose-200',
  warning: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
  info: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200',
}[severity || ''] || 'border-border bg-muted text-muted-foreground')

const alertContent = (alert: agentApi.AgentAlertEvent) => {
  const current = alert.currentValue ?? 0
  const threshold = alert.thresholdValue ?? 0
  const rate = `${Math.round(current * 100)}%`
  const thresholdRate = `${Math.round(threshold * 100)}%`

  switch (alert.metricName) {
    case 'tool_failure_rate':
      return {
        title: '工具调用失败较多',
        description: `最近的 Agent 任务中，约 ${rate} 的工具调用没有成功完成，已超过 ${thresholdRate} 的提醒阈值。`,
        advice: '请到“Agent 任务”查看失败任务，确认 AI 服务和工具连接是否正常。',
      }
    case 'citation_miss_rate':
      return {
        title: '回答缺少知识来源',
        description: `近期约 ${rate} 的回答没有附带可追溯的知识来源，已超过 ${thresholdRate} 的提醒阈值。`,
        advice: '请检查知识库是否完成索引，并在“RAG 观测”中确认检索是否正常。',
      }
    case 'running_timeout':
      return {
        title: '有任务等待时间过长',
        description: `检测到 ${Math.round(current)} 个任务长时间没有完成，已超过预设的等待阈值。`,
        advice: '请到“Agent 任务”查看执行状态，可取消或重试卡住的任务。',
      }
    case 'approval_timeout':
      return {
        title: '有待确认的操作超时',
        description: `检测到 ${Math.round(current)} 个需要人工确认的操作等待过久。`,
        advice: '请前往“Agent 任务”完成批准或拒绝，避免任务一直停留在等待状态。',
      }
    default:
      return {
        title: alert.ruleName || '发现需要关注的任务',
        description: '系统检测到一项运行指标超过了预设范围。',
        advice: '请查看相关 Agent 任务，确认是否需要重试或调整配置。',
      }
  }
}

const handleGlobalSearch = () => {
  const keyword = globalSearchQuery.value.trim().toLowerCase()
  if (!keyword) return

  const target = commandRoutes.find((item) =>
    item.keywords.some((word) => keyword.includes(word.toLowerCase()))
  )
  router.push(target?.path || '/knowledge-base')
  globalSearchQuery.value = ''
}

const handleLogout = async () => {
  await userStore.logout()
  router.push('/login')
}

onMounted(() => {
  initializeTheme()
  void refreshServiceHealth()
  void loadNotifications()
})
</script>

<template>
  <div class="app-shell h-screen overflow-hidden bg-background text-foreground">
    <aside
      :class="[
        'glass-sidebar relative z-10 flex shrink-0 flex-col transition-[width] duration-300 ease-out',
        isSidebarOpen ? 'w-[17rem]' : 'w-[5rem]',
      ]"
    >
      <div class="flex h-[72px] items-center justify-between px-4">
        <button
          type="button"
          class="flex min-w-0 items-center gap-3"
          title="返回任务总览"
          @click="router.push('/')"
        >
          <span class="brand-mark">HF</span>
          <span v-if="isSidebarOpen" class="min-w-0 text-left">
            <span class="block truncate text-base font-semibold text-white">HFusionHub</span>
            <span class="block truncate text-xs text-zinc-500">AI Knowledge OS</span>
          </span>
        </button>

        <Button
          variant="ghost"
          size="icon"
          class="h-9 w-9 rounded-lg text-zinc-400 hover:bg-white/10 hover:text-white"
          title="折叠导航"
          @click="toggleSidebar"
        >
          <Menu v-if="!isSidebarOpen" class="h-4 w-4" />
          <X v-else class="h-4 w-4" />
        </Button>
      </div>

      <nav class="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        <section v-for="group in menuGroups" :key="group.label" class="space-y-1.5">
          <p v-if="isSidebarOpen" class="px-3 text-[11px] font-medium uppercase tracking-[0.12em] text-zinc-600">{{ group.label }}</p>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            :title="item.label"
            :class="[
              'nav-pill group flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition-all duration-200',
              isActive(item.path) ? 'is-active text-white' : 'text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100',
              !isSidebarOpen && 'justify-center px-0',
            ]"
          >
            <component :is="item.icon" class="h-5 w-5 shrink-0" />
            <span v-if="isSidebarOpen" class="min-w-0"><span class="block truncate">{{ item.label }}</span><span class="block truncate text-xs font-normal text-zinc-600 group-hover:text-zinc-400">{{ item.description }}</span></span>
          </router-link>
        </section>
      </nav>

      <div class="space-y-3 border-t border-white/10 p-3">
        <button
          type="button"
          :class="[
            'user-chip flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors hover:bg-white/[0.06]',
            !isSidebarOpen && 'justify-center',
          ]"
          @click="router.push('/profile')"
        >
          <span class="user-avatar">{{ userInitial }}</span>
          <span v-if="isSidebarOpen" class="min-w-0">
            <span class="block truncate text-sm font-medium text-zinc-100">{{ userDisplayName }}</span>
            <span class="block truncate text-xs text-emerald-400">在线工作中</span>
          </span>
        </button>

        <Button
          variant="ghost"
          :class="logoutButtonClass"
          @click="handleLogout"
        >
          <LogOut class="h-5 w-5" />
          <span v-if="isSidebarOpen">退出登录</span>
        </Button>
      </div>
    </aside>

    <div class="relative z-10 flex min-w-0 flex-1 flex-col">
      <header
        class="glass-header mx-4 mt-4 flex h-[68px] shrink-0 items-center justify-between gap-4 px-4 sm:mx-6 lg:mx-8"
      >
        <div class="flex min-w-0 items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            class="h-9 w-9 rounded-lg text-zinc-400 hover:bg-white/10 hover:text-white lg:hidden"
            title="展开导航"
            @click="toggleSidebar"
          >
            <Menu class="h-4 w-4" />
          </Button>
          <div class="min-w-0">
            <p class="text-xs text-zinc-500">当前模块</p>
            <h1 class="truncate text-lg font-semibold text-zinc-50">
              {{ currentItem?.label || 'HFusionHub' }}
            </h1>
          </div>
        </div>

        <form
          class="command-bar hidden min-w-[18rem] max-w-xl flex-1 items-center gap-2 lg:flex"
          @submit.prevent="handleGlobalSearch"
        >
          <Search class="h-4 w-4 text-zinc-500" />
          <input
            v-model="globalSearchQuery"
            class="min-w-0 flex-1 bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
            placeholder="搜索或跳转到知识库、文档、对话"
          >
        </form>

        <div class="flex shrink-0 items-center gap-2">
          <button
            class="hidden items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors hover:bg-white/[0.08] sm:flex"
            :class="serviceClass"
            title="查看服务状态"
            @click="serviceDialogOpen = true; refreshServiceHealth()"
          >
            <span class="h-2 w-2 rounded-full" :class="serviceState === 'online' ? 'bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.9)]' : serviceState === 'offline' ? 'bg-rose-400' : 'bg-amber-300 animate-pulse'" />
            {{ serviceLabel }}
          </button>
          <Button
            variant="ghost"
            size="icon"
            class="relative h-9 w-9 rounded-lg text-zinc-400 hover:bg-white/10 hover:text-white"
            title="需要处理的事项"
            @click="openNotifications"
          >
            <Bell class="h-4 w-4" />
            <span v-if="unreadNotificationCount" class="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-rose-400 ring-2 ring-[#111413]" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            class="h-9 w-9 rounded-lg text-zinc-400 hover:bg-white/10 hover:text-white"
            :title="isDarkMode ? '切换浅色主题' : '切换暗色主题'"
            @click="toggleTheme"
          >
            <Sun v-if="isDarkMode" class="h-4 w-4" />
            <Moon v-else class="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            class="h-9 w-9 rounded-lg text-zinc-400 hover:bg-white/10 hover:text-white"
            title="个人中心"
            @click="router.push('/profile')"
          >
            <User class="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            class="hidden h-9 w-9 rounded-lg text-zinc-400 hover:bg-white/10 hover:text-white sm:inline-flex"
            title="设置"
            @click="router.push('/settings')"
          >
            <Settings class="h-4 w-4" />
          </Button>
        </div>
      </header>

      <main class="min-h-0 flex-1 overflow-auto p-4 sm:p-6 lg:p-8">
        <div class="mx-auto w-full max-w-[1480px]">
          <router-view />
        </div>
      </main>

      <Sparkles class="pointer-events-none absolute right-8 top-28 h-5 w-5 text-emerald-300/40" />
    </div>

    <Dialog v-model:open="serviceDialogOpen">
      <DialogContent class="max-w-md">
        <DialogHeader>
          <DialogTitle>服务状态</DialogTitle>
          <DialogDescription>检查浏览器当前连接的应用服务。</DialogDescription>
        </DialogHeader>
        <div class="mt-4 rounded-xl border p-4" :class="serviceState === 'online' ? 'border-emerald-400/20 bg-emerald-400/[0.06]' : serviceState === 'offline' ? 'border-rose-400/20 bg-rose-400/[0.06]' : 'border-amber-400/20 bg-amber-400/[0.06]'">
          <div class="flex items-center gap-2"><span class="h-2.5 w-2.5 rounded-full" :class="serviceState === 'online' ? 'bg-emerald-400' : serviceState === 'offline' ? 'bg-rose-400' : 'bg-amber-300 animate-pulse'" /><span class="font-medium">{{ serviceLabel }}</span></div>
          <p class="mt-2 text-sm text-muted-foreground">{{ serviceMessage }}</p>
          <p v-if="serviceCheckedAt" class="mt-3 text-xs text-muted-foreground">最近检查：{{ formatDateTime(serviceCheckedAt) }}</p>
        </div>
        <Button variant="outline" class="mt-4 w-full" @click="refreshServiceHealth">重新检查</Button>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="notificationsDialogOpen">
      <DialogContent class="max-w-lg">
        <DialogHeader>
          <DialogTitle>需要处理的事项</DialogTitle>
          <DialogDescription>这里会提示可能影响 AI 回答或任务执行的问题。</DialogDescription>
        </DialogHeader>
        <div class="mt-4 max-h-[26rem] space-y-2 overflow-y-auto">
          <div v-if="notificationsLoading" class="py-10 text-center text-sm text-muted-foreground">正在加载通知…</div>
          <div v-else-if="notificationsError" class="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-4 text-sm text-rose-100/85">{{ notificationsError }}</div>
          <div v-else-if="!notifications.length" class="flex flex-col items-center justify-center py-10 text-center"><Bell class="h-7 w-7 text-emerald-300" /><p class="mt-3 text-sm font-medium">暂时没有需要处理的事项</p><p class="mt-1 text-xs text-muted-foreground">系统发现异常时会在这里用易懂的方式提醒你。</p></div>
          <article v-for="alert in notifications" :key="alert.id" class="rounded-xl border border-border bg-muted/30 p-3.5"><div class="flex items-start justify-between gap-3"><div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><span class="text-sm font-medium">{{ alertContent(alert).title }}</span><span class="rounded-full border px-2 py-0.5 text-[11px]" :class="severityClass(alert.severity)">{{ severityLabel(alert.severity) }}</span></div><p class="mt-2 break-words text-sm leading-5 text-muted-foreground">{{ alertContent(alert).description }}</p><p class="mt-2 rounded-lg bg-background/60 p-2.5 text-xs leading-5 text-foreground/80"><strong>建议：</strong>{{ alertContent(alert).advice }}</p><div class="mt-2 flex items-center justify-between gap-3"><span class="text-xs text-muted-foreground">{{ formatDateTime(alert.createdAt) }}</span><details class="text-xs text-muted-foreground"><summary class="cursor-pointer hover:text-foreground">技术详情</summary><p class="mt-1 max-w-56 break-all font-mono">{{ alert.metricName }} · 当前值 {{ alert.currentValue }} · 阈值 {{ alert.thresholdValue }}</p></details></div></div><Button variant="outline" size="sm" class="shrink-0" @click="resolveNotification(alert.id)">标记已处理</Button></div></article>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
