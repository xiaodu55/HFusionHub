<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  Menu,
  X,
  Home,
  BookOpen,
  FileText,
  MessageSquare,
  Activity,
  User,
  LogOut,
  Moon,
  Sun,
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const isSidebarOpen = ref(true)
const isDarkMode = ref(false)

const menuItems = [
  { path: '/', label: '仪表盘', icon: Home },
  { path: '/knowledge-base', label: '知识库', icon: BookOpen },
  { path: '/document', label: '文档', icon: FileText },
  { path: '/chat', label: '对话', icon: MessageSquare },
  { path: '/rag', label: 'RAG 调试', icon: Activity },
]

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value
}

const toggleTheme = () => {
  isDarkMode.value = !isDarkMode.value
  document.documentElement.classList.toggle('dark')
}

const handleLogout = async () => {
  await userStore.logout()
  router.push('/login')
}

const isActive = (path: string) => {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(path)
}
</script>

<template>
  <div class="flex h-screen bg-background">
    <!-- 侧边栏 -->
    <aside
      :class="[
        'flex flex-col border-r bg-card transition-all duration-300',
        isSidebarOpen ? 'w-64' : 'w-16'
      ]"
    >
      <!-- Logo -->
      <div class="flex h-16 items-center justify-between border-b px-4">
        <span v-if="isSidebarOpen" class="text-xl font-bold text-primary">
          HFusionHub
        </span>
        <Button variant="ghost" size="icon" @click="toggleSidebar">
          <Menu v-if="!isSidebarOpen" class="h-5 w-5" />
          <X v-else class="h-5 w-5" />
        </Button>
      </div>

      <!-- 导航菜单 -->
      <nav class="flex-1 space-y-1 p-2">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          :class="[
            'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
            isActive(item.path)
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
          ]"
        >
          <component :is="item.icon" class="h-5 w-5" />
          <span v-if="isSidebarOpen">{{ item.label }}</span>
        </router-link>
      </nav>

      <!-- 底部操作 -->
      <div class="border-t p-2">
        <Button
          variant="ghost"
          class="w-full justify-start gap-3"
          @click="router.push('/profile')"
        >
          <User class="h-5 w-5" />
          <span v-if="isSidebarOpen">个人中心</span>
        </Button>
        <Button
          variant="ghost"
          class="w-full justify-start gap-3"
          @click="handleLogout"
        >
          <LogOut class="h-5 w-5" />
          <span v-if="isSidebarOpen">退出登录</span>
        </Button>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="flex flex-1 flex-col overflow-hidden">
      <!-- 顶栏 -->
      <header class="flex h-16 items-center justify-between border-b bg-card px-4">
        <div class="flex items-center gap-4">
          <h1 class="text-lg font-semibold">
            {{ menuItems.find(item => isActive(item.path))?.label || 'HFusionHub' }}
          </h1>
        </div>
        <div class="flex items-center gap-4">
          <Button variant="ghost" size="icon" @click="toggleTheme">
            <Sun v-if="isDarkMode" class="h-5 w-5" />
            <Moon v-else class="h-5 w-5" />
          </Button>
          <div class="flex items-center gap-2">
            <span class="text-sm text-muted-foreground">
              {{ userStore.nickname || userStore.username }}
            </span>
          </div>
        </div>
      </header>

      <!-- 内容区域 -->
      <main class="flex-1 overflow-auto p-6">
        <router-view />
      </main>
    </div>
  </div>
</template>
