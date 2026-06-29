import { get } from './request'
import type { ApiResponse } from './types'

export interface CostSummary {
  totalCost: number
  totalTokens: number
  totalRequests: number
  currentMonthCost: number
  estimatedMonthCost: number
}

export interface DailyCost {
  statDate: string
  requestCount: number
  totalTokens: number
  totalCost: number
  avgLatencyMs: number
}

export interface ModelBreakdown {
  model: string
  requestCount: number
  totalTokens: number
  totalCost: number
}

export interface TenantCostSummary {
  tenantId: number
  tenantName: string
  totalCost: number
  totalTokens: number
  userCount: number
}

export const getCostSummary = (days = 30): Promise<ApiResponse<CostSummary>> =>
  get('/cost/summary', { days })

export const getDailyCosts = (days = 30): Promise<ApiResponse<DailyCost[]>> =>
  get('/cost/daily', { days })

export const getModelBreakdown = (days = 30): Promise<ApiResponse<ModelBreakdown[]>> =>
  get('/cost/models', { days })

export const getTenantCost = (tenantId: number): Promise<ApiResponse<TenantCostSummary>> =>
  get(`/cost/tenant/${tenantId}`)
