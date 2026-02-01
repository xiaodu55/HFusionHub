import request from '@/api/request'

/**
 * 触发文档向量化（使用较长超时时间，因为解析可能较慢）
 */
export function startVectorization(documentId: number) {
  return request.post(`/vectorize/${documentId}`, null, { timeout: 120000 })
}

/**
 * 获取文档分块列表
 */
export function getDocumentChunks(
  documentId: number,
  params: {
    page?: number
    size?: number
    blockType?: string
  } = {}
) {
  return request.get(`/vectorize/${documentId}/chunks`, { params })
}

/**
 * 获取单个分块详情
 */
export function getChunkDetail(chunkId: string) {
  return request.get(`/vectorize/chunks/${chunkId}`)
}

/**
 * 查询文档处理状态
 */
export function getVectorizationStatus(documentId: number) {
  return request.get(`/vectorize/${documentId}/status`)
}
