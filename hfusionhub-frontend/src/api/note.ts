import { get, post, put, del } from './request'
import type { ApiResponse } from './types'

export interface Note {
  id: number
  userId?: number
  tenantId?: number
  knowledgeBaseId?: number
  conversationId?: number
  messageId?: number
  title: string
  content: string
  source: 'manual' | 'agent_write_note'
  createdAt?: string
  updatedAt?: string
}

export const listMyNotes = (limit = 100): Promise<ApiResponse<Note[]>> =>
  get('/note/my', { limit })

export const getNote = (id: number): Promise<ApiResponse<Note>> =>
  get(`/note/${id}`)

export const createNote = (data: { title?: string; content: string; knowledgeBaseId?: number }): Promise<ApiResponse<Note>> =>
  post('/note', data)

export const updateNote = (id: number, data: { title?: string; content?: string }): Promise<ApiResponse<Note>> =>
  put(`/note/${id}`, data)

export const deleteNote = (id: number): Promise<ApiResponse<void>> =>
  del(`/note/${id}`)
