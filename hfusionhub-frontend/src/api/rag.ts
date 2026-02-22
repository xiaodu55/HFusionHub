import { get, post } from './request'

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
  error_only?: boolean
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

const toJavaQueryParams = (params: TraceFilters) => {
  const { knowledge_base_id, ...rest } = params
  return {
    ...rest,
    knowledgeBaseId: knowledge_base_id,
  }
}

export const getTraces = (params: TraceFilters) =>
  get<{ data: { traces: RetrievalTrace[], total: number } }>('/rag/traces', {
    limit: 50,
    offset: 0,
    ...toJavaQueryParams(params),
  })

export const getTraceStats = (days: number, knowledgeBaseId: number) =>
  get<{ data: TraceStats }>('/rag/traces/stats', { days, knowledgeBaseId })

export const exportTraces = (format: 'json' | 'csv', filters: Omit<TraceFilters, 'limit' | 'offset'>) =>
  get<{ data: TraceExport }>('/rag/traces/export', {
    format,
    ...toJavaQueryParams(filters),
  })

export const evaluateRetrieval = (data: {
  knowledge_base_id: number
  top_k: number
  label?: string
  cases: EvaluationCaseInput[]
}) => post<{ data: EvaluationReport }>('/rag/evaluate', data)

export const getEvaluationRuns = (params: { limit?: number, knowledge_base_id: number }) =>
  get<{ data: { runs: EvaluationRun[] } }>('/rag/evaluation-runs', {
    limit: params.limit,
    knowledgeBaseId: params.knowledge_base_id,
  })
