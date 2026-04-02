import { get, post } from './request'
import type { ApiResponse } from './types'

// ── Plugin Types ──────────────────────────────────────────────────────

export interface PluginEntry {
  id: number
  pluginId: string
  name: string
  displayName: string | null
  description: string | null
  version: string
  author: string | null
  authorEmail: string | null
  license: string | null
  minHfusionhubVersion: string | null
  maxHfusionhubVersion: string | null
  iconUrl: string | null
  source: 'local' | 'git' | 'wheel'
  status: 'active' | 'disabled' | 'failed' | 'pending'
  manifestHash: string | null
  artifactPath: string | null
  artifactHash: string | null
  sandboxConfig: string | null
  permissions: string | null
  enabled: boolean
  installedBy: number | null
  installedAt: string | null
  createdAt: string
  updatedAt: string
}

export interface PluginAuditLog {
  id: number
  pluginName: string
  action: string
  operatorId: number | null
  oldValue: string | null
  newValue: string | null
  reason: string | null
  createdAt: string
}

export interface PluginListResponse {
  records: PluginEntry[]
  total: number
  page: number
  pageSize: number
}

// ── API ────────────────────────────────────────────────────────────────

/** 分页查询已安装插件 */
export const listPlugins = (page = 1, pageSize = 20, status?: string): Promise<ApiResponse<PluginListResponse>> =>
  get('/plugin/list', { page, pageSize, ...(status && status !== 'all' ? { status } : {}) })

/** 获取插件详情 */
export const getPlugin = (pluginId: string): Promise<ApiResponse<PluginEntry>> =>
  get(`/plugin/${pluginId}`)

/** 查询所有已启用插件 */
export const listEnabledPlugins = (): Promise<ApiResponse<PluginEntry[]>> =>
  get('/plugin/enabled')

/** 安装插件 */
export const installPlugin = (manifest: Record<string, unknown>): Promise<ApiResponse<PluginEntry>> =>
  post('/plugin/install', manifest)

/** 启用插件 */
export const enablePlugin = (pluginId: string): Promise<ApiResponse<PluginEntry>> =>
  post(`/plugin/${pluginId}/enable`)

/** 禁用插件 */
export const disablePlugin = (pluginId: string, reason?: string): Promise<ApiResponse<PluginEntry>> =>
  post(`/plugin/${pluginId}/disable`, reason ? { reason } : {})

/** 卸载插件 */
export const uninstallPlugin = (pluginId: string, reason?: string): Promise<ApiResponse<void>> =>
  post(`/plugin/${pluginId}/uninstall`, reason ? { reason } : {})

/** 获取插件审计日志 */
export const getPluginAuditLogs = (pluginId: string, limit = 20): Promise<ApiResponse<PluginAuditLog[]>> =>
  get(`/plugin/${pluginId}/audit-logs`, { limit })
