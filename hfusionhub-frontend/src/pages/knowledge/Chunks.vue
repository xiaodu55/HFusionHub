<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as vectorizationApi from '@/api/vectorization'
import * as documentApi from '@/api/document'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ArrowLeft, FileText, Code, Table, List, Heading, AlignLeft } from 'lucide-vue-next'

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
const selectedBlockType = ref('all')
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
    const res = await documentApi.getDocument(documentId.value)
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
    let chunksData = res.data
    if (typeof chunksData === 'string') {
      chunksData = JSON.parse(chunksData)
    }
    if (chunksData && chunksData.success) {
      chunks.value = chunksData.chunks || []
      totalChunks.value = chunksData.total_chunks || 0
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

const handleBlockTypeChange = (e: Event) => {
  selectedBlockType.value = (e.target as HTMLSelectElement).value
  currentPage.value = 1
  loadChunks()
}

const getBlockTypeIcon = (type: string) => {
  switch (type) {
    case 'HEADING': return Heading
    case 'PARAGRAPH': return AlignLeft
    case 'CODE': return Code
    case 'TABLE': return Table
    case 'LIST': return List
    default: return FileText
  }
}

const getBlockTypeLabel = (type: string) => {
  switch (type) {
    case 'HEADING': return '标题'
    case 'PARAGRAPH': return '段落'
    case 'CODE': return '代码'
    case 'TABLE': return '表格'
    case 'LIST': return '列表'
    default: return type
  }
}

const getBlockTypeBadgeClass = (type: string) => {
  switch (type) {
    case 'CODE': return 'bg-red-100 text-red-700'
    case 'HEADING': return 'bg-blue-100 text-blue-700'
    case 'TABLE': return 'bg-purple-100 text-purple-700'
    default: return 'bg-gray-100 text-gray-700'
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
      <Button variant="ghost" size="sm" @click="goBack">
        <ArrowLeft class="mr-2 h-4 w-4" />
        返回
      </Button>
      <div class="flex-1">
        <h2 class="text-2xl font-bold">{{ documentName }} 分块详情</h2>
        <p class="text-muted-foreground">共 {{ totalChunks }} 个块</p>
      </div>
    </div>

    <!-- 筛选器 -->
    <Card>
      <CardContent class="pt-6">
        <div class="flex items-center gap-4">
          <span class="text-sm font-medium">筛选：</span>
          <select
            :value="selectedBlockType"
            @change="handleBlockTypeChange"
            class="rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option v-for="type in blockTypes" :key="type.value" :value="type.value">
              {{ type.label }}
            </option>
          </select>
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
                  块 #{{ (currentPage - 1) * pageSize + index + 1 }}
                </span>
                <span
                  :class="[
                    'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium',
                    getBlockTypeBadgeClass(chunk.block_type)
                  ]"
                >
                  <component :is="getBlockTypeIcon(chunk.block_type)" class="h-3 w-3" />
                  {{ getBlockTypeLabel(chunk.block_type) }}
                </span>
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
