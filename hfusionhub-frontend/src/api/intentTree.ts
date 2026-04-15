import { del, get, post, put } from './request'
import type {
  ApiResponse,
  PageResult,
  RagIntentNode,
  RagIntentNodeCreateDTO,
  RagIntentNodeQuery,
  RagIntentNodeUpdateDTO,
} from './types'

export const getIntentTree = (params?: {
  enabled?: number
}): Promise<ApiResponse<RagIntentNode[]>> => {
  return get('/rag/intent-tree/tree', params)
}

export const getIntentNodeList = (
  params: RagIntentNodeQuery
): Promise<ApiResponse<PageResult<RagIntentNode>>> => {
  return get('/rag/intent-tree/list', params)
}

export const createIntentNode = (
  data: RagIntentNodeCreateDTO
): Promise<ApiResponse<RagIntentNode>> => {
  return post('/rag/intent-tree', data)
}

export const updateIntentNode = (
  id: number,
  data: RagIntentNodeUpdateDTO
): Promise<ApiResponse<RagIntentNode>> => {
  return put(`/rag/intent-tree/${id}`, data)
}

export const deleteIntentNode = (id: number): Promise<ApiResponse<void>> => {
  return del(`/rag/intent-tree/${id}`)
}
