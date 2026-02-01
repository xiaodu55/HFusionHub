import { get, post, put, del } from './request'
import type {
  ApiResponse,
  PageResult,
  KnowledgeBase,
  KnowledgeBaseCreateDTO,
  KnowledgeBaseUpdateDTO
} from './types'

// 创建知识库
export const createKnowledgeBase = (data: KnowledgeBaseCreateDTO): Promise<ApiResponse<number>> => {
  return post('/knowledge-base', data)
}

// 更新知识库
export const updateKnowledgeBase = (id: number, data: KnowledgeBaseUpdateDTO): Promise<ApiResponse<void>> => {
  return put(`/knowledge-base/${id}`, data)
}

// 删除知识库
export const deleteKnowledgeBase = (id: number): Promise<ApiResponse<void>> => {
  return del(`/knowledge-base/${id}`)
}

// 获取知识库详情
export const getKnowledgeBase = (id: number): Promise<ApiResponse<KnowledgeBase>> => {
  return get(`/knowledge-base/${id}`)
}

// 分页查询知识库列表
export const getKnowledgeBaseList = (params: {
  pageNum: number
  pageSize: number
  name?: string
}): Promise<ApiResponse<PageResult<KnowledgeBase>>> => {
  return get('/knowledge-base/list', params)
}

// 获取当前用户的知识库列表
export const getMyKnowledgeBaseList = (params?: {
  pageNum?: number
  pageSize?: number
}): Promise<ApiResponse<PageResult<KnowledgeBase>>> => {
  return get('/knowledge-base/my', params)
}
