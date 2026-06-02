import { post } from './request'
import type { ApiResponse } from './types'

/** 单个菜单的分项导入结果 */
export interface DemoSectionResult {
  section: string
  label: string
  importedCount: number
  skippedCount: number
}

/** 演示数据导入结果 */
export interface DemoImportResult {
  knowledgeBaseId: number
  knowledgeBaseName: string
  importedCount: number
  skippedCount: number
  parseFailedCount: number
  sections?: DemoSectionResult[]
  message: string
}

/**
 * 一键导入演示数据（管理员）：
 * 覆盖知识库文档、回答方案、我的笔记、我的记忆、应用发布、公告，幂等可重复调用。
 */
export const importDemoData = (): Promise<ApiResponse<DemoImportResult>> =>
  post('/demo/import')

/**
 * 一键清除演示数据（管理员）：
 * 知识库与回答方案移入回收站（7 天保留），笔记/记忆/应用/公告直接删除。
 */
export const clearDemoData = (): Promise<ApiResponse<DemoImportResult>> =>
  post('/demo/clear')

/**
 * 导入行业免费试用样例（管理员）：
 * 建行业样例知识库（3 篇脱敏招标文件）+ 示例投标项目，与行业方案包离线评测语料同源。
 *
 * @param industry 行业 code：construction（工程施工）/ it（IT 集成）
 */
export const importBidIndustrySamples = (industry: string): Promise<ApiResponse<DemoImportResult>> =>
  post('/demo/import-bid-industry', null, { params: { industry } })
