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

// 更新文档
export const updateDocument = (id: number, data: { name?: string }): Promise<ApiResponse<void>> => {
  return put(`/document/${id}`, data)
}

// 删除文档
export const deleteDocument = (id: number): Promise<ApiResponse<void>> => {
  return del(`/document/${id}`)
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
  pageNum: number
  pageSize: number
  name?: string
}): Promise<ApiResponse<PageResult<Document>>> => {
  return get('/document/list', params)
}

// 根据知识库ID获取文档列表
export const getDocumentsByKbId = (kbId: number, params?: {
  pageNum?: number
  pageSize?: number
}): Promise<ApiResponse<PageResult<Document>>> => {
  return get(`/document/list/${kbId}`, params)
}

// 获取当前用户在指定知识库的文档列表
export const getMyDocumentsByKbId = (kbId: number, params?: {
  pageNum?: number
  pageSize?: number
}): Promise<ApiResponse<PageResult<Document>>> => {
  return get(`/document/my/${kbId}`, params)
}

// 解析文档
export const parseDocument = (id: number, model?: string): Promise<ApiResponse<string>> => {
  return post(`/document/${id}/parse`, { model })
}
