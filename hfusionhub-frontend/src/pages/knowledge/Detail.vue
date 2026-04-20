<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import * as documentApi from '@/api/document'
import * as vectorizationApi from '@/api/vectorization'
import * as conversationApi from '@/api/conversation'
import * as kbShareApi from '@/api/kbShare'
import { searchUsers, type UserSearchResult } from '@/api/user'
import { useToast } from '@/composables/useToast'
import { useDocumentProcessor } from '@/composables/useDocumentProcessor'
import { formatFileSize, getStatusBadge } from '@/utils/format'
import type { KnowledgeBase, Document } from '@/api/types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
import { ArrowLeft, Plus, FileText, Trash2, Upload, Play, Eye, Loader2, RefreshCw, RefreshCcw, Power, PowerOff, MessageSquare, Share2, Search, UserPlus, X } from 'lucide-vue-next'
import { formatDateTime } from '@/utils/date'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'

const route = useRoute()
const toast = useToast()
const router = useRouter()

// 使用文档处理器 composable
const {
  processingDocs,
  isModelDialogOpen,
  selectedDocForVectorize,
  availableModels,
  selectedModel,
  loadingModels,
  processingStatus,
  openModelDialog,
  pollDocumentStatus,
  startVectorization,
  resetDocument,
  trackProcessingDocuments,
  processingProgress,
  formatProcessingTime,
  getStageText,
} = useDocumentProcessor()

const knowledgeBase = ref<KnowledgeBase | null>(null)
const documents = ref<Document[]>([])
const loading = ref(false)
const loadError = ref(false)
const isUploadDialogOpen = ref(false)
const uploadFile = ref<File | null>(null)
const uploading = ref(false)
const syncing = ref(false)
const statusUpdating = ref(false)

// ── 知识库共享 ──
const isShareDialogOpen = ref(false)
const shares = ref<kbShareApi.KbShareInfo[]>([])
const shareLoading = ref(false)
const shareKeyword = ref('')
const shareResults = ref<UserSearchResult[]>([])
const shareSearching = ref(false)
const shareSearchError = ref('')
const sharingUserId = ref<number | null>(null)

const loadShares = async () => {
  if (!knowledgeBase.value) return
  shareLoading.value = true
  try {
    shares.value = (await kbShareApi.listKbShares(knowledgeBase.value.id)).data
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载共享记录失败')
  } finally {
    shareLoading.value = false
  }
}

const openShareDialog = async () => {
  isShareDialogOpen.value = true
  shareKeyword.value = ''
  shareResults.value = []
  shareSearchError.value = ''
  await loadShares()
}

const searchShareUsers = async () => {
  const keyword = shareKeyword.value.trim()
  if (!keyword) {
    shareResults.value = []
    return
  }
  shareSearching.value = true
  shareSearchError.value = ''
  try {
    shareResults.value = (await searchUsers(keyword)).data
  } catch (error) {
    shareSearchError.value = error instanceof Error ? error.message : '搜索用户失败'
    shareResults.value = []
  } finally {
    shareSearching.value = false
  }
}

const handleShare = async (user: UserSearchResult) => {
  if (!knowledgeBase.value || sharingUserId.value !== null) return
  sharingUserId.value = user.id
  try {
    await kbShareApi.shareKnowledgeBase(knowledgeBase.value.id, user.id)
    toast.success(`已共享「${knowledgeBase.value.name}」给 ${user.nickname || user.username}`)
    shareKeyword.value = ''
    shareResults.value = []
    await loadShares()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '共享失败')
  } finally {
    sharingUserId.value = null
  }
}

const handleRevokeShare = async (share: kbShareApi.KbShareInfo) => {
  if (!knowledgeBase.value) return
  try {
    await kbShareApi.revokeKbShare(knowledgeBase.value.id, share.id)
    toast.success(`已撤销对 ${share.sharedUsername || '该用户'} 的共享`)
    shares.value = shares.value.filter(item => item.id !== share.id)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '撤销共享失败')
  }
}

// 基于该知识库发起对话
const startChatWithKb = async () => {
  if (!knowledgeBase.value || knowledgeBase.value.status !== 0) return
  try {
    const res = await conversationApi.createConversation({
      title: `关于「${knowledgeBase.value.name}」的对话`,
      knowledgeBaseId: knowledgeBase.value.id,
    })
    if (res.data?.id) {
      router.push(`/chat/${res.data.id}`)
    }
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '创建对话失败')
  }
}

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error && error.message ? `${fallback}：${error.message}` : fallback

