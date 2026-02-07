<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Activity, BarChart3, Clock3, RefreshCw, Search, Send, XCircle } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/composables/useToast'
import * as ragApi from '@/api/rag'
import type { EvaluationReport, RetrievalTrace, TraceStats } from '@/api/rag'

const toast = useToast()
const loading = ref(false)
const evaluating = ref(false)
const traces = ref<RetrievalTrace[]>([])
const stats = ref<TraceStats>({
  total_traces: 0,
  failed_traces: 0,
  average_latency_ms: 0,
  result_source_counts: {},
})
const selectedTrace = ref<RetrievalTrace | null>(null)
const knowledgeBaseId = ref<number | undefined>()
const topK = ref(5)
const evaluationQuery = ref('')
const expectedDocumentIds = ref('')
const evaluationReport = ref<EvaluationReport | null>(null)

const sourceSummary = computed(() => Object.entries(stats.value.result_source_counts)
  .map(([source, count]) => `${source}: ${count}`)
  .join(' · ') || '暂无结果')

const loadData = async () => {
  loading.value = true
  try {
    const [tracesResponse, statsResponse] = await Promise.all([
      ragApi.getTraces(),
      ragApi.getTraceStats(),
    ])
    traces.value = tracesResponse.data.traces
    stats.value = statsResponse.data
    if (selectedTrace.value) {
      selectedTrace.value = traces.value.find(item => item.trace_id === selectedTrace.value?.trace_id) || null
    }
  } catch (error) {
    console.error('加载 RAG 调试数据失败:', error)
    toast.error('加载 RAG 调试数据失败，请确认 Python AI 服务已启动')
  } finally {
    loading.value = false
  }
}

const selectTrace = (trace: RetrievalTrace) => {
  selectedTrace.value = trace
}

