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
export const publishPromptTemplate = (id: number): Promise<ApiResponse<PromptTemplate>> => post(`/prompt-templates/${id}/publish`)
export const unpublishPromptTemplate = (id: number): Promise<ApiResponse<PromptTemplate>> => post(`/prompt-templates/${id}/unpublish`)
export const deletePromptTemplate = (id: number): Promise<ApiResponse<void>> => del(`/prompt-templates/${id}`)

/** List all version snapshots for a template, newest first. */
export const listPromptTemplateVersions = (id: number): Promise<ApiResponse<PromptTemplateVersion[]>> =>
  get(`/prompt-templates/${id}/versions`)

/** Rollback to a specific version snapshot (by its id). Returns the updated template (new version, DRAFT status). */
export const rollbackPromptTemplate = (id: number, versionId: number): Promise<ApiResponse<PromptTemplate>> =>
  post(`/prompt-templates/${id}/rollback/${versionId}`)
