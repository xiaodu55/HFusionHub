<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Activity, AlertTriangle, BarChart3, ChevronLeft, ChevronRight, Clock3, Download, Filter, RefreshCw, Search, Send, TrendingUp, XCircle } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/composables/useToast'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'
import * as ragApi from '@/api/rag'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import type { EvaluationReport, EvaluationRun, RetrievalTrace, TraceFilters, TraceStats } from '@/api/rag'
import type { KnowledgeBase } from '@/api/types'

const PAGE_SIZE = 20
const toast = useToast()
const loading = ref(false)
const loadError = ref(false)
const exporting = ref(false)
const evaluating = ref(false)
const traces = ref<RetrievalTrace[]>([])
const totalTraces = ref(0)
const currentPage = ref(1)
const stats = ref<TraceStats>({
  total_traces: 0,
  failed_traces: 0,
  hit_traces: 0,
  hit_rate: 0,
  average_latency_ms: 0,
  result_source_counts: {},
  recent_failures: [],
  daily_metrics: [],
  window_days: 7,
})
const selectedTrace = ref<RetrievalTrace | null>(null)
const filterQuery = ref('')
const filterSource = ref('')
const errorsOnly = ref(false)
const trendDays = ref(7)
const topK = ref(5)
const evaluationQuery = ref('')
const expectedDocumentIds = ref('')
const evaluationReport = ref<EvaluationReport | null>(null)
const evaluationRuns = ref<EvaluationRun[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedKnowledgeBaseId = ref<number | undefined>()

const sourceSummary = computed(() => Object.entries(stats.value.result_source_counts)
  .map(([source, count]) => `${source}: ${count}`)
  .join(' · ') || '暂无结果')
const hitRatePercent = computed(() => `${Math.round(stats.value.hit_rate * 100)}%`)
const totalPages = computed(() => Math.max(1, Math.ceil(totalTraces.value / PAGE_SIZE)))
const canGoPrevious = computed(() => currentPage.value > 1)
const canGoNext = computed(() => currentPage.value < totalPages.value)
const maxDailyTotal = computed(() => Math.max(1, ...stats.value.daily_metrics.map(metric => metric.total_traces)))

const requireKnowledgeBaseId = () => {
  if (!selectedKnowledgeBaseId.value) {
    throw new Error('请先选择知识库')
  }
  return selectedKnowledgeBaseId.value
}

const buildFilters = (page = currentPage.value): TraceFilters => ({
  limit: PAGE_SIZE,
  offset: (page - 1) * PAGE_SIZE,
  query: filterQuery.value.trim() || undefined,
  knowledge_base_id: requireKnowledgeBaseId(),
  error_only: errorsOnly.value || undefined,
  source: filterSource.value.trim() || undefined,
})

const refreshStats = async () => {
  if (!selectedKnowledgeBaseId.value) return
  const response = await ragApi.getTraceStats(trendDays.value, requireKnowledgeBaseId())
  stats.value = response.data
}

const loadEvaluationRuns = async () => {
  if (!selectedKnowledgeBaseId.value) return
  const response = await ragApi.getEvaluationRuns({
    limit: 20,
    knowledge_base_id: requireKnowledgeBaseId(),
  })
  evaluationRuns.value = response.data.runs
}

const loadData = async (page = 1) => {
  if (!selectedKnowledgeBaseId.value) {
    traces.value = []
    totalTraces.value = 0
    currentPage.value = 1
    evaluationRuns.value = []
    return
  }
  loading.value = true
  try {
    const [tracesResponse] = await Promise.all([
      ragApi.getTraces(buildFilters(page)),
      refreshStats(),
      loadEvaluationRuns(),
    ])
    traces.value = tracesResponse.data.traces
    totalTraces.value = tracesResponse.data.total
    currentPage.value = Math.min(Math.max(1, page), totalPages.value)
    if (selectedTrace.value) {
      selectedTrace.value = traces.value.find(item => item.trace_id === selectedTrace.value?.trace_id) || null
    }
  } catch (error) {
    console.error('加载 RAG 调试数据失败:', error)
    toast.error('加载 RAG 调试数据失败，请检查后端服务或知识库权限')
  } finally {
    loading.value = false
  }
}

const goToPage = async (page: number) => {
  if (loading.value || page < 1 || page > totalPages.value || page === currentPage.value) return
  selectedTrace.value = null
  await loadData(page)
}

const applyFilters = () => {
  selectedTrace.value = null
  loadData(1)
}

const clearFilters = () => {
  filterQuery.value = ''
  filterSource.value = ''
  errorsOnly.value = false
  applyFilters()
}

const loadKnowledgeBases = async () => {
  const response = await knowledgeBaseApi.getMyKnowledgeBaseList({
    page: 1,
    pageSize: 100,
  })
  knowledgeBases.value = response.data.records
  selectedKnowledgeBaseId.value = knowledgeBases.value[0]?.id
}

const changeKnowledgeBase = () => {
  selectedTrace.value = null
  evaluationReport.value = null
  loadData(1)
}

const selectTrace = (trace: RetrievalTrace) => {
  selectedTrace.value = trace
}

const exportTraces = async (format: 'json' | 'csv') => {
  if (!selectedKnowledgeBaseId.value) {
    toast.error('请先选择知识库')
    return
  }
  exporting.value = true
  try {
    const response = await ragApi.exportTraces(format, buildFilters())
    const exported = response.data
    const blob = new Blob([exported.content], { type: `${exported.mime_type};charset=utf-8` })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = exported.filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
    toast.success(`${format.toUpperCase()} 检索记录已导出`)
  } catch (error) {
    console.error('导出检索记录失败:', error)
    toast.error('导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

const submitEvaluation = async () => {
  if (!selectedKnowledgeBaseId.value) {
    toast.error('请先选择知识库')
    return
  }
  const documentIds = expectedDocumentIds.value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
  if (!evaluationQuery.value.trim() || documentIds.length === 0) {
    toast.error('请填写问题和至少一个期望文档 ID')
    return
  }

  evaluating.value = true
  try {
    const response = await ragApi.evaluateRetrieval({
      knowledge_base_id: selectedKnowledgeBaseId.value,
      top_k: topK.value,
      cases: [{
        case_id: `manual-${Date.now()}`,
        query: evaluationQuery.value.trim(),
        expected_document_ids: documentIds,
      }],
    })
    evaluationReport.value = response.data
    toast.success('评测完成')
    await loadEvaluationRuns()
    await loadData()
  } catch (error) {
    console.error('RAG 评测失败:', error)
    toast.error('RAG 评测失败，请检查知识库和 Python AI 服务')
  } finally {
    evaluating.value = false
  }
}

onMounted(async () => {
  try {
    await loadKnowledgeBases()
    await loadData()
  } catch (error) {
    console.error('初始化 RAG 调试中心失败:', error)
    toast.error('初始化 RAG 调试中心失败，请检查后端服务')
  }
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold">RAG 调试中心</h2>
        <p class="text-muted-foreground">定位检索命中原因、追踪失败请求，并用真实问题持续评测知识库质量。</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <select
          v-model.number="selectedKnowledgeBaseId"
          class="min-w-48 rounded-md border bg-background px-3 py-2 text-sm"
          :disabled="knowledgeBases.length === 0"
          @change="changeKnowledgeBase"
        >
          <option v-if="knowledgeBases.length === 0" :value="undefined">暂无知识库</option>
          <option v-for="knowledgeBase in knowledgeBases" :key="knowledgeBase.id" :value="knowledgeBase.id">
            {{ knowledgeBase.name }}
          </option>
        </select>
        <Button variant="outline" :disabled="exporting || !selectedKnowledgeBaseId" @click="exportTraces('csv')"><Download class="mr-2 h-4 w-4" />导出 CSV</Button>
        <Button variant="outline" :disabled="exporting || !selectedKnowledgeBaseId" @click="exportTraces('json')"><Download class="mr-2 h-4 w-4" />导出 JSON</Button>
        <Button variant="outline" :disabled="loading || !selectedKnowledgeBaseId" @click="loadData"><RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': loading }" />刷新数据</Button>
      </div>
    </div>

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      <Card><CardContent class="pt-6"><div class="flex items-center justify-between"><span class="text-sm text-muted-foreground">检索次数</span><Activity class="h-4 w-4 text-blue-500" /></div><p class="mt-2 text-2xl font-bold">{{ stats.total_traces }}</p></CardContent></Card>
      <Card><CardContent class="pt-6"><div class="flex items-center justify-between"><span class="text-sm text-muted-foreground">命中率</span><TrendingUp class="h-4 w-4 text-emerald-500" /></div><p class="mt-2 text-2xl font-bold">{{ hitRatePercent }}</p><p class="text-xs text-muted-foreground">{{ stats.hit_traces }} 次有结果</p></CardContent></Card>
      <Card><CardContent class="pt-6"><div class="flex items-center justify-between"><span class="text-sm text-muted-foreground">平均耗时</span><Clock3 class="h-4 w-4 text-amber-500" /></div><p class="mt-2 text-2xl font-bold">{{ stats.average_latency_ms }} ms</p></CardContent></Card>
      <Card><CardContent class="pt-6"><div class="flex items-center justify-between"><span class="text-sm text-muted-foreground">失败次数</span><XCircle class="h-4 w-4 text-red-500" /></div><p class="mt-2 text-2xl font-bold">{{ stats.failed_traces }}</p></CardContent></Card>
      <Card><CardContent class="pt-6"><div class="flex items-center justify-between"><span class="text-sm text-muted-foreground">结果来源</span><Search class="h-4 w-4 text-violet-500" /></div><p class="mt-2 text-sm font-medium">{{ sourceSummary }}</p></CardContent></Card>
    </div>

    <div class="grid gap-6 xl:grid-cols-2">
      <Card class="h-[22rem] flex flex-col">
        <CardHeader class="shrink-0"><CardTitle class="flex items-center gap-2"><TrendingUp class="h-5 w-5" />{{ trendDays }} 日检索趋势</CardTitle><CardDescription>请求量 · 命中率 · 失败次数 · 平均耗时</CardDescription></CardHeader>
        <CardContent class="flex-1 flex flex-col">
          <div class="mb-3 flex items-center justify-between gap-2">
            <div class="flex gap-1">
              <Button v-for="days in [7, 14, 30]" :key="days" size="sm" :variant="trendDays === days ? 'default' : 'outline'" :disabled="!selectedKnowledgeBaseId" class="h-7 px-3 text-xs" @click="trendDays = days; refreshStats()">{{ days }}天</Button>
            </div>
            <div class="flex gap-3 text-xs text-muted-foreground">
              <span>总 {{ stats.total_traces }} 次</span>
              <span>命中 {{ hitRatePercent }}</span>
              <span>失败 {{ stats.failed_traces }}</span>
            </div>
          </div>
          <!-- Fixed-height mini bar chart -->
          <div v-if="stats.daily_metrics.length === 0" class="flex-1 flex items-center justify-center text-sm text-muted-foreground">暂无 RAG 观测数据，选择知识库后发送消息即可生成趋势</div>
          <div v-else class="flex-1 flex items-end gap-0.5 overflow-hidden min-h-0">
            <div v-for="metric in stats.daily_metrics" :key="metric.date" class="flex-1 flex flex-col items-center justify-end min-w-0" :title="`${metric.date}: ${metric.total_traces}次, ${Math.round(metric.hit_rate*100)}%命中`">
              <div class="w-full max-w-[3rem] rounded-t-sm transition-all" :class="metric.failed_traces > metric.total_traces * 0.3 ? 'bg-red-400' : 'bg-blue-400'" :style="{ height: `${Math.max(4, (metric.total_traces / maxDailyTotal) * 100)}%` }" />
            </div>
          </div>
          <div v-if="stats.daily_metrics.length > 0" class="mt-1 flex justify-between text-[10px] text-muted-foreground shrink-0">
            <span>{{ stats.daily_metrics[0]?.date?.slice(5) }}</span>
            <span>{{ stats.daily_metrics[stats.daily_metrics.length-1]?.date?.slice(5) }}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle class="flex items-center gap-2"><AlertTriangle class="h-5 w-5 text-red-500" />最近失败</CardTitle><CardDescription>优先查看最近五条失败，快速排查通道、模型或依赖异常。</CardDescription></CardHeader>
        <CardContent>
          <div v-if="stats.recent_failures.length === 0" class="py-8 text-center text-muted-foreground">最近没有失败检索。</div>
          <button v-for="failure in stats.recent_failures" :key="failure.trace_id" class="mb-2 w-full rounded-lg border border-red-200 p-3 text-left hover:bg-red-50 dark:border-red-900 dark:hover:bg-red-950" @click="errorsOnly = true; filterQuery = failure.query; applyFilters()">
            <div class="flex justify-between gap-3"><span class="truncate font-medium">{{ failure.query }}</span><span class="shrink-0 text-xs text-muted-foreground">{{ failure.latency_ms }} ms</span></div>
            <p class="mt-1 truncate text-xs text-red-600 dark:text-red-400">{{ failure.error }}</p>
          </button>
        </CardContent>
      </Card>
    </div>

    <Card>
      <CardHeader><CardTitle class="flex items-center gap-2"><Filter class="h-5 w-5" />检索记录筛选</CardTitle><CardDescription>筛选条件会同时作用于页面列表与导出的数据。</CardDescription></CardHeader>
      <CardContent class="space-y-4">
        <div class="grid gap-3 md:grid-cols-3">
          <input v-model="filterQuery" class="rounded-md border bg-background px-3 py-2 text-sm" placeholder="按问题关键词筛选" @keyup.enter="applyFilters" />
          <input v-model="filterSource" class="rounded-md border bg-background px-3 py-2 text-sm" placeholder="结果来源，如 vector / graph" @keyup.enter="applyFilters" />
          <label class="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"><input v-model="errorsOnly" type="checkbox" />仅看失败记录</label>
        </div>
        <div class="flex flex-wrap gap-2"><Button @click="applyFilters"><Filter class="mr-2 h-4 w-4" />应用筛选</Button><Button variant="outline" @click="clearFilters">清除筛选</Button><span class="self-center text-sm text-muted-foreground">共 {{ totalTraces }} 条匹配记录</span></div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader><CardTitle class="flex items-center gap-2"><BarChart3 class="h-5 w-5" />评测历史</CardTitle><CardDescription>仅保留聚合指标与失败用例 ID；原始问题和文档内容不会写入运行记录。</CardDescription></CardHeader>
      <CardContent>
        <div v-if="evaluationRuns.length === 0" class="py-6 text-center text-muted-foreground">暂无已持久化的评测记录。</div>
        <div v-for="run in evaluationRuns" :key="run.run_id" class="mb-2 rounded-lg border p-3 text-sm">
          <div class="flex flex-wrap items-center justify-between gap-2"><span class="font-medium">{{ run.label || '手动评测' }}</span><span class="text-xs text-muted-foreground">{{ run.created_at }}</span></div>
          <div class="mt-2 grid gap-2 text-muted-foreground md:grid-cols-4"><span>KB {{ run.knowledge_base_id ?? '自动' }} · {{ run.case_count }} 题</span><span>Recall@{{ run.top_k }} {{ run.recall_at_k.toFixed(3) }}</span><span>MRR {{ run.mean_reciprocal_rank.toFixed(3) }}</span><span :class="run.failed_case_ids.length ? 'text-amber-600' : 'text-emerald-600'">{{ run.failed_case_ids.length ? `失败：${run.failed_case_ids.join('、')}` : '全部命中' }}</span></div>
        </div>
      </CardContent>
    </Card>

    <div class="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>检索记录</CardTitle><CardDescription>点击一条记录查看路由和命中文档。</CardDescription></CardHeader>
        <CardContent>
          <LoadingSkeleton v-if="loading" type="list" :count="5" />
          <div v-else-if="traces.length === 0" class="py-8 text-center">
            <Search class="mx-auto h-10 w-10 text-muted-foreground" :stroke-width="1.5" />
            <p class="mt-3 text-muted-foreground">没有匹配的检索记录</p>
            <p class="mt-1 text-sm text-muted-foreground">选择知识库后发送消息，检索记录将显示在这里</p>
          </div>
          <button v-for="trace in traces" :key="trace.trace_id" class="mb-2 w-full rounded-lg border p-3 text-left transition-colors hover:bg-accent" :class="{ 'border-primary bg-accent': selectedTrace?.trace_id === trace.trace_id, 'border-red-300': trace.error }" @click="selectTrace(trace)">
            <div class="flex items-center justify-between gap-3"><span class="truncate font-medium">{{ trace.query }}</span><span class="shrink-0 text-xs text-muted-foreground">{{ trace.latency_ms }} ms</span></div>
            <div class="mt-1 text-xs text-muted-foreground">KB {{ trace.knowledge_base_id ?? '自动' }} · {{ trace.results.length }} 条结果 · {{ trace.routes[0]?.selected_channels?.join(' / ') || '未知通道' }}</div>
            <p v-if="trace.error" class="mt-1 truncate text-xs text-red-600">{{ trace.error }}</p>
          </button>
          <div v-if="totalTraces > 0" class="mt-4 flex items-center justify-between gap-3 border-t pt-4">
            <Button
              variant="outline"
              size="sm"
              :disabled="loading || !canGoPrevious"
              @click="goToPage(currentPage - 1)"
            >
              <ChevronLeft class="mr-1 h-4 w-4" />
              上一页
            </Button>
            <span class="text-sm text-muted-foreground">
              第 {{ currentPage }} / {{ totalPages }} 页，共 {{ totalTraces }} 条
            </span>
            <Button
              variant="outline"
              size="sm"
              :disabled="loading || !canGoNext"
              @click="goToPage(currentPage + 1)"
            >
              下一页
              <ChevronRight class="ml-1 h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card class="flex flex-col max-h-[32rem]">
        <CardHeader class="shrink-0"><CardTitle>检索详情</CardTitle><CardDescription>路由策略、候选来源与片段预览。</CardDescription></CardHeader>
        <CardContent class="flex-1 overflow-y-auto min-h-0">
          <div v-if="!selectedTrace" class="py-12 text-center text-muted-foreground">请选择左侧的一条检索记录。</div>
          <div v-else class="space-y-3">
            <div class="rounded-lg bg-muted p-3 text-sm space-y-1">
              <div><strong>路由：</strong>{{ selectedTrace.routes.map(route => `${route.query_type || 'general'} / ${route.strategy || 'adaptive'}`).join('，') }}</div>
              <div><strong>重写：</strong>{{ selectedTrace.rewrite_count }}次 · <strong>TopK：</strong>{{ selectedTrace.top_k }} · <strong>耗时：</strong>{{ selectedTrace.latency_ms }}ms</div>
            </div>
            <div v-if="selectedTrace.error" class="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"><strong>错误：</strong>{{ selectedTrace.error }}</div>
            <div v-for="(result, index) in selectedTrace.results" :key="`${result.document_id}-${index}`" class="rounded-lg border p-3">
              <div class="flex justify-between gap-3 text-sm"><span class="font-medium truncate">{{ (result as any).document_name || `文档 ${result.document_id ?? '图谱实体'}` }}</span><span class="shrink-0 text-muted-foreground">{{ result.source }} · {{ result.score.toFixed(3) }}</span></div>
              <p class="mt-1 text-sm text-muted-foreground line-clamp-3">{{ result.content_preview }}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>

    <Card>
      <CardHeader><CardTitle class="flex items-center gap-2"><BarChart3 class="h-5 w-5" />快速检索评测</CardTitle><CardDescription>输入一个问题和正确应命中的文档 ID，得到当前知识库的检索指标。</CardDescription></CardHeader>
      <CardContent class="space-y-4">
        <div class="grid gap-4 md:grid-cols-2"><label class="space-y-1 text-sm">Top K<input v-model.number="topK" type="number" min="1" max="20" class="w-full rounded-md border bg-background px-3 py-2" /></label><label class="space-y-1 text-sm">期望文档 ID（逗号分隔）<input v-model="expectedDocumentIds" class="w-full rounded-md border bg-background px-3 py-2" placeholder="例如：12,15" /></label></div>
        <label class="block space-y-1 text-sm">测试问题<textarea v-model="evaluationQuery" rows="3" class="w-full rounded-md border bg-background px-3 py-2" placeholder="例如：RAG 的检索流程是什么？" /></label>
        <Button :disabled="evaluating || !selectedKnowledgeBaseId" @click="submitEvaluation"><Send class="mr-2 h-4 w-4" />{{ evaluating ? '评测中...' : '运行评测' }}</Button>
        <div v-if="evaluationReport" class="grid gap-3 rounded-lg bg-muted p-4 md:grid-cols-3"><div>Precision@{{ evaluationReport.summary.top_k }}<p class="text-xl font-bold">{{ evaluationReport.summary.precision_at_k }}</p></div><div>Recall@{{ evaluationReport.summary.top_k }}<p class="text-xl font-bold">{{ evaluationReport.summary.recall_at_k }}</p></div><div>MRR<p class="text-xl font-bold">{{ evaluationReport.summary.mean_reciprocal_rank }}</p></div></div>
      </CardContent>
    </Card>
  </div>
</template>
