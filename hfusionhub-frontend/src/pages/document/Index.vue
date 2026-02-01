<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import * as documentApi from '@/api/document'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
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
import { Select } from '@/components/ui/select'
import { Plus, Search, FileText, Trash2, Upload } from 'lucide-vue-next'

const documents = ref<Document[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const searchQuery = ref('')
const isUploadDialogOpen = ref(false)
const uploadForm = ref({
  kbId: 0,
  file: null as File | null,
  title: '',
})
const uploading = ref(false)

const loadDocuments = async () => {
  loading.value = true
  try {
    const res = await documentApi.getMyDocumentsByKbId(0, {
      pageNum: 1,
      pageSize: 100,
    })
    documents.value = res.data.records
  } catch (error) {
    console.error('加载文档失败:', error)
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
  }
}

const handleFileSelect = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (input.files && input.files[0]) {
    uploadForm.value.file = input.files[0]
  }
}

const handleUpload = async () => {
  if (!uploadForm.value.file || !uploadForm.value.kbId) return

  uploading.value = true
  try {
    await documentApi.uploadDocument(uploadForm.value.file, uploadForm.value.kbId, uploadForm.value.title)
    isUploadDialogOpen.value = false
    uploadForm.value = { kbId: 0, file: null, title: '' }
    await loadDocuments()
  } catch (error) {
    console.error('上传文档失败:', error)
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

onMounted(() => {
  loadDocuments()
  loadKnowledgeBases()
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
      <Button @click="isUploadDialogOpen = true">
        <Upload class="mr-2 h-4 w-4" />
        上传文档
      </Button>
    </div>

    <!-- 搜索栏 -->
    <div class="flex items-center gap-4">
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
      <Card
        v-for="doc in filteredDocuments"
        :key="doc.id"
        class="transition-shadow hover:shadow-md"
      >
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <FileText className="h-10 w-10 text-muted-foreground" />
              <div>
                <p className="font-medium">{{ doc.title }}</p>
                <p className="text-sm text-muted-foreground">
                  {{ doc.knowledgeBaseName }} · {{ formatFileSize(doc.fileSize) }} · {{ new Date(doc.createdAt).toLocaleDateString() }}
                </p>
                <p v-if="doc.username" className="text-sm text-muted-foreground">
                  上传者：{{ doc.username }}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge :variant="doc.status === 1 ? 'default' : 'secondary'">
                {{ doc.status === 1 ? '已解析' : '待解析' }}
              </Badge>
              <Button
                variant="ghost"
                size="icon"
                @click="handleDelete(doc)"
              >
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
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
