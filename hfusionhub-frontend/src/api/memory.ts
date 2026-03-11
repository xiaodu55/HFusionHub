import { del, get, post, put } from './request'
import type { ApiResponse } from './types'

export interface MemoryEntry {
  id: number; type: string; content: string; importance: number; conversationId?: number | null
  knowledgeBaseId?: number | null; expiresAt?: string | null; createdAt: string; updatedAt: string
}
export const listMemories = (params?: { type?: string; conversationId?: number }): Promise<ApiResponse<MemoryEntry[]>> => get('/memory', params)
export const createMemory = (data: Partial<MemoryEntry>): Promise<ApiResponse<MemoryEntry>> => post('/memory', data)
export const updateMemory = (id: number, data: Partial<MemoryEntry>): Promise<ApiResponse<MemoryEntry>> => put(`/memory/${id}`, data)
export const deleteMemory = (id: number): Promise<ApiResponse<void>> => del(`/memory/${id}`)
