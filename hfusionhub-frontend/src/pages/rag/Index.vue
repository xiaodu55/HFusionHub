<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Activity,
  AlertCircle,
  ArrowDownToLine,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileSearch,
  Filter,
  Gauge,
  LoaderCircle,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Target,
  XCircle,
  FlaskConical,
  GitCompareArrows,
  Download,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { useToast } from '@/composables/useToast'
import * as ragApi from '@/api/rag'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import type { EvaluationReport, EvaluationRun, RetrievalTrace, TraceFilters, TraceStats } from '@/api/rag'
import type { KnowledgeBase } from '@/api/types'

const PAGE_SIZE = 20
const emptyStats = (): TraceStats => ({
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

const toast = useToast()
const loading = ref(false)
const exporting = ref(false)
const evaluating = ref(false)
const loadNotice = ref('')
const traces = ref<RetrievalTrace[]>([])
const totalTraces = ref(0)
const currentPage = ref(1)
const stats = ref<TraceStats>(emptyStats())
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

const selectedKnowledgeBase = computed(() => knowledgeBases.value.find(item => item.id === selectedKnowledgeBaseId.value))
const hasObservabilityData = computed(() => stats.value.total_traces > 0 || totalTraces.value > 0)
const hitRatePercent = computed(() => `${Math.round(stats.value.hit_rate * 100)}%`)
const totalPages = computed(() => Math.max(1, Math.ceil(totalTraces.value / PAGE_SIZE)))
const canGoPrevious = computed(() => currentPage.value > 1)
const canGoNext = computed(() => currentPage.value < totalPages.value)
const maxDailyTotal = computed(() => Math.max(1, ...stats.value.daily_metrics.map(metric => metric.total_traces)))

const requireKnowledgeBaseId = () => {
  if (!selectedKnowledgeBaseId.value) throw new Error('请先选择知识库')
  return selectedKnowledgeBaseId.value
}

const buildFilters = (page = currentPage.value): TraceFilters => ({
  limit: PAGE_SIZE,
  offset: (page - 1) * PAGE_SIZE,
  knowledge_base_id: requireKnowledgeBaseId(),
  query: filterQuery.value.trim() || undefined,
  source: filterSource.value.trim() || undefined,
  errorOnly: errorsOnly.value || undefined,
})

// 请求序号：快速切 KB / 狂点刷新时丢弃过期响应，防止旧响应覆盖新数据（F1）
let loadSeq = 0

const loadData = async (page = 1, showErrorToast = false) => {
  if (!selectedKnowledgeBaseId.value) {
    traces.value = []
    totalTraces.value = 0
    currentPage.value = 1
    evaluationRuns.value = []
    stats.value = emptyStats()
    return
  }

  const seq = ++loadSeq
  loading.value = true
  loadNotice.value = ''
  try {
    const [traceResult, statsResult, evaluationResult] = await Promise.allSettled([
      ragApi.getTraces(buildFilters(page)),
      ragApi.getTraceStats(trendDays.value, requireKnowledgeBaseId()),
      ragApi.getEvaluationRuns({ limit: 20, knowledge_base_id: requireKnowledgeBaseId() }),
    ])

    if (seq !== loadSeq) return // 过期响应（已切换知识库或发起新请求）
    if (traceResult.status === 'rejected') throw traceResult.reason
    traces.value = traceResult.value.data.traces
    totalTraces.value = traceResult.value.data.total
    currentPage.value = Math.min(Math.max(1, page), totalPages.value)
    if (selectedTrace.value) {
      selectedTrace.value = traces.value.find(item => item.trace_id === selectedTrace.value?.trace_id) || null
    }

    const unavailable: string[] = []
    if (statsResult.status === 'fulfilled') stats.value = statsResult.value.data
    else unavailable.push('概览指标')
    if (evaluationResult.status === 'fulfilled') evaluationRuns.value = evaluationResult.value.data.runs
    else unavailable.push('评测历史')
    if (unavailable.length) loadNotice.value = `${unavailable.join('、')}暂时不可用；你仍可查看已有的检索记录。`
  } catch (error) {
    console.error('加载 RAG 数据失败:', error)
    if (seq !== loadSeq) return
    const message = error instanceof Error ? error.message : 'RAG 调试服务暂时不可用'
    loadNotice.value = `暂时无法读取此知识库的观测数据：${message}`
    if (showErrorToast) toast.error(message)
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

const refreshStats = async () => {
  if (!selectedKnowledgeBaseId.value) return
  try {
    stats.value = (await ragApi.getTraceStats(trendDays.value, requireKnowledgeBaseId())).data
  } catch (error) {
    loadNotice.value = `趋势指标暂时不可用：${error instanceof Error ? error.message : '请稍后重试'}`
  }
}

const changeTrend = async (days: number) => {
  trendDays.value = days
  await refreshStats()
}

const goToPage = async (page: number) => {
  if (loading.value || page < 1 || page > totalPages.value || page === currentPage.value) return
  selectedTrace.value = null
  await loadData(page, true)
}

const applyFilters = async () => {
  selectedTrace.value = null
  await loadData(1, true)
}

const clearFilters = async () => {
  filterQuery.value = ''
  filterSource.value = ''
  errorsOnly.value = false
  await applyFilters()
}

const loadKnowledgeBases = async () => {
  const response = await knowledgeBaseApi.getMyKnowledgeBaseList({ page: 1, pageSize: 100 })
  knowledgeBases.value = response.data.records.filter(item => item.status === 0)
  selectedKnowledgeBaseId.value = knowledgeBases.value[0]?.id
}

const changeKnowledgeBase = async () => {
  selectedTrace.value = null
  evaluationReport.value = null
  await loadData(1)
}

const refreshAll = async () => loadData(currentPage.value, true)

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
    toast.success(`${format.toUpperCase()} 记录已导出`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

const submitEvaluation = async () => {
  if (!selectedKnowledgeBaseId.value) {
    toast.error('请先选择知识库')
    return
  }
  const documentIds = expectedDocumentIds.value.split(',').map(item => item.trim()).filter(Boolean)
  if (!evaluationQuery.value.trim() || documentIds.length === 0) {
    toast.error('请填写问题和至少一个期望文档 ID')
    return
  }

  evaluating.value = true
  try {
    const response = await ragApi.evaluateRetrieval({
      knowledge_base_id: selectedKnowledgeBaseId.value,
      top_k: topK.value,
      cases: [{ case_id: `manual-${Date.now()}`, query: evaluationQuery.value.trim(), expected_document_ids: documentIds }],
    })
    evaluationReport.value = response.data
    toast.success('评测完成')
    await loadData(currentPage.value)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'RAG 评测失败，请检查知识库和 AI 服务')
  } finally {
    evaluating.value = false
  }
}

// ── 评估中枢（eval_harness）：生成质量 / 行为红线 / TTFT / A/B 门禁 ──
const harnessRunning = ref(false)
const harnessResult = ref<Record<string, number> | null>(null)
const harnessRunFile = ref('')
const harnessReport = ref('')
const harnessRuns = ref<ragApi.HarnessRunFile[]>([])
const harnessDatasets = ref<string[]>([])
const harnessDataset = ref('')
const harnessEnableJudge = ref(false)
const diffBase = ref('')
const diffCandidate = ref('')
const diffRows = ref<ragApi.HarnessDiffRow[]>([])
const diffHasRegression = ref(false)
const diffLoading = ref(false)

const HARNESS_METRIC_LABELS: Record<string, string> = {
  'retrieval_hit@5': '检索 Hit@5',
  'retrieval_recall@5': '检索 Recall@5',
  'retrieval_mrr@5': '检索 MRR@5',
  refusal_when_required_rate: '该答未答率',
  fallback_when_required_rate: '回退话术率',
  over_retrieval_rate: '过度检索率',
  ttft_p50_ms: '首字延迟 P50 (ms)',
  ttft_mean_ms: '首字延迟均值 (ms)',
  latency_mean_ms: '总延迟均值 (ms)',
  judge_faithfulness_mean: '忠实度',
  judge_answer_correctness_mean: '答案正确性',
  judge_answer_relevancy_mean: '答案相关性',
}

const loadHarnessRuns = async () => {
  try {
    const [runsRes, dsRes] = await Promise.all([
      ragApi.listHarnessRuns(),
      ragApi.listHarnessDatasets().catch(() => ({ data: { datasets: [] } }) as any),
    ])
    harnessRuns.value = runsRes.data.runs
    harnessDatasets.value = dsRes.data.datasets
  } catch {
    // 评估服务未启动时静默降级（页面其余功能不受影响）
  }
}

const runHarness = async () => {
  if (!selectedKnowledgeBaseId.value) return
  harnessRunning.value = true
  try {
    const res = await ragApi.runHarnessEvaluation({
      label: 'kb' + selectedKnowledgeBaseId.value,
      knowledge_base_id: selectedKnowledgeBaseId.value,
      dataset_name: harnessDataset.value || undefined,
      enable_judge: harnessEnableJudge.value,
    })
    harnessResult.value = res.data.summary
    harnessRunFile.value = res.data.run_file
    const reportRes = await ragApi.getHarnessReport(res.data.run_file)
    harnessReport.value = reportRes.data.report
    toast.success('评估完成')
    await loadHarnessRuns()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '评估失败，请检查评估服务与数据集')
  } finally {
    harnessRunning.value = false
  }
}

const downloadSlides = async () => {
  const res = await ragApi.getHarnessSlides(harnessRunFile.value)
  const blob = new Blob([res.data.html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = harnessRunFile.value.replace('.jsonl', '_slides.html')
  a.click()
  URL.revokeObjectURL(url)
}

const downloadReport = () => {
  const blob = new Blob([harnessReport.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = harnessRunFile.value.replace('.jsonl', '_report.md')
  a.click()
  URL.revokeObjectURL(url)
}

const runDiff = async () => {
  if (!diffBase.value || !diffCandidate.value || diffBase.value === diffCandidate.value) return
  diffLoading.value = true
  try {
    const res = await ragApi.diffHarnessRuns({ base_run: diffBase.value, candidate_run: diffCandidate.value })
    diffRows.value = res.data.rows
    diffHasRegression.value = res.data.has_regression
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'A/B 对比失败')
  } finally {
    diffLoading.value = false
  }
}

const formatMetric = (_key: string, value: number) =>
  value > 1.5 ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : value.toFixed(4)

const jumpToEvaluation = () => document.getElementById('retrieval-evaluation')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
const formatDate = (value?: string) => value ? value.replace('T', ' ').slice(0, 16) : '—'

onMounted(async () => {
  try {
    await loadKnowledgeBases()
    await loadData()
    await loadHarnessRuns()
  } catch (error) {
    console.error('初始化 RAG 调试中心失败:', error)
    loadNotice.value = `暂时无法加载知识库：${error instanceof Error ? error.message : '请稍后刷新页面'}`
  }
})
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-10 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:p-6 xl:flex-row xl:items-center xl:justify-between">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary"><Target class="h-5 w-5" /></div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-primary/90">RETRIEVAL QUALITY</p>
            <h2 class="mt-1 text-2xl font-semibold tracking-tight">知识检索质量中心</h2>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">RAG 会让 AI 从知识库中找依据再回答。这里用来确认“有没有找到、找得准不准、为什么失败”；日常对话无需打开。</p>
          </div>
        </div>
        <div class="flex flex-wrap gap-2 xl:justify-end">
          <select v-model.number="selectedKnowledgeBaseId" class="h-10 min-w-52 rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20" :disabled="knowledgeBases.length === 0" @change="changeKnowledgeBase">
            <option v-if="knowledgeBases.length === 0" :value="undefined">暂无可用知识库</option>
            <option v-for="knowledgeBase in knowledgeBases" :key="knowledgeBase.id" :value="knowledgeBase.id">{{ knowledgeBase.name }}</option>
          </select>
          <Button variant="outline" size="sm" :disabled="loading || !selectedKnowledgeBaseId" class="gap-1.5" @click="refreshAll"><RefreshCw class="h-3.5 w-3.5" :class="loading && 'animate-spin'" />刷新</Button>
          <Button variant="outline" size="sm" :disabled="exporting || !selectedKnowledgeBaseId" class="gap-1.5" @click="exportTraces('csv')"><ArrowDownToLine class="h-3.5 w-3.5" />导出</Button>
        </div>
      </div>
    </section>

    <div v-if="selectedKnowledgeBase" class="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-sm text-muted-foreground"><span>正在观察 <strong class="font-medium text-foreground">{{ selectedKnowledgeBase.name }}</strong></span><span class="hidden text-border sm:inline">•</span><span>最近 {{ trendDays }} 天</span><span class="hidden text-border sm:inline">•</span><span>记录与导出只包含当前知识库</span></div>

    <div v-if="loadNotice" class="flex gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.07] p-4 text-sm leading-6 text-amber-100/85"><AlertCircle class="mt-0.5 h-4 w-4 shrink-0 text-amber-300" /><p>{{ loadNotice }}</p></div>

    <section v-if="selectedKnowledgeBaseId" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div class="rounded-xl border border-border bg-card/75 p-4"><div class="flex items-center justify-between"><p class="text-sm text-muted-foreground">检索请求</p><Activity class="h-4 w-4 text-primary" /></div><p class="mt-2 text-2xl font-semibold">{{ stats.total_traces }}</p><p class="mt-1 text-xs text-muted-foreground">近 {{ trendDays }} 天</p></div>
      <div class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-4"><div class="flex items-center justify-between"><p class="text-sm text-muted-foreground">找到结果</p><CheckCircle2 class="h-4 w-4 text-emerald-300" /></div><p class="mt-2 text-2xl font-semibold text-emerald-200">{{ hitRatePercent }}</p><p class="mt-1 text-xs text-muted-foreground">{{ stats.hit_traces }} 次有可用结果</p></div>
      <div class="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] p-4"><div class="flex items-center justify-between"><p class="text-sm text-muted-foreground">平均检索耗时</p><Clock3 class="h-4 w-4 text-cyan-200" /></div><p class="mt-2 text-2xl font-semibold text-cyan-100">{{ stats.average_latency_ms }} <span class="text-base font-medium">ms</span></p><p class="mt-1 text-xs text-muted-foreground">不含模型生成时间</p></div>
      <div class="rounded-xl border border-rose-400/15 bg-rose-400/[0.04] p-4"><div class="flex items-center justify-between"><p class="text-sm text-muted-foreground">失败请求</p><XCircle class="h-4 w-4 text-rose-300" /></div><p class="mt-2 text-2xl font-semibold text-rose-200">{{ stats.failed_traces }}</p><p class="mt-1 text-xs text-muted-foreground">需要优先排查的检索</p></div>
    </section>

    <Card v-if="!selectedKnowledgeBaseId" class="border-border bg-card/80">
      <div class="flex min-h-72 flex-col items-center justify-center px-6 text-center"><FileSearch class="h-10 w-10 text-muted-foreground/70" /><h3 class="mt-4 text-lg font-semibold">先创建或选择一个知识库</h3><p class="mt-2 max-w-md text-sm leading-6 text-muted-foreground">RAG 观测数据按知识库隔离，选择知识库后才能查看它的检索质量。</p></div>
    </Card>

    <template v-else>
      <Card v-if="!hasObservabilityData && !loading" class="overflow-hidden border-primary/20 bg-card/80">
        <div class="grid gap-6 p-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(16rem,0.7fr)] lg:p-7">
          <div>
            <div class="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary"><Sparkles class="h-5 w-5" /></div>
            <h3 class="mt-5 text-xl font-semibold">这个知识库还没有检索记录</h3>
            <p class="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">这是正常状态，不代表出错。完成一次带知识库的对话后，系统才会在这里记录检索耗时、命中结果和失败原因。</p>
            <div class="mt-5 flex flex-wrap items-center gap-2 text-sm"><span class="rounded-full border border-border bg-muted/45 px-3 py-1.5">1. 上传并完成索引</span><ArrowRight class="h-4 w-4 text-muted-foreground" /><span class="rounded-full border border-border bg-muted/45 px-3 py-1.5">2. 在智能对话中选择该知识库</span><ArrowRight class="h-4 w-4 text-muted-foreground" /><span class="rounded-full border border-border bg-muted/45 px-3 py-1.5">3. 回到这里查看质量</span></div>
          </div>
          <div class="rounded-xl border border-border bg-muted/25 p-5"><p class="text-sm font-medium">已经有测试文档？</p><p class="mt-2 text-sm leading-6 text-muted-foreground">可直接运行一次检索评测，验证指定文档能否被正确找回。</p><Button variant="outline" size="sm" class="mt-4 gap-1.5" @click="jumpToEvaluation"><Play class="h-3.5 w-3.5" />开始评测</Button></div>
        </div>
      </Card>

      <section v-else class="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(18rem,0.75fr)]">
        <Card class="min-h-80 border-border bg-card/80">
          <CardHeader class="flex-row items-start justify-between gap-4 p-5"><div><CardTitle class="flex items-center gap-2 text-base"><Gauge class="h-4 w-4 text-primary" />检索趋势</CardTitle><CardDescription class="mt-1">每天的请求量；柱体变红表示当天失败比例较高</CardDescription></div><div class="flex gap-1 rounded-lg bg-muted/45 p-1"><button v-for="days in [7, 14, 30]" :key="days" class="rounded-md px-2.5 py-1.5 text-xs transition-colors" :class="trendDays === days ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'" @click="changeTrend(days)">{{ days }}天</button></div></CardHeader>
          <CardContent class="flex h-52 flex-col p-5 pt-0">
            <div v-if="stats.daily_metrics.length" class="flex min-h-0 flex-1 items-end gap-1.5"><div v-for="metric in stats.daily_metrics" :key="metric.date" class="group flex h-full min-w-0 flex-1 flex-col justify-end" :title="`${metric.date}：${metric.total_traces} 次请求，命中 ${Math.round(metric.hit_rate * 100)}%，失败 ${metric.failed_traces}`"><div class="relative w-full rounded-t-md transition-all" :class="metric.failed_traces > metric.total_traces * 0.3 ? 'bg-rose-400/80' : 'bg-primary/80'" :style="{ height: `${Math.max(5, (metric.total_traces / maxDailyTotal) * 100)}%` }"><span class="absolute -top-5 left-1/2 hidden -translate-x-1/2 whitespace-nowrap text-[10px] text-muted-foreground group-hover:block">{{ metric.total_traces }}</span></div></div></div>
            <div v-else class="flex flex-1 items-center justify-center text-sm text-muted-foreground">暂时没有可显示的趋势数据</div>
            <div v-if="stats.daily_metrics.length" class="mt-2 flex justify-between text-[10px] text-muted-foreground"><span>{{ stats.daily_metrics[0]?.date?.slice(5) }}</span><span>{{ stats.daily_metrics[stats.daily_metrics.length - 1]?.date?.slice(5) }}</span></div>
          </CardContent>
        </Card>

        <Card class="border-border bg-card/80">
          <CardHeader class="p-5"><CardTitle class="flex items-center gap-2 text-base"><ShieldAlert class="h-4 w-4 text-rose-300" />需要关注</CardTitle><CardDescription class="mt-1">最近失败的检索请求</CardDescription></CardHeader>
          <CardContent class="p-5 pt-0"><div v-if="!stats.recent_failures.length" class="flex min-h-36 flex-col items-center justify-center text-center"><CheckCircle2 class="h-6 w-6 text-emerald-300" /><p class="mt-2 text-sm font-medium">没有失败记录</p><p class="mt-1 text-xs text-muted-foreground">最近的检索都正常完成</p></div><button v-for="failure in stats.recent_failures.slice(0, 3)" :key="failure.trace_id" class="mb-2 w-full rounded-lg border border-rose-400/15 bg-rose-400/[0.04] p-3 text-left transition-colors hover:bg-rose-400/[0.08]" @click="errorsOnly = true; filterQuery = failure.query; applyFilters()"><div class="flex justify-between gap-3"><span class="truncate text-sm font-medium">{{ failure.query }}</span><span class="shrink-0 text-xs text-muted-foreground">{{ failure.latency_ms }} ms</span></div><p class="mt-1 truncate text-xs text-rose-200/75">{{ failure.error || '未记录错误详情' }}</p></button></CardContent>
        </Card>
      </section>

      <Card class="overflow-hidden border-border bg-card/80">
        <CardHeader class="flex-row items-start justify-between gap-4 border-b border-border/70 p-5"><div><CardTitle class="flex items-center gap-2 text-base"><FileSearch class="h-4 w-4 text-primary" />检索记录</CardTitle><CardDescription class="mt-1">查看某次问题走了哪些检索通道、找到了哪些文档</CardDescription></div><span class="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">{{ totalTraces }} 条</span></CardHeader>
        <CardContent class="p-0">
          <details class="border-b border-border/70 px-5 py-3"><summary class="cursor-pointer list-none text-sm text-muted-foreground hover:text-foreground"><span class="inline-flex items-center gap-2"><Filter class="h-3.5 w-3.5" />筛选与导出</span></summary><div class="grid gap-3 py-4 md:grid-cols-3"><input v-model="filterQuery" class="h-10 rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50" placeholder="按问题关键词筛选" @keyup.enter="applyFilters" /><input v-model="filterSource" class="h-10 rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50" placeholder="来源，如 vector / graph" @keyup.enter="applyFilters" /><label class="flex h-10 items-center gap-2 rounded-md border border-input bg-background/70 px-3 text-sm"><input v-model="errorsOnly" type="checkbox" class="accent-primary" />只看失败请求</label><div class="flex flex-wrap gap-2 md:col-span-3"><Button size="sm" @click="applyFilters"><Filter class="mr-1.5 h-3.5 w-3.5" />应用</Button><Button size="sm" variant="outline" @click="clearFilters">清除</Button><Button size="sm" variant="outline" :disabled="exporting" class="ml-auto" @click="exportTraces('json')">导出 JSON</Button></div></div></details>
          <div class="grid xl:grid-cols-[minmax(0,0.9fr)_minmax(20rem,1.1fr)]">
            <div class="border-b border-border/70 p-4 xl:border-b-0 xl:border-r">
              <LoadingSkeleton v-if="loading" type="list" :count="4" />
              <div v-else-if="!traces.length" class="flex min-h-60 flex-col items-center justify-center px-6 text-center"><Search class="h-8 w-8 text-muted-foreground/60" /><p class="mt-3 text-sm font-medium">没有匹配的检索记录</p><p class="mt-1 text-xs leading-5 text-muted-foreground">可调整筛选条件，或在智能对话中使用当前知识库提问。</p></div>
              <button v-for="trace in traces" :key="trace.trace_id" class="mb-2 w-full rounded-xl border p-3.5 text-left transition-colors" :class="selectedTrace?.trace_id === trace.trace_id ? 'border-primary/45 bg-primary/[0.07]' : trace.error ? 'border-rose-400/20 bg-rose-400/[0.03] hover:bg-rose-400/[0.06]' : 'border-border bg-muted/20 hover:border-primary/25 hover:bg-muted/45'" @click="selectedTrace = trace"><div class="flex items-center justify-between gap-3"><span class="truncate text-sm font-medium">{{ trace.query }}</span><span class="shrink-0 text-xs text-muted-foreground">{{ trace.latency_ms }} ms</span></div><p class="mt-1.5 text-xs text-muted-foreground">{{ trace.results.length }} 条结果 · {{ trace.routes[0]?.selected_channels?.join(' / ') || '未记录通道' }} · {{ formatDate(trace.created_at) }}</p><p v-if="trace.error" class="mt-1.5 truncate text-xs text-rose-200/80">{{ trace.error }}</p></button>
              <div v-if="totalTraces > 0" class="mt-4 flex items-center justify-between gap-3 border-t border-border/70 pt-4"><Button variant="outline" size="sm" :disabled="loading || !canGoPrevious" @click="goToPage(currentPage - 1)"><ChevronLeft class="mr-1 h-3.5 w-3.5" />上一页</Button><span class="text-xs text-muted-foreground">{{ currentPage }} / {{ totalPages }}</span><Button variant="outline" size="sm" :disabled="loading || !canGoNext" @click="goToPage(currentPage + 1)">下一页<ChevronRight class="ml-1 h-3.5 w-3.5" /></Button></div>
            </div>
            <div class="min-h-80 p-5"><div v-if="!selectedTrace" class="flex h-full min-h-60 flex-col items-center justify-center text-center"><CircleHelp class="h-8 w-8 text-muted-foreground/60" /><p class="mt-3 text-sm font-medium">选择左侧的一条记录</p><p class="mt-1 max-w-xs text-xs leading-5 text-muted-foreground">即可查看它的检索路线与命中文档片段。</p></div><div v-else class="space-y-4"><div><p class="text-xs font-medium tracking-[0.12em] text-primary">检索详情</p><h3 class="mt-1 break-words text-base font-semibold">{{ selectedTrace.query }}</h3></div><div class="grid gap-2 sm:grid-cols-3"><div class="rounded-lg bg-muted/45 p-3 text-xs"><p class="text-muted-foreground">检索耗时</p><p class="mt-1 font-medium">{{ selectedTrace.latency_ms }} ms</p></div><div class="rounded-lg bg-muted/45 p-3 text-xs"><p class="text-muted-foreground">查询改写</p><p class="mt-1 font-medium">{{ selectedTrace.rewrite_count }} 次</p></div><div class="rounded-lg bg-muted/45 p-3 text-xs"><p class="text-muted-foreground">返回结果</p><p class="mt-1 font-medium">{{ selectedTrace.results.length }} 条</p></div></div><div v-if="selectedTrace.error" class="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-3 text-sm leading-6 text-rose-100/80"><strong class="text-rose-100">本次失败：</strong>{{ selectedTrace.error }}</div><div v-if="selectedTrace.routes.length" class="rounded-xl border border-border bg-muted/20 p-3 text-sm"><p class="font-medium">检索路线</p><p class="mt-1.5 text-muted-foreground">{{ selectedTrace.routes.map(route => `${route.query_type || '通用问题'} · ${route.strategy || '自适应策略'}`).join('；') }}</p></div><div class="space-y-2"><p class="text-sm font-medium">命中文档</p><div v-if="!selectedTrace.results.length" class="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">这次检索没有返回文档片段。</div><div v-for="(result, index) in selectedTrace.results" :key="`${result.document_id}-${index}`" class="rounded-xl border border-border bg-muted/20 p-3"><div class="flex justify-between gap-3 text-sm"><span class="truncate font-medium">{{ `文档 ${result.document_id ?? '图谱实体'}` }}</span><span class="shrink-0 text-xs text-muted-foreground">{{ result.source }} · {{ result.score.toFixed(3) }}</span></div><p class="mt-1.5 text-sm leading-6 text-muted-foreground">{{ result.content_preview }}</p></div></div></div></div>
          </div>
        </CardContent>
      </Card>

      <Card id="retrieval-evaluation" class="border-border bg-card/80 scroll-mt-6">
        <CardHeader class="p-5"><CardTitle class="flex items-center gap-2 text-base"><BarChart3 class="h-4 w-4 text-primary" />验证一次检索</CardTitle><CardDescription class="mt-1">用一个真实问题，检查指定文档能否排在检索结果中。适合在更新文档或策略后做快速验收。</CardDescription></CardHeader>
        <CardContent class="p-5 pt-0"><div class="grid gap-3 md:grid-cols-[7rem_minmax(0,1fr)_minmax(0,1.2fr)]"><label class="text-sm"><span class="mb-1.5 block text-muted-foreground">返回条数</span><input v-model.number="topK" type="number" min="1" max="20" class="h-10 w-full rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50" /></label><label class="text-sm"><span class="mb-1.5 block text-muted-foreground">测试问题</span><input v-model="evaluationQuery" class="h-10 w-full rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50" placeholder="例如：RAG 的检索流程是什么？" /></label><label class="text-sm"><span class="mb-1.5 block text-muted-foreground">期望命中的文档 ID</span><input v-model="expectedDocumentIds" class="h-10 w-full rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50" placeholder="多个 ID 用英文逗号分隔，例如 12,15" /></label></div><div class="mt-4 flex flex-wrap items-center gap-3"><Button :disabled="evaluating" class="gap-2" @click="submitEvaluation"><LoaderCircle v-if="evaluating" class="h-4 w-4 animate-spin" /><Play v-else class="h-4 w-4" />{{ evaluating ? '正在评测' : '运行评测' }}</Button><p class="text-xs text-muted-foreground">文档 ID 可在文档管理页查看</p></div><div v-if="evaluationReport" class="mt-5 grid gap-3 rounded-xl border border-primary/20 bg-primary/[0.05] p-4 sm:grid-cols-3"><div><p class="text-xs text-muted-foreground">Precision@{{ evaluationReport.summary.top_k }}</p><p class="mt-1 text-xl font-semibold">{{ evaluationReport.summary.precision_at_k }}</p></div><div><p class="text-xs text-muted-foreground">Recall@{{ evaluationReport.summary.top_k }}</p><p class="mt-1 text-xl font-semibold">{{ evaluationReport.summary.recall_at_k }}</p></div><div><p class="text-xs text-muted-foreground">MRR</p><p class="mt-1 text-xl font-semibold">{{ evaluationReport.summary.mean_reciprocal_rank }}</p></div></div></CardContent>
      </Card>

      <Card v-if="evaluationRuns.length" class="border-border bg-card/80"><CardHeader class="p-5"><CardTitle class="text-base">最近评测</CardTitle><CardDescription class="mt-1">保存的是聚合指标与失败用例标识，不保存原始问题或文档内容。</CardDescription></CardHeader><CardContent class="space-y-2 p-5 pt-0"><div v-for="run in evaluationRuns.slice(0, 5)" :key="run.run_id" class="grid gap-2 rounded-xl border border-border bg-muted/20 p-3 text-sm md:grid-cols-[minmax(0,1fr)_auto_auto_auto]"><span class="font-medium">{{ run.label || '手动评测' }}</span><span class="text-muted-foreground">{{ run.case_count }} 题 · Top {{ run.top_k }}</span><span class="text-muted-foreground">Recall {{ run.recall_at_k.toFixed(3) }} · MRR {{ run.mean_reciprocal_rank.toFixed(3) }}</span><span :class="run.failed_case_ids.length ? 'text-amber-200' : 'text-emerald-300'">{{ run.failed_case_ids.length ? `失败 ${run.failed_case_ids.length} 题` : '全部命中' }}</span></div></CardContent></Card>

      <Card id="generation-evaluation" class="border-border bg-card/80 scroll-mt-6">
        <CardHeader class="p-5"><CardTitle class="flex items-center gap-2 text-base"><FlaskConical class="h-4 w-4 text-primary" />生成质量评估（评估中枢）</CardTitle><CardDescription class="mt-1">端到端评估：真实驱动对话链路，产出检索命中、行为红线（该答未答/过度检索）、首字延迟与 LLM 评审（忠实度/正确性/相关性）指标。会真实调用模型，请在评测环境使用。</CardDescription></CardHeader>
        <CardContent class="p-5 pt-0">
          <div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
            <label class="text-sm"><span class="mb-1.5 block text-muted-foreground">评测数据集（JSONL，可选）</span><select v-model="harnessDataset" class="h-10 w-full rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50"><option value="">不使用数据集（仅冒烟）</option><option v-for="dataset in harnessDatasets" :key="dataset" :value="dataset">{{ dataset }}</option></select></label>
            <label class="mt-[1.4rem] flex items-center gap-2 text-sm"><input v-model="harnessEnableJudge" type="checkbox" class="accent-primary" /><span class="text-muted-foreground">启用 LLM 评审（会产生模型调用成本）</span></label>
            <div class="flex items-end"><Button :disabled="harnessRunning || !selectedKnowledgeBaseId" class="gap-2" @click="runHarness"><LoaderCircle v-if="harnessRunning" class="h-4 w-4 animate-spin" /><Play v-else class="h-4 w-4" />{{ harnessRunning ? '评估运行中…' : '运行评估' }}</Button></div>
          </div>

          <div v-if="harnessResult" class="mt-5 space-y-4">
            <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              <div v-for="(value, key) in harnessResult" :key="key" class="rounded-lg border border-border bg-muted/20 p-3"><p class="text-xs text-muted-foreground">{{ HARNESS_METRIC_LABELS[String(key)] || key }}</p><p class="mt-1 font-semibold tabular-nums">{{ formatMetric(String(key), Number(value)) }}</p></div>
            </div>
            <div class="flex flex-wrap items-center gap-3"><p class="text-xs text-muted-foreground">运行文件：<code class="rounded bg-muted px-1.5 py-0.5">{{ harnessRunFile }}</code></p><Button v-if="harnessReport" variant="outline" size="sm" class="gap-1.5" @click="downloadReport"><Download class="h-3.5 w-3.5" />下载报告</Button><Button v-if="harnessReport" variant="outline" size="sm" class="gap-1.5" @click="downloadSlides"><Download class="h-3.5 w-3.5" />下载幻灯片</Button></div>
          </div>
        </CardContent>
      </Card>

      <Card id="ab-diff" class="border-border bg-card/80 scroll-mt-6">
        <CardHeader class="p-5"><CardTitle class="flex items-center gap-2 text-base"><GitCompareArrows class="h-4 w-4 text-primary" />A/B 回归对比</CardTitle><CardDescription class="mt-1">选择两次评估运行做阈值化对比，回归指标标记为红色。用于验证改动没有劣化回答质量。</CardDescription></CardHeader>
        <CardContent class="p-5 pt-0">
          <div v-if="harnessRuns.length < 2" class="text-sm text-muted-foreground">至少完成两次评估后才能对比。</div>
          <template v-else>
            <div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              <label class="text-sm"><span class="mb-1.5 block text-muted-foreground">基线（改动前）</span><select v-model="diffBase" class="h-10 w-full rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50"><option v-for="run in harnessRuns" :key="run.file" :value="run.file">{{ run.file }}</option></select></label>
              <label class="text-sm"><span class="mb-1.5 block text-muted-foreground">候选（改动后）</span><select v-model="diffCandidate" class="h-10 w-full rounded-md border border-input bg-background/70 px-3 text-sm outline-none focus:border-primary/50"><option v-for="run in harnessRuns" :key="run.file" :value="run.file">{{ run.file }}</option></select></label>
              <div class="flex items-end"><Button :disabled="diffLoading" class="gap-2" @click="runDiff"><GitCompareArrows v-if="!diffLoading" class="h-4 w-4" /><LoaderCircle v-else class="h-4 w-4 animate-spin" />对比</Button></div>
            </div>
            <div v-if="diffRows.length" class="mt-5 space-y-2">
              <p v-if="diffHasRegression" class="rounded-lg border border-rose-400/25 bg-rose-400/[0.07] px-3 py-2 text-sm text-rose-200">存在回归指标 —— 请检查改动是否劣化了回答质量。</p>
              <div class="overflow-hidden rounded-xl border border-border">
                <table class="w-full text-sm">
                  <thead class="bg-muted/40 text-left text-xs text-muted-foreground"><tr><th class="px-3 py-2">指标</th><th class="px-3 py-2 text-right">基线</th><th class="px-3 py-2 text-right">候选</th><th class="px-3 py-2 text-right">变化</th><th class="px-3 py-2 text-center">结论</th></tr></thead><tbody>
                    <tr v-for="row in diffRows" :key="row.metric" class="border-t border-border/70">
                      <td class="px-3 py-2">{{ HARNESS_METRIC_LABELS[row.metric] || row.metric }}</td>
                      <td class="px-3 py-2 text-right tabular-nums">{{ row.base === null ? '—' : formatMetric(row.metric, row.base) }}</td>
                      <td class="px-3 py-2 text-right tabular-nums">{{ row.candidate === null ? '—' : formatMetric(row.metric, row.candidate) }}</td>
                      <td class="px-3 py-2 text-right tabular-nums" :class="row.verdict === 'regressed' ? 'text-rose-300' : row.verdict === 'improved' ? 'text-emerald-300' : 'text-muted-foreground'">{{ row.delta === null ? '—' : (row.delta > 0 ? '+' : '') + row.delta }}</td>
                      <td class="px-3 py-2 text-center"><span :class="row.verdict === 'regressed' ? 'rounded-full bg-rose-400/15 px-2 py-0.5 text-xs text-rose-300' : row.verdict === 'improved' ? 'rounded-full bg-emerald-400/15 px-2 py-0.5 text-xs text-emerald-300' : 'text-xs text-muted-foreground'">{{ ({ improved: '改善', regressed: '回归', neutral: '持平', missing_in_candidate: '候选缺失' } as Record<string, string>)[row.verdict] }}</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
