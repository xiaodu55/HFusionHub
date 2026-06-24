<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { get } from '@/api/request'
import type { ApiResponse, UserRole } from '@/api/types'
import * as agentApi from '@/api/agent'
import * as notificationApi from '@/api/notification'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useTheme } from '@/composables/useTheme'
import { useToast } from '@/composables/useToast'
import { levelBadgeClass } from '@/utils/badge'
import { formatDateTime } from '@/utils/date'
import { APPROVAL_POLL_INTERVAL_MS, NOTICE_POLL_INTERVAL_MS } from '@/constants/timing'
import {
  Activity,
  Bell,
  BookOpen,
  Cable,
  Cpu,
  CreditCard,
  DollarSign,
  FileSearch,
  FileText,
  GitBranch,
  FlaskConical,
  Fingerprint,
  Home,
  LogOut,
  Megaphone,
  ScrollText,
  Menu,
  MessageSquare,
  Moon,
  Package,
  PenLine,
  Rocket,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  StickyNote,
  Sun,
  User,
  Users,
  Wrench,
  X,
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const { isDarkMode, initializeTheme, toggleTheme } = useTheme()
const toast = useToast()

const isSidebarOpen = ref(typeof window === 'undefined' ? true : window.innerWidth >= 1024)
const globalSearchQuery = ref('')
const serviceDialogOpen = ref(false)
const notificationsDialogOpen = ref(false)
const serviceState = ref<'checking' | 'online' | 'offline'>('checking')
const serviceCheckedAt = ref('')
const serviceMessage = ref('正在检查应用服务…')
const notificationsLoading = ref(false)
const notificationsError = ref('')
const notifications = ref<agentApi.AgentAlertEvent[]>([])

// ── 系统公告（用户侧） ──
const unreadNotices = ref<notificationApi.SystemNotice[]>([])
const noticesLoading = ref(false)
const noticesError = ref('')
const unreadNoticeCount = ref(0)
const readNoticeIds = ref<Set<number>>(new Set())

const menuItems: Array<{
  path: string
  label: string
  description: string
  icon: Component
  roles?: UserRole[]
  group: 'use' | 'personal' | 'build' | 'admin'
  keywords: string[]
}> = [
  { path: '/', label: '首页', description: '查看当前工作', icon: Home, group: 'use', keywords: ['首页', '工作台'] },
  { path: '/knowledge-base', label: '知识库', description: '管理知识资料', icon: BookOpen, group: 'use', keywords: ['知识', '知识库', 'kb'] },
  { path: '/document', label: '文档', description: '上传、解析和恢复', icon: FileText, group: 'use', keywords: ['文档', '文件', '索引', 'doc'] },
  { path: '/chat', label: '智能对话', description: '提问并引用知识', icon: MessageSquare, group: 'use', keywords: ['对话', '聊天', 'chat'] },
  { path: '/bid/projects', label: '投标项目', description: '招标解读与标书工作台', icon: FileSearch, group: 'use', keywords: ['投标', '招标', '解读', '标书', 'bid'] },
  { path: '/bid/billing', label: '套餐中心', description: '选择套餐与行业标书模板', icon: CreditCard, group: 'use', keywords: ['套餐', '订阅', '计费', '方案包', 'billing', '模板商城'] },
  { path: '/builder/models', label: '我的模型', description: '选择供应商和模型', icon: Cpu, group: 'personal', keywords: ['model', '模型', 'llm', 'embedding', '向量'] },
  { path: '/builder/tools', label: 'AI 能力', description: '查看和创建可用工具', icon: Wrench, group: 'personal', keywords: ['工具', 'tool', 'mcp', '能力'] },
  { path: '/agent', label: '运行记录', description: '查看执行和失败原因', icon: Sparkles, group: 'personal', keywords: ['运行', '任务', 'agent', '失败'] },
  { path: '/approvals', label: '待确认操作', description: '允许或阻止敏感操作', icon: Fingerprint, group: 'personal', keywords: ['确认', '审批', '允许', '拒绝'] },
  { path: '/memory', label: '我的记忆', description: '管理 AI 记住的信息', icon: User, group: 'personal', keywords: ['记忆', 'memory'] },
  { path: '/notes', label: '我的笔记', description: '查看 Agent 保存的笔记', icon: StickyNote, group: 'personal', keywords: ['笔记', 'note', '写笔记'] },
  { path: '/cost', label: '模型用量', description: '查看调用次数和预估费用', icon: DollarSign, group: 'personal', keywords: ['用量', '费用', '成本', 'token'] },
  { path: '/builder/prompts', label: '回答方案', description: '设置 AI 回答方式', icon: PenLine, roles: ['builder', 'admin'], group: 'build', keywords: ['prompt', '提示词', '模板', '回答方案'] },
  { path: '/builder/test-bench', label: '方案测试', description: '验证单个回答效果', icon: FlaskConical, roles: ['builder', 'admin'], group: 'build', keywords: ['测试', 'test', 'bench', '评测'] },
  { path: '/builder/test-sets', label: '回归用例', description: '批量比较回答结果', icon: FlaskConical, roles: ['builder', 'admin'], group: 'build', keywords: ['用例', '批量', '回归', 'suite'] },
  { path: '/rag', label: '回答效果', description: '分析检索和引用质量', icon: Activity, roles: ['builder', 'admin'], group: 'build', keywords: ['rag', '检索', '引用', '评估'] },
  { path: '/builder/plugins', label: '插件管理', description: '安装和隔离运行插件', icon: Package, roles: ['admin'], group: 'admin', keywords: ['插件', 'plugin', '沙箱'] },
  { path: '/builder/apps', label: '应用发布', description: '打包知识库为对外 API', icon: Rocket, roles: ['builder', 'admin'], group: 'build', keywords: ['应用', '发布', 'api', 'key', 'app'] },
  { path: '/builder/mcp', label: 'MCP 服务', description: '接入外部 MCP 工具服务器', icon: Cable, roles: ['builder', 'admin'], group: 'build', keywords: ['mcp', '外部', '服务', 'cable'] },
  { path: '/admin/flags', label: '能力开关', description: '直接开启或关闭 AI 增强能力', icon: ShieldCheck, roles: ['admin'], group: 'admin', keywords: ['开关', 'flag', '能力'] },
  { path: '/admin/intent-tree', label: '问题分流', description: '让不同问题使用对应知识库', icon: GitBranch, roles: ['admin'], group: 'admin', keywords: ['意图', '路由', '问题分流', 'intent tree'] },
  { path: '/admin/users', label: '账号权限', description: '给新用户分配身份', icon: Users, roles: ['admin'], group: 'admin', keywords: ['用户', '权限', '身份', '角色'] },
  { path: '/admin/notices', label: '公告管理', description: '发布和删除系统公告', icon: Megaphone, roles: ['admin'], group: 'admin', keywords: ['公告', '通知', 'notice', '发布'] },
  { path: '/admin/audit-logs', label: '审计日志', description: '敏感操作与跨租户审计', icon: ScrollText, roles: ['admin'], group: 'admin', keywords: ['审计', 'audit', '日志', '跨租户'] },
  { path: '/admin/plans', label: '套餐管理', description: '维护平台套餐目录', icon: Package, roles: ['admin'], group: 'admin', keywords: ['套餐', '订阅', '目录', '方案包', 'plan'] },
]

const visibleMenuItems = computed(() => menuItems.filter(item => !item.roles || userStore.hasAnyRole(item.roles)))
const menuGroups = computed(() => [
  { label: '使用', items: visibleMenuItems.value.filter(item => item.group === 'use') },
  { label: '我的设置', items: visibleMenuItems.value.filter(item => item.group === 'personal') },
  { label: '构建与评测', items: visibleMenuItems.value.filter(item => item.group === 'build') },
  { label: '系统管理', items: visibleMenuItems.value.filter(item => item.group === 'admin') },
].filter(group => group.items.length > 0))

const isActive = (path: string) => {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(path)
}

const currentItem = computed(() => menuItems.find((item) => isActive(item.path)))
const userDisplayName = computed(() => userStore.nickname || userStore.username || 'HFusionHub 用户')
const userInitial = computed(() => userDisplayName.value.trim().slice(0, 1).toUpperCase() || 'H')
const userAvatarUrl = computed(() => userStore.userInfo?.avatar || '')
const userRoleLabel = computed(() => ({ pending: '等待分配', user: '普通用户', builder: 'AI 配置员', admin: '超级管理员' }[userStore.role]))
const unreadNotificationCount = computed(() => notifications.value.length + unreadNoticeCount.value)
const serviceLabel = computed(() => ({ checking: '检查中', online: '服务在线', offline: '服务异常' }[serviceState.value]))
const serviceClass = computed(() => ({
  checking: 'border-amber-400/20 bg-amber-400/10 text-amber-800 dark:text-amber-200',
  online: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-700 dark:text-emerald-300',
  offline: 'border-rose-400/20 bg-rose-400/10 text-rose-700 dark:text-rose-200',
}[serviceState.value]))
const logoutButtonClass = computed(() =>
  [
    'w-full rounded-lg text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground',
    isSidebarOpen.value ? 'justify-start gap-3' : 'justify-center px-0',
  ].join(' ')
)

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value
}

