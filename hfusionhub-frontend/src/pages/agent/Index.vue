<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  Clock3,
  FileSearch,
  Fingerprint,
  Gauge,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Route,
  Sparkles,
  TerminalSquare,
  Wrench,
  XCircle,
} from 'lucide-vue-next'
import * as agentApi from '@/api/agent'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { useToast } from '@/composables/useToast'

type StatusTone = 'success' | 'danger' | 'warning' | 'progress' | 'neutral'

const router = useRouter()
const toast = useToast()
const loading = ref(false)
const loadingDetail = ref(false)
const actionLoading = ref(false)
const tasks = ref<agentApi.AgentTaskSummary[]>([])
const selected = ref<agentApi.AgentTaskDetail | null>(null)
const events = ref<agentApi.AgentStatusEvent[]>([])
const metrics = ref<agentApi.AgentMetrics | null>(null)
const statusFilter = ref('ALL')

const statusFilters = [
  { value: 'ALL', label: '全部' },
  { value: 'RUNNING', label: '执行中' },
  { value: 'SUCCEEDED', label: '已完成' },
  { value: 'FAILED', label: '失败' },
]

const normalizedStatus = (status?: string) => (status || 'UNKNOWN').toUpperCase()

const statusMeta = (status?: string) => {
  const normalized = normalizedStatus(status)
  if (['SUCCEEDED', 'COMPLETED', 'SUCCESS'].includes(normalized)) return { label: '已完成', tone: 'success' as StatusTone }
  if (['FAILED', 'TIMEOUT', 'DEAD_LETTER', 'CANCELLED'].includes(normalized)) return { label: normalized === 'TIMEOUT' ? '已超时' : normalized === 'CANCELLED' ? '已取消' : normalized === 'DEAD_LETTER' ? '待处理' : '失败', tone: 'danger' as StatusTone }
  if (['RUNNING', 'PROCESSING'].includes(normalized)) return { label: '执行中', tone: 'progress' as StatusTone }
  if (['QUEUED', 'PENDING', 'RETRYING'].includes(normalized)) return { label: '等待执行', tone: 'warning' as StatusTone }
  return { label: status || '未知状态', tone: 'neutral' as StatusTone }
}

const statusBadgeClass = (status?: string) => {
  const tone = statusMeta(status).tone
  return {
    success: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300',
    danger: 'border-rose-400/25 bg-rose-400/10 text-rose-300',
    warning: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
    progress: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200',
    neutral: 'border-white/10 bg-white/5 text-muted-foreground',
  }[tone]
}

const filteredTasks = computed(() => statusFilter.value === 'ALL'
  ? tasks.value
  : tasks.value.filter(task => normalizedStatus(task.status) === statusFilter.value))
const completedCount = computed(() => tasks.value.filter(task => statusMeta(task.status).tone === 'success').length)
const runningCount = computed(() => tasks.value.filter(task => ['progress', 'warning'].includes(statusMeta(task.status).tone)).length)
const failedCount = computed(() => tasks.value.filter(task => statusMeta(task.status).tone === 'danger').length)
const activeRun = computed(() => selected.value?.runs?.find(run => run.id === selected.value?.currentRunId) || selected.value?.runs?.[0])
const isFailed = computed(() => statusMeta(selected.value?.status).tone === 'danger')
const canRetry = computed(() => ['FAILED', 'TIMEOUT', 'DEAD_LETTER'].includes(normalizedStatus(selected.value?.status)))
const canCancel = computed(() => ['RUNNING', 'QUEUED', 'PROCESSING'].includes(normalizedStatus(selected.value?.status)))
const failureDetail = computed(() => metrics.value?.errorDetail || activeRun.value?.errorDetail || selected.value?.deadLetterReason || '')
const failureTitle = computed(() => {
  const detail = failureDetail.value.toLowerCase()
  if (detail.includes('connection refused') || detail.includes('connectexception')) return 'AI 服务当前不可用'
  if (detail.includes('timeout') || detail.includes('timed out')) return '执行等待超时'
  if (detail.includes('unauthorized') || detail.includes('forbidden')) return '服务认证失败'
  return '这次任务没有完成'
})
const failureHint = computed(() => {
  const detail = failureDetail.value.toLowerCase()
  if (detail.includes('connection refused') || detail.includes('connectexception')) return '对话后端无法连接 AI 服务。确认 Python AI 服务已启动且内部地址配置正确后，再重试此任务。'
  if (detail.includes('timeout') || detail.includes('timed out')) return '服务在规定时间内没有返回结果。可以稍后重试；若频繁出现，请检查模型服务和网络。'
  return '你可以重试任务；如果持续失败，可将下方技术细节提供给管理员排查。'
})

