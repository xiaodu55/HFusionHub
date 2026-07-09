import { get, post, del } from './request'
import type { ApiResponse } from './types'

/** 知识库共享记录 */
export interface KbShareInfo {
  id: number
  knowledgeBaseId: number
  knowledgeBaseName?: string
  ownerUserId: number
  ownerUsername?: string
  sharedUserId: number
  sharedUsername?: string
  permission: 'read' | 'read_write'
  createdAt: string
}

/** 共享知识库给用户（permission: read 只读 | read_write 可上传，Batch 10 授权矩阵） */
export const shareKnowledgeBase = (
  knowledgeBaseId: number,
  targetUserId: number,
  permission: 'read' | 'read_write' = 'read',
): Promise<ApiResponse<KbShareInfo>> =>
  post('/knowledge-base/share', { knowledgeBaseId, targetUserId, permission })

/** 某知识库的共享记录（所有者） */
export const listKbShares = (knowledgeBaseId: number): Promise<ApiResponse<KbShareInfo[]>> =>
  get(`/knowledge-base/share/${knowledgeBaseId}`)

/** 撤销共享 */
export const revokeKbShare = (knowledgeBaseId: number, shareId: number): Promise<ApiResponse<void>> =>
  del(`/knowledge-base/share/${knowledgeBaseId}/${shareId}`)

/** 共享给我的知识库 */
export const listSharedToMe = (): Promise<ApiResponse<KbShareInfo[]>> => get('/knowledge-base/share/to-me')
