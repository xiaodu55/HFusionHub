import { del, get, post, put } from './request'
import type { ApiResponse } from './types'

// ── Types ────────────────────────────────────────────────────────────

export interface PromptTestSet {
  id: number
  name: string
  description?: string | null
  caseCount: number
  createdAt: string
  updatedAt: string
}

export interface PromptTestCase {
  id: number
  question: string
  variables?: Record<string, string | number | boolean> | null
  sortOrder: number
}

export interface PromptTestSetDetail {
  id: number
  name: string
  description?: string | null
  createdAt: string
  updatedAt: string
  cases: PromptTestCase[]
}

export interface PromptTestSetSaveDTO {
  name: string
  description?: string
}

export interface PromptTestCaseSaveDTO {
  question: string
  variables?: Record<string, string | number | boolean>
  sortOrder?: number
}

export interface PromptTestSetRunRequest {
  templateContent: string
  knowledgeBaseId?: number
}

export interface PromptTestCaseResult {
  caseId: number
  question: string
  renderedTemplate: string
  content?: string | null
  model?: string
  tokenCount: number
  tokenUsage?: Record<string, number> | null
  sources?: Array<Record<string, unknown>> | null
  elapsedMs: number
  success: boolean
  error?: string | null
}

export interface PromptTestSetRunResponse {
  setId: number
  totalCases: number
  successCount: number
  failureCount: number
  totalElapsedMs: number
  results: PromptTestCaseResult[]
}

// ── API ──────────────────────────────────────────────────────────────

export const listPromptTestSets = (): Promise<ApiResponse<PromptTestSet[]>> => get('/prompt-test-sets')
export const createPromptTestSet = (data: PromptTestSetSaveDTO): Promise<ApiResponse<PromptTestSetDetail>> =>
  post('/prompt-test-sets', data)
export const getPromptTestSet = (id: number): Promise<ApiResponse<PromptTestSetDetail>> => get(`/prompt-test-sets/${id}`)
export const updatePromptTestSet = (id: number, data: PromptTestSetSaveDTO): Promise<ApiResponse<PromptTestSetDetail>> =>
  put(`/prompt-test-sets/${id}`, data)
export const deletePromptTestSet = (id: number): Promise<ApiResponse<void>> => del(`/prompt-test-sets/${id}`)

export const addPromptTestCase = (setId: number, data: PromptTestCaseSaveDTO): Promise<ApiResponse<PromptTestCase>> =>
  post(`/prompt-test-sets/${setId}/cases`, data)
export const updatePromptTestCase = (setId: number, caseId: number, data: PromptTestCaseSaveDTO): Promise<ApiResponse<PromptTestCase>> =>
  put(`/prompt-test-sets/${setId}/cases/${caseId}`, data)
export const deletePromptTestCase = (setId: number, caseId: number): Promise<ApiResponse<void>> =>
  del(`/prompt-test-sets/${setId}/cases/${caseId}`)

export const runPromptTestSet = (setId: number, data: PromptTestSetRunRequest): Promise<ApiResponse<PromptTestSetRunResponse>> =>
  post(`/prompt-test-sets/${setId}/run`, data)
