import { get, post, upload } from './request'
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
  source: 'local' | 'git' | 'wheel' | 'builder'
  pluginKind: 'package' | 'declarative' | null
  toolSpecsJson: string | null
  status: 'active' | 'disabled' | 'failed' | 'pending' | 'circuit_open'
  manifestHash: string | null
  artifactPath: string | null
  artifactHash: string | null
  sandboxConfig: string | null
  permissions: string | null
  enabled: boolean
  installedBy: number | null
  installedAt: string | null
  canaryWeight: number | null
  circuitOpenUntil: string | null
  previousVersion: string | null
  healthStatus: string | null
  lastHealthCheck: string | null
  sbomJson: string | null
  vulnerabilityStatus: string | null
  lastScanAt: string | null
  containerImage: string | null
  createdAt: string
  updatedAt: string
}

export interface PluginAuditLog {
  id: number
  eventId: string | null
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

export interface DeclarativeToolInput {
  name: string
  display_name: string
  description: string
  example: string
  endpoint_url: string
  method: 'GET'
  timeout_seconds: number
  input_schema: {
    type: 'object'
    properties: Record<string, { type: 'string'; description: string }>
    required: string[]
  }
}

export interface DeclarativePluginInput {
  name: string
  display_name: string
  version: string
  description: string
  tools: DeclarativeToolInput[]
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

/** 安装插件（JSON manifest） */
export const installPlugin = (manifest: Record<string, unknown>): Promise<ApiResponse<PluginEntry>> =>
  post('/plugin/install', manifest)

/** 在网页中创建低代码插件和只读 HTTP GET 工具 */
export const createDeclarativePlugin = (manifest: DeclarativePluginInput): Promise<ApiResponse<PluginEntry>> =>
  post('/plugin/create', manifest)

/** 上传 wheel 文件并安装插件 */
export const installPluginWithWheel = (manifest: Record<string, unknown>, wheelFile: File): Promise<ApiResponse<PluginEntry>> => {
  const formData = new FormData()
  formData.append('manifest', new Blob([JSON.stringify(manifest)], { type: 'application/json' }))
  formData.append('wheel', wheelFile)
  return upload('/plugin/install/upload', formData)
}

/** 启用插件 */
export const enablePlugin = (pluginId: string): Promise<ApiResponse<PluginEntry>> =>
  post(`/plugin/${pluginId}/enable`)

/** 禁用插件 */
export const disablePlugin = (pluginId: string, reason?: string): Promise<ApiResponse<PluginEntry>> =>
  post(`/plugin/${pluginId}/disable`, reason ? { reason } : {})

/** 卸载插件 */
export const uninstallPlugin = (pluginId: string, reason?: string): Promise<ApiResponse<void>> =>
  post(`/plugin/${pluginId}/uninstall`, reason ? { reason } : {})

/** 设置金丝雀流量权重 */
export const setCanary = (pluginId: string, weight: number): Promise<ApiResponse<PluginEntry>> =>
  post(`/plugin/${pluginId}/canary`, { weight })

/** 提合金丝雀为正式版本 */
export const promoteCanary = (pluginId: string): Promise<ApiResponse<PluginEntry>> =>
  post(`/plugin/${pluginId}/canary/promote`)

/** 回滚到上一版本 */
export const rollbackPlugin = (pluginId: string): Promise<ApiResponse<PluginEntry>> =>
  post(`/plugin/${pluginId}/rollback`)

/** 获取插件审计日志 */
export const getPluginAuditLogs = (pluginId: string, limit = 20): Promise<ApiResponse<PluginAuditLog[]>> =>
  get(`/plugin/${pluginId}/audit-logs`, { limit })

/** 导出审计日志 */
export const exportAuditLogs = (pluginId?: string, format = 'json', limit = 100): Promise<ApiResponse<PluginAuditLog[]>> =>
  get('/plugin/audit-logs/export', { pluginId, format, limit })
