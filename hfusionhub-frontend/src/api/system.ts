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

export interface ModelGatewayProvider {
  provider: string
  type: string
  enabled: boolean
  available: boolean
  circuit: 'closed' | 'open' | 'half_open'
  failure_count: number
  total_failures: number
  total_successes: number
  cooldown_remaining_seconds?: number | null
  rate_limit_tokens_remaining?: number | null
  model_count: number
}

export interface ModelGatewayHealth {
  gateway_enabled: boolean
  failover_enabled: boolean
  cost_tracking_enabled?: boolean
  providers: ModelGatewayProvider[]
  error?: string
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
  model_gateway?: ModelGatewayHealth
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
