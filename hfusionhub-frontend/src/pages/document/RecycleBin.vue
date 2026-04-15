<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as documentApi from '@/api/document'
import type { Document } from '@/api/types'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/date'
import { formatFileSize } from '@/utils/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  AlertTriangle,
  Archive,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  Loader2,
  RotateCcw,
  Search,
  Trash2,
} from 'lucide-vue-next'

const PAGE_SIZE = 20
const router = useRouter()
const toast = useToast()
const documents = ref<Document[]>([])
const total = ref(0)
const page = ref(1)
const searchTitle = ref('')
const loading = ref(false)
const loadError = ref(false)
const actionId = ref<number | null>(null)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const isSearching = computed(() => Boolean(searchTitle.value.trim()))

const loadDocuments = async (targetPage = page.value) => {
  loading.value = true
  loadError.value = false
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
    loadError.value = true
    toast.error('加载回收站失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const restore = async (document: Document) => {
  actionId.value = document.id
  try {
    await documentApi.restoreDocument(document.id)
    toast.success('文档已恢复到文档列表，请重新解析后用于对话')
    await loadDocuments()
  } catch (error) {
    console.error('恢复文档失败:', error)
    toast.error('恢复文档失败，请稍后重试')
  } finally {
    actionId.value = null
  }
}

const purge = async (document: Document) => {
  if (!confirm(`确定要永久删除「${document.title}」吗？此操作无法恢复。`)) return

  actionId.value = document.id
  try {
    await documentApi.purgeDocument(document.id)
    toast.success('已提交永久删除，系统正在清理文档和索引')
    await loadDocuments()
  } catch (error) {
    console.error('永久删除文档失败:', error)
    toast.error('永久删除失败，请稍后重试')
  } finally {
    actionId.value = null
  }
}

const applySearch = () => loadDocuments(1)

const clearSearch = () => {
  searchTitle.value = ''
  loadDocuments(1)
}

const goToPage = (targetPage: number) => {
  if (loading.value || targetPage < 1 || targetPage > totalPages.value) return
  loadDocuments(targetPage)
}

const getExpiryLabel = (document: Document) =>
  document.recycleExpiresAt ? formatDateTime(document.recycleExpiresAt) : '等待系统自动清理'

onMounted(() => loadDocuments(1))
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-amber-400/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex items-start gap-4">
          <Button variant="ghost" size="icon" class="mt-0.5 shrink-0" title="返回文档列表" @click="router.push('/document')">
            <ArrowLeft class="h-5 w-5" />
          </Button>
          <div class="flex gap-4">
            <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-amber-400/25 bg-amber-400/10 text-amber-300">
              <Archive class="h-5 w-5" />
            </div>
            <div>
              <p class="text-xs font-medium tracking-[0.16em] text-amber-300/90">DOCUMENT RECOVERY</p>
              <h2 class="mt-1 text-2xl font-semibold tracking-tight">文档回收站</h2>
              <p class="mt-1 text-sm leading-6 text-muted-foreground">已删除的文档将在这里保留 7 天，可恢复或永久删除。</p>
            </div>
          </div>
        </div>
        <div class="shrink-0 rounded-full border border-amber-400/20 bg-amber-400/[0.06] px-3 py-1.5 text-sm text-amber-200">
          {{ total }} 个待处理文档
        </div>
      </div>
    </section>

    <div class="flex items-start gap-3 rounded-xl border border-amber-400/15 bg-amber-400/[0.04] p-4 text-sm leading-6 text-muted-foreground">
      <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
      <p>恢复后的文档会回到“待解析”状态，需要重新解析后才能继续被 AI 检索；永久删除无法撤销。</p>
    </div>

    <Card class="border-border bg-card/80">
      <CardContent class="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:p-5">
        <div class="relative flex-1">
          <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input v-model="searchTitle" class="pl-10" placeholder="搜索回收站中的文档名称" @keyup.enter="applySearch" />
        </div>
        <div class="flex gap-2">
          <Button v-if="isSearching" variant="ghost" @click="clearSearch">清除</Button>
          <Button variant="outline" @click="applySearch">搜索</Button>
        </div>
      </CardContent>
    </Card>

    <Card class="overflow-hidden border-border bg-card/80">
      <CardContent class="p-4 sm:p-5">
        <div v-if="loading" class="flex min-h-64 flex-col items-center justify-center text-center text-muted-foreground">
          <Loader2 class="h-7 w-7 animate-spin text-primary" />
          <p class="mt-3 text-sm">正在加载回收站…</p>
        </div>
        <div v-else-if="loadError" class="flex min-h-64 flex-col items-center justify-center text-center">
          <AlertTriangle class="h-10 w-10 text-amber-300" />
          <p class="mt-4 font-medium">回收站暂时无法加载</p>
          <p class="mt-1 text-sm text-muted-foreground">请检查网络连接后重试。</p>
          <Button class="mt-4" variant="outline" @click="loadDocuments">重新加载</Button>
        </div>
        <div v-else-if="documents.length === 0" class="flex min-h-72 flex-col items-center justify-center text-center">
          <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
            <Archive class="h-7 w-7" />
          </div>
          <p class="mt-4 font-medium">{{ isSearching ? '没有找到匹配的文档' : '回收站是空的' }}</p>
          <p class="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
            {{ isSearching ? '换一个关键词，或清除搜索条件后再试。' : '删除的文档会暂时出现在这里，保留期内可以恢复。' }}
          </p>
          <Button v-if="isSearching" variant="outline" class="mt-4" @click="clearSearch">清除搜索</Button>
          <Button v-else variant="outline" class="mt-4" @click="router.push('/document')">返回文档列表</Button>
        </div>

        <div v-else class="space-y-3">
          <article v-for="document in documents" :key="document.id" class="rounded-xl border border-border bg-muted/20 p-4 transition-colors hover:border-amber-400/25 hover:bg-muted/40">
            <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div class="flex min-w-0 gap-3.5">
                <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300">
                  <FileText class="h-5 w-5" />
                </div>
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <h3 class="truncate font-medium">{{ document.title }}</h3>
                    <Badge variant="outline" class="border-amber-400/25 bg-amber-400/10 text-amber-200">回收站</Badge>
                  </div>
                  <p class="mt-1 text-sm text-muted-foreground">{{ document.knowledgeBaseName || '原知识库已删除' }} · {{ formatFileSize(document.fileSize) }}</p>
                  <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>删除于 {{ formatDateTime(document.recycledAt || document.updatedAt) }}</span>
                    <span class="flex items-center gap-1"><Clock3 class="h-3.5 w-3.5" />保留至 {{ getExpiryLabel(document) }}</span>
                  </div>
                </div>
              </div>

              <div class="flex shrink-0 flex-wrap items-center gap-2 xl:justify-end">
                <Button variant="outline" size="sm" :disabled="actionId === document.id" @click="restore(document)">
                  <Loader2 v-if="actionId === document.id" class="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  <RotateCcw v-else class="mr-1.5 h-3.5 w-3.5" />
                  恢复文档
                </Button>
                <Button variant="ghost" size="sm" class="text-destructive hover:bg-rose-400/10 hover:text-destructive" :disabled="actionId === document.id" @click="purge(document)">
                  <Trash2 class="mr-1.5 h-3.5 w-3.5" />
                  永久删除
                </Button>
              </div>
            </div>
          </article>

          <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 border-t border-border/70 pt-5">
            <Button variant="outline" size="sm" :disabled="loading || page <= 1" @click="goToPage(page - 1)"><ChevronLeft class="h-4 w-4" /></Button>
            <span class="text-sm text-muted-foreground">第 {{ page }} / {{ totalPages }} 页 · 共 {{ total }} 条</span>
            <Button variant="outline" size="sm" :disabled="loading || page >= totalPages" @click="goToPage(page + 1)"><ChevronRight class="h-4 w-4" /></Button>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
