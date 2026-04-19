import { post } from './request'
import type { ApiResponse } from './types'

/** 演示知识库导入结果 */
export interface DemoImportResult {
  knowledgeBaseId: number
  knowledgeBaseName: string
  importedCount: number
  skippedCount: number
  parseFailedCount: number
  message: string
}

/**
 * 一键导入演示知识库（管理员）：
 * 创建/复用「演示知识库」，导入内置示例文档并触发解析，幂等可重复调用。
 */
export const importDemoKnowledgeBase = (): Promise<ApiResponse<DemoImportResult>> =>
  post('/demo/import')
