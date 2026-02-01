<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as documentApi from '@/api/document'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import * as vectorizationApi from '@/api/vectorization'
import { useToast } from '@/composables/useToast'
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
import { Plus, Search, FileText, Trash2, Upload, Play, Eye, Loader2, RefreshCw, RefreshCcw } from 'lucide-vue-next'
import { formatDateTime } from '@/utils/date'

const router = useRouter()
const toast = useToast()

const documents = ref<Document[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const searchQuery = ref('')
const selectedKbId = ref<number>(0) // 0 = 全部
const isUploadDialogOpen = ref(false)
const uploadForm = ref({
  kbId: 0,
  file: null as File | null,
  title: '',
})
const uploading = ref(false)
const processingDocs = ref<Set<number>>(new Set())
const pollingTimers = new Set<ReturnType<typeof setTimeout>>()
const addProcessing = (id: number) => {
  const s = new Set(processingDocs.value)
  s.add(id)
  processingDocs.value = s
}
const removeProcessing = (id: number) => {
  const s = new Set(processingDocs.value)
  s.delete(id)
  processingDocs.value = s
}
const syncing = ref(false)

const loadDocuments = async () => {
  loading.value = true
  try {
    let res
    if (selectedKbId.value > 0) {
      res = await documentApi.getMyDocumentsByKbId(selectedKbId.value, {
        pageNum: 1,
        pageSize: 100,
      })
    } else {
      res = await documentApi.getMyDocumentsByKbId(0, {
        pageNum: 1,
        pageSize: 100,
      })
    }
    documents.value = res.data.records
  } catch (error) {
    console.error('加载文档失败:', error)
    toast.error('加载文档失败')
  } finally {
    loading.value = false
  }
}

const loadKnowledgeBases = async () => {
  try {
    const res = await knowledgeBaseApi.getMyKnowledgeBaseList({
      pageNum: 1,
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
    toast.error('上传文档失败')
  } finally {
    uploading.value = false
  }
}

const handleDelete = async (doc: Document) => {
  if (!confirm(`确定要删除文档「${doc.title}」吗？`)) return

  try {
    await documentApi.deleteDocument(doc.id)
    await loadDocuments()
  } catch (error) {
    console.error('删除文档失败:', error)
    toast.error('删除文档失败')
  }
}

const handleStartVectorization = async (doc: Document) => {
  addProcessing(doc.id)
  try {
    await vectorizationApi.startVectorization(doc.id)
    doc.status = 1
    pollDocumentStatus(doc.id)
  } catch (error) {
    console.error('启动向量化失败:', error)
    toast.error('启动向量化失败')
    removeProcessing(doc.id)
  }
}

const handleResetDocument = async (doc: Document) => {
  try {
    await vectorizationApi.resetDocument(doc.id)
    doc.status = 0
    doc.errorMessage = null
  } catch (error) {
    console.error('重置文档失败:', error)
    toast.error('重置文档失败')
  }
}

const pollDocumentStatus = async (docId: number) => {
  const maxAttempts = 60
  let attempts = 0

  const checkStatus = async () => {
    if (attempts >= maxAttempts) {
      removeProcessing(docId)
      return
    }

    try {
      const res = await vectorizationApi.getVectorizationStatus(docId)
      const status = res.data?.status

      if (status === 2 || status === 3) {
        removeProcessing(docId)
        await loadDocuments()
        return
      }

      attempts++
      const timer = setTimeout(checkStatus, 2000)
      pollingTimers.add(timer)
    } catch (error) {
      console.error('查询状态失败:', error)
      toast.error('查询状态失败')
      removeProcessing(docId)
    }
  }

  checkStatus()
}

const handleViewChunks = (doc: Document) => {
  router.push(`/knowledge-base/${doc.knowledgeBaseId}/chunks/${doc.id}`)
}

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

const getStatusBadge = (status: number) => {
  switch (status) {
    case 0:
      return { text: '待解析', variant: 'outline' as const }
    case 1:
      return { text: '解析中...', variant: 'secondary' as const }
    case 2:
      return { text: '已完成', variant: 'default' as const }
    case 3:
      return { text: '解析失败', variant: 'destructive' as const }
    default:
      return { text: '未知', variant: 'outline' as const }
  }
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const filteredDocuments = computed(() => {
  if (!searchQuery.value) return documents.value
  return documents.value.filter(
    (doc) =>
      doc.title.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
})

watch(selectedKbId, () => {
  loadDocuments()
})

onMounted(() => {
  loadDocuments()
  loadKnowledgeBases()
})

onBeforeUnmount(() => {
  pollingTimers.forEach(timer => clearTimeout(timer))
  pollingTimers.clear()
})
</script>

<template>
  <div class="space-y-6">
    <!-- 页面头部 -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold">文档管理</h2>
        <p class="text-muted-foreground">上传和管理文档</p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" @click="handleSyncAll" :disabled="syncing">
          <RefreshCcw :class="['mr-2 h-4 w-4', { 'animate-spin': syncing }]" />
          同步状态
        </Button>
        <Button @click="isUploadDialogOpen = true">
          <Upload class="mr-2 h-4 w-4" />
          上传文档
        </Button>
      </div>
    </div>

    <!-- 筛选和搜索 -->
    <div class="flex items-center gap-4">
      <select
        v-model="selectedKbId"
        class="flex h-10 w-[200px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <option :value="0">全部知识库</option>
        <option
          v-for="kb in knowledgeBases"
          :key="kb.id"
          :value="kb.id"
        >
          {{ kb.name }}
        </option>
      </select>
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="searchQuery"
          placeholder="搜索文档..."
          class="pl-10"
        />
      </div>
    </div>

    <!-- 文档列表 -->
    <div v-if="loading" class="text-center text-muted-foreground py-8">
      加载中...
    </div>
    <div v-else-if="filteredDocuments.length === 0" class="text-center py-8">
      <FileText class="mx-auto h-12 w-12 text-muted-foreground" />
      <p class="mt-4 text-muted-foreground">
        {{ searchQuery ? '没有找到匹配的文档' : '暂无文档，点击上方按钮上传' }}
      </p>
    </div>
    <div v-else class="space-y-4">
      <div
        v-for="doc in filteredDocuments"
        :key="doc.id"
        class="flex items-center justify-between rounded-lg border p-4"
      >
        <div class="flex items-center gap-4">
          <FileText class="h-8 w-8 text-muted-foreground" />
          <div>
            <p class="font-medium">{{ doc.title }}</p>
            <p class="text-sm text-muted-foreground">
              {{ doc.knowledgeBaseName }} · {{ formatFileSize(doc.fileSize) }} · {{ formatDateTime(doc.createdAt) }}
            </p>
            <p v-if="doc.username" class="text-sm text-muted-foreground">
              上传者：{{ doc.username }}
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <Badge :variant="getStatusBadge(doc.status).variant">
            {{ getStatusBadge(doc.status).text }}
          </Badge>

          <!-- 开始解析按钮 -->
          <Button
            v-if="doc.status === 0"
            variant="outline"
            size="sm"
            :disabled="processingDocs.has(doc.id)"
            @click="handleStartVectorization(doc)"
          >
            <Loader2 v-if="processingDocs.has(doc.id)" class="mr-2 h-4 w-4 animate-spin" />
            <Play v-else class="mr-2 h-4 w-4" />
            {{ processingDocs.has(doc.id) ? '处理中...' : '开始解析' }}
          </Button>

          <!-- 重新解析按钮 -->
          <Button
            v-if="doc.status === 1 || doc.status === 3"
            variant="outline"
            size="sm"
            @click="handleResetDocument(doc)"
          >
            <RefreshCw class="mr-2 h-4 w-4" />
            重新解析
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
            variant="ghost"
            size="icon"
            @click="handleDelete(doc)"
          >
            <Trash2 class="h-4 w-4 text-destructive" />
          </Button>
        </div>
      </div>
    </div>

    <!-- 上传文档对话框 -->
    <Dialog v-model:open="isUploadDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>上传文档</DialogTitle>
          <DialogDescription>上传文档到指定知识库</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="kb-select">选择知识库 *</Label>
            <select
              id="kb-select"
              v-model="uploadForm.kbId"
              class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option :value="0" disabled>请选择知识库</option>
              <option
                v-for="kb in knowledgeBases"
                :key="kb.id"
                :value="kb.id"
              >
                {{ kb.name }}
              </option>
            </select>
          </div>
          <div class="space-y-2">
            <Label for="doc-title">文档标题 *</Label>
            <Input
              id="doc-title"
              v-model="uploadForm.title"
              placeholder="请输入文档标题"
            />
          </div>
          <div class="space-y-2">
            <Label>选择文件 *</Label>
            <Input
              type="file"
              accept=".txt,.pdf,.doc,.docx,.md"
              @change="handleFileSelect"
            />
            <p class="text-sm text-muted-foreground">
              支持 TXT、PDF、DOC、DOCX、MD 格式
            </p>
          </div>
          <div v-if="uploadForm.file" class="rounded-lg bg-muted p-3">
            <p class="text-sm">
              {{ uploadForm.file.name }} ({{ formatFileSize(uploadForm.file.size) }})
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isUploadDialogOpen = false">
            取消
          </Button>
          <Button
            :disabled="!uploadForm.file || !uploadForm.kbId || !uploadForm.title || uploading"
            @click="handleUpload"
          >
            {{ uploading ? '上传中...' : '上传' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
