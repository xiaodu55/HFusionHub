import { del, get, post, put } from './request'
import type { ApiResponse, PageResult } from './types'

export interface AgentTaskSummary {
  id: number
  requestId: string
  query: string
  status: string
  currentRunId?: number
  createdAt: string
  updatedAt: string
}

export interface AgentStatusEvent {
  id: number
  taskId?: number
  runId?: number
  eventType: string
  status?: string
  payload?: unknown
  createdAt: string
}

export interface AgentStep {
  id: number
  runId?: number
  sequence?: number
  stepType?: string
  action?: string
  inputSummary?: string
  outputSummary?: string
  durationMs?: number
  errorCode?: string
  createdAt?: string
}

export interface AgentRun {
  id: number
  taskId?: number
  runUuid?: string
  attemptNumber?: number
  status?: string
  scheduledAt?: string
  startedAt?: string
  completedAt?: string
  durationMs?: number
  model?: string
  style?: string
  maxToolSteps?: number
  toolCallsCount?: number
  errorCode?: string
  errorDetail?: string
  failedTool?: string
  steps?: AgentStep[]
}

export interface AgentTaskDetail extends AgentTaskSummary {
  userId: number
  conversationId?: number
  knowledgeBaseId?: number
  deadLetterReason?: string
  deadLetterAt?: string
  runs?: AgentRun[]
}

export interface AgentMetrics {
  taskId?: number
  runId?: number
  runUuid?: string
  status?: string
  totalDurationMs?: number
  avgStepLatencyMs?: number
  maxStepLatencyMs?: number
  totalTokens?: number
  promptTokens?: number
  completionTokens?: number
  toolCallsCount?: number
  sourcesCount?: number
  stepCount?: number
  approvalCount?: number
  avgApprovalDurationMs?: number
  errorCode?: string
  errorDetail?: string
  failedTool?: string
  model?: string
  style?: string
  maxToolSteps?: number
  tokenUsage?: Record<string, unknown>
}

export interface AgentAlertEvent {
  id: number
  ruleId?: number
  ruleName?: string
  knowledgeBaseId?: number
  severity?: 'critical' | 'warning' | 'info' | string
  metricName?: string
  currentValue?: number
  thresholdValue?: number
  message?: string
  resolved?: boolean
  createdAt?: string
}

export const listTasks = (params?: { status?: string; page?: number; pageSize?: number }): Promise<ApiResponse<PageResult<AgentTaskSummary>>> => get('/agent-task/list', params)
export const getTask = (id: number): Promise<ApiResponse<AgentTaskDetail>> => get(`/agent-task/${id}`)
export const getTaskStatus = (id: number): Promise<ApiResponse<any>> => get(`/agent-task/${id}/status`)
export const getTaskEvents = (id: number, sinceId?: number): Promise<ApiResponse<AgentStatusEvent[]>> => get(`/agent-task/${id}/events`, { sinceId, limit: 200 })
export const retryTask = (id: number): Promise<ApiResponse<string>> => post(`/agent-task/${id}/retry`)
export const cancelTask = (id: number): Promise<ApiResponse<boolean>> => post(`/agent-task/${id}/cancel`)
export const getTaskMetrics = (id: number): Promise<ApiResponse<AgentMetrics>> => get(`/agent-observability/metrics/tasks/${id}`)
export const getDashboard = (): Promise<ApiResponse<Record<string, unknown>>> => get('/agent-observability/dashboard')
export const getUnresolvedAlerts = (): Promise<ApiResponse<AgentAlertEvent[]>> => get('/agent-observability/alerts/events/unresolved')
export const resolveAlert = (id: number): Promise<ApiResponse<string>> => post(`/agent-observability/alerts/events/${id}/resolve`)
