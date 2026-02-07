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
  average_latency_ms: number
  result_source_counts: Record<string, number>
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
}

export const getTraces = (limit = 50) =>
  get<{ data: { traces: RetrievalTrace[] } }>('/rag/traces', { limit })

export const getTraceStats = () =>
  get<{ data: TraceStats }>('/rag/traces/stats')

export const evaluateRetrieval = (data: {
  knowledge_base_id?: number
  top_k: number
  cases: EvaluationCaseInput[]
}) => post<{ data: EvaluationReport }>('/rag/evaluate', data)