const load = async () => {
  loading.value = true
  try {
    tasks.value = (await agentApi.listTasks({ page: 1, pageSize: 50 })).data.records
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载 Agent 任务失败')
  } finally {
    loading.value = false
  }
}

const open = async (task: agentApi.AgentTaskSummary) => {
  loadingDetail.value = true
  try {
    const [detailResponse, eventsResponse, metricsResponse] = await Promise.all([
      agentApi.getTask(task.id),
      agentApi.getTaskEvents(task.id),
      agentApi.getTaskMetrics(task.id),
    ])
    selected.value = detailResponse.data
    events.value = eventsResponse.data
    metrics.value = metricsResponse.data
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载任务详情失败')
  } finally {
    loadingDetail.value = false
  }
}

const refresh = async () => {
  await load()
  const task = selected.value && tasks.value.find(item => item.id === selected.value?.id)
  if (task) await open(task)
}

const retry = async () => {
  if (!selected.value || actionLoading.value) return
  actionLoading.value = true
  try {
    await agentApi.retryTask(selected.value.id)
    toast.success('任务已重新排队，请从对话中重新发起请求')
    await refresh()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '重试任务失败')
  } finally {
    actionLoading.value = false
  }
}

const cancel = async () => {
  if (!selected.value || actionLoading.value) return
  actionLoading.value = true
  try {
    await agentApi.cancelTask(selected.value.id)
    toast.success('已发送取消请求')
    await refresh()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '取消任务失败')
  } finally {
    actionLoading.value = false
  }
}

