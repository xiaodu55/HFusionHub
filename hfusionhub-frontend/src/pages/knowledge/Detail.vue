<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import * as documentApi from '@/api/document'
import * as vectorizationApi from '@/api/vectorization'
import { useToast } from '@/composables/useToast'
import type { KnowledgeBase, Document } from '@/api/types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ArrowLeft, Plus, FileText, Trash2, Upload, Play, Eye, Loader2, RefreshCw, RefreshCcw } from 'lucide-vue-next'

const route = useRoute()
const toast = useToast()
const router = useRouter()

const knowledgeBase = ref<KnowledgeBase | null>(null)
const documents = ref<Document[]>([])
const loading = ref(false)
const isUploadDialogOpen = ref(false)
const uploadFile = ref<File | null>(null)
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
  const id = Number(route.params.id)
  try {
    const res = await documentApi.getMyDocumentsByKbId(id, {
      pageNum: 1,
      pageSize: 100,
    })
    documents.value = res.data.records
  } catch (error) {
    console.error('加载文档失败:', error)
    toast.error('加载文档失败')
  } finally {
    loading.value = false
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
    toast.error('上传文档失败')
  } finally {
    uploading.value = false
  }
}

const handleDeleteDocument = async (doc: Document) => {
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
    // 更新文档状态为处理中
    doc.status = 1
    // 轮询检查处理状态
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

const syncing = ref(false)
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

const pollDocumentStatus = async (docId: number) => {
  const maxAttempts = 60 // 最多轮询60次，每次2秒
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
        // 完成或失败，停止轮询
        removeProcessing(docId)
        await loadDocuments() // 刷新列表
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
  router.push(`/knowledge-base/${route.params.id}/chunks/${doc.id}`)
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

const goBack = () => {
  router.push('/knowledge-base')
}

onMounted(() => {
  loadKnowledgeBase()
  loadDocuments()
})

onBeforeUnmount(() => {
  pollingTimers.forEach(timer => clearTimeout(timer))
  pollingTimers.clear()
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
      <Button @click="isUploadDialogOpen = true">
        <Upload class="mr-2 h-4 w-4" />
        上传文档
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
        <div v-if="loading" class="text-center text-muted-foreground py-8">
          加载中...
        </div>
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
                  {{ formatFileSize(doc.fileSize) }} · {{ new Date(doc.createdAt).toLocaleDateString() }}
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

              <!-- 重新解析按钮（处理中或失败时显示） -->
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
                @click="handleDeleteDocument(doc)"
              >
                <Trash2 class="h-4 w-4 text-destructive" />
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
              accept=".txt,.pdf,.doc,.docx,.md"
              @change="handleFileSelect"
            />
            <p class="text-sm text-muted-foreground">
              支持 TXT、PDF、DOC、DOCX、MD 格式
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
          <Button :disabled="!uploadFile || uploading" @click="handleUpload">
            {{ uploading ? '上传中...' : '上传' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
