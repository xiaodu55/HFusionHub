import { get, post } from './request'
import type { ApiResponse } from './types'

export interface RetrievalTraceResult {
  document_id: string | number | null
  score: number
  source: string
  content_preview: string
  outline_path: string[]
}

export interface RetrievalTraceRoute {
  query: string
  query_type?: string
  strategy?: string
  confidence?: number
  selected_channels?: string[]
}

export interface RetrievalTrace {
  trace_id: string
  created_at: string
  query: string
  knowledge_base_id: number | null
  top_k: number
  rewrite_count: number
  latency_ms: number
  error: string | null
  routes: RetrievalTraceRoute[]
  results: RetrievalTraceResult[]
}

export interface TraceStats {
  total_traces: number
  failed_traces: number
  hit_traces: number
  hit_rate: number
  average_latency_ms: number
  result_source_counts: Record<string, number>
  recent_failures: Array<{
    trace_id: string
    created_at: string
    query: string
    knowledge_base_id: number | null
    latency_ms: number
    error: string | null
    top_k: number
  }>
  daily_metrics: TraceDailyMetric[]
  window_days: number
}

export interface TraceDailyMetric {
  date: string
  total_traces: number
  failed_traces: number
  hit_traces: number
  hit_rate: number
  average_latency_ms: number
}

export interface TraceFilters {
  limit?: number
  offset?: number
  knowledge_base_id: number
  errorOnly?: boolean
  query?: string
  source?: string
}

export interface TraceExport {
  filename: string
  mime_type: string
  content: string
}

export interface EvaluationCaseInput {
  case_id?: string
  query: string
  expected_document_ids: string[]
}

export interface EvaluationSummary {
  case_count: number
  top_k: number
  precision_at_k: number
  recall_at_k: number
  mean_reciprocal_rank: number
}

export interface EvaluationReport {
  summary: EvaluationSummary
  cases: Array<{
    case_id?: string
    query: string
    retrieved_document_ids: string[]
    expected_document_ids: string[]
    precision_at_k: number
    recall_at_k: number
    reciprocal_rank: number
  }>
  run?: EvaluationRun
}

export interface EvaluationRun {
  run_id: string
  created_at: string
  knowledge_base_id: number | null
  label: string | null
  top_k: number
  case_count: number
  precision_at_k: number
  recall_at_k: number
  mean_reciprocal_rank: number
  failed_case_ids: string[]
}

export interface AnswerFeedback {
  id: number
  conversationId: number
  messageId: number
  rating: 'UP' | 'DOWN'
  reason?: string
  expectedAnswer?: string
  evaluationCaseId?: number
}

const toJavaQueryParams = (params: TraceFilters) => {
  const { knowledge_base_id, ...rest } = params
  return {
    ...rest,
    knowledgeBaseId: knowledge_base_id,
  }
}

export const getTraces = (params: TraceFilters): Promise<ApiResponse<{ traces: RetrievalTrace[], total: number }>> =>
  get('/rag/traces', {
    limit: 50,
    offset: 0,
    ...toJavaQueryParams(params),
  })

export const getTraceStats = (days: number, knowledgeBaseId: number): Promise<ApiResponse<TraceStats>> =>
  get('/rag/traces/stats', { days, knowledgeBaseId })

export const exportTraces = (format: 'json' | 'csv', filters: Omit<TraceFilters, 'limit' | 'offset'>): Promise<ApiResponse<TraceExport>> =>
  get('/rag/traces/export', {
    format,
    ...toJavaQueryParams(filters),
  })

export const evaluateRetrieval = (data: {
  knowledge_base_id: number
  top_k: number
  label?: string
  cases: EvaluationCaseInput[]
}): Promise<ApiResponse<EvaluationReport>> => post('/rag/evaluate', data)

export const getEvaluationRuns = (params: { limit?: number, knowledge_base_id: number }): Promise<ApiResponse<{ runs: EvaluationRun[] }>> =>
  get('/rag/evaluation-runs', {
    limit: params.limit,
    knowledgeBaseId: params.knowledge_base_id,
  })

export const saveAnswerFeedback = (data: {
  messageId: number
  rating: 'UP' | 'DOWN'
  reason?: string
  expectedAnswer?: string
}): Promise<ApiResponse<AnswerFeedback>> => post('/rag/feedback', data)

export const getAnswerFeedback = (conversationId: number): Promise<ApiResponse<AnswerFeedback[]>> =>
  get('/rag/feedback', { conversationId })

export const evaluateProductionPath = (data: {
  query: string
  knowledge_base_id?: number
  top_k?: number
  conversation_history?: Array<Record<string, unknown>>
}): Promise<ApiResponse<Record<string, unknown>>> => post('/rag/eval', data)


// ── 评估中枢（eval_harness）：生成质量 / 行为红线 / TTFT / A/B 门禁 ──

export interface HarnessCase {
  query_id: string
  metrics: Record<string, number>
  skip_reason?: string | null
  flags?: string[]
}

export interface HarnessResult {
  run_file: string
  overall: Record<string, number>
  cases: HarnessCase[]
  meta: Record<string, any>
}

export interface HarnessRunFile {
  file: string
  size_bytes: number
  modified_at: string
}

export interface HarnessDiffRow {
  metric: string
  base: number | null
  candidate: number | null
  delta: number | null
  direction: 'higher' | 'lower'
  threshold: number | null
  verdict: 'improved' | 'regressed' | 'neutral' | 'missing_in_candidate'
}

/** 运行一次评估（同步；会真实驱动生产链路，耗时与并发配置相关） */
export const runHarnessEvaluation = (body: {
  label?: string
  knowledge_base_id: number
  top_k?: number
  dataset_name?: string
  samples?: Array<Record<string, any>>
  concurrency?: number
  enable_judge?: boolean
  judge_runs?: number
}): Promise<ApiResponse<{ run_file: string; summary: Record<string, number>; meta: Record<string, any> }>> =>
  post('/eval-harness/run', body)

/** 重放评分（不重打生产链路） */
export const scoreHarnessRun = (body: {
  run_file: string
  enable_judge?: boolean
  retrieval_k?: number
}): Promise<ApiResponse<{ scores_file: string; result: HarnessResult }>> =>
  post('/eval-harness/score', body)

/** 运行文件列表 */
export const listHarnessRuns = (): Promise<ApiResponse<{ runs: HarnessRunFile[] }>> =>
  get('/eval-harness/runs')

/** markdown 评估报告 */
export const getHarnessReport = (runFile: string): Promise<ApiResponse<{ run_file: string; report: string }>> =>
  get('/eval-harness/report', { run_file: runFile })

/** A/B 回归门禁对比 */
export const diffHarnessRuns = (body: {
  base_run: string
  candidate_run: string
}): Promise<ApiResponse<{ base_run: string; candidate_run: string; rows: HarnessDiffRow[]; has_regression: boolean }>> =>
  post('/eval-harness/diff', body)

/** 数据集白名单 */
export const listHarnessDatasets = (): Promise<ApiResponse<{ datasets: string[] }>> =>
  get('/eval-harness/datasets')

/** 自包含 HTML 幻灯片（原文） */
export const getHarnessSlides = (runFile: string): Promise<ApiResponse<{ run_file: string; html: string }>> =>
  get('/eval-harness/slides', { run_file: runFile })
