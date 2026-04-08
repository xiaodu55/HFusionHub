import { get } from './request'

export interface CostSummary {
  totalCost: number
  totalTokens: number
  totalRequests: number
  avgCostPerRequest: number
  projectedMonthlyCost: number
}

export interface DailyCost {
  date: string
  cost: number
  tokens: number
  requests: number
}

export interface ModelBreakdown {
  model: string
  cost: number
  tokens: number
  percentage: number
}

export interface TenantCostSummary {
  tenantId: number
  tenantName: string
  totalCost: number
  totalTokens: number
  userCount: number
}

export const getCostSummary = (days = 30) =>
  get<{ data: CostSummary }>('/cost/summary', { days })

export const getDailyCosts = (days = 30) =>
  get<{ data: DailyCost[] }>('/cost/daily', { days })

export const getModelBreakdown = (days = 30) =>
  get<{ data: ModelBreakdown[] }>('/cost/models', { days })

export const getTenantCost = (tenantId: number) =>
  get<{ data: TenantCostSummary }>(`/cost/tenant/${tenantId}`)