const loadKnowledgeBase = async () => {
  const id = Number(route.params.id)
  try {
    const res = await knowledgeBaseApi.getKnowledgeBase(id)
    knowledgeBase.value = res.data
  } catch (error) {
    console.error('加载知识库失败:', error)
    toast.error('加载知识库失败')
  }
}

const loadDocuments = async () => {
  loading.value = true
  loadError.value = false
  const id = Number(route.params.id)
  try {
    const res = await documentApi.getMyDocumentsByKbId(id, {
      page: 1,
      pageSize: 100,
    })
    documents.value = res.data.records
    trackProcessingDocuments(documents.value, () => loadDocuments())
  } catch (error) {
    console.error('加载文档失败:', error)
    loadError.value = true
    toast.error(errorMessage(error, '加载文档失败'))
  } finally {
    loading.value = false
  }
}

const handleToggleStatus = async () => {
  if (!knowledgeBase.value) return

  const nextStatus = knowledgeBase.value.status === 0 ? 1 : 0
  statusUpdating.value = true
  try {
    await knowledgeBaseApi.updateKnowledgeBase(knowledgeBase.value.id, { status: nextStatus })
    toast.success(nextStatus === 0 ? '知识库已启用' : '知识库已禁用，正在清理分块和索引')
    await Promise.all([loadKnowledgeBase(), loadDocuments()])
  } catch (error) {
    console.error('更新知识库状态失败:', error)
    toast.error(errorMessage(error, '更新知识库状态失败'))
  } finally {
    statusUpdating.value = false
  }
}

const handleFileSelect = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (input.files && input.files[0]) {
    uploadFile.value = input.files[0]
  }
}

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

const handleUpload = async () => {
  if (!uploadFile.value || !knowledgeBase.value) return
  if (knowledgeBase.value.status !== 0) {
    toast.error('知识库已禁用，无法上传文档')
    return
  }

  // 文件大小校验
  if (uploadFile.value.size > MAX_FILE_SIZE) {
    toast.error('文件大小不能超过 10MB')
    return
  }

  uploading.value = true
  try {
    await documentApi.uploadDocument(uploadFile.value, knowledgeBase.value.id)
    isUploadDialogOpen.value = false
    uploadFile.value = null
    toast.success('文档上传成功')
    await loadDocuments()
  } catch (error) {
    console.error('上传文档失败:', error)
    toast.error(errorMessage(error, '上传文档失败'))
  } finally {
    uploading.value = false
  }
}

const handleDeleteDocument = async (doc: Document) => {
  if (!confirm(`确定要删除文档「${doc.title}」吗？`)) return

  try {
    await documentApi.deleteDocument(doc.id)
    toast.success('已提交删除任务')
    await loadDocuments()
  } catch (error) {
    console.error('删除文档失败:', error)
    toast.error('删除文档失败')
  }
}

const handleStartVectorization = async (doc: Document) => {
  openModelDialog(doc)
}

const confirmStartVectorization = async () => {
  if (!selectedDocForVectorize.value) return

  try {
    await startVectorization(selectedDocForVectorize.value, {
      onSuccess: () => loadDocuments(),
    })
    toast.success('开始解析')
  } catch (error) {
    console.error('启动向量化失败:', error)
    toast.error(errorMessage(error, '启动向量化失败'))
  }
}

const reparseLoading = ref<Set<number>>(new Set())

const handleResetDocument = async (doc: Document) => {
  const s = new Set(reparseLoading.value)
  s.add(doc.id)
  reparseLoading.value = s
  try {
    // 1. 重置文档状态
    await resetDocument(doc)
    // 2. 直接启动向量化（跳过模型对话框，使用默认模型）
    await startVectorization(doc, {
      onSuccess: () => {
        loadDocuments()
        const s2 = new Set(reparseLoading.value)
        s2.delete(doc.id)
        reparseLoading.value = s2
      },
    })
    toast.success('已开始重新解析')
  } catch (error) {
    const s2 = new Set(reparseLoading.value)
    s2.delete(doc.id)
    reparseLoading.value = s2
    toast.error('重新解析失败')
  }
}