watch(() => route.path, () => {
  if (window.innerWidth < 1024) isSidebarOpen.value = false
})

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
  await Promise.all([loadNotifications(), loadNotices()])
}

const loadNotices = async () => {
  noticesLoading.value = true
  noticesError.value = ''
  try {
    const [listRes, countRes] = await Promise.all([
      notificationApi.listMyNotices(),
      notificationApi.getUnreadNoticeCount().catch(() => null),
    ])
    unreadNotices.value = listRes.data
    unreadNoticeCount.value = countRes?.data?.count ?? 0
  } catch (error) {
    noticesError.value = error instanceof Error ? error.message : '暂时无法加载公告'
  } finally {
    noticesLoading.value = false
  }
}

const markNoticeRead = async (noticeId: number) => {
  try {
    await notificationApi.markNoticeRead(noticeId)
    readNoticeIds.value.add(noticeId)
    unreadNoticeCount.value = Math.max(0, unreadNoticeCount.value - 1)
  } catch (error) {
    noticesError.value = error instanceof Error ? error.message : '标记已读失败'
  }
}

const noticeLevelLabel = (level?: string) => ({ info: '提示', warning: '重要', error: '紧急' }[level || ''] || '提示')
const noticeLevelClass = (level?: string) => levelBadgeClass(level)

