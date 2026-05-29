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

// ── P1：标书撰写 + 废标自检 ───────────────────────────────────────

/** 标书分节草稿 */
export interface BidDraft {
  id: number
  projectId: number
  sectionKey: 'commercial' | 'technical' | 'qualification' | 'format'
  sectionTitle: string
  content?: string
  status: 'drafting' | 'approved' | 'rejected'
  version: number
  approvedBy?: number | null
  createdAt: string
  updatedAt: string
}

/** 废标自检报告 */
export interface BidCheckReport {
  id: number
  projectId: number
  sectionKey?: string | null
  severity: 'critical' | 'warning' | 'info'
  category: string
  finding: string
  evidence?: string | null
  suggestedFix?: string | null
  status: 'open' | 'confirmed' | 'fixed'
  createdAt: string
}

/** 自检统计 */
export interface BidCheckSummary {
  total: number
  critical: number
  warning: number
  info: number
}

export const BID_SECTION_LABELS: Record<string, string> = {
  commercial: '商务标',
  technical: '技术方案',
  qualification: '资质文件',
  format: '格式文件',
}

/** 同步撰写标书（落库） */
export const writeBidDraft = (projectId: number): Promise<ApiResponse<BidDraft[]>> =>
  post(`/bid/write/${projectId}`)

/** 查询标书分节 */
export const listBidDrafts = (projectId: number): Promise<ApiResponse<BidDraft[]>> =>
  get(`/bid/write/${projectId}/drafts`)

/** 分节人工审批（approved|rejected） */
export const updateBidDraftStatus = (
  draftId: number,
  status: BidDraft['status'],
): Promise<ApiResponse<void>> =>
  put(`/bid/write/${draftId}/status`, null, { params: { status } })

/** 执行废标自检 */
export const runBidCheck = (projectId: number): Promise<ApiResponse<BidCheckSummary>> =>
  post(`/bid/check/${projectId}`)

/** 查询自检报告 */
export const listBidCheckReports = (projectId: number): Promise<ApiResponse<BidCheckReport[]>> =>
  get(`/bid/check/${projectId}/reports`)

/** 处理自检报告（confirmed|fixed） */
export const updateBidCheckReportStatus = (
  reportId: number,
  status: BidCheckReport['status'],
): Promise<ApiResponse<void>> =>
  put(`/bid/check/report/${reportId}/status`, null, { params: { status } })
