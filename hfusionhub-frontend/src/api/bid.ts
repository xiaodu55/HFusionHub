import { get, post, put, del } from './request'
import type { ApiResponse, PageResult } from './types'

/** 投标项目状态机 */
export const BID_PROJECT_STATUS = {
  INTERPRETING: 'interpreting',
  REQUIREMENTS: 'requirements',
  DRAFTING: 'drafting',
  CHECKING: 'checking',
  SUBMITTED: 'submitted',
  ARCHIVED: 'archived',
} as const

export type BidProjectStatus = (typeof BID_PROJECT_STATUS)[keyof typeof BID_PROJECT_STATUS]

/** 投标项目信息 */
export interface BidProjectInfo {
  id: number
  knowledgeBaseId: number
  tenderNumber?: string
  title: string
  budget?: number | null
  deadline?: string | null
  bidBond?: string | null
  openingDate?: string | null
  status: BidProjectStatus
  createdBy: number
  requirementCount?: number
  createdAt: string
  updatedAt: string
}

/** 招标结构化要素 */
export interface TenderElement {
  id: number
  projectId: number
  elementKey: string
  elementValue?: string
  evidenceChunkIds?: string
  confidence?: number | null
  sourceClause?: string
  riskLevel?: string
}

/** 评分办法 */
export interface BidScoringMethod {
  id: number
  projectId: number
  methodType: 'comprehensive' | 'lowest_price'
  pointsJson?: string
  totalScore?: number | null
}

/** 投标需求项 */
export interface BidRequirement {
  id: number
  projectId: number
  category: string
  requirement: string
  sourceClause?: string
  satisfiedStatus: 'pending' | 'drafting' | 'checked' | 'manual_review'
}

/** 投标项目详情 */
export interface BidProjectDetail {
  project: BidProjectInfo
  elements: TenderElement[]
  scoringMethods: BidScoringMethod[]
  requirements: BidRequirement[]
}

export interface BidProjectCreatePayload {
  knowledgeBaseId: number
  title: string
  tenderNumber?: string
  budget?: number
  deadline?: string
  bidBond?: string
  openingDate?: string
}

export interface BidProjectQuery {
  keyword?: string
  status?: BidProjectStatus
  page: number
  pageSize: number
}

/** 创建投标项目 */
export const createBidProject = (payload: BidProjectCreatePayload): Promise<ApiResponse<BidProjectInfo>> =>
  post('/bid/project', payload)

/** 分页查询投标项目 */
export const listBidProjects = (query: BidProjectQuery): Promise<ApiResponse<PageResult<BidProjectInfo>>> =>
  get('/bid/project/list', query)

/** 获取投标项目详情 */
export const getBidProjectDetail = (id: number): Promise<ApiResponse<BidProjectDetail>> =>
  get(`/bid/project/${id}/detail`)

/** 删除投标项目 */
export const deleteBidProject = (id: number): Promise<ApiResponse<void>> =>
  del(`/bid/project/${id}`)

/** 推进项目状态 */
export const updateBidProjectStatus = (id: number, status: BidProjectStatus): Promise<ApiResponse<BidProjectInfo>> =>
  put(`/bid/project/${id}/status`, null, { params: { status } })

/** 触发招标解读 */
export const interpretBidProject = (id: number): Promise<ApiResponse<BidProjectDetail>> =>
  post(`/bid/project/${id}/interpret`)

/** 更新需求项状态（人工确认/修正） */
export const updateBidRequirementStatus = (
  projectId: number,
  requirementId: number,
  status: BidRequirement['satisfiedStatus'],
): Promise<ApiResponse<void>> =>
  put(`/bid/project/${projectId}/requirements/${requirementId}/status`, null, { params: { status } })
