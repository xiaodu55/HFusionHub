<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as conversationApi from '@/api/conversation'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import * as promptTemplateApi from '@/api/promptTemplate'
import type { Conversation, KnowledgeBase } from '@/api/types'
import type { PromptTemplate } from '@/api/promptTemplate'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
import {
  ArrowRight,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Clock3,
  MessageSquare,
  Plus,
  Search,
  Sparkles,
  Trash2,
} from 'lucide-vue-next'
import { formatDateTime } from '@/utils/date'
import { useToast } from '@/composables/useToast'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'

const router = useRouter()
const toast = useToast()

const conversations = ref<Conversation[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const promptTemplates = ref<PromptTemplate[]>([])
const loading = ref(false)
const loadError = ref(false)
const searchQuery = ref('')
const isCreateDialogOpen = ref(false)
const createForm = ref({
  title: '',
  knowledgeBaseId: undefined as number | undefined,
  promptTemplateId: undefined as number | undefined,
})

const currentPage = ref(1)
const pageSize = ref(12)
const total = ref(0)
const selectedKbId = ref<number>(0) // 0 = 全部知识库

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))
const filteredConversations = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase()
  if (!keyword) return conversations.value

  return conversations.value.filter((conversation) =>
    [conversation.title, conversation.knowledgeBaseName, conversation.lastMessage, conversation.userName]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword)),
  )
})

const loadConversations = async () => {
  loading.value = true
  loadError.value = false
  try {
    const res = await conversationApi.getMyConversations({
      page: currentPage.value,
      pageSize: pageSize.value,
      title: searchQuery.value.trim() || undefined,
      knowledgeBaseId: selectedKbId.value > 0 ? selectedKbId.value : undefined,
    })
    conversations.value = res.data.records
    total.value = res.data.total
  } catch (error) {
    console.error('加载对话列表失败:', error)
    loadError.value = true
    toast.error('加载对话列表失败，请检查网络连接后重试')
  } finally {
    loading.value = false
  }
}

const handleFilterChange = () => {
  currentPage.value = 1
  loadConversations()
}

const loadKnowledgeBases = async () => {
  try {
    const res = await knowledgeBaseApi.getMyKnowledgeBaseList({ page: 1, pageSize: 100 })
    knowledgeBases.value = res.data.records.filter((knowledgeBase) => knowledgeBase.status === 0)
  } catch (error) {
    console.error('加载知识库失败:', error)
  }
}

const loadPromptTemplates = async () => {
  try {
    const res = await promptTemplateApi.listPromptTemplates()
    promptTemplates.value = res.data.filter((template) => template.status === 'PUBLISHED')
  } catch (error) {
    console.error('加载提示词模板失败:', error)
  }
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadConversations()
}

const openCreateDialog = () => {
  createForm.value = { title: '', knowledgeBaseId: undefined, promptTemplateId: undefined }
  isCreateDialogOpen.value = true
}

const handleCreate = async () => {
  const title = createForm.value.title.trim()
  if (!title) {
    toast.error('请先填写对话名称')
    return
  }

  try {
    const res = await conversationApi.createConversation({
      title,
      knowledgeBaseId: createForm.value.knowledgeBaseId,
      promptTemplateId: createForm.value.promptTemplateId,
    })
    isCreateDialogOpen.value = false
    const conversationId = res.data?.id
    if (conversationId) {
      router.push(`/chat/${conversationId}`)
    }
  } catch (error) {
    console.error('创建对话失败:', error)
    toast.error('创建对话失败，请稍后重试')
  }
}

const handleDelete = async (conversation: Conversation) => {
  if (!confirm(`确定要删除对话「${conversation.title}」吗？`)) return

  try {
    await conversationApi.deleteConversation(conversation.id)
    toast.success('对话已删除')
    await loadConversations()
  } catch (error) {
    console.error('删除对话失败:', error)
    toast.error('删除对话失败，请稍后重试')
  }
}

const goToChat = (id: number) => router.push(`/chat/${id}`)

const getKnowledgeBaseName = (conversation: Conversation) => conversation.knowledgeBaseName || '通用对话'
const getConversationPreview = (conversation: Conversation) =>
  conversation.lastMessage?.trim() || '从这里继续与 AI 交流。'
const getLastActivity = (conversation: Conversation) => conversation.updatedAt || conversation.createdAt

