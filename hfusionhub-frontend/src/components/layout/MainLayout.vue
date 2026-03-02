<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import {
  Activity,
  Bell,
  BookOpen,
  FileText,
  Home,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
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

const isSidebarOpen = ref(true)
const isDarkMode = ref(true)
const globalSearchQuery = ref('')

const menuItems: Array<{
  path: string
  label: string
  description: string
  icon: Component
}> = [
  { path: '/', label: '任务总览', description: '工作台', icon: Home },
  { path: '/knowledge-base', label: '知识库', description: '知识治理', icon: BookOpen },
  { path: '/document', label: '文档管理', description: '解析与索引', icon: FileText },
  { path: '/chat', label: '智能对话', description: '多轮问答', icon: MessageSquare },
  { path: '/rag', label: 'RAG 观测', description: '检索评估', icon: Activity },
  { path: '/admin/flags', label: '功能开关', description: '灰度控制', icon: ShieldCheck },
]

const commandRoutes = [
  { keywords: ['知识', '知识库', 'kb'], path: '/knowledge-base' },
  { keywords: ['文档', '文件', '索引', 'doc'], path: '/document' },
  { keywords: ['对话', '聊天', 'chat'], path: '/chat' },
  { keywords: ['rag', '观测', '调试', '评估'], path: '/rag' },
  { keywords: ['开关', 'flag', '灰度'], path: '/admin/flags' },
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
const logoutButtonClass = computed(() =>
  [
    'w-full rounded-lg text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100',
    isSidebarOpen.value ? 'justify-start gap-3' : 'justify-center px-0',
  ].join(' ')
)

const applyTheme = (dark: boolean) => {
  document.documentElement.classList.toggle('dark', dark)
}

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value
}

const toggleTheme = () => {
  isDarkMode.value = !isDarkMode.value
  applyTheme(isDarkMode.value)
  localStorage.setItem('hfusionhub-theme', isDarkMode.value ? 'dark' : 'light')
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
  const storedTheme = localStorage.getItem('hfusionhub-theme')
  isDarkMode.value = storedTheme ? storedTheme === 'dark' : true
  applyTheme(isDarkMode.value)
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

      <nav class="flex-1 space-y-2 px-3 py-4">
        <p
          v-if="isSidebarOpen"
          class="px-3 text-xs font-medium uppercase text-zinc-600"
        >
          Workspace
        </p>
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          :title="item.label"
          :class="[
            'nav-pill group flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition-all duration-200',
            isActive(item.path)
              ? 'is-active text-white'
              : 'text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100',
            !isSidebarOpen && 'justify-center px-0',
          ]"
        >
          <component :is="item.icon" class="h-5 w-5 shrink-0" />
          <span v-if="isSidebarOpen" class="min-w-0">
            <span class="block truncate">{{ item.label }}</span>
            <span class="block truncate text-xs font-normal text-zinc-600 group-hover:text-zinc-400">
              {{ item.description }}
            </span>
          </span>
        </router-link>
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
          <span class="hidden items-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs font-medium text-emerald-300 sm:flex">
            <span class="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.9)]" />
            服务在线
          </span>
          <Button
            variant="ghost"
            size="icon"
            class="h-9 w-9 rounded-lg text-zinc-400 hover:bg-white/10 hover:text-white"
            title="通知"
          >
            <Bell class="h-4 w-4" />
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
            title="系统设置"
            @click="router.push('/admin/flags')"
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
  </div>
</template>
