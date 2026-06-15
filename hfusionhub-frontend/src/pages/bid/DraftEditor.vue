<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as bidApi from '@/api/bid'
import type { BidDraft } from '@/api/bid'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  ArrowLeft,
  CheckCheck,
  CheckCircle2,
  FileSearch,
  FileText,
  Loader2,
  PenLine,
  ShieldCheck,
  Square,
  XCircle,
} from 'lucide-vue-next'
import { SseDataParser, type SseDataEvent } from '@/utils/sse'
import { useUserStore } from '@/stores/user'
import { formatDateTime } from '@/utils/date'
import { BID_PROJECT_STATUS_LABELS, bidProjectStatusClass } from '@/utils/badge'
import { useToast } from '@/composables/useToast'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'
import CheckReport from './CheckReport.vue'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const userStore = useUserStore()

const projectId = computed(() => Number(route.params.id))

const project = ref<bidApi.BidProjectInfo | null>(null)
const drafts = ref<BidDraft[]>([])
const loading = ref(false)
const loadError = ref(false)
const activeTab = ref<'draft' | 'check'>('draft')

const streaming = ref(false)
const streamingSection = ref('')
const streamError = ref('')
let abortController: AbortController | null = null

const STATUS_LABELS = BID_PROJECT_STATUS_LABELS

const DRAFT_STATUS_LABELS: Record<BidDraft['status'], string> = {
  drafting: '待审批',
  approved: '已通过',
  rejected: '已驳回',
}

const DRAFT_STATUS_CLASS: Record<BidDraft['status'], string> = {
  drafting: 'bg-amber-50 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300',
  approved: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300',
  rejected: 'bg-red-100 text-red-700',
}

const approvedCount = computed(() => drafts.value.filter(d => d.status === 'approved').length)
const totalChars = computed(() =>
  drafts.value.reduce((sum, d) => sum + (d.content?.length ?? 0), 0),
)

const loadDrafts = async () => {
  loading.value = true
  loadError.value = false
  try {
    drafts.value = (await bidApi.listBidDrafts(projectId.value)).data
  } catch (error) {
    loadError.value = true
    toast.error(error instanceof Error ? error.message : '加载标书分节失败')
  } finally {
    loading.value = false
  }
}

const loadProject = async () => {
  try {
    const res = await bidApi.getBidProjectDetail(projectId.value)
    project.value = res.data.project
  } catch {
    /* 头部状态非关键路径 */
  }
}

/** 同步撰写（流式失败时的兜底路径） */
const writeSync = async () => {
  try {
    const res = await bidApi.writeBidDraft(projectId.value)
    drafts.value = res.data
    await loadProject()
    toast.success(`撰写完成，共 ${drafts.value.length} 节`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '撰写失败')
  }
}