const submitEvaluation = async () => {
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
      knowledge_base_id: knowledgeBaseId.value,
      top_k: topK.value,
      cases: [{
        case_id: `manual-${Date.now()}`,
        query: evaluationQuery.value.trim(),
        expected_document_ids: documentIds,
      }],
    })
    evaluationReport.value = response.data
    toast.success('评测完成')
    await loadData()
  } catch (error) {
    console.error('RAG 评测失败:', error)
    toast.error('RAG 评测失败，请检查知识库和 Python AI 服务')
  } finally {
    evaluating.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold">RAG 调试中心</h2>
        <p class="text-muted-foreground">查看检索为什么命中，并用真实问题持续评测知识库质量。</p>
      </div>
      <Button variant="outline" :disabled="loading" @click="loadData">
        <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': loading }" />
        刷新数据
      </Button>
    </div>

    <div class="grid gap-4 md:grid-cols-4">
      <Card>
        <CardContent class="pt-6">
          <div class="flex items-center justify-between"><span class="text-sm text-muted-foreground">检索次数</span><Activity class="h-4 w-4 text-blue-500" /></div>
          <p class="mt-2 text-2xl font-bold">{{ stats.total_traces }}</p>
        </CardContent>
      </Card>
      <Card>
        <CardContent class="pt-6">
          <div class="flex items-center justify-between"><span class="text-sm text-muted-foreground">平均耗时</span><Clock3 class="h-4 w-4 text-amber-500" /></div>
          <p class="mt-2 text-2xl font-bold">{{ stats.average_latency_ms }} ms</p>
        </CardContent>
      </Card>
      <Card>
        <CardContent class="pt-6">
          <div class="flex items-center justify-between"><span class="text-sm text-muted-foreground">失败次数</span><XCircle class="h-4 w-4 text-red-500" /></div>
          <p class="mt-2 text-2xl font-bold">{{ stats.failed_traces }}</p>
        </CardContent>
      </Card>
      <Card>
        <CardContent class="pt-6">
          <div class="flex items-center justify-between"><span class="text-sm text-muted-foreground">结果来源</span><Search class="h-4 w-4 text-emerald-500" /></div>
          <p class="mt-2 text-sm font-medium">{{ sourceSummary }}</p>
        </CardContent>
      </Card>
    </div>

    <div class="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>最近检索</CardTitle><CardDescription>点击一条记录查看路由和命中文档。</CardDescription></CardHeader>
        <CardContent>
          <div v-if="loading" class="py-8 text-center text-muted-foreground">加载中...</div>
          <div v-else-if="traces.length === 0" class="py-8 text-center text-muted-foreground">暂无检索记录。先在对话页向知识库提问。</div>
          <button
            v-for="trace in traces"
            :key="trace.trace_id"
            class="mb-2 w-full rounded-lg border p-3 text-left transition-colors hover:bg-accent"
            :class="{ 'border-primary bg-accent': selectedTrace?.trace_id === trace.trace_id }"
            @click="selectTrace(trace)"
          >
            <div class="flex items-center justify-between gap-3"><span class="truncate font-medium">{{ trace.query }}</span><span class="shrink-0 text-xs text-muted-foreground">{{ trace.latency_ms }} ms</span></div>
            <div class="mt-1 text-xs text-muted-foreground">KB {{ trace.knowledge_base_id ?? '自动' }} · {{ trace.results.length }} 条结果 · {{ trace.routes[0]?.selected_channels?.join(' / ') || '未知通道' }}</div>
          </button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>检索详情</CardTitle><CardDescription>路由策略、候选来源与片段预览。</CardDescription></CardHeader>
        <CardContent>
          <div v-if="!selectedTrace" class="py-8 text-center text-muted-foreground">请选择左侧的一条检索记录。</div>
          <div v-else class="space-y-4">
            <div class="rounded-lg bg-muted p-3 text-sm"><strong>路由：</strong>{{ selectedTrace.routes.map(route => `${route.query_type || 'general'} / ${route.strategy || 'adaptive'}`).join('，') }}<br><strong>重写次数：</strong>{{ selectedTrace.rewrite_count }} · <strong>Top K：</strong>{{ selectedTrace.top_k }}</div>
            <div v-for="(result, index) in selectedTrace.results" :key="`${result.document_id}-${index}`" class="rounded-lg border p-3">
              <div class="flex justify-between gap-3 text-sm"><span class="font-medium">文档 {{ result.document_id ?? '图谱实体' }}</span><span class="text-muted-foreground">{{ result.source }} · {{ result.score.toFixed(4) }}</span></div>
              <p class="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{{ result.content_preview }}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>

    <Card>
      <CardHeader><CardTitle class="flex items-center gap-2"><BarChart3 class="h-5 w-5" />快速检索评测</CardTitle><CardDescription>输入一个问题和正确应命中的文档 ID，得到当前知识库的检索指标。</CardDescription></CardHeader>
      <CardContent class="space-y-4">
        <div class="grid gap-4 md:grid-cols-3">
          <label class="space-y-1 text-sm">知识库 ID（可选）<input v-model.number="knowledgeBaseId" type="number" min="1" class="w-full rounded-md border bg-background px-3 py-2" placeholder="例如：1" /></label>
          <label class="space-y-1 text-sm">Top K<input v-model.number="topK" type="number" min="1" max="20" class="w-full rounded-md border bg-background px-3 py-2" /></label>
          <label class="space-y-1 text-sm">期望文档 ID（逗号分隔）<input v-model="expectedDocumentIds" class="w-full rounded-md border bg-background px-3 py-2" placeholder="例如：12,15" /></label>
        </div>
        <label class="block space-y-1 text-sm">测试问题<textarea v-model="evaluationQuery" rows="3" class="w-full rounded-md border bg-background px-3 py-2" placeholder="例如：RAG 的检索流程是什么？" /></label>
        <Button :disabled="evaluating" @click="submitEvaluation"><Send class="mr-2 h-4 w-4" />{{ evaluating ? '评测中...' : '运行评测' }}</Button>
        <div v-if="evaluationReport" class="grid gap-3 rounded-lg bg-muted p-4 md:grid-cols-3"><div>Precision@{{ evaluationReport.summary.top_k }}<p class="text-xl font-bold">{{ evaluationReport.summary.precision_at_k }}</p></div><div>Recall@{{ evaluationReport.summary.top_k }}<p class="text-xl font-bold">{{ evaluationReport.summary.recall_at_k }}</p></div><div>MRR<p class="text-xl font-bold">{{ evaluationReport.summary.mean_reciprocal_rank }}</p></div></div>
      </CardContent>
    </Card>
  </div>
</template>
