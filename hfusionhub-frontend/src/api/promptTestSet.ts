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
  expectedKeywords?: string[] | null
  requiredDocumentIds?: number[] | null
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
  expectedKeywords?: string[]
  requiredDocumentIds?: number[]
  sortOrder?: number
}

export interface PromptTestSetRunRequest {
  templateContent: string
  knowledgeBaseId?: number
  templateId?: number
  templateVersion?: number
  templateName?: string
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
  passed: boolean
  passNotes?: string[] | null
  error?: string | null
}

export interface PromptTestSetRunResponse {
  setId: number
  runId?: number
  status?: string
  templateId?: number
  templateVersion?: number
  templateName?: string
  totalCases: number
  successCount: number
  failureCount: number
  passCount: number
  passRate: number
  totalElapsedMs: number
  results: PromptTestCaseResult[]
}

export type PromptTestSetRunStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export interface PromptTestSetRunStatusDTO {
  id: number
  setId: number
  status: PromptTestSetRunStatus
  attemptNumber: number
  progressCount: number
  totalCases: number
  successCount: number
  failureCount: number
  passCount: number
  passRate: number
  errorMessage?: string | null
  scheduledAt?: string | null
  startedAt?: string | null
  completedAt?: string | null
  createdAt: string
}

export interface PromptTestSetRun {
  id: number
  templateId?: number
  templateVersion?: number
  templateName?: string
  knowledgeBaseId?: number
  totalCases: number
  successCount: number
  failureCount: number
  passCount: number
  passRate: number
  totalElapsedMs: number
  status?: string
  attemptNumber?: number
  progressCount?: number
  errorMessage?: string | null
  startedAt?: string | null
  completedAt?: string | null
  createdAt: string
}

export interface PromptTestSetRunDetail {
  run: PromptTestSetRun
  results: PromptTestCaseResult[]
}

export interface PromptTestSetCompareRequest {
  runIdA: number
  runIdB: number
}

export interface PromptTestCaseComparison {
  caseId: number
  question: string
  resultA: PromptTestCaseResult | null
  resultB: PromptTestCaseResult | null
  answerIdentical: boolean | null
}

export interface PromptTestSetCompareResponse {
  runA: PromptTestSetRun
  runB: PromptTestSetRun
  comparisons: PromptTestCaseComparison[]
  comparedCases: number
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

export const runPromptTestSet = (setId: number, data: PromptTestSetRunRequest): Promise<ApiResponse<PromptTestSetRunStatusDTO>> =>
  post(`/prompt-test-sets/${setId}/run`, data)
export const getPromptTestSetRunStatus = (runId: number): Promise<ApiResponse<PromptTestSetRunStatusDTO>> =>
  get(`/prompt-test-sets/runs/${runId}/status`)
export const cancelPromptTestSetRun = (runId: number): Promise<ApiResponse<PromptTestSetRunStatusDTO>> =>
  post(`/prompt-test-sets/runs/${runId}/cancel`)
export const retryPromptTestSetRun = (runId: number): Promise<ApiResponse<PromptTestSetRunStatusDTO>> =>
  post(`/prompt-test-sets/runs/${runId}/retry`)

// ── Run history & comparison ─────────────────────────────────────────

export const listPromptTestSetRuns = (setId: number): Promise<ApiResponse<PromptTestSetRun[]>> =>
  get(`/prompt-test-sets/${setId}/runs`)
export const getPromptTestSetRun = (runId: number): Promise<ApiResponse<PromptTestSetRunDetail>> =>
  get(`/prompt-test-sets/runs/${runId}`)
export const comparePromptTestSetRuns = (data: PromptTestSetCompareRequest): Promise<ApiResponse<PromptTestSetCompareResponse>> =>
  post(`/prompt-test-sets/compare`, data)