/** 流式撰写：逐节推送 bid_section_started/completed，run_completed 后回读 */
const writeStream = async () => {
  streaming.value = true
  streamError.value = ''
  streamingSection.value = ''
  abortController = new AbortController()
  try {
    const response = await fetch(`/api/bid/write/${projectId.value}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'satoken': userStore.token || '',
      },
      signal: abortController.signal,
    })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const reader = response.body?.getReader()
    if (!reader) throw new Error('No reader available')

    const decoder = new TextDecoder()
    const parser = new SseDataParser()
    let completed = false

    const applyEvents = async (events: SseDataEvent[]) => {
      for (const event of events) {
        if (event.type === 'done') continue
        let parsed: Record<string, unknown>
        try {
          parsed = JSON.parse(event.data)
        } catch {
          continue // 非 JSON 数据行（如心跳）忽略
        }
        const evt = String(parsed.event ?? '')
        if (evt === 'bid_section_started') {
          streamingSection.value = String(parsed.section_key ?? '')
        } else if (evt === 'bid_section_completed') {
          streamingSection.value = ''
          // 乐观更新：让内容实时上屏，run_completed 后回读权威数据
          const key = String(parsed.section_key ?? '')
          const found = drafts.value.find(d => d.sectionKey === key)
          if (found) {
            found.content = String(parsed.content ?? '')
            found.status = 'drafting'
          }
        } else if (evt === 'run_completed') {
          completed = true
        } else if (evt === 'run_error') {
          streamError.value = String(parsed.error_detail ?? '撰写服务异常')
        }
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      await applyEvents(parser.push(decoder.decode(value, { stream: true })))
    }
    await applyEvents(parser.push(decoder.decode()))
    await applyEvents(parser.flush())

    if (streamError.value) {
      throw new Error(streamError.value)
    }
    if (!completed) {
      throw new Error('撰写流意外中断')
    }
    await loadDrafts()
    await loadProject()
    toast.success('标书撰写完成，请逐节审批')
  } catch (error) {
    if (abortController?.signal.aborted) {
      // 用户主动停止：保留已落库内容
      await loadDrafts()
    } else {
      toast.error(error instanceof Error ? error.message : '流式撰写失败')
      // 兜底：切换同步撰写路径
      await writeSync()
    }
  } finally {
    streaming.value = false
    streamingSection.value = ''
    abortController = null
  }
}

const stopStream = () => {
  abortController?.abort()
}

const updateDraftStatus = async (draft: BidDraft, status: BidDraft['status']) => {
  try {
    await bidApi.updateBidDraftStatus(draft.id, status)
    draft.status = status
    toast.success(status === 'approved' ? `「${draft.sectionTitle}」已通过审批` : `「${draft.sectionTitle}」已驳回`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '更新分节状态失败')
  }
}

/** 全部通过（便捷入口：每节强制审批的人工动作仍记录 approved_by） */
const approveAll = async () => {
  const pending = drafts.value.filter(d => d.status !== 'approved')
  if (pending.length === 0) {
    toast.success('所有分节均已通过')
    return
  }
  for (const draft of pending) {
    await bidApi.updateBidDraftStatus(draft.id, 'approved')
    draft.status = 'approved'
  }
  toast.success(`已通过 ${pending.length} 节，可执行废标自检`)
}

const sectionTitle = (key: string) => bidApi.BID_SECTION_LABELS[key] || key

onMounted(() => {
  loadProject()
  loadDrafts()
})

onBeforeUnmount(() => abortController?.abort())
</script>

<template>
  <div class="container mx-auto max-w-6xl px-4 py-6">
    <!-- 步骤导航：解读 → 需求确认 → 撰写 / 自检 -->
    <nav class="mb-6 flex flex-wrap items-center gap-2 text-sm">
      <Button variant="ghost" size="sm" @click="router.push(`/bid/projects/${projectId}/interpret`)">
        <FileSearch class="mr-1 h-4 w-4" /> 解读
      </Button>
      <span class="text-muted-foreground">→</span>
      <Button variant="ghost" size="sm" @click="router.push(`/bid/projects/${projectId}/requirements`)">
        <CheckCircle2 class="mr-1 h-4 w-4" /> 需求确认
      </Button>
      <span class="text-muted-foreground">→</span>
      <span class="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1 font-medium text-primary-foreground">
        <PenLine class="h-4 w-4" /> 撰写 / 自检
      </span>
    </nav>

    <!-- 项目头部 -->
    <div v-if="project" class="mb-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <Button variant="ghost" size="sm" class="-ml-2" @click="router.push('/bid/projects')">
              <ArrowLeft class="mr-1 h-4 w-4" /> 返回列表
            </Button>
            <Badge :class="bidProjectStatusClass(project.status)">{{ STATUS_LABELS[project.status] }}</Badge>
          </div>
          <h1 class="mt-2 text-2xl font-bold">{{ project.title }}</h1>
          <p class="mt-1 text-sm text-muted-foreground">
            <template v-if="project.tenderNumber">招标编号：{{ project.tenderNumber }} · </template>
            创建于 {{ formatDateTime(project.createdAt) }}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <Button v-if="!streaming" @click="writeStream">
            <PenLine class="mr-1 h-4 w-4" />
            {{ drafts.length ? '重新生成标书' : '生成标书' }}
          </Button>
          <Button v-else variant="destructive" @click="stopStream">
            <Square class="mr-1 h-4 w-4" /> 停止生成
          </Button>
        </div>
      </div>

      <!-- 流式生成进度条 -->
      <div
        v-if="streaming"
        class="mt-4 flex items-center gap-3 rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm"
      >
        <Loader2 class="h-4 w-4 animate-spin text-primary" />
        <span class="text-muted-foreground">
          AI 正在撰写
          <span class="font-medium text-primary">
            {{ streamingSection ? `「${sectionTitle(streamingSection)}」` : '标书' }}
          </span>
          …
        </span>
      </div>

      <!-- Tab 切换 -->
      <div class="mt-4 flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-1">
        <button
          class="flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors"
          :class="activeTab === 'draft' ? 'bg-card shadow-sm' : 'text-muted-foreground hover:text-foreground'"
          @click="activeTab = 'draft'"
        >
          分节草稿
          <span v-if="drafts.length" class="ml-1 text-xs text-muted-foreground">
            {{ approvedCount }}/{{ drafts.length }} 已通过
          </span>
        </button>
        <button
          class="flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors"
          :class="activeTab === 'check' ? 'bg-card shadow-sm' : 'text-muted-foreground hover:text-foreground'"
          @click="activeTab = 'check'"
        >
          废标自检
        </button>
      </div>
    </div>

    <!-- 分节草稿 -->
    <div v-if="activeTab === 'draft'">
      <LoadingSkeleton v-if="loading" type="card" :count="4" />
      <ErrorState
        v-else-if="loadError"
        title="加载失败"
        message="无法加载标书分节，请稍后重试"
        @retry="loadDrafts"
      />
      <EmptyState
        v-else-if="drafts.length === 0"
        :icon="FileText"
        title="尚未生成标书"
        description="确认需求清单后，点击「生成标书」，AI 将按 商务标/技术方案/资质文件/格式文件 逐节撰写"
      />

      <template v-else>
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p class="text-xs text-muted-foreground">
            共 {{ drafts.length }} 节 · 约 {{ totalChars }} 字 · 每节须人工审批后进入自检
          </p>
          <Button variant="outline" size="sm" :disabled="streaming" @click="approveAll">
            <CheckCheck class="mr-1 h-4 w-4" /> 全部通过审批
          </Button>
        </div>
        <div class="space-y-4">
          <Card
            v-for="draft in drafts"
            :key="draft.id"
            :class="draft.status === 'approved' ? 'border-emerald-400' : ''"
          >
            <CardHeader class="flex flex-row items-center justify-between pb-2">
              <div class="flex items-center gap-2">
                <CardTitle class="text-sm">{{ draft.sectionTitle }}</CardTitle>
                <Badge :class="DRAFT_STATUS_CLASS[draft.status]">
                  {{ DRAFT_STATUS_LABELS[draft.status] }}
                </Badge>
                <span class="text-xs text-muted-foreground">v{{ draft.version }}</span>
              </div>
              <div class="flex items-center gap-2">
                <Button
                  v-if="draft.status !== 'approved'"
                  variant="outline"
                  size="sm"
                  :disabled="streaming"
                  @click="updateDraftStatus(draft, 'approved')"
                >
                  <CheckCheck class="mr-1 h-4 w-4" /> 通过
                </Button>
                <Button
                  v-if="draft.status !== 'rejected'"
                  variant="ghost"
                  size="sm"
                  :disabled="streaming"
                  @click="updateDraftStatus(draft, 'rejected')"
                >
                  <XCircle class="mr-1 h-4 w-4" /> 驳回
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <p class="whitespace-pre-wrap break-words text-sm leading-relaxed">
                {{ draft.content || '（本节内容为空，等待生成）' }}
              </p>
              <p class="mt-2 text-[11px] text-muted-foreground">
                更新于 {{ formatDateTime(draft.updatedAt) }}
                <template v-if="draft.approvedBy"> · 审批人 #{{ draft.approvedBy }}</template>
              </p>
            </CardContent>
          </Card>
        </div>

        <!-- 合规提示 -->
        <div class="mt-6 flex items-start gap-3 rounded-lg border border-amber-400/60 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200">
          <ShieldCheck class="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p class="font-medium">提交前合规提醒</p>
            <p class="mt-1 text-amber-700/90">
              标书由 AI 依据招标文件与已确认需求生成，可能出错。请逐节审批并核对引用来源；
              发出前请务必在「废标自检」中确认无 critical 级风险，并以招标文件原文为准。
            </p>
          </div>
        </div>
      </template>
    </div>

    <!-- 自检报告 -->
    <div v-else>
      <CheckReport v-if="project" :project-id="projectId" />
    </div>
  </div>
</template>
