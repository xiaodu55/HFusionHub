<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as vectorizationApi from '@/api/vectorization'
import * as documentApi from '@/api/document'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ArrowLeft, FileText, Code, Table, List, Heading, Paragraph } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

interface Chunk {
  chunk_id: string
  content: string
  block_type: string
  outline_path: string[]
  metadata: Record<string, any>
}

const documentId = ref<number>(Number(route.params.docId))
const documentName = ref('')
const chunks = ref<Chunk[]>([])
const totalChunks = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const selectedBlockType = ref<string>('all')
const loading = ref(false)

const blockTypes = [
  { value: 'all', label: '全部' },
  { value: 'HEADING', label: '标题' },
  { value: 'PARAGRAPH', label: '段落' },
  { value: 'CODE', label: '代码' },
  { value: 'TABLE', label: '表格' },
  { value: 'LIST', label: '列表' },
]

const loadDocumentInfo = async () => {
  try {
    const res = await documentApi.getDocumentById(documentId.value)
    documentName.value = res.data.title
  } catch (error) {
    console.error('加载文档信息失败:', error)
  }
}

const loadChunks = async () => {
  loading.value = true
  try {
    const params: any = {
      page: currentPage.value,
      size: pageSize.value,
    }
    if (selectedBlockType.value !== 'all') {
      params.blockType = selectedBlockType.value
    }

    const res = await vectorizationApi.getDocumentChunks(documentId.value, params)
    const data = res.data
    if (data && data.data) {
      chunks.value = data.data.records || []
      totalChunks.value = data.data.total || 0
    }
  } catch (error) {
    console.error('加载分块失败:', error)
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadChunks()
}

const handleBlockTypeChange = (value: string) => {
  selectedBlockType.value = value
  currentPage.value = 1
  loadChunks()
}

const getBlockTypeIcon = (type: string) => {
  switch (type) {
    case 'HEADING':
      return Heading
    case 'PARAGRAPH':
      return Paragraph
    case 'CODE':
      return Code
    case 'TABLE':
      return Table
    case 'LIST':
      return List
    default:
      return FileText
  }
}

const getBlockTypeBadge = (type: string) => {
  switch (type) {
    case 'HEADING':
      return { text: '标题', variant: 'default' as const }
    case 'PARAGRAPH':
      return { text: '段落', variant: 'secondary' as const }
    case 'CODE':
      return { text: '代码', variant: 'destructive' as const }
    case 'TABLE':
      return { text: '表格', variant: 'outline' as const }
    case 'LIST':
      return { text: '列表', variant: 'outline' as const }
    default:
      return { text: type, variant: 'outline' as const }
  }
}

const formatOutlinePath = (path: string[]) => {
  if (!path || path.length === 0) return '无章节信息'
  return path.join(' > ')
}

const goBack = () => {
  router.back()
}

onMounted(() => {
  loadDocumentInfo()
  loadChunks()
})
</script>

<template>
  <div class="space-y-6">
    <!-- 返回按钮和标题 -->
    <div class="flex items-center gap-4">
      <Button variant="ghost" size="icon" @click="goBack">
        <ArrowLeft class="h-5 w-5" />
      </Button>
      <div class="flex-1">
        <h2 class="text-2xl font-bold">{{ documentName }} 分块详情</h2>
        <p class="text-muted-foreground">
          共 {{ totalChunks }} 个块
        </p>
      </div>
    </div>

    <!-- 筛选器 -->
    <Card>
      <CardContent className="pt-6">
        <div class="flex items-center gap-4">
          <span class="text-sm font-medium">筛选：</span>
          <Select :value="selectedBlockType" @update:model-value="handleBlockTypeChange">
            <SelectTrigger class="w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="type in blockTypes" :key="type.value" :value="type.value">
                {{ type.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>

    <!-- 分块列表 -->
    <Card>
      <CardHeader>
        <CardTitle>分块列表</CardTitle>
        <CardDescription>查看文档的分块内容和类型</CardDescription>
      </CardHeader>
      <CardContent>
        <div v-if="loading" class="text-center text-muted-foreground py-8">
          加载中...
        </div>
        <div v-else-if="chunks.length === 0" class="text-center py-8">
          <FileText class="mx-auto h-12 w-12 text-muted-foreground" />
          <p class="mt-4 text-muted-foreground">暂无分块数据</p>
        </div>
        <div v-else class="space-y-4">
          <div
            v-for="(chunk, index) in chunks"
            :key="chunk.chunk_id"
            class="rounded-lg border p-4"
          >
            <!-- 分块头部 -->
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-3">
                <span class="text-sm text-muted-foreground">
                  块 #{{ (currentPage - 1) * pageSize + index }}
                </span>
                <Badge :variant="getBlockTypeBadge(chunk.block_type).variant">
                  <component :is="getBlockTypeIcon(chunk.block_type)" class="mr-1 h-3 w-3" />
                  {{ getBlockTypeBadge(chunk.block_type).text }}
                </Badge>
              </div>
              <span class="text-xs text-muted-foreground">
                {{ formatOutlinePath(chunk.outline_path) }}
              </span>
            </div>

            <!-- 分块内容 -->
            <div class="rounded bg-muted p-3 font-mono text-sm whitespace-pre-wrap">
              {{ chunk.content }}
            </div>

            <!-- 元数据 -->
            <div class="mt-2 text-xs text-muted-foreground">
              字符数：{{ chunk.metadata?.char_count || chunk.content.length }}
              <template v-if="chunk.metadata?.language">
                · 语言：{{ chunk.metadata.language }}
              </template>
            </div>
          </div>
        </div>

        <!-- 分页 -->
        <div v-if="totalChunks > pageSize" class="flex justify-center mt-6 gap-2">
          <Button
            variant="outline"
            :disabled="currentPage <= 1"
            @click="handlePageChange(currentPage - 1)"
          >
            上一页
          </Button>
          <span class="flex items-center px-4 text-sm text-muted-foreground">
            {{ currentPage }} / {{ Math.ceil(totalChunks / pageSize) }}
          </span>
          <Button
            variant="outline"
            :disabled="currentPage >= Math.ceil(totalChunks / pageSize)"
            @click="handlePageChange(currentPage + 1)"
          >
            下一页
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