const handleSyncStatus = async () => {
  syncing.value = true
  try {
    await vectorizationApi.syncAllDocuments()
    toast.success('状态同步完成')
    await loadDocuments()
  } catch (error) {
    console.error('同步状态失败:', error)
    toast.error('同步状态失败')
  } finally {
    syncing.value = false
  }
}

const handleViewChunks = (doc: Document) => {
  router.push(`/knowledge-base/${route.params.id}/chunks/${doc.id}`)
}

const goBack = () => {
  router.push('/knowledge-base')
}

onMounted(() => {
  loadKnowledgeBase()
  loadDocuments()
})
</script>

<template>
  <div class="space-y-6">
    <!-- 返回按钮和标题 -->
    <div class="flex items-center gap-4">
      <Button variant="ghost" size="icon" @click="goBack">
        <ArrowLeft class="h-5 w-5" />
      </Button>
      <div v-if="knowledgeBase" class="flex-1">
        <div class="flex items-center gap-3">
          <h2 class="text-2xl font-bold">{{ knowledgeBase.name }}</h2>
          <Badge :variant="knowledgeBase.status === 0 ? 'default' : 'secondary'">
            {{ knowledgeBase.status === 0 ? '启用' : '禁用' }}
          </Badge>
        </div>
        <p class="text-muted-foreground">
          {{ knowledgeBase.description || '暂无描述' }}
        </p>
      </div>
      <Button
        :disabled="!knowledgeBase || knowledgeBase.status !== 0"
        @click="startChatWithKb"
      >
        <MessageSquare class="mr-2 h-4 w-4" />
        开始对话
      </Button>
      <Button
        :disabled="!knowledgeBase"
        variant="outline"
        @click="openShareDialog"
      >
        <Share2 class="mr-2 h-4 w-4" />
        共享
      </Button>
      <Button
        :disabled="!knowledgeBase || knowledgeBase.status !== 0"
        @click="isUploadDialogOpen = true"
      >
        <Upload class="mr-2 h-4 w-4" />
        上传文档
      </Button>
      <Button
        v-if="knowledgeBase"
        variant="outline"
        :disabled="statusUpdating"
        :title="knowledgeBase.status === 0 ? '禁用知识库并清理分块与索引' : '启用知识库'"
        @click="handleToggleStatus"
      >
        <Loader2 v-if="statusUpdating" class="mr-2 h-4 w-4 animate-spin" />
        <PowerOff v-else-if="knowledgeBase.status === 0" class="mr-2 h-4 w-4" />
        <Power v-else class="mr-2 h-4 w-4" />
        {{ knowledgeBase.status === 0 ? '禁用知识库' : '启用知识库' }}
      </Button>
      <Button variant="outline" @click="handleSyncStatus" :disabled="syncing">
        <RefreshCcw :class="['mr-2 h-4 w-4', { 'animate-spin': syncing }]" />
        同步状态
      </Button>
    </div>

    <!-- 文档列表 -->
    <Card>
      <CardHeader>
        <CardTitle>文档列表</CardTitle>
        <CardDescription>管理此知识库中的文档</CardDescription>
      </CardHeader>
      <CardContent>
        <LoadingSkeleton v-if="loading" type="card" :count="3" />
        <ErrorState v-else-if="loadError" message="加载文档失败" @retry="loadDocuments" />
        <div v-else-if="documents.length === 0" class="text-center py-8">
          <FileText class="mx-auto h-12 w-12 text-muted-foreground" />
          <p class="mt-4 text-muted-foreground">暂无文档，点击上方按钮上传</p>
        </div>
        <div v-else class="space-y-4">
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="flex items-center justify-between rounded-lg border p-4"
          >
            <div class="flex items-center gap-4">
              <FileText class="h-8 w-8 text-muted-foreground" />
              <div>
                <p class="font-medium">{{ doc.title }}</p>
                <p class="text-sm text-muted-foreground">
                  {{ formatFileSize(doc.fileSize) }} · {{ formatDateTime(doc.createdAt) }}
                </p>
                <p v-if="doc.username" class="text-sm text-muted-foreground">
                  上传者：{{ doc.username }}
                </p>
                <div v-if="processingDocs.has(doc.id)" class="mt-2 w-full max-w-md space-y-1">
                  <div class="h-2 rounded bg-muted">
                    <div
                      class="h-2 rounded bg-primary transition-all"
                      :style="{ width: `${processingProgress(doc.id)}%` }"
                    />
                  </div>
                  <p class="text-xs text-muted-foreground">
                    {{ getStageText(processingStatus[doc.id]?.stage) }} · {{ processingProgress(doc.id) }}% · 已用 {{ formatProcessingTime(processingStatus[doc.id]?.elapsedSeconds) }} · 预计剩余 {{ formatProcessingTime(processingStatus[doc.id]?.remainingSeconds) }}
                  </p>
                </div>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <Badge :variant="getStatusBadge(doc.status).variant">
                {{ getStatusBadge(doc.status).text }}
              </Badge>

              <!-- 开始解析按钮 -->
              <Button
                v-if="doc.status === 0 && !reparseLoading.has(doc.id)"
                variant="outline"
                size="sm"
                :disabled="knowledgeBase?.status !== 0 || processingDocs.has(doc.id)"
                @click="handleStartVectorization(doc)"
              >
                <Loader2 v-if="processingDocs.has(doc.id)" class="mr-2 h-4 w-4 animate-spin" />
                <Play v-else class="mr-2 h-4 w-4" />
                {{ processingDocs.has(doc.id) ? '处理中...' : '开始解析' }}
              </Button>

              <!-- 重新解析按钮（处理中或失败时显示，以及正在重新解析时显示） -->
              <Button
                v-if="doc.status === 1 || doc.status === 3 || reparseLoading.has(doc.id)"
                variant="outline"
                size="sm"
                :disabled="knowledgeBase?.status !== 0 || reparseLoading.has(doc.id)"
                @click="handleResetDocument(doc)"
              >
                <Loader2 v-if="reparseLoading.has(doc.id)" class="mr-2 h-4 w-4 animate-spin" />
                <RefreshCw v-else class="mr-2 h-4 w-4" />
                {{ reparseLoading.has(doc.id) ? '重新解析中...' : '重新解析' }}
              </Button>

              <!-- 查看分块按钮 -->
              <Button
                v-if="doc.status === 2"
                variant="outline"
                size="sm"
                @click="handleViewChunks(doc)"
              >
                <Eye class="mr-2 h-4 w-4" />
                查看分块
              </Button>

              <Button
                v-if="doc.status === 2"
                variant="outline"
                size="sm"
                :disabled="knowledgeBase?.status !== 0 || processingDocs.has(doc.id)"
                @click="handleStartVectorization(doc)"
              >
                <Loader2 v-if="processingDocs.has(doc.id)" class="mr-2 h-4 w-4 animate-spin" />
                <RefreshCw v-else class="mr-2 h-4 w-4" />
                {{ processingDocs.has(doc.id) ? '处理中...' : '重新分块' }}
              </Button>

              <Button
                variant="ghost"
                size="icon"
                :disabled="doc.status === 4"
                @click="handleDeleteDocument(doc)"
              >
                <Loader2 v-if="doc.status === 4" class="h-4 w-4 animate-spin" />
                <Trash2 v-else class="h-4 w-4 text-destructive" />
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- 上传文档对话框 -->
    <Dialog v-model:open="isUploadDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>上传文档</DialogTitle>
          <DialogDescription>上传文档到此知识库</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <Input
              type="file"
              accept=".txt,.pdf,.docx,.md"
              @change="handleFileSelect"
            />
            <p class="text-sm text-muted-foreground">
              支持 TXT、PDF、DOCX、MD 格式
            </p>
          </div>
          <div v-if="uploadFile" class="rounded-lg bg-muted p-3">
            <p class="text-sm">
              {{ uploadFile.name }} ({{ formatFileSize(uploadFile.size) }})
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isUploadDialogOpen = false">
            取消
          </Button>
          <Button :disabled="!uploadFile || uploading || knowledgeBase?.status !== 0" @click="handleUpload">
            {{ uploading ? '上传中...' : '上传' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 模型选择对话框 -->
    <Dialog v-model:open="isModelDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>选择嵌入模型</DialogTitle>
          <DialogDescription>
            选择用于向量化的嵌入模型。文档：{{ selectedDocForVectorize?.title }}
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div v-if="loadingModels" class="text-center py-4">
            <Loader2 class="h-6 w-6 animate-spin mx-auto" />
            <p class="text-sm text-muted-foreground mt-2">加载模型列表...</p>
          </div>
          <div v-else class="space-y-3">
            <Label>可用模型</Label>
            <div class="space-y-2">
              <div
                v-for="model in availableModels"
                :key="model.id"
                class="flex items-center space-x-3 rounded-lg border p-3 cursor-pointer hover:bg-muted"
                :class="{ 'border-primary bg-muted': selectedModel === model.id }"
                @click="selectedModel = model.id"
              >
                <input
                  type="radio"
                  :value="model.id"
                  v-model="selectedModel"
                  class="h-4 w-4"
                />
                <div class="flex-1">
                  <p class="font-medium">{{ model.name }}</p>
                  <p class="text-sm text-muted-foreground">{{ model.description }}</p>
                  <p class="text-xs text-muted-foreground">
                    类型：{{ model.type === 'local' ? '本地' : model.type === 'cloud' ? '云端' : '降级' }}
                    · 维度：{{ model.dimension }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isModelDialogOpen = false">
            取消
          </Button>
          <Button @click="confirmStartVectorization" :disabled="!selectedModel || loadingModels">
            开始解析
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 共享知识库对话框 -->
    <Dialog v-model:open="isShareDialogOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>共享知识库</DialogTitle>
          <DialogDescription>将「{{ knowledgeBase?.name }}」以只读方式共享给其他用户，对方即可基于它提问。</DialogDescription>
        </DialogHeader>

        <div class="space-y-4">
          <!-- 搜索并添加 -->
          <div class="space-y-2">
            <Label for="share-search">按用户名搜索用户</Label>
            <div class="flex gap-2">
              <Input
                id="share-search"
                v-model="shareKeyword"
                placeholder="输入用户名或昵称"
                @keyup.enter="searchShareUsers"
              />
              <Button variant="outline" :disabled="shareSearching || !shareKeyword.trim()" @click="searchShareUsers">
                <Loader2 v-if="shareSearching" class="h-4 w-4 animate-spin" />
                <Search v-else class="h-4 w-4" />
                搜索
              </Button>
            </div>
            <p v-if="shareSearchError" class="text-sm text-destructive">{{ shareSearchError }}</p>
            <div v-if="shareResults.length" class="space-y-1.5">
              <div
                v-for="user in shareResults"
                :key="user.id"
                class="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2"
              >
                <div class="min-w-0">
                  <p class="truncate text-sm font-medium">{{ user.nickname || user.username }}</p>
                  <p class="truncate text-xs text-muted-foreground">@{{ user.username }}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  :disabled="sharingUserId !== null || shares.some(s => s.sharedUserId === user.id)"
                  @click="handleShare(user)"
                >
                  <Loader2 v-if="sharingUserId === user.id" class="mr-1 h-3 w-3 animate-spin" />
                  <UserPlus v-else class="mr-1 h-3 w-3" />
                  {{ shares.some(s => s.sharedUserId === user.id) ? '已共享' : '共享' }}
                </Button>
              </div>
              <p v-if="shareResults.length && !shareResults.some(u => !shares.some(s => s.sharedUserId === u.id))" class="text-xs text-muted-foreground">
                以上用户均已共享过该知识库。
              </p>
            </div>
            <p v-else-if="shareKeyword.trim() && !shareSearching" class="text-xs text-muted-foreground">
              未找到匹配的用户，请尝试其他用户名或昵称。
            </p>
          </div>

          <!-- 已有共享记录 -->
          <div class="space-y-2">
            <p class="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">当前共享（{{ shares.length }}）</p>
            <div v-if="shareLoading" class="py-4 text-center text-sm text-muted-foreground">正在加载…</div>
            <div v-else-if="!shares.length" class="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
              还没有共享给其他用户。
            </div>
            <div v-else class="space-y-1.5">
              <div
                v-for="share in shares"
                :key="share.id"
                class="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2"
              >
                <div class="min-w-0">
                  <p class="truncate text-sm font-medium">{{ share.sharedUsername || `用户 #${share.sharedUserId}` }}</p>
                  <p class="truncate text-xs text-muted-foreground">只读 · {{ formatDateTime(share.createdAt) }}</p>
                </div>
                <Button variant="ghost" size="sm" class="text-destructive hover:bg-rose-400/10" @click="handleRevokeShare(share)">
                  <X class="mr-1 h-3 w-3" />
                  撤销
                </Button>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="isShareDialogOpen = false">关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