onMounted(() => {
  loadConversations()
  loadKnowledgeBases()
  loadPromptTemplates()
})
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary">
            <Sparkles class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-primary/90">AI WORKSPACE</p>
            <h2 class="mt-1 text-2xl font-semibold tracking-tight">智能对话</h2>
            <p class="mt-1 text-sm leading-6 text-muted-foreground">选择知识库后，AI 会优先根据其中已解析的资料回答问题。</p>
          </div>
        </div>
        <Button class="shrink-0 gap-2" @click="openCreateDialog">
          <Plus class="h-4 w-4" />
          新建对话
        </Button>
      </div>
    </section>

    <Card class="border-border bg-card/80">
      <CardContent class="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:p-5">
        <div class="relative flex-1">
          <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            v-model="searchQuery"
            placeholder="搜索对话名称、知识库或内容"
            class="pl-10"
            @keyup.enter="handleFilterChange"
          />
        </div>
        <select
          v-model="selectedKbId"
          aria-label="按知识库筛选对话"
          class="h-10 rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50"
          @change="handleFilterChange"
        >
          <option :value="0">全部知识库</option>
          <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
        </select>
        <div class="flex items-center gap-2 text-sm text-muted-foreground">
          <span class="rounded-full bg-muted px-3 py-1.5">共 {{ total }} 个对话</span>
          <span v-if="searchQuery || selectedKbId > 0" class="rounded-full bg-primary/10 px-3 py-1.5 text-primary">当前页 {{ filteredConversations.length }} 个匹配</span>
        </div>
      </CardContent>
    </Card>

    <LoadingSkeleton v-if="loading" type="card" :count="6" />
    <ErrorState v-else-if="loadError" message="加载对话列表失败" @retry="loadConversations" />
    <EmptyState
      v-else-if="conversations.length === 0"
      :icon="MessageSquare"
      title="还没有对话"
      description="新建一个对话，开始向 AI 提问；也可以选择知识库，让回答基于你的资料。"
      action="新建对话"
      :show-action="true"
      @action="openCreateDialog"
    />
    <EmptyState
      v-else-if="filteredConversations.length === 0"
      :icon="Search"
      title="没有找到匹配的对话"
      description="尝试更换搜索关键词。"
    />
    <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <article
        v-for="conversation in filteredConversations"
        :key="conversation.id"
        class="group relative cursor-pointer overflow-hidden rounded-2xl border border-border bg-card/80 p-5 transition-all hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-[0_18px_38px_rgba(0,0,0,0.14)] focus-within:border-primary/35"
        tabindex="0"
        role="link"
        @click="goToChat(conversation.id)"
        @keydown.enter="goToChat(conversation.id)"
      >
        <div class="flex items-start gap-3.5">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <MessageSquare class="h-5 w-5" />
          </div>
          <div class="min-w-0 flex-1">
            <h3 class="truncate text-base font-semibold">{{ conversation.title }}</h3>
            <Badge variant="outline" :class="`mt-2 max-w-full truncate ${conversation.knowledgeBaseName ? 'border-primary/25 bg-primary/10 text-primary' : 'border-border bg-muted text-muted-foreground'}`">
              <BookOpen class="mr-1 inline h-3 w-3" />
              {{ getKnowledgeBaseName(conversation) }}
            </Badge>
          </div>
        </div>

        <p class="mt-5 min-h-10 line-clamp-2 text-sm leading-5 text-muted-foreground">{{ getConversationPreview(conversation) }}</p>

        <div class="mt-5 flex items-center justify-between border-t border-border/70 pt-4 text-xs text-muted-foreground">
          <span v-if="conversation.userName" class="truncate">{{ conversation.userName }}</span>
          <span v-else>我的对话</span>
          <span class="ml-3 flex shrink-0 items-center gap-1"><Clock3 class="h-3.5 w-3.5" />{{ formatDateTime(getLastActivity(conversation)) }}</span>
        </div>

        <div class="absolute right-4 top-4 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          <Button variant="ghost" size="icon" class="h-8 w-8 hover:bg-rose-400/10" title="删除对话" @click.stop="handleDelete(conversation)">
            <Trash2 class="h-4 w-4 text-destructive" />
          </Button>
        </div>
        <div class="mt-4 flex items-center gap-1 text-sm font-medium text-primary">继续对话 <ArrowRight class="h-3.5 w-3.5" /></div>
      </article>
    </div>

    <div v-if="!searchQuery && totalPages > 1" class="flex items-center justify-center gap-2 pt-2">
      <Button variant="outline" size="sm" :disabled="currentPage === 1" @click="handlePageChange(currentPage - 1)">
        <ChevronLeft class="h-4 w-4" />
      </Button>
      <span class="text-sm text-muted-foreground">第 {{ currentPage }} / {{ totalPages }} 页</span>
      <Button variant="outline" size="sm" :disabled="currentPage === totalPages" @click="handlePageChange(currentPage + 1)">
        <ChevronRight class="h-4 w-4" />
      </Button>
    </div>

    <Dialog v-model:open="isCreateDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建对话</DialogTitle>
          <DialogDescription>为对话选择一个清晰的名称；选择知识库后，AI 会优先检索其中的资料。</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="title">对话名称 *</Label>
            <Input id="title" v-model="createForm.title" placeholder="例如：整理产品常见问题" @keydown.enter="handleCreate" />
          </div>
          <div class="space-y-2">
            <Label for="kb-select">关联知识库（可选）</Label>
            <select id="kb-select" v-model="createForm.knowledgeBaseId" class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
              <option :value="undefined">不关联知识库（通用对话）</option>
              <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
            </select>
            <p class="text-xs leading-5 text-muted-foreground">只显示当前可用的知识库。资料需完成解析后才会被 AI 检索。</p>
          </div>
          <div class="space-y-2">
            <Label for="prompt-template-select">回答方案（可选）</Label>
            <select id="prompt-template-select" v-model="createForm.promptTemplateId" class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
              <option :value="undefined">默认回答方式</option>
              <option v-for="template in promptTemplates" :key="template.id" :value="template.id">{{ template.name }}</option>
            </select>
            <p class="text-xs leading-5 text-muted-foreground">回答方案控制 AI 的语气、结构和回答边界；知识内容仍来自上方选择的知识库。这里只显示已发布方案。</p>
            <p v-if="!promptTemplates.length" class="rounded-md border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-xs leading-5 text-amber-100/85">当前没有已发布的回答方案。请先在“回答方案”页面创建、测试并发布。</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isCreateDialogOpen = false">取消</Button>
          <Button @click="handleCreate">创建并开始对话</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
