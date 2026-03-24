import { get } from './request'
import type { ApiResponse } from './types'

export type RuntimeState = 'ready' | 'configured' | 'development' | 'reachable' | 'unavailable' | 'not_configured'

export interface RuntimeComponent {
  provider: string | null
  provider_label: string
  model: string | null
  dimension?: number
  state: RuntimeState
  detail: string
}

export interface RuntimeProvider {
  id: string
  label: string
  purpose: string
  model?: string
  configured: boolean
  reachable?: boolean
  model_available?: boolean
  state: RuntimeState
}

export interface AiRuntimeOverview {
  status: 'ready' | 'degraded' | 'unavailable'
  generated_at?: string
  gateway_reachable?: boolean
  detail?: string
  llm?: RuntimeComponent
  embedding?: RuntimeComponent
  vector_store?: {
    ready: boolean
    collection?: string | null
    collection_exists?: boolean | null
    detail: string
  }
  providers?: RuntimeProvider[]
  features?: {
    hybrid_retrieval: boolean
    graph_retrieval: boolean
    reranker: string
    agent_workflow: boolean
    multi_agent: boolean
  }
}

export const getAiRuntimeOverview = (): Promise<ApiResponse<AiRuntimeOverview>> =>
  get('/system/ai-runtime')
