import { get, post, put, del } from './request'
import type { ApiResponse, PageResult, Document } from './types'

// 上传文档
export const uploadDocument = (file: File, kbId: number, title?: string): Promise<ApiResponse<number>> => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('knowledgeBaseId', kbId.toString())
  if (title) {
    formData.append('title', title)
  } else {
    formData.append('title', file.name)
  }
  return post('/document/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}

// 从公开网页 URL 创建文档（Python AI 抓取并暂存为 markdown，待解析）
export const createDocumentFromUrl = (
  url: string,
  kbId: number,
  title?: string,
): Promise<ApiResponse<Document>> => {
  return post(`/document/from-url?knowledgeBaseId=${kbId}`, { url, title })
}

// 更新文档
export const updateDocument = (id: number, data: { title?: string; content?: string }): Promise<ApiResponse<void>> => {
  return put(`/document/${id}`, data)
}

// 删除文档
export const deleteDocument = (id: number): Promise<ApiResponse<void>> => {
  return del(`/document/${id}`)
}

export const getRecycleBin = (params?: {
  page?: number
  pageSize?: number
  title?: string
}): Promise<ApiResponse<PageResult<Document>>> => {
  return get('/document/recycle-bin', params)
}

export const restoreDocument = (id: number): Promise<ApiResponse<void>> => {
  return post(`/document/${id}/restore`)
}

export const purgeDocument = (id: number): Promise<ApiResponse<void>> => {
  return del(`/document/${id}/purge`)
}

// 获取文档详情
export const getDocument = (id: number): Promise<ApiResponse<Document>> => {
  return get(`/document/${id}`)
}

// 获取文档内容
export const getDocumentContent = (id: number): Promise<ApiResponse<string>> => {
  return get(`/document/${id}/content`)
}

// 分页查询文档列表
export const getDocumentList = (params: {
  page: number
  pageSize: number
  title?: string
}): Promise<ApiResponse<PageResult<Document>>> => {
  return get('/document/list', params)
}

// 根据知识库ID获取文档列表
export const getDocumentsByKbId = (kbId: number, params?: {
  page?: number
  pageSize?: number
}): Promise<ApiResponse<PageResult<Document>>> => {
  return get(`/document/list/${kbId}`, params)
}

// 获取当前用户在指定知识库的文档列表
export const getMyDocumentsByKbId = (kbId: number, params?: {
  page?: number
  pageSize?: number
  /** 文档状态：0-待解析，1-解析中，2-已完成，3-失败；不传 = 全部 */
  status?: number
}): Promise<ApiResponse<PageResult<Document>>> => {
  return get(`/document/my/${kbId}`, params)
}

// 解析文档
export const parseDocument = (id: number, model?: string): Promise<ApiResponse<string>> => {
  return post(`/document/${id}/parse`, { model })
}