const resolveNotification = async (alertId: number) => {
  try {
    await agentApi.resolveAlert(alertId)
    notifications.value = notifications.value.filter(alert => alert.id !== alertId)
  } catch (error) {
    notificationsError.value = error instanceof Error ? error.message : '无法解除该通知'
  }
}

const pendingApprovals = ref(0)
let approvalPollTimer: ReturnType<typeof setInterval> | null = null
let pollTickCount = 0
const loadPendingApprovals = async () => {
  try {
    const res = (await get('/agent-task/approvals/pending')) as ApiResponse<unknown[]>
    pendingApprovals.value = Array.isArray(res.data) ? res.data.length : 0
  } catch {
    pendingApprovals.value = 0
  }
}
const refreshUnreadNoticeCount = () => {
  notificationApi.getUnreadNoticeCount().then(res => {
    unreadNoticeCount.value = res.data?.count ?? unreadNoticeCount.value
  }).catch(() => {})
}

// 审批与公告原本各有一个独立轮询，合并为单一定时器：
// 每 30s 刷新待审批数，每 60s（第 2 个周期）顺带刷新未读公告数
const pollLayoutCounters = () => {
  loadPendingApprovals()
  refreshUnreadNoticeCount()
  approvalPollTimer = setInterval(() => {
    pollTickCount += 1
    loadPendingApprovals()
    if ((pollTickCount * APPROVAL_POLL_INTERVAL_MS) % NOTICE_POLL_INTERVAL_MS === 0) {
      refreshUnreadNoticeCount()
    }
  }, APPROVAL_POLL_INTERVAL_MS)
}

const severityLabel = (severity?: string) => ({ critical: '需要立即处理', warning: '需要关注', info: '提示' }[severity || ''] || '提示')
const severityClass = (severity?: string) => levelBadgeClass(severity)

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

  const target = visibleMenuItems.value.find((item) =>
    item.keywords.some((word) => keyword.includes(word.toLowerCase()))
  )
  if (target) {
    router.push(target.path)
  } else {
    toast.error(`没有找到与「${globalSearchQuery.value.trim()}」相关的功能页面`)
  }
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
  void loadNotices()
  pollLayoutCounters()
})

onBeforeUnmount(() => {
  if (approvalPollTimer) clearInterval(approvalPollTimer)
})
</script>

