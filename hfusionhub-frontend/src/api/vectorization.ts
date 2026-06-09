import { get, post } from './request'
import type { ApiResponse } from './types'

/** 可用嵌入模型 */
export interface EmbeddingModel {
  id: string
  name: string
  type: string
  dimension: number
  description?: string
}

/** 文档分块 */
export interface DocumentChunk {
  chunk_id: string
  block_type: string
  outline_path: string[]
  content: string
  metadata: {
    char_count?: number
    language?: string
    [key: string]: unknown
  }
}

/** 分块分页结果（后端可能返回 JSON 串，由调用方自行 parse） */
export interface ChunkPage {
  chunks: DocumentChunk[]
  totalChunks?: number
}

/**
 * 获取可用的嵌入模型列表
 */
export const getAvailableModels = (): Promise<ApiResponse<{ models: EmbeddingModel[] }>> =>
  get('/vectorize/models')

/**
 * 触发文档向量化（使用较长超时时间，因为解析可能较慢）
 */
export const startVectorization = (documentId: number, model?: string): Promise<ApiResponse<void>> =>
  post(`/vectorize/${documentId}`, { model }, { timeout: 120000 })

/**
 * 获取文档分块列表
 */
export const getDocumentChunks = (
  documentId: number,
  params: {
    page?: number
    size?: number
    blockType?: string
  } = {}
): Promise<ApiResponse<ChunkPage | string>> =>
  get(`/vectorize/${documentId}/chunks`, params)

/**
 * 获取单个分块详情
 */
export const getChunkDetail = (chunkId: string): Promise<ApiResponse<DocumentChunk>> =>
  get(`/vectorize/chunks/${chunkId}`)

/**
 * 查询文档处理状态（载荷可能是 JSON 串或对象，由调用方归一化）
 */
export const getVectorizationStatus = (documentId: number): Promise<ApiResponse<unknown>> =>
  get(`/vectorize/${documentId}/status`)

/**
 * 重置文档状态为待解析
 */
export const resetDocument = (documentId: number): Promise<ApiResponse<void>> =>
  post(`/vectorize/${documentId}/reset`)

/**
 * 同步所有待解析文档的状态（从Python引擎查询实际分块数）
 */
export const syncAllDocuments = (): Promise<ApiResponse<void>> =>
  post('/vectorize/sync-all')
