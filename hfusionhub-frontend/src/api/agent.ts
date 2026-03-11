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

export interface AgentStatusEvent { id: number; eventType: string; status?: string; message?: string; createdAt: string }
export interface AgentTaskDetail extends AgentTaskSummary { userId: number; conversationId?: number; knowledgeBaseId?: number; runs?: any[]; steps?: any[] }
export interface AgentMetrics { taskId?: number; runId?: number; status?: string; durationMs?: number; tokenCount?: number; toolCallsCount?: number; error?: string }

export const listTasks = (params?: { status?: string; page?: number; pageSize?: number }): Promise<ApiResponse<PageResult<AgentTaskSummary>>> => get('/agent-task/list', params)
export const getTask = (id: number): Promise<ApiResponse<AgentTaskDetail>> => get(`/agent-task/${id}`)
export const getTaskStatus = (id: number): Promise<ApiResponse<any>> => get(`/agent-task/${id}/status`)
export const getTaskEvents = (id: number, sinceId?: number): Promise<ApiResponse<AgentStatusEvent[]>> => get(`/agent-task/${id}/events`, { sinceId, limit: 200 })
export const retryTask = (id: number): Promise<ApiResponse<string>> => post(`/agent-task/${id}/retry`)
export const cancelTask = (id: number): Promise<ApiResponse<boolean>> => post(`/agent-task/${id}/cancel`)
export const getTaskMetrics = (id: number): Promise<ApiResponse<AgentMetrics>> => get(`/agent-observability/metrics/tasks/${id}`)
export const getDashboard = (): Promise<ApiResponse<Record<string, unknown>>> => get('/agent-observability/dashboard')