const formatDate = (value?: string) => value ? value.replace('T', ' ').slice(0, 16) : '—'
const formatNumber = (value?: number | null) => value == null ? '—' : new Intl.NumberFormat('zh-CN').format(value)
const formatDuration = (value?: number | null) => {
  if (value == null) return '—'
  if (value < 1000) return `${value} ms`
  if (value < 60000) return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} 秒`
  return `${Math.floor(value / 60000)} 分 ${(value % 60000 / 1000).toFixed(0)} 秒`
}
const eventText = (event: agentApi.AgentStatusEvent) => {
  if (typeof event.payload === 'string') return event.payload
  if (event.payload && typeof event.payload === 'object') {
    const payload = event.payload as Record<string, unknown>
    for (const key of ['message', 'reason', 'detail', 'error']) {
      if (typeof payload[key] === 'string' && payload[key]) return payload[key]
    }
  }
  return event.status ? `任务状态更新为 ${statusMeta(event.status).label}` : '已记录任务状态变化'
}
const runTime = (run: agentApi.AgentRun) => formatDuration(run.durationMs)
const stepLabel = (step: agentApi.AgentStep) => step.action || step.stepType || '执行步骤'

const openApprovals = () => {
  if (!selected.value) return
  router.push({ path: '/approvals', query: { taskId: selected.value.id } })
}

onMounted(load)
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary">
            <Route class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-primary/90">AGENT OPERATIONS</p>
            <h2 class="mt-1 text-2xl font-semibold tracking-tight">任务执行中心</h2>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">这里记录每次 AI 对话在后台的执行过程。平时直接在“智能对话”使用即可；遇到回答慢、失败或需要审批时，再来这里查看原因和处理。</p>
          </div>
        </div>
        <Button :disabled="loading || loadingDetail" class="shrink-0 gap-2" @click="refresh">
          <RefreshCw class="h-4 w-4" :class="(loading || loadingDetail) && 'animate-spin'" />
          刷新状态
        </Button>
      </div>
    </section>

    <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div class="rounded-xl border border-border bg-card/70 p-4">
        <p class="text-sm text-muted-foreground">最近任务</p>
        <div class="mt-2 flex items-end justify-between"><strong class="text-2xl">{{ tasks.length }}</strong><Route class="h-4 w-4 text-muted-foreground" /></div>
      </div>
      <div class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-4">
        <p class="text-sm text-muted-foreground">已完成</p>
        <div class="mt-2 flex items-end justify-between"><strong class="text-2xl text-emerald-300">{{ completedCount }}</strong><CheckCircle2 class="h-4 w-4 text-emerald-300" /></div>
      </div>
      <div class="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] p-4">
        <p class="text-sm text-muted-foreground">等待或执行中</p>
        <div class="mt-2 flex items-end justify-between"><strong class="text-2xl text-cyan-200">{{ runningCount }}</strong><LoaderCircle class="h-4 w-4 text-cyan-200" /></div>
      </div>
      <div class="rounded-xl border border-rose-400/15 bg-rose-400/[0.04] p-4">
        <p class="text-sm text-muted-foreground">需要处理</p>
        <div class="mt-2 flex items-end justify-between"><strong class="text-2xl text-rose-300">{{ failedCount }}</strong><AlertCircle class="h-4 w-4 text-rose-300" /></div>
      </div>
    </section>

    <div class="grid items-start gap-6 xl:grid-cols-[minmax(19rem,0.82fr)_minmax(0,1.5fr)]">
      <Card class="overflow-hidden border-border bg-card/80">
        <CardHeader class="border-b border-border/70 p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <CardTitle class="text-base">任务列表</CardTitle>
              <CardDescription class="mt-1">选择一条记录查看执行情况</CardDescription>
            </div>
            <span class="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">{{ filteredTasks.length }}</span>
          </div>
          <div class="mt-4 flex gap-1 overflow-x-auto pb-1">
            <button
              v-for="filter in statusFilters"
              :key="filter.value"
              class="shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors"
              :class="statusFilter === filter.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
              @click="statusFilter = filter.value"
            >
              {{ filter.label }}
            </button>
          </div>
        </CardHeader>
        <CardContent class="max-h-[42rem] space-y-2 overflow-y-auto p-3">
          <LoadingSkeleton v-if="loading" type="list" :count="5" />
          <div v-else-if="!filteredTasks.length" class="flex min-h-72 flex-col items-center justify-center px-6 text-center">
            <CircleDashed class="h-9 w-9 text-muted-foreground/60" />
            <p class="mt-4 font-medium">暂时没有这类任务</p>
            <p class="mt-1 text-sm leading-6 text-muted-foreground">从智能对话发出问题后，系统会自动在这里留下运行记录。</p>
          </div>
          <button
            v-for="task in filteredTasks"
            :key="task.id"
            class="group w-full rounded-xl border p-3.5 text-left transition-all"
            :class="selected?.id === task.id ? 'border-primary/50 bg-primary/[0.08] shadow-[inset_0_0_0_1px_rgba(52,211,153,0.08)]' : 'border-transparent hover:border-border hover:bg-muted/50'"
            @click="open(task)"
          >
            <div class="flex items-start gap-3">
              <div class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg" :class="statusMeta(task.status).tone === 'danger' ? 'bg-rose-400/10 text-rose-300' : statusMeta(task.status).tone === 'success' ? 'bg-emerald-400/10 text-emerald-300' : 'bg-primary/10 text-primary'">
                <XCircle v-if="statusMeta(task.status).tone === 'danger'" class="h-4 w-4" />
                <CheckCircle2 v-else-if="statusMeta(task.status).tone === 'success'" class="h-4 w-4" />
                <Bot v-else class="h-4 w-4" />
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs font-medium text-muted-foreground">任务 #{{ task.id }}</span>
                  <Badge variant="outline" class="shrink-0 font-medium" :class="statusBadgeClass(task.status)">{{ statusMeta(task.status).label }}</Badge>
                </div>
                <p class="mt-1.5 truncate text-sm font-medium text-foreground">{{ task.query || '未提供问题内容' }}</p>
                <div class="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{{ formatDate(task.createdAt) }}</span>
                  <ChevronRight class="h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                </div>
              </div>
            </div>
          </button>
        </CardContent>
      </Card>

      <Card class="min-h-[38rem] overflow-hidden border-border bg-card/80">
        <template v-if="!selected && !loadingDetail">
          <div class="flex min-h-[38rem] flex-col items-center justify-center px-6 text-center">
            <div class="flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary"><Sparkles class="h-6 w-6" /></div>
            <h3 class="mt-5 text-lg font-semibold">选择一项任务</h3>
            <p class="mt-2 max-w-md text-sm leading-6 text-muted-foreground">查看这次对话是否完成、耗时多久、是否调用工具，以及发生失败时该如何处理。</p>
          </div>
        </template>
        <template v-else-if="loadingDetail">
          <div class="p-6"><LoadingSkeleton type="card" :count="4" /></div>
        </template>
        <template v-else-if="selected">
          <CardHeader class="border-b border-border/70 p-5 sm:p-6">
            <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-sm text-muted-foreground">任务 #{{ selected.id }}</span>
                  <Badge variant="outline" class="font-medium" :class="statusBadgeClass(selected.status)">{{ statusMeta(selected.status).label }}</Badge>
                </div>
                <CardTitle class="mt-3 break-words text-xl leading-8">{{ selected.query || '未提供问题内容' }}</CardTitle>
                <CardDescription class="mt-2">创建于 {{ formatDate(selected.createdAt) }} · 最近更新 {{ formatDate(selected.updatedAt) }}</CardDescription>
              </div>
              <div class="flex shrink-0 gap-2">
                <Button v-if="canRetry" variant="outline" size="sm" :disabled="actionLoading" class="gap-1.5" @click="retry"><RotateCcw class="h-3.5 w-3.5" />重试</Button>
                <Button v-if="canCancel" variant="outline" size="sm" :disabled="actionLoading" class="gap-1.5" @click="cancel"><XCircle class="h-3.5 w-3.5" />取消</Button>
                <Button variant="outline" size="sm" class="gap-1.5" @click="openApprovals"><Fingerprint class="h-3.5 w-3.5" />审批记录</Button>
              </div>
            </div>
          </CardHeader>

          <CardContent class="space-y-6 p-5 sm:p-6">
            <section v-if="isFailed" class="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-4">
              <div class="flex gap-3">
                <AlertCircle class="mt-0.5 h-5 w-5 shrink-0 text-rose-300" />
                <div class="min-w-0">
                  <h3 class="font-medium text-rose-100">{{ failureTitle }}</h3>
                  <p class="mt-1 text-sm leading-6 text-rose-100/75">{{ failureHint }}</p>
                  <details v-if="failureDetail" class="mt-3">
                    <summary class="cursor-pointer text-xs text-rose-200/75 hover:text-rose-100">查看技术细节</summary>
                    <p class="mt-2 break-words rounded-lg bg-black/15 p-2.5 font-mono text-xs leading-5 text-rose-100/75">{{ failureDetail }}</p>
                  </details>
                </div>
              </div>
            </section>

            <section>
              <div class="mb-3 flex items-center gap-2"><Gauge class="h-4 w-4 text-primary" /><h3 class="font-medium">本次执行概览</h3></div>
              <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div class="rounded-xl border border-border bg-muted/35 p-3.5"><p class="text-xs text-muted-foreground">执行耗时</p><p class="mt-2 text-lg font-semibold">{{ formatDuration(metrics?.totalDurationMs ?? activeRun?.durationMs) }}</p></div>
                <div class="rounded-xl border border-border bg-muted/35 p-3.5"><p class="text-xs text-muted-foreground">执行步骤</p><p class="mt-2 text-lg font-semibold">{{ formatNumber(metrics?.stepCount ?? activeRun?.steps?.length) }}</p></div>
                <div class="rounded-xl border border-border bg-muted/35 p-3.5"><p class="text-xs text-muted-foreground">工具调用</p><p class="mt-2 text-lg font-semibold">{{ formatNumber(metrics?.toolCallsCount ?? activeRun?.toolCallsCount) }}</p></div>
                <div class="rounded-xl border border-border bg-muted/35 p-3.5"><p class="text-xs text-muted-foreground">消耗 Token</p><p class="mt-2 text-lg font-semibold">{{ formatNumber(metrics?.totalTokens) }}</p></div>
              </div>
              <div v-if="metrics?.model || activeRun?.model || metrics?.sourcesCount" class="mt-3 flex flex-wrap gap-2 text-xs">
                <span v-if="metrics?.model || activeRun?.model" class="rounded-full border border-border bg-muted/40 px-2.5 py-1 text-muted-foreground">模型：{{ metrics?.model || activeRun?.model }}</span>
                <span v-if="metrics?.sourcesCount != null" class="rounded-full border border-border bg-muted/40 px-2.5 py-1 text-muted-foreground">引用来源：{{ metrics.sourcesCount }}</span>
                <span v-if="metrics?.approvalCount" class="rounded-full border border-border bg-muted/40 px-2.5 py-1 text-muted-foreground">人工审批：{{ metrics.approvalCount }} 次</span>
              </div>
            </section>

            <section v-if="selected.runs?.length">
              <div class="mb-3 flex items-center gap-2"><Clock3 class="h-4 w-4 text-primary" /><h3 class="font-medium">执行记录</h3><span class="text-xs text-muted-foreground">每次重试都会新增一条记录</span></div>
              <div class="space-y-2">
                <div v-for="run in selected.runs" :key="run.id" class="rounded-xl border border-border bg-muted/25 p-3.5">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <div class="flex items-center gap-2"><span class="font-medium">第 {{ run.attemptNumber || 1 }} 次执行</span><Badge variant="outline" class="font-medium" :class="statusBadgeClass(run.status)">{{ statusMeta(run.status).label }}</Badge></div>
                    <span class="text-xs text-muted-foreground">{{ runTime(run) }}</span>
                  </div>
                  <p class="mt-2 text-xs text-muted-foreground">{{ run.startedAt ? `开始于 ${formatDate(run.startedAt)}` : `计划于 ${formatDate(run.scheduledAt)}` }}</p>
                  <p v-if="run.errorDetail" class="mt-2 break-words text-xs leading-5 text-rose-200/80">{{ run.errorDetail }}</p>
                  <div v-if="run.steps?.length" class="mt-3 space-y-2 border-t border-border/70 pt-3">
                    <div v-for="step in run.steps.slice(0, 6)" :key="step.id" class="flex items-start gap-2 text-xs">
                      <span class="mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] text-primary">{{ step.sequence || '·' }}</span>
                      <div class="min-w-0"><span class="font-medium">{{ stepLabel(step) }}</span><span v-if="step.durationMs != null" class="ml-2 text-muted-foreground">{{ formatDuration(step.durationMs) }}</span><p v-if="step.outputSummary || step.errorCode" class="mt-0.5 break-words text-muted-foreground">{{ step.errorCode || step.outputSummary }}</p></div>
                    </div>
                    <p v-if="run.steps.length > 6" class="text-xs text-muted-foreground">另有 {{ run.steps.length - 6 }} 个步骤未展开</p>
                  </div>
                </div>
              </div>
            </section>

            <section>
              <div class="mb-3 flex items-center gap-2"><FileSearch class="h-4 w-4 text-primary" /><h3 class="font-medium">状态时间线</h3></div>
              <div v-if="events.length" class="timeline-track">
                <div v-for="event in events" :key="event.id" class="timeline-item" :class="`tone-${statusMeta(event.status).tone === 'danger' ? 'amber' : statusMeta(event.status).tone === 'success' ? 'green' : 'cyan'}`">
                  <span class="timeline-dot" />
                  <div class="min-w-0 pb-3"><div class="flex flex-wrap items-center gap-x-2 gap-y-1"><span class="text-sm font-medium">{{ event.eventType || '状态更新' }}</span><span class="text-xs text-muted-foreground">{{ formatDate(event.createdAt) }}</span></div><p class="mt-1 break-words text-sm leading-5 text-muted-foreground">{{ eventText(event) }}</p></div>
                </div>
              </div>
              <div v-else class="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">暂时没有记录到状态事件。</div>
            </section>

            <div v-if="metrics?.errorCode || metrics?.failedTool" class="flex flex-wrap gap-2 border-t border-border/70 pt-4 text-xs text-muted-foreground">
              <span v-if="metrics.errorCode" class="rounded-md bg-muted px-2 py-1">错误代码：{{ metrics.errorCode }}</span>
              <span v-if="metrics.failedTool" class="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1"><Wrench class="h-3 w-3" />失败工具：{{ metrics.failedTool }}</span>
              <span v-if="metrics.maxStepLatencyMs" class="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1"><TerminalSquare class="h-3 w-3" />最慢步骤：{{ formatDuration(metrics.maxStepLatencyMs) }}</span>
            </div>
          </CardContent>
        </template>
      </Card>
    </div>
  </div>
</template>
