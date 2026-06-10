import { get, post, put, del } from './request'
import type { ApiResponse, PageResult } from './types'

/** Webhook 订阅 */
export interface WebhookSubscription {
  id: number
  userId: number
  name: string
  url: string
  secret?: string
  events: string[]
  isActive: number
  lastTriggeredAt?: string
  failureCount?: number
  createdAt?: string
  updatedAt?: string
}

/** Webhook 投递记录 */
export interface WebhookDelivery {
  id: number
  subscriptionId: number
  eventType: string
  payload?: string
  responseStatus?: number
  responseBody?: string
  durationMs?: number
  success?: number
  createdAt?: string
}

/** 平台支持的事件类型（与 Java WebhookEventTypes 对齐） */
export const WEBHOOK_EVENTS: Array<{ value: string; label: string; description: string }> = [
  { value: 'agent.task.completed', label: 'Agent 任务完成', description: 'Agent 任务执行成功时通知' },
  { value: 'agent.task.failed', label: 'Agent 任务失败', description: 'Agent 任务失败或超时时通知' },
  { value: 'agent.approval.required', label: '等待人工确认', description: 'Agent 请求执行敏感操作等待审批时通知' },
  { value: 'document.indexed', label: '文档索引完成', description: '文档解析并向量化完成时通知' },
  { value: 'evaluation.completed', label: '评测完成', description: '回答质量评测运行结束时通知' },
]

export const webhookEventLabel = (value: string): string =>
  WEBHOOK_EVENTS.find(e => e.value === value)?.label || value

/** 当前用户的订阅列表 */
export const listSubscriptions = (): Promise<ApiResponse<WebhookSubscription[]>> =>
  get('/webhook')

/** 创建订阅 */
export const createSubscription = (
  data: Pick<WebhookSubscription, 'name' | 'url' | 'events'> & { secret?: string },
): Promise<ApiResponse<WebhookSubscription>> => post('/webhook', data)

/** 更新订阅 */
export const updateSubscription = (
  id: number,
  data: Partial<Pick<WebhookSubscription, 'name' | 'url' | 'events' | 'secret'>>,
): Promise<ApiResponse<WebhookSubscription>> => put(`/webhook/${id}`, data)

/** 删除订阅 */
export const deleteSubscription = (id: number): Promise<ApiResponse<void>> =>
  del(`/webhook/${id}`)

/** 启停订阅 */
export const setActive = (id: number, active: boolean): Promise<ApiResponse<WebhookSubscription>> =>
  put(`/webhook/${id}/active`, { active })

/** 同步测试触发一次投递 */
export const testFire = (id: number): Promise<ApiResponse<WebhookDelivery>> =>
  post(`/webhook/${id}/test`)

/** 投递历史（分页） */
export const listDeliveries = (
  id: number,
  params?: { page?: number; pageSize?: number },
): Promise<ApiResponse<PageResult<WebhookDelivery>>> =>
  get(`/webhook/${id}/deliveries`, params)
