import { get, post } from './request'
import type { ApiResponse } from './types'

/** HFusionData Analytics — 运营数仓大屏接口(分析扩展包) */

export interface AnalyticsOverview {
  days: number
  totalCalls: number
  totalTokens: number
  totalCostUsd: number
  realtime: {
    windowMinutes: number
    requests: number
    costUsd: number
    avgLatencyMs: number
  }
}

export interface AnalyticsCostDaily {
  tenantId: number
  statDate: string
  callCount: number
  totalTokens: number
  costUsd: number
  estMonthCost: number | null
}

export interface AnalyticsModelShare {
  tenantId: number
  model: string
  statDate: string
  callCount: number
  costUsd: number
  costShare: number
}

export interface AnalyticsToolSuccess {
  tenantId: number
  stepType: string
  statDate: string
  stepCount: number
  errorCount: number
  successRate: number
}

export interface AnalyticsEvalQuality {
  tenantId: number
  statDate: string
  evalCount: number
  avgHitRatio: number | null
  avgLatencyMs: number | null
  failureRate: number
}

export interface AnalyticsRealtimeMetric {
  tenantId: number
  model: string
  windowStart: string
  windowEnd: string
  requestCount: number
  totalTokens: number
  totalCost: number
  avgLatencyMs: number
  maxLatencyMs: number
}

export interface BatchTriggerResult {
  date: string
  stepLogIds: number[]
}

export const getOverview = (days = 7): Promise<ApiResponse<AnalyticsOverview>> =>
  get('/analytics/overview', { days })

export const getCostDaily = (days = 7, tenantId?: number): Promise<ApiResponse<AnalyticsCostDaily[]>> =>
  get('/analytics/cost-daily', { days, tenantId })

export const getModelShare = (date?: string, tenantId?: number): Promise<ApiResponse<AnalyticsModelShare[]>> =>
  get('/analytics/model-share', { date, tenantId })

export const getToolSuccess = (days = 7, tenantId?: number): Promise<ApiResponse<AnalyticsToolSuccess[]>> =>
  get('/analytics/tool-success', { days, tenantId })

export const getEvalQuality = (days = 30, tenantId?: number): Promise<ApiResponse<AnalyticsEvalQuality[]>> =>
  get('/analytics/eval-quality', { days, tenantId })

export const getRealtime = (minutes = 60, tenantId?: number): Promise<ApiResponse<AnalyticsRealtimeMetric[]>> =>
  get('/analytics/realtime', { minutes, tenantId })

/** 手工回补指定日期的批处理管线(运维动作,内部令牌保护) */
export const triggerBatchRun = (date: string): Promise<ApiResponse<BatchTriggerResult>> =>
  post('/internal/analytics/batch/run', { date })
