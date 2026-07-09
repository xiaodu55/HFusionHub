<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as documentApi from '@/api/document'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import * as vectorizationApi from '@/api/vectorization'
import { useToast } from '@/composables/useToast'
import { useDocumentProcessor } from '@/composables/useDocumentProcessor'
import { formatFileSize } from '@/utils/format'
import { getStatusBadge } from '@/utils/badge'
import type { Document, KnowledgeBase } from '@/api/types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Search, FileText, Trash2, Upload, Play, Eye, Loader2, RefreshCw, RefreshCcw, Archive, Files, FolderOpen, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { formatDateTime } from '@/utils/date'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

const router = useRouter()
const toast = useToast()

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

const documents = ref<Document[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const loadError = ref(false)
const searchQuery = ref('')
const selectedKbId = ref<number>(0) // 0 = 全部
// 状态筛选：'' = 全部；0-待解析 1-解析中 2-已完成 3-失败（DocumentStatus 枚举）
const selectedStatus = ref<number | ''>('')
// 服务端分页（后端 /document/my/{kbId} 支持 page/pageSize）
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const isUploadDialogOpen = ref(false)
const uploadForm = ref({
  kbId: 0,
  file: null as File | null,
  title: '',
})
const uploadMode = ref<'file' | 'url'>('file')
const urlForm = ref({
  kbId: 0,
  url: '',
  title: '',
})
const uploading = ref(false)
const urlAdding = ref(false)
const syncing = ref(false)
const deleteTarget = ref<Document | null>(null)
const confirmDeleteOpen = ref(false)
const confirmDeleteLoading = ref(false)
const hasEnabledKnowledgeBase = computed(() => knowledgeBases.value.some((kb) => kb.status === 0))
const parsedDocumentCount = computed(() => documents.value.filter(doc => doc.status === 2).length)
const processingDocumentCount = computed(() => documents.value.filter(doc => doc.status === 1 || processingDocs.value.has(doc.id)).length)

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error && error.message ? `${fallback}：${error.message}` : fallback

// 请求序号：切换知识库 / 触发轮询时丢弃过期响应，防止旧响应覆盖新列表（F1）
let loadSeq = 0

const loadDocuments = async () => {
  const seq = ++loadSeq
  loading.value = true
  loadError.value = false
  try {
    const statusParam = selectedStatus.value === '' ? undefined : selectedStatus.value
    let res
    if (selectedKbId.value > 0) {
      res = await documentApi.getMyDocumentsByKbId(selectedKbId.value, {
        page: currentPage.value,
        pageSize: pageSize.value,
        status: statusParam,
      })
    } else {
      res = await documentApi.getMyDocumentsByKbId(0, {
        page: currentPage.value,
        pageSize: pageSize.value,
        status: statusParam,
      })
    }
    if (seq !== loadSeq) return // 过期响应（用户已切换知识库/翻页）
    documents.value = res.data.records
    total.value = res.data.total
    // 删除后当前页可能为空：若总记录数仍大于 0，回退一页
    if (documents.value.length === 0 && currentPage.value > 1 && total.value > 0) {
      currentPage.value -= 1
      await loadDocuments()
    }
    trackProcessingDocuments(documents.value, () => loadDocuments())
  } catch (error) {
    console.error('加载文档失败:', error)
    if (seq !== loadSeq) return
    loadError.value = true
    toast.error(errorMessage(error, '加载文档失败'))
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

const handlePageChange = (page: number) => {
  if (page < 1 || page > totalPages.value || page === currentPage.value) return
  currentPage.value = page
  loadDocuments()
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
    toast.error('加载知识库失败')
  }
}

const handleFileSelect = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (input.files && input.files[0]) {
    uploadForm.value.file = input.files[0]
  }
}

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

const handleUpload = async () => {
  if (!uploadForm.value.file || !uploadForm.value.kbId) return
  const selectedKnowledgeBase = knowledgeBases.value.find((kb) => kb.id === uploadForm.value.kbId)
  if (!selectedKnowledgeBase || selectedKnowledgeBase.status !== 0) {
    toast.error('知识库已禁用，无法上传文档')
    return
  }

  // 文件大小校验
  if (uploadForm.value.file.size > MAX_FILE_SIZE) {
    toast.error('文件大小不能超过 10MB')
    return
  }

  uploading.value = true
  try {
    await documentApi.uploadDocument(uploadForm.value.file, uploadForm.value.kbId, uploadForm.value.title)
    isUploadDialogOpen.value = false
    uploadForm.value = { kbId: 0, file: null, title: '' }
    toast.success('文档上传成功')
    await loadDocuments()
  } catch (error) {
    console.error('上传文档失败:', error)
    toast.error(errorMessage(error, '上传文档失败'))
  } finally {
    uploading.value = false
  }
}

const handleAddFromUrl = async () => {
  if (!urlForm.value.url.trim() || !urlForm.value.kbId) return
  const selectedKnowledgeBase = knowledgeBases.value.find((kb) => kb.id === urlForm.value.kbId)
  if (!selectedKnowledgeBase || selectedKnowledgeBase.status !== 0) {
    toast.error('知识库已禁用，无法添加网页文档')
    return
  }
  if (!/^https:\/\//i.test(urlForm.value.url.trim())) {
    toast.error('仅支持公开的 HTTPS 网页地址')
    return
  }

  urlAdding.value = true
  try {
    await documentApi.createDocumentFromUrl(urlForm.value.url.trim(), urlForm.value.kbId, urlForm.value.title.trim() || undefined)
    isUploadDialogOpen.value = false
    urlForm.value = { kbId: 0, url: '', title: '' }
    toast.success('网页已抓取，请在列表中点击解析')
    await loadDocuments()
  } catch (error) {
    console.error('添加网页失败:', error)
    toast.error(errorMessage(error, '添加网页失败'))
  } finally {
    urlAdding.value = false
  }
}

const handleDelete = (doc: Document) => {
  deleteTarget.value = doc
  confirmDeleteOpen.value = true
}

const confirmDelete = async () => {
  const doc = deleteTarget.value
  if (!doc) return
  confirmDeleteLoading.value = true
  try {
    await documentApi.deleteDocument(doc.id)
    toast.success('已提交移入回收站任务')
    await loadDocuments()
  } catch (error) {
    console.error('删除文档失败:', error)
    toast.error('删除文档失败')
  } finally {
    confirmDeleteLoading.value = false
    confirmDeleteOpen.value = false
    deleteTarget.value = null
  }
}

const handleStartVectorization = async (doc: Document) => {
  openModelDialog(doc)
}

const confirmStartVectorization = async () => {
  if (!selectedDocForVectorize.value) return

  try {
    // 根据文档状态调用不同的API
    if (selectedDocForVectorize.value.status === 0) {
      await startVectorization(selectedDocForVectorize.value, {
        onSuccess: () => loadDocuments(),
      })
    } else {
      // 已完成状态，调用重新解析 — 加入 processingDocs 以显示进度
      const docId = selectedDocForVectorize.value.id
      const s = new Set(processingDocs.value)
      s.add(docId)
      processingDocs.value = s
      try {
        await documentApi.parseDocument(docId, selectedModel.value)
        selectedDocForVectorize.value.status = 1
        pollDocumentStatus(docId, () => loadDocuments())
      } catch (reparseError) {
        const s2 = new Set(processingDocs.value)
        s2.delete(docId)
        processingDocs.value = s2
        throw reparseError
      }
    }
    toast.success('开始解析')
  } catch (error) {
    console.error('启动向量化失败:', error)
    toast.error(errorMessage(error, '启动向量化失败'))
  }
}

const handleResetDocument = async (doc: Document) => {
  try {
    await resetDocument(doc)
  } catch (error) {
    toast.error('重置文档失败')
  }
}

const handleViewChunks = (doc: Document) => {
  router.push(`/knowledge-base/${doc.knowledgeBaseId}/chunks/${doc.id}`)
}

const handleReparsen = async (doc: Document) => {
  openModelDialog(doc)
}

const isKnowledgeBaseEnabled = (doc: Document) =>
  knowledgeBases.value.find((kb) => kb.id === doc.knowledgeBaseId)?.status === 0

const handleSyncAll = async () => {
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

const filteredDocuments = computed(() => {
  if (!searchQuery.value) return documents.value
  return documents.value.filter(
    (doc) =>
      doc.title.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
})

watch(selectedKbId, () => {
  currentPage.value = 1
  loadDocuments()
})

watch(selectedStatus, () => {
  currentPage.value = 1
  loadDocuments()
})

onMounted(() => {
  loadDocuments()
  loadKnowledgeBases()
})
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]"><div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" /><div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6"><div class="flex gap-4"><div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary"><Files class="h-5 w-5" /></div><div><p class="text-xs font-medium tracking-[0.16em] text-primary/90">DOCUMENT LIBRARY</p><h2 class="mt-1 text-2xl font-semibold tracking-tight">文档</h2><p class="mt-1 text-sm leading-6 text-muted-foreground">上传、解析并维护 AI 可以检索的资料。</p></div></div><div class="flex flex-wrap gap-2"><Button variant="outline" size="sm" @click="router.push('/document/recycle-bin')"><Archive class="mr-1.5 h-3.5 w-3.5" />回收站</Button><Button variant="outline" size="sm" :disabled="syncing" @click="handleSyncAll"><RefreshCcw :class="['mr-1.5 h-3.5 w-3.5', { 'animate-spin': syncing }]" />同步状态</Button><Button class="gap-2" :disabled="!hasEnabledKnowledgeBase" @click="isUploadDialogOpen = true"><Upload class="h-4 w-4" />添加文档</Button></div></div></section>

    <Card class="border-border bg-card/80"><CardContent class="grid gap-3 p-4 md:grid-cols-[13rem_11rem_minmax(0,1fr)]"><select v-model="selectedKbId" aria-label="按知识库筛选" class="h-10 rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50"><option :value="0">全部知识库</option><option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">{{ kb.name }}</option></select><select v-model="selectedStatus" aria-label="按解析状态筛选" class="h-10 rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50"><option :value="''">全部状态</option><option :value="0">待解析</option><option :value="1">解析中</option><option :value="2">已解析</option><option :value="3">解析失败</option></select><div class="relative"><Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input v-model="searchQuery" placeholder="搜索文档名称" class="pl-10" /></div></CardContent></Card>

    <section class="grid gap-3 sm:grid-cols-3"><div class="rounded-xl border border-border bg-card/70 p-4"><p class="text-sm text-muted-foreground">文档总数</p><p class="mt-2 text-2xl font-semibold">{{ total }}</p></div><div class="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] p-4"><p class="text-sm text-muted-foreground">正在处理</p><p class="mt-2 text-2xl font-semibold text-cyan-200">{{ processingDocumentCount }}</p></div><div class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-4"><p class="text-sm text-muted-foreground">已可检索</p><p class="mt-2 text-2xl font-semibold text-emerald-200">{{ parsedDocumentCount }}</p></div></section>

    <Card class="overflow-hidden border-border bg-card/80"><CardHeader class="flex-row items-center justify-between border-b border-border/70 p-5"><div><CardTitle class="text-base">文档列表</CardTitle><CardDescription class="mt-1">选择文档开始解析，完成后即可在对话中被检索。</CardDescription></div><span class="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">{{ filteredDocuments.length }} 条</span></CardHeader><CardContent class="p-4 sm:p-5"><LoadingSkeleton v-if="loading" type="card" :count="3" /><ErrorState v-else-if="loadError" message="加载文档失败，请检查网络连接后重试" @retry="loadDocuments" /><EmptyState v-else-if="filteredDocuments.length === 0" :icon="searchQuery ? FolderOpen : FileText" :title="searchQuery ? '没有找到匹配的文档' : '还没有文档'" :description="searchQuery ? '尝试更换搜索关键词' : '上传一份资料，AI 才能在对话中引用其中的信息。'" :steps="searchQuery || !hasEnabledKnowledgeBase ? undefined : [{ title: '上传文档', description: '支持 PDF、Word、Markdown，单次可多选' }, { title: '点击「开始解析」', description: '系统会分块并向量化，状态变为「已完成」即可被检索' }, { title: '到智能对话中提问', description: '回答会引用这份文档的原文片段' }]" :action="searchQuery ? undefined : '添加文档'" :show-action="!searchQuery && hasEnabledKnowledgeBase" @action="isUploadDialogOpen = true" /><div v-else class="space-y-3"><article v-for="doc in filteredDocuments" :key="doc.id" class="rounded-xl border border-border bg-muted/20 p-4 transition-colors hover:border-primary/25 hover:bg-muted/40"><div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between"><div class="flex min-w-0 gap-3.5"><div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"><FileText class="h-5 w-5" /></div><div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><h3 class="truncate font-medium">{{ doc.title }}</h3><Badge :variant="getStatusBadge(doc.status).variant">{{ getStatusBadge(doc.status).text }}</Badge></div><p class="mt-1 text-sm text-muted-foreground">{{ doc.knowledgeBaseName || '未归属知识库' }} · {{ formatFileSize(doc.fileSize) }} · {{ formatDateTime(doc.createdAt) }}</p><p v-if="doc.username" class="mt-1 text-xs text-muted-foreground">上传者：{{ doc.username }}</p><p v-if="doc.status === 3 && doc.errorMessage" class="mt-2 max-w-xl text-xs leading-5 text-destructive">解析失败：{{ doc.errorMessage }}</p><div v-if="processingDocs.has(doc.id)" class="mt-3 max-w-xl space-y-1.5"><div class="h-1.5 overflow-hidden rounded-full bg-muted"><div class="h-full rounded-full bg-primary transition-all" :style="{ width: `${processingProgress(doc.id)}%` }" /></div><p class="text-xs text-muted-foreground">{{ getStageText(processingStatus[doc.id]?.stage) }} · {{ processingProgress(doc.id) }}% · 已用 {{ formatProcessingTime(processingStatus[doc.id]?.elapsedSeconds) }} · 预计剩余 {{ formatProcessingTime(processingStatus[doc.id]?.remainingSeconds) }}</p></div></div></div><div class="flex flex-wrap items-center gap-2 xl:justify-end"><Button v-if="doc.status === 0" variant="outline" size="sm" :disabled="!isKnowledgeBaseEnabled(doc) || processingDocs.has(doc.id)" @click="handleStartVectorization(doc)"><Play class="mr-1.5 h-3.5 w-3.5" />开始解析</Button><Button v-if="doc.status === 1 || doc.status === 3" variant="outline" size="sm" :disabled="!isKnowledgeBaseEnabled(doc)" @click="handleResetDocument(doc)"><RefreshCw class="mr-1.5 h-3.5 w-3.5" />重新解析</Button><Button v-if="doc.status === 2" variant="outline" size="sm" @click="handleViewChunks(doc)"><Eye class="mr-1.5 h-3.5 w-3.5" />查看分块</Button><Button v-if="doc.status === 2" variant="outline" size="sm" :disabled="!isKnowledgeBaseEnabled(doc) || processingDocs.has(doc.id)" @click="handleReparsen(doc)"><Loader2 v-if="processingDocs.has(doc.id)" class="mr-1.5 h-3.5 w-3.5 animate-spin" /><RefreshCw v-else class="mr-1.5 h-3.5 w-3.5" />重新解析</Button><Button variant="ghost" size="icon" :disabled="doc.status === 4" title="移入回收站" @click="handleDelete(doc)"><Loader2 v-if="doc.status === 4" class="h-4 w-4 animate-spin" /><Trash2 v-else class="h-4 w-4 text-destructive" /></Button></div></div></article></div>
    <div v-if="totalPages > 1" class="mt-4 flex items-center justify-center gap-3 border-t border-border/70 pt-4">
      <Button variant="outline" size="sm" :disabled="loading || currentPage === 1" @click="handlePageChange(currentPage - 1)"><ChevronLeft class="mr-1 h-3.5 w-3.5" />上一页</Button>
      <span class="text-xs text-muted-foreground">第 {{ currentPage }} / {{ totalPages }} 页 · 共 {{ total }} 条</span>
      <Button variant="outline" size="sm" :disabled="loading || currentPage === totalPages" @click="handlePageChange(currentPage + 1)">下一页<ChevronRight class="ml-1 h-3.5 w-3.5" /></Button>
    </div></CardContent></Card>

    <Dialog v-model:open="isUploadDialogOpen">
      <DialogContent>
        <DialogHeader><DialogTitle>添加文档</DialogTitle><DialogDescription>先选择归属知识库；上传或抓取后再开始解析，资料才可用于对话检索。</DialogDescription></DialogHeader>
        <div class="flex gap-1 rounded-lg border border-border bg-muted/40 p-1">
          <button
            type="button"
            class="flex-1 rounded-md px-3 py-1.5 text-sm"
            :class="uploadMode === 'file' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'"
            @click="uploadMode = 'file'"
          >上传文件</button>
          <button
            type="button"
            class="flex-1 rounded-md px-3 py-1.5 text-sm"
            :class="uploadMode === 'url' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'"
            @click="uploadMode = 'url'"
          >网页地址</button>
        </div>
        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="kb-select">选择知识库 *</Label>
            <select
              id="kb-select"
              :value="uploadMode === 'file' ? uploadForm.kbId : urlForm.kbId"
              class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              @change="(e) => {
                const v = Number((e.target as HTMLSelectElement).value)
                if (uploadMode === 'file') uploadForm.kbId = v
                else urlForm.kbId = v
              }"
            >
              <option :value="0" disabled>请选择知识库</option>
              <option
                v-for="kb in knowledgeBases"
                :key="kb.id"
                :value="kb.id"
                :disabled="kb.status !== 0"
              >
                {{ kb.name }}{{ kb.status === 0 ? '' : '（已禁用）' }}
              </option>
            </select>
          </div>

          <template v-if="uploadMode === 'file'">
            <div class="space-y-2">
              <Label for="doc-title">文档标题 *</Label>
              <Input
                id="doc-title"
                v-model="uploadForm.title"
                placeholder="请输入便于识别的文档标题"
              />
            </div>
            <div class="space-y-2">
              <Label for="doc-file">选择文件 *</Label>
              <Input
                id="doc-file"
                type="file"
                accept=".txt,.pdf,.docx,.md,.csv,.xlsx,.pptx,.html,.htm,.png,.jpg,.jpeg"
                @change="handleFileSelect"
              />
              <p class="text-sm text-muted-foreground">
                支持 TXT、PDF、DOCX、MD、CSV、XLSX 格式，单个文件不超过 10 MB
              </p>
            </div>
            <div v-if="uploadForm.file" class="rounded-lg bg-muted p-3">
              <p class="text-sm">
                {{ uploadForm.file.name }} ({{ formatFileSize(uploadForm.file.size) }})
              </p>
            </div>
          </template>

          <template v-else>
            <div class="space-y-2">
              <Label for="url-title">文档标题（可选）</Label>
              <Input
                id="url-title"
                v-model="urlForm.title"
                placeholder="留空则自动使用网页标题"
              />
            </div>
            <div class="space-y-2">
              <Label for="doc-url">网页地址 *</Label>
              <Input
                id="doc-url"
                v-model="urlForm.url"
                placeholder="https://example.com/article"
              />
              <p class="text-sm text-muted-foreground">
                仅支持公开的 HTTPS 网页；抓取正文后作为文档待解析
              </p>
            </div>
          </template>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isUploadDialogOpen = false">取消</Button>
          <Button
            v-if="uploadMode === 'file'"
            :disabled="!uploadForm.file || !uploadForm.kbId || !uploadForm.title || uploading || knowledgeBases.find((kb) => kb.id === uploadForm.kbId)?.status !== 0"
            @click="handleUpload"
          >
            {{ uploading ? '上传中...' : '上传文档' }}
          </Button>
          <Button
            v-else
            :disabled="!urlForm.url.trim() || !urlForm.kbId || urlAdding || knowledgeBases.find((kb) => kb.id === urlForm.kbId)?.status !== 0"
            @click="handleAddFromUrl"
          >
            {{ urlAdding ? '抓取中...' : '抓取网页' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isModelDialogOpen">
      <DialogContent>
        <DialogHeader><DialogTitle>选择解析模型</DialogTitle><DialogDescription>模型会将文档转换为可检索的知识片段。</DialogDescription></DialogHeader>
        <div class="space-y-4">
          <div v-if="loadingModels" class="text-center py-4">
            <Loader2 class="h-6 w-6 animate-spin mx-auto" />
            <p class="text-sm text-muted-foreground mt-2">加载模型列表...</p>
          </div>
          <div v-else class="space-y-2">
            <div
              v-for="model in availableModels"
              :key="model.id"
              class="flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-colors"
              :class="{ 'border-primary bg-muted': selectedModel === model.id }"
              @click="selectedModel = model.id"
            >
              <div class="flex items-center gap-3">
                <input
                  type="radio"
                  :value="model.id"
                  v-model="selectedModel"
                  class="h-4 w-4"
                />
                <div>
                  <p class="font-medium">{{ model.name }}</p>
                  <p class="text-sm text-muted-foreground">{{ model.description }}</p>
                </div>
              </div>
              <Badge variant="outline">{{ model.dimension }}维</Badge>
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

    <ConfirmDialog
      v-model:open="confirmDeleteOpen"
      title="删除确认"
      :description="`确定要删除文档「${deleteTarget?.title}」吗？`"
      confirm-text="删除"
      destructive
      :loading="confirmDeleteLoading"
      @confirm="confirmDelete"
    />
  </div>
</template>
