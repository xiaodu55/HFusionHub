<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import * as conversationApi from '@/api/conversation'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import type { Conversation, KnowledgeBase } from '@/api/types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Plus, MessageSquare, Trash2, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { formatDateTime } from '@/utils/date'

const router = useRouter()

const conversations = ref<Conversation[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const isCreateDialogOpen = ref(false)
const createForm = ref({
  title: '',
  knowledgeBaseId: undefined as number | undefined,
})

// 分页状态
const currentPage = ref(1)
const pageSize = ref(12)
const total = ref(0)

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

const loadConversations = async () => {
  loading.value = true
  try {
    const res = await conversationApi.getMyConversations({
      page: currentPage.value,
      pageSize: pageSize.value,
    })
    conversations.value = res.data.records
    total.value = res.data.total
  } catch (error) {
    console.error('加载对话列表失败:', error)
  } finally {
    loading.value = false
  }
}

const loadKnowledgeBases = async () => {
  try {
    const res = await knowledgeBaseApi.getMyKnowledgeBaseList({
      page: 1,
      pageSize: 100,
    })
    knowledgeBases.value = res.data.records
  } catch (error) {
    console.error('加载知识库失败:', error)
  }
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadConversations()
}

const handleCreate = async () => {
  if (!createForm.value.title) return

  try {
    const res = await conversationApi.createConversation({
      title: createForm.value.title,
      knowledgeBaseId: createForm.value.knowledgeBaseId,
    })
    isCreateDialogOpen.value = false
    createForm.value = { title: '', knowledgeBaseId: undefined }
    // 后端返回完整 ConversationInfoDTO，提取 id
    const conversationId = res.data?.id
    if (conversationId) {
      router.push(`/chat/${conversationId}`)
    }
  } catch (error) {
    console.error('创建对话失败:', error)
  }
}

const handleDelete = async (conversation: Conversation) => {
  if (!confirm(`确定要删除对话「${conversation.title}」吗？`)) return

  try {
    await conversationApi.deleteConversation(conversation.id)
    await loadConversations()
  } catch (error) {
    console.error('删除对话失败:', error)
  }
}

const goToChat = (id: number) => {
  router.push(`/chat/${id}`)
}

const getKnowledgeBaseName = (conversation: Conversation) => {
  return conversation.knowledgeBaseName || '通用对话'
}

onMounted(() => {
  loadConversations()
  loadKnowledgeBases()
})
</script>

<template>
  <div class="space-y-6">
    <!-- 页面头部 -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold">对话管理</h2>
        <p class="text-muted-foreground">与 AI 进行智能对话</p>
      </div>
      <Button @click="isCreateDialogOpen = true">
        <Plus class="mr-2 h-4 w-4" />
        新建对话
      </Button>
    </div>

    <!-- 对话列表 -->
    <div v-if="loading" class="text-center text-muted-foreground py-8">
      加载中...
    </div>
    <div v-else-if="conversations.length === 0" class="text-center py-8">
      <MessageSquare class="mx-auto h-12 w-12 text-muted-foreground" />
      <p class="mt-4 text-muted-foreground">暂无对话，点击上方按钮新建</p>
    </div>
    <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <Card
        v-for="conversation in conversations"
        :key="conversation.id"
        class="cursor-pointer transition-shadow hover:shadow-md"
        @click="goToChat(conversation.id)"
      >
        <CardHeader>
          <div class="flex items-start justify-between">
            <div class="space-y-1">
              <CardTitle class="text-lg">{{ conversation.title }}</CardTitle>
              <CardDescription>
                {{ getKnowledgeBaseName(conversation) }}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div class="flex items-center justify-between text-sm text-muted-foreground">
            <span v-if="conversation.userName">{{ conversation.userName }}</span>
            <span>{{ formatDateTime(conversation.createdAt) }}</span>
          </div>
        </CardContent>
        <CardFooter class="flex justify-end">
          <Button
            variant="ghost"
            size="icon"
            @click.stop="handleDelete(conversation)"
          >
            <Trash2 class="h-4 w-4 text-destructive" />
          </Button>
        </CardFooter>
      </Card>
    </div>

    <!-- 分页控件 -->
    <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 mt-6">
      <Button
        variant="outline"
        size="sm"
        :disabled="currentPage === 1"
        @click="handlePageChange(currentPage - 1)"
      >
        <ChevronLeft class="h-4 w-4" />
      </Button>
      <span class="text-sm text-muted-foreground">
        第 {{ currentPage }} / {{ totalPages }} 页
      </span>
      <Button
        variant="outline"
        size="sm"
        :disabled="currentPage === totalPages"
        @click="handlePageChange(currentPage + 1)"
      >
        <ChevronRight class="h-4 w-4" />
      </Button>
    </div>

    <!-- 新建对话对话框 -->
    <Dialog v-model:open="isCreateDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建对话</DialogTitle>
          <DialogDescription>创建一个新的 AI 对话</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="title">对话标题 *</Label>
            <Input
              id="title"
              v-model="createForm.title"
              placeholder="请输入对话标题"
            />
          </div>
          <div class="space-y-2">
            <Label for="kb-select">选择知识库（可选）</Label>
            <select
              id="kb-select"
              v-model="createForm.knowledgeBaseId"
              class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option :value="undefined">通用对话</option>
              <option
                v-for="kb in knowledgeBases"
                :key="kb.id"
                :value="kb.id"
              >
                {{ kb.name }}
              </option>
            </select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isCreateDialogOpen = false">
            取消
          </Button>
          <Button @click="handleCreate">创建</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