<template>
  <div class="app-shell h-screen overflow-hidden bg-background text-foreground">
    <button
      v-if="isSidebarOpen"
      type="button"
      class="fixed inset-0 z-30 bg-black/65 lg:hidden"
      aria-label="关闭导航"
      @click="isSidebarOpen = false"
    />
    <aside
      :class="[
        'glass-sidebar fixed inset-y-0 left-0 z-40 flex w-[17rem] shrink-0 flex-col transition-transform duration-300 ease-out lg:relative lg:inset-auto lg:z-10 lg:translate-x-0 lg:transition-[width]',
        isSidebarOpen ? 'translate-x-0 lg:w-[17rem]' : '-translate-x-full lg:w-[5rem]',
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
            <span class="block truncate text-base font-semibold text-foreground">HFusionHub</span>
            <span class="block truncate text-xs text-muted-foreground">AI Knowledge OS</span>
          </span>
        </button>

        <Button
          variant="ghost"
          size="icon"
          class="h-9 w-9 rounded-lg text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
          title="折叠导航"
          @click="toggleSidebar"
        >
          <Menu v-if="!isSidebarOpen" class="h-4 w-4" />
          <X v-else class="h-4 w-4" />
        </Button>
      </div>

      <nav class="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        <section v-for="group in menuGroups" :key="group.label" class="space-y-1.5">
          <p v-if="isSidebarOpen" class="px-3 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground/70">{{ group.label }}</p>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            :title="item.label"
            :class="[
              'nav-pill group flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition-all duration-200',
              isActive(item.path) ? 'is-active text-foreground' : 'text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground',
              !isSidebarOpen && 'justify-center px-0',
            ]"
          >
            <component :is="item.icon" class="h-5 w-5 shrink-0" />
            <span v-if="isSidebarOpen" class="min-w-0"><span class="block truncate">{{ item.label }}</span><span class="block truncate text-xs font-normal text-muted-foreground/70 group-hover:text-muted-foreground">{{ item.description }}</span></span>
            <span
              v-if="item.path === '/approvals' && pendingApprovals > 0"
              class="ml-auto shrink-0 rounded-full bg-amber-400/20 px-2 py-0.5 text-xs font-semibold text-amber-700 dark:text-amber-300"
              :title="`${pendingApprovals} 项待确认操作`"
            >
              {{ pendingApprovals }}
            </span>
          </router-link>
        </section>
      </nav>

      <div class="space-y-3 border-t border-border p-3">
        <button
          type="button"
          :class="[
            'user-chip flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors hover:bg-foreground/[0.06]',
            !isSidebarOpen && 'justify-center',
          ]"
          @click="router.push('/profile')"
        >
          <img
            v-if="userAvatarUrl"
            :src="userAvatarUrl"
            alt="头像"
            class="user-avatar object-cover"
          />
          <span v-else class="user-avatar">{{ userInitial }}</span>
          <span v-if="isSidebarOpen" class="min-w-0">
            <span class="block truncate text-sm font-medium text-foreground">{{ userDisplayName }}</span>
            <span class="block truncate text-xs text-emerald-600 dark:text-emerald-400">{{ userRoleLabel }}</span>
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
            class="h-9 w-9 rounded-lg text-muted-foreground hover:bg-foreground/10 hover:text-foreground lg:hidden"
            title="展开导航"
            @click="toggleSidebar"
          >
            <Menu class="h-4 w-4" />
          </Button>
          <div class="min-w-0">
            <p class="text-xs text-muted-foreground">当前模块</p>
            <h1 class="truncate text-lg font-semibold text-foreground">
              {{ currentItem?.label || 'HFusionHub' }}
            </h1>
          </div>
        </div>

        <form
          class="command-bar hidden min-w-[18rem] max-w-xl flex-1 items-center gap-2 transition-colors focus-within:border-primary/40 lg:flex"
          @submit.prevent="handleGlobalSearch"
        >
          <Search class="h-4 w-4 text-muted-foreground" />
          <input
            v-model="globalSearchQuery"
            class="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground/70"
            placeholder="搜索或跳转到知识库、文档、对话"
          >
        </form>

        <div class="flex shrink-0 items-center gap-2">
          <button
            class="hidden items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors hover:bg-foreground/[0.08] sm:flex"
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
            class="relative h-9 w-9 rounded-lg text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
            title="需要处理的事项"
            @click="openNotifications"
          >
            <Bell class="h-4 w-4" />
            <span v-if="unreadNotificationCount" class="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-rose-400 ring-2 ring-background" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            class="h-9 w-9 rounded-lg text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
            :title="isDarkMode ? '切换浅色主题' : '切换暗色主题'"
            @click="toggleTheme"
          >
            <Sun v-if="isDarkMode" class="h-4 w-4" />
            <Moon v-else class="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            class="h-9 w-9 rounded-lg text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
            title="个人中心"
            @click="router.push('/profile')"
          >
            <User class="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            class="hidden h-9 w-9 rounded-lg text-muted-foreground hover:bg-foreground/10 hover:text-foreground sm:inline-flex"
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
          <DialogTitle>通知中心</DialogTitle>
          <DialogDescription>系统公告与需要关注的事项都会在这里提醒你。</DialogDescription>
        </DialogHeader>
        <div class="mt-4 max-h-[26rem] space-y-4 overflow-y-auto">
          <!-- 系统公告 -->
          <section v-if="noticesLoading || unreadNotices.length || noticesError" class="space-y-2">
            <p class="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">系统公告</p>
            <div v-if="noticesLoading" class="py-6 text-center text-sm text-muted-foreground">正在加载公告…</div>
            <div v-else-if="noticesError" class="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-4 text-sm text-rose-800 dark:text-rose-100/85">{{ noticesError }}</div>
            <template v-else>
              <article
                v-for="notice in unreadNotices"
                :key="notice.id"
                class="rounded-xl border p-3.5"
                :class="readNoticeIds.has(notice.id) ? 'border-border bg-muted/20 opacity-70' : 'border-amber-400/20 bg-amber-400/[0.04]'"
              >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-sm font-medium">{{ notice.title }}</span>
                    <span class="rounded-full border px-2 py-0.5 text-[11px]" :class="noticeLevelClass(notice.level)">{{ noticeLevelLabel(notice.level) }}</span>
                    <span v-if="!readNoticeIds.has(notice.id)" class="rounded-full bg-primary/15 px-2 py-0.5 text-[11px] text-primary">未读</span>
                  </div>
                  <p class="mt-2 whitespace-pre-wrap break-words text-sm leading-5 text-muted-foreground">{{ notice.content }}</p>
                  <p class="mt-2 text-xs text-muted-foreground">{{ formatDateTime(notice.createdAt) }} · {{ notice.publisher || '系统' }}</p>
                </div>
                <Button
                  v-if="!readNoticeIds.has(notice.id)"
                  variant="outline"
                  size="sm"
                  class="shrink-0"
                  @click="markNoticeRead(notice.id)"
                >标记已读</Button>
              </div>
            </article>
            </template>
          </section>

          <!-- 需要处理的事项（Agent 告警） -->
          <section class="space-y-2">
            <p class="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">需要处理的事项</p>
            <div v-if="notificationsLoading" class="py-6 text-center text-sm text-muted-foreground">正在加载通知…</div>
            <div v-else-if="notificationsError" class="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-4 text-sm text-rose-800 dark:text-rose-100/85">{{ notificationsError }}</div>
            <div v-else-if="!notifications.length" class="flex flex-col items-center justify-center py-6 text-center"><Bell class="h-6 w-6 text-emerald-700 dark:text-emerald-300" /><p class="mt-2 text-sm font-medium">暂时没有需要处理的事项</p><p class="mt-1 text-xs text-muted-foreground">系统发现异常时会在这里用易懂的方式提醒你。</p></div>
            <article v-for="alert in notifications" :key="alert.id" class="rounded-xl border border-border bg-muted/30 p-3.5"><div class="flex items-start justify-between gap-3"><div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><span class="text-sm font-medium">{{ alertContent(alert).title }}</span><span class="rounded-full border px-2 py-0.5 text-[11px]" :class="severityClass(alert.severity)">{{ severityLabel(alert.severity) }}</span></div><p class="mt-2 break-words text-sm leading-5 text-muted-foreground">{{ alertContent(alert).description }}</p><p class="mt-2 rounded-lg bg-background/60 p-2.5 text-xs leading-5 text-foreground/80"><strong>建议：</strong>{{ alertContent(alert).advice }}</p><div class="mt-2 flex items-center justify-between gap-3"><span class="text-xs text-muted-foreground">{{ formatDateTime(alert.createdAt) }}</span><details class="text-xs text-muted-foreground"><summary class="cursor-pointer hover:text-foreground">技术详情</summary><p class="mt-1 max-w-56 break-all font-mono">{{ alert.metricName }} · 当前值 {{ alert.currentValue }} · 阈值 {{ alert.thresholdValue }}</p></details></div></div><Button variant="outline" size="sm" class="shrink-0" @click="resolveNotification(alert.id)">标记已处理</Button></div></article>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
