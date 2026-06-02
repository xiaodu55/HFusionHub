import { del, get, post, put } from './request'
import type { ApiResponse } from './types'

/** 投标模块开关键（与 bid_subscription.module_flags 对齐） */
export type BidModule = 'draft' | 'check' | 'docx' | 'openapi'

export const BID_MODULE_LABELS: Record<BidModule, string> = {
  draft: '标书撰写',
  check: '废标自检',
  docx: '标书导出',
  openapi: '投标开放 API',
}

/** 订阅套餐（平台目录 / 租户自定义） */
export interface BidSubscription {
  id: number
  tenantId?: number | null
  planCode: string
  planName: string
  planType: 'tier' | 'industry'
  priceCents: number
  maxProjects: number
  maxSeats: number
  charQuota: number
  moduleFlags: string
  status: 'active' | 'archived'
  createdAt?: string
}

/** 租户套餐绑定视图 */
export interface PlanBinding {
  bindingId: number
  subscriptionId: number
  planCode: string
  planName: string
  planType: 'tier' | 'industry'
  priceCents: number
  maxProjects: number
  maxSeats: number
  charQuota: number
  moduleFlags: string
  status: 'active' | 'expired' | 'canceled'
  startAt?: string
  endAt?: string
}

/** 模块生效状态（套餐授权 ∩ 平台开关） */
export type ModuleStatus = Record<BidModule, boolean>

/** 当前租户套餐概览 */
export interface PlanCurrent {
  tier: string
  modules: ModuleStatus
  bindings: PlanBinding[]
}

/** 标书模板（平台级 + 租户自有） */
export interface BidTemplate {
  id: number
  tenantId?: number | null
  name: string
  description?: string
  industry?: string
  sectionDefs: string
  isActive: number
  createdAt?: string
}

/** 解析 module_flags JSON（值可能为 0/1 或 true/false） */
export function parseModuleFlags(raw: string | null | undefined): Record<string, boolean> {
  try {
    const parsed = raw ? JSON.parse(raw) : {}
    return Object.fromEntries(
      Object.entries(parsed).map(([key, value]) => [key, Boolean(value)]),
    )
  } catch {
    return {}
  }
}

/** 金额：分 → 元展示 */
export function formatCents(cents: number | null | undefined): string {
  if (cents == null) return '—'
  return `¥${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}`
}

// ── 套餐目录 / 绑定 ───────────────────────────────────────────────

/** 平台内置套餐目录（供租户选购） */
export const listPlatformPlans = (): Promise<ApiResponse<BidSubscription[]>> =>
  get('/bid/plan/catalog')

/** 当前租户套餐概览（tier + 模块生效状态 + 有效绑定） */
export const getPlanCurrent = (): Promise<ApiResponse<PlanCurrent>> =>
  get('/bid/plan/current')

/** 绑定套餐 */
export const bindPlan = (subscriptionId: number): Promise<ApiResponse<PlanBinding>> =>
  post('/bid/plan/bind', null, { params: { subscriptionId } })

/** 解绑套餐 */
export const unbindPlan = (subscriptionId: number): Promise<ApiResponse<void>> =>
  post('/bid/plan/unbind', null, { params: { subscriptionId } })

// ── 平台管理员套餐管理 ─────────────────────────────────────────────

export const listAllPlans = (): Promise<ApiResponse<BidSubscription[]>> =>
  get('/bid/plan/admin')

export const createPlan = (payload: Partial<BidSubscription>): Promise<ApiResponse<BidSubscription>> =>
  post('/bid/plan/admin', payload)

export const updatePlan = (payload: Partial<BidSubscription>): Promise<ApiResponse<void>> =>
  put('/bid/plan/admin', payload)

export const archivePlan = (id: number): Promise<ApiResponse<void>> =>
  del(`/bid/plan/admin/${id}`)

// ── 模板商城 ──────────────────────────────────────────────────────

/** 模板列表（平台级 + 本租户自有，可按行业过滤） */
export const listBidTemplates = (industry?: string): Promise<ApiResponse<BidTemplate[]>> =>
  get('/bid/template/list', { industry })

/** 模板详情 */
export const getBidTemplate = (id: number): Promise<ApiResponse<BidTemplate>> =>
  get(`/bid/template/${id}`)

/** 新建租户私有模板 */
export const createBidTemplate = (payload: Partial<BidTemplate>): Promise<ApiResponse<BidTemplate>> =>
  post('/bid/template', payload)

/** 更新自有模板 */
export const updateBidTemplate = (payload: Partial<BidTemplate>): Promise<ApiResponse<void>> =>
  put('/bid/template', payload)

/** 归档自有模板 */
export const archiveBidTemplate = (id: number): Promise<ApiResponse<void>> =>
  del(`/bid/template/${id}`)
