<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as documentApi from '@/api/document'
import type { Document } from '@/api/types'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/date'
import { formatFileSize } from '@/utils/format'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { ArrowLeft, Archive, Loader2, RotateCcw, Search, Trash2 } from 'lucide-vue-next'

const PAGE_SIZE = 20
const router = useRouter()
const toast = useToast()
const documents = ref<Document[]>([])
const total = ref(0)
const page = ref(1)
const searchTitle = ref('')
const loading = ref(false)
const actionId = ref<number | null>(null)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

const loadDocuments = async (targetPage = page.value) => {
  loading.value = true
  try {
    const response = await documentApi.getRecycleBin({
      page: targetPage,
      pageSize: PAGE_SIZE,
      title: searchTitle.value.trim() || undefined,
    })
    documents.value = response.data.records
    total.value = response.data.total
    page.value = Math.min(Math.max(1, targetPage), totalPages.value)
  } catch (error) {
    console.error('加载回收站失败:', error)
    toast.error('加载回收站失败')
  } finally {
    loading.value = false
  }
}

const restore = async (document: Document) => {
  actionId.value = document.id
  try {
    await documentApi.restoreDocument(document.id)
    toast.success('文档已恢复到待解析状态')
    await loadDocuments()
  } catch (error) {
    console.error('恢复文档失败:', error)
    toast.error('恢复文档失败')
  } finally {
    actionId.value = null
  }
}

const purge = async (document: Document) => {
  if (!confirm(`确定彻底删除《${document.title}》吗？此操作不可恢复。`)) return
  actionId.value = document.id
  try {
    await documentApi.purgeDocument(document.id)
    toast.success('已提交彻底删除任务')
    await loadDocuments()
  } catch (error) {
    console.error('彻底删除文档失败:', error)
    toast.error('彻底删除文档失败')
  } finally {
    actionId.value = null
  }
}

const applySearch = () => {
  loadDocuments(1)
}

const goToPage = (targetPage: number) => {
  if (loading.value || targetPage < 1 || targetPage > totalPages.value) return
  loadDocuments(targetPage)
}

onMounted(() => {
  loadDocuments(1)
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <Button variant="ghost" size="icon" @click="router.push('/document')">
          <ArrowLeft class="h-5 w-5" />
        </Button>
        <div>
          <h2 class="text-2xl font-bold">文档回收站</h2>
          <p class="text-muted-foreground">文档保留 7 天，恢复后需要重新分块</p>
        </div>
      </div>
      <Archive class="h-8 w-8 text-muted-foreground" />
    </div>

    <div class="flex items-center gap-3">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="searchTitle"
          class="pl-10"
          placeholder="搜索回收站文档..."
          @keyup.enter="applySearch"
        />
      </div>
      <Button variant="outline" @click="applySearch">搜索</Button>
    </div>

    <div v-if="loading" class="py-10 text-center text-muted-foreground">
      <Loader2 class="mx-auto h-6 w-6 animate-spin" />
      <p class="mt-2">加载中...</p>
    </div>
    <div v-else-if="documents.length === 0" class="py-10 text-center text-muted-foreground">
      <Archive class="mx-auto h-12 w-12" />
      <p class="mt-3">回收站为空</p>
    </div>
    <div v-else class="space-y-3">
      <div
        v-for="document in documents"
        :key="document.id"
        class="flex items-center justify-between gap-4 rounded-lg border p-4"
      >
        <div class="min-w-0">
          <p class="truncate font-medium">{{ document.title }}</p>
          <p class="text-sm text-muted-foreground">
            {{ document.knowledgeBaseName || '知识库已删除' }}
            · {{ formatFileSize(document.fileSize) }}
            · 删除于 {{ formatDateTime(document.recycledAt || document.updatedAt) }}
          </p>
          <p class="text-sm text-muted-foreground">
            保留至 {{ document.recycleExpiresAt ? formatDateTime(document.recycleExpiresAt) : '系统清理时' }}
          </p>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <Badge variant="secondary">回收站</Badge>
          <Button
            variant="outline"
            size="sm"
            :disabled="actionId === document.id"
            @click="restore(document)"
          >
            <Loader2 v-if="actionId === document.id" class="mr-2 h-4 w-4 animate-spin" />
            <RotateCcw v-else class="mr-2 h-4 w-4" />
            恢复
          </Button>
          <Button
            variant="destructive"
            size="sm"
            :disabled="actionId === document.id"
            @click="purge(document)"
          >
            <Trash2 class="mr-2 h-4 w-4" />
            彻底删除
          </Button>
        </div>
      </div>

      <div class="flex items-center justify-between border-t pt-4">
        <Button
          variant="outline"
          size="sm"
          :disabled="loading || page <= 1"
          @click="goToPage(page - 1)"
        >
          上一页
        </Button>
        <span class="text-sm text-muted-foreground">
          第 {{ page }} / {{ totalPages }} 页，共 {{ total }} 条
        </span>
        <Button
          variant="outline"
          size="sm"
          :disabled="loading || page >= totalPages"
          @click="goToPage(page + 1)"
        >
          下一页
        </Button>
      </div>
    </div>
  </div>
</template>
