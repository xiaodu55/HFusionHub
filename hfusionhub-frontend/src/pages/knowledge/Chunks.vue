<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as vectorizationApi from '@/api/vectorization'
import * as documentApi from '@/api/document'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ArrowLeft, FileText, Code, Table, List, Heading, AlignLeft, ChevronDown, ChevronUp, Copy, Check } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'

const route = useRoute()
const router = useRouter()
const toast = useToast()

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
const loadError = ref(false)
const expandedChunks = ref<Set<string>>(new Set())
const copiedChunkId = ref<string | null>(null)

const blockTypes = [
  { value: 'all', label: '全部类型' },
  { value: 'HEADING', label: '标题' },
  { value: 'PARAGRAPH', label: '段落' },
  { value: 'CODE', label: '代码' },
  { value: 'TABLE', label: '表格' },
  { value: 'LIST', label: '列表' },
]

// 长内容折叠阈值（字符）
const COLLAPSE_THRESHOLD = 400

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
  loadError.value = false
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
      chunksData = JSON.parse(chunksData) as vectorizationApi.ChunkPage
    }
    if (chunksData && chunksData.chunks) {
      chunks.value = chunksData.chunks || []
      totalChunks.value = chunksData.totalChunks || 0
    }
  } catch (error) {
    console.error('加载分块失败:', error)
    loadError.value = true
    toast.error('加载分块数据失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  expandedChunks.value.clear()
  loadChunks()
}

const handleBlockTypeChange = (value: string) => {
  selectedBlockType.value = value
  currentPage.value = 1
  expandedChunks.value.clear()
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

/** 类型徽标配色（含 dark 变体）+ 内容区左侧色条 */
const getBlockTypeTheme = (type: string): { badge: string; bar: string } => {
  switch (type) {
    case 'HEADING':
      return { badge: 'bg-blue-50 text-blue-700 dark:bg-blue-400/15 dark:text-blue-300', bar: 'bg-blue-400 dark:bg-blue-500' }
    case 'CODE':
      return { badge: 'bg-red-50 text-red-700 dark:bg-red-400/15 dark:text-red-300', bar: 'bg-red-400 dark:bg-red-500' }
    case 'TABLE':
      return { badge: 'bg-purple-50 text-purple-700 dark:bg-purple-400/15 dark:text-purple-300', bar: 'bg-purple-400 dark:bg-purple-500' }
    case 'LIST':
      return { badge: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300', bar: 'bg-emerald-400 dark:bg-emerald-500' }
    case 'PARAGRAPH':
      return { badge: 'bg-slate-100 text-slate-700 dark:bg-slate-400/15 dark:text-slate-300', bar: 'bg-slate-300 dark:bg-slate-500' }
    default:
      return { badge: 'bg-gray-100 text-gray-700 dark:bg-gray-400/15 dark:text-gray-300', bar: 'bg-gray-300 dark:bg-gray-500' }
  }
}

const formatOutlinePath = (path: string[]) => {
  if (!path || path.length === 0) return ''
  return path.join(' › ')
}

const isLongContent = (chunk: Chunk) => chunk.content.length > COLLAPSE_THRESHOLD

const isExpanded = (chunk: Chunk) => expandedChunks.value.has(chunk.chunk_id)

const toggleExpand = (chunk: Chunk) => {
  if (isExpanded(chunk)) {
    expandedChunks.value.delete(chunk.chunk_id)
  } else {
    expandedChunks.value.add(chunk.chunk_id)
  }
  // Set 响应式触发
  expandedChunks.value = new Set(expandedChunks.value)
}

const displayContent = (chunk: Chunk) => {
  if (isLongContent(chunk) && !isExpanded(chunk)) {
    return chunk.content.slice(0, COLLAPSE_THRESHOLD) + '…'
  }
  return chunk.content
}

const copyChunk = async (chunk: Chunk) => {
  try {
    await navigator.clipboard.writeText(chunk.content)
    copiedChunkId.value = chunk.chunk_id
    toast.success('已复制到剪贴板')
    setTimeout(() => { copiedChunkId.value = null }, 1500)
  } catch {
    toast.error('复制失败')
  }
}

const pageLabel = computed(() => {
  if (totalChunks.value === 0) return ''
  const start = (currentPage.value - 1) * pageSize.value + 1
  const end = Math.min(currentPage.value * pageSize.value, totalChunks.value)
  return `${start}–${end} / ${totalChunks.value}`
})

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
        <p class="text-sm text-muted-foreground">共 <span class="tabular-nums font-medium text-foreground">{{ totalChunks }}</span> 个块 · 已向量化用于语义检索</p>
      </div>
    </div>

    <!-- 分块列表 -->
    <Card>
      <CardHeader>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>分块列表</CardTitle>
            <p class="text-sm text-muted-foreground mt-1">查看文档解析后的分块内容与类型</p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <!-- 类型快捷筛选 chips -->
            <button
              v-for="type in blockTypes"
              :key="type.value"
              type="button"
              :class="[
                'inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors',
                selectedBlockType === type.value
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-input bg-background text-muted-foreground hover:bg-muted hover:text-foreground'
              ]"
              @click="handleBlockTypeChange(type.value)"
            >
              <component :is="getBlockTypeIcon(type.value)" class="h-3.5 w-3.5" />
              {{ type.label }}
            </button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <LoadingSkeleton v-if="loading" type="card" :count="3" />
        <ErrorState v-else-if="loadError" message="加载分块数据失败" @retry="loadChunks" />
        <EmptyState
          v-else-if="chunks.length === 0"
          :icon="FileText"
          title="暂无分块数据"
          description="文档解析完成后，系统会将内容分割成多个可检索的小块。"
        />
        <div v-else class="space-y-3">
          <article
            v-for="(chunk, index) in chunks"
            :key="chunk.chunk_id"
            class="group relative overflow-hidden rounded-lg border bg-card transition-shadow hover:shadow-sm"
          >
            <!-- 类型色条 -->
            <div class="absolute inset-y-0 left-0 w-1" :class="getBlockTypeTheme(chunk.block_type).bar" />

            <div class="pl-5 pr-4 py-4">
              <!-- 分块头部 -->
              <div class="mb-2.5 flex items-start justify-between gap-3">
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  <span class="shrink-0 text-xs font-medium tabular-nums text-muted-foreground">
                    #{{ (currentPage - 1) * pageSize + index + 1 }}
                  </span>
                  <span
                    :class="[
                      'inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
                      getBlockTypeTheme(chunk.block_type).badge
                    ]"
                  >
                    <component :is="getBlockTypeIcon(chunk.block_type)" class="h-3 w-3" />
                    {{ getBlockTypeLabel(chunk.block_type) }}
                  </span>
                  <span v-if="formatOutlinePath(chunk.outline_path)" class="min-w-0 truncate text-xs text-muted-foreground" :title="formatOutlinePath(chunk.outline_path)">
                    {{ formatOutlinePath(chunk.outline_path) }}
                  </span>
                </div>
                <div class="flex shrink-0 items-center gap-1">
                  <span class="text-xs tabular-nums text-muted-foreground">{{ chunk.metadata?.char_count || chunk.content.length }} 字</span>
                  <button
                    type="button"
                    class="ml-1 rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground focus:opacity-100 group-hover:opacity-100"
                    :aria-label="`复制分块 #${(currentPage - 1) * pageSize + index + 1}`"
                    @click="copyChunk(chunk)"
                  >
                    <Check v-if="copiedChunkId === chunk.chunk_id" class="h-3.5 w-3.5 text-emerald-500" />
                    <Copy v-else class="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <!-- 分块内容：按类型差异化排版 -->
              <div
                v-if="chunk.block_type === 'CODE'"
                class="overflow-x-auto rounded-md bg-zinc-900 p-3.5 font-mono text-[13px] leading-relaxed text-zinc-100 whitespace-pre-wrap dark:bg-zinc-950"
              >{{ displayContent(chunk) }}</div>
              <div
                v-else-if="chunk.block_type === 'TABLE'"
                class="overflow-x-auto rounded-md bg-muted/60 p-3.5 font-mono text-[13px] leading-relaxed whitespace-pre-wrap"
              >{{ displayContent(chunk) }}</div>
              <p
                v-else
                :class="[
                  'whitespace-pre-wrap text-sm leading-relaxed text-foreground/90',
                  chunk.block_type === 'HEADING' && 'font-semibold text-foreground'
                ]"
              >{{ displayContent(chunk) }}</p>

              <!-- 展开收起 -->
              <div v-if="isLongContent(chunk)" class="mt-2">
                <button
                  type="button"
                  class="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                  @click="toggleExpand(chunk)"
                >
                  <component :is="isExpanded(chunk) ? ChevronUp : ChevronDown" class="h-3.5 w-3.5" />
                  {{ isExpanded(chunk) ? '收起' : `展开全文（共 ${chunk.content.length} 字）` }}
                </button>
              </div>
            </div>
          </article>
        </div>

        <!-- 分页 -->
        <div
          v-if="totalChunks > pageSize"
          class="mt-6 flex flex-wrap items-center justify-center gap-3"
        >
          <p class="mr-2 text-xs tabular-nums text-muted-foreground">{{ pageLabel }}</p>
          <Button
            variant="outline"
            size="sm"
            :disabled="currentPage <= 1"
            @click="handlePageChange(currentPage - 1)"
          >
            上一页
          </Button>
          <span class="text-sm tabular-nums text-muted-foreground">
            {{ currentPage }} / {{ Math.ceil(totalChunks / pageSize) }}
          </span>
          <Button
            variant="outline"
            size="sm"
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
