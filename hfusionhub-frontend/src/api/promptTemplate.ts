import { del, get, post, put } from './request'
import type { ApiResponse } from './types'

export type PromptTemplateStatus = 'DRAFT' | 'PUBLISHED'

export interface PromptTemplate {
  id: number
  name: string
  description?: string | null
  content: string
  status: PromptTemplateStatus
  version: number
  createdAt: string
  updatedAt: string
}

export interface PromptTemplateSaveDTO {
  name: string
  description?: string
  content: string
  /** 客户端当前持有的版本号，用于并发修改保护 */
  expectedVersion?: number
}

// ── Version history ───────────────────────────────────────────────────

export type VersionOperation = 'CREATE' | 'EDIT' | 'PUBLISH' | 'UNPUBLISH' | 'ROLLBACK'

export interface PromptTemplateVersion {
  id: number
  version: number
  name: string
  description?: string | null
  content: string
  status: PromptTemplateStatus
  operation: VersionOperation
  operatorId: number
  createdAt: string
}

// ── API ──────────────────────────────────────────────────────────────

export const listPromptTemplates = (): Promise<ApiResponse<PromptTemplate[]>> => get('/prompt-templates')
export const createPromptTemplate = (data: PromptTemplateSaveDTO): Promise<ApiResponse<PromptTemplate>> => post('/prompt-templates', data)
export const updatePromptTemplate = (id: number, data: PromptTemplateSaveDTO): Promise<ApiResponse<PromptTemplate>> => put(`/prompt-templates/${id}`, data)
export const publishPromptTemplate = (id: number, expectedVersion: number): Promise<ApiResponse<PromptTemplate>> => post(`/prompt-templates/${id}/publish`, null, { params: { expectedVersion } })
export const unpublishPromptTemplate = (id: number, expectedVersion: number): Promise<ApiResponse<PromptTemplate>> => post(`/prompt-templates/${id}/unpublish`, null, { params: { expectedVersion } })
export const deletePromptTemplate = (id: number): Promise<ApiResponse<void>> => del(`/prompt-templates/${id}`)

/** List all version snapshots for a template, newest first. */
export const listPromptTemplateVersions = (id: number): Promise<ApiResponse<PromptTemplateVersion[]>> =>
  get(`/prompt-templates/${id}/versions`)

/** Rollback to a specific version snapshot (by its id). Returns the updated template (new version, DRAFT status). */
export const rollbackPromptTemplate = (id: number, versionId: number, expectedVersion: number): Promise<ApiResponse<PromptTemplate>> =>
  post(`/prompt-templates/${id}/rollback/${versionId}`, null, { params: { expectedVersion } })
