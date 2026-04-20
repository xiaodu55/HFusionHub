import { get, post, del } from './request'
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
  display_name?: string | null
  example?: string | null
  plugin_name?: string | null
  category?: 'knowledge' | 'utility' | 'external' | null
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

// ── MCP Client（B5）────────────────────────────────────────────────────

export interface McpServerInfo {
  id: string
  name: string
  url: string
  transport: 'sse' | 'streamable-http'
  status: 'connected' | 'disconnected' | 'error' | 'connecting'
  tool_count: number
  error_message?: string | null
}

export const listMcpServers = (): Promise<ApiResponse<{ servers: McpServerInfo[]; error?: string }>> =>
  get('/tools/mcp/servers')

export const addMcpServer = (input: {
  id: string
  name: string
  url: string
  transport: 'sse' | 'streamable-http'
  api_key?: string
}): Promise<ApiResponse<{ success: boolean; message?: string; server?: McpServerInfo }>> =>
  post('/tools/mcp/servers', input)

export const reconnectMcpServer = (serverId: string): Promise<ApiResponse<{ success: boolean; message?: string }>> =>
  post(`/tools/mcp/servers/${serverId}/reconnect`)

export const removeMcpServer = (serverId: string): Promise<ApiResponse<{ success: boolean; message?: string }>> =>
  del(`/tools/mcp/servers/${serverId}`)
