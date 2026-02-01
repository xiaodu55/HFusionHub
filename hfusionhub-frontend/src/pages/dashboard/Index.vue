<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { BookOpen, FileText, MessageSquare, Plus } from 'lucide-vue-next'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import * as documentApi from '@/api/document'
import * as conversationApi from '@/api/conversation'

const router = useRouter()
const userStore = useUserStore()

const stats = ref([
  { title: '知识库', value: 0, icon: BookOpen, color: 'text-blue-500', path: '/knowledge-base' },
  { title: '文档', value: 0, icon: FileText, color: 'text-green-500', path: '/document' },
  { title: '对话', value: 0, icon: MessageSquare, color: 'text-purple-500', path: '/chat' },
])

const quickActions = [
  { label: '创建知识库', icon: Plus, path: '/knowledge-base', color: 'bg-blue-500' },
  { label: '上传文档', icon: FileText, path: '/document', color: 'bg-green-500' },
  { label: '开始对话', icon: MessageSquare, path: '/chat', color: 'bg-purple-500' },
]

const loadStats = async () => {
  try {
    const [kbRes, docRes, convRes] = await Promise.all([
      knowledgeBaseApi.getMyKnowledgeBaseList({ pageNum: 1, pageSize: 1 }),
      documentApi.getMyDocumentsByKbId(0, { pageNum: 1, pageSize: 1 }),
      conversationApi.getMyConversations({ pageNum: 1, pageSize: 1 }),
    ])
    stats.value[0].value = kbRes.data.total || 0
    stats.value[1].value = docRes.data.total || 0
    stats.value[2].value = convRes.data.total || 0
  } catch (error) {
    console.error('获取统计数据失败:', error)
  }
}

onMounted(async () => {
  try {
    await userStore.getUserInfo()
    await loadStats()
  } catch (error) {
    console.error('获取用户信息失败:', error)
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- 欢迎信息 -->
    <div>
      <h2 class="text-2xl font-bold">
        欢迎回来，{{ userStore.nickname || userStore.username }}
      </h2>
      <p class="text-muted-foreground">
        HFusionHub AI Agent 智能平台
      </p>
    </div>

    <!-- 统计卡片 -->
    <div class="grid gap-4 md:grid-cols-3">
      <Card
        v-for="stat in stats"
        :key="stat.title"
        class="cursor-pointer transition-shadow hover:shadow-md"
        @click="router.push(stat.path)"
      >
        <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle class="text-sm font-medium">
            {{ stat.title }}
          </CardTitle>
          <component :is="stat.icon" :class="['h-4 w-4', stat.color]" />
        </CardHeader>
        <CardContent>
          <div class="text-2xl font-bold">{{ stat.value }}</div>
          <p class="text-xs text-muted-foreground">
            点击查看全部
          </p>
        </CardContent>
      </Card>
    </div>

    <!-- 快捷操作 -->
    <Card>
      <CardHeader>
        <CardTitle>快捷操作</CardTitle>
        <CardDescription>快速开始使用平台功能</CardDescription>
      </CardHeader>
      <CardContent>
        <div class="grid gap-4 md:grid-cols-3">
          <Button
            v-for="action in quickActions"
            :key="action.label"
            variant="outline"
            class="h-24 flex-col gap-2"
            @click="router.push(action.path)"
          >
            <component :is="action.icon" class="h-6 w-6" />
            <span>{{ action.label }}</span>
          </Button>
        </div>
      </CardContent>
    </Card>

    <!-- 功能介绍 -->
    <Card>
      <CardHeader>
        <CardTitle>平台功能</CardTitle>
        <CardDescription>HFusionHub 提供的核心功能</CardDescription>
      </CardHeader>
      <CardContent>
        <div class="grid gap-6 md:grid-cols-2">
          <div class="space-y-2">
            <h3 class="font-semibold">📚 知识库管理</h3>
            <p class="text-sm text-muted-foreground">
              创建和管理知识库，为 AI 提供专属知识支持
            </p>
          </div>
          <div class="space-y-2">
            <h3 class="font-semibold">📄 文档处理</h3>
            <p class="text-sm text-muted-foreground">
              上传和管理文档，自动解析提取知识内容
            </p>
          </div>
          <div class="space-y-2">
            <h3 class="font-semibold">💬 智能对话</h3>
            <p class="text-sm text-muted-foreground">
              基于知识库的 AI 对话，精准回答问题
            </p>
          </div>
          <div class="space-y-2">
            <h3 class="font-semibold">🔧 工具集成</h3>
            <p class="text-sm text-muted-foreground">
              支持自定义工具扩展 AI Agent 能力
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
