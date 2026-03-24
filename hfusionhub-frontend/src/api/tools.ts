import { get } from './request'
import type { ApiResponse } from './types'

// ── Tool Registry ──────────────────────────────────────────────────────

export interface ToolEntry {
  name: string
  description: string
  risk_level: 'read_only' | 'read_write' | 'external'
  risk_label: string
  timeout_seconds: number
  required_permissions: string[]
  agent_version: string
  status: 'active' | 'beta' | 'experimental' | 'unknown'
  input_schema: {
    properties: Record<string, { type: string; description?: string }>
    required: string[]
  }
}

export interface ToolRegistryResponse {
  tools: ToolEntry[]
  total: number
  risk_summary?: {
    read_only: number
    read_write: number
    external: number
  }
  notice?: string
}

// ── Tool Call Record ───────────────────────────────────────────────────

export interface ToolCallTaskContext {
  id: number
  query: string
  status: string
}

export interface ToolCallRecord {
  id: number
  tool_name: string
  duration_ms: number | null
  success: boolean
  error_code: string | null
  error_summary: string | null
  task: ToolCallTaskContext
  created_at: string
}

export interface ToolCallsResponse {
  calls: ToolCallRecord[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

// ── API ────────────────────────────────────────────────────────────────

/** 获取完整工具注册表（元数据来自 Python Tool Registry） */
export const getToolRegistry = (): Promise<ApiResponse<ToolRegistryResponse>> =>
  get('/tools')

/** 获取最近工具调用记录（分页，来自 agent_step 表） */
export const getToolCalls = (page = 1, pageSize = 20): Promise<ApiResponse<ToolCallsResponse>> =>
  get('/tools/calls', { page, pageSize })
