import { get, post, put, del } from './request'
import type { ApiResponse } from './types'

/** 应用（对外发布 Agent） */
export interface AppInfo {
  id: number
  name: string
  description?: string
  knowledgeBaseId?: number
  knowledgeBaseName?: string
  promptTemplateId?: number
  model?: string
  style: 'concise' | 'detailed' | 'report'
  status: number // 0 草稿, 1 已发布, 2 已停用
  apiKeyCount: number
  createdAt: string
}

/** 应用创建/更新入参 */
export interface AppInput {
  name: string
  description?: string
  knowledgeBaseId?: number
  promptTemplateId?: number
  model?: string
  style: 'concise' | 'detailed' | 'report'
}

/** API Key 信息 */
export interface AppApiKeyInfo {
  id: number
  appId: number
  name?: string
  keyPrefix: string
  secret?: string // 仅创建时返回一次
  enabled: number
  createdAt: string
}

export const createApp = (input: AppInput): Promise<ApiResponse<AppInfo>> => post('/app', input)
export const listApps = (): Promise<ApiResponse<AppInfo[]>> => get('/app')
export const getApp = (id: number): Promise<ApiResponse<AppInfo>> => get(`/app/${id}`)
export const updateApp = (id: number, input: AppInput): Promise<ApiResponse<AppInfo>> => put(`/app/${id}`, input)
export const deleteApp = (id: number): Promise<ApiResponse<void>> => del(`/app/${id}`)
export const publishApp = (id: number): Promise<ApiResponse<AppInfo>> => post(`/app/${id}/publish`)
export const unpublishApp = (id: number): Promise<ApiResponse<AppInfo>> => post(`/app/${id}/unpublish`)
export const createApiKey = (appId: number, name?: string): Promise<ApiResponse<AppApiKeyInfo>> =>
  post(`/app/${appId}/api-keys`, { name })
export const listApiKeys = (appId: number): Promise<ApiResponse<AppApiKeyInfo[]>> =>
  get(`/app/${appId}/api-keys`)
export const deleteApiKey = (appId: number, keyId: number): Promise<ApiResponse<void>> =>
  del(`/app/${appId}/api-keys/${keyId}`)
