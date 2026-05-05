import { get } from './request'
import type { ApiResponse } from './types'

/** 租户配额摘要（单计量项） */
export interface QuotaSummary {
  meter: string
  label: string
  unit: string
  committed: number
  reserved: number
  used: number
  dailyLimit: number
  remaining: number
  percent: number
}

/** 当前租户今日各计量项用量与日限额 */
export const getQuotaSummary = (): Promise<ApiResponse<QuotaSummary[]>> =>
  get('/quota/summary')
