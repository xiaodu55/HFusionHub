import { get, post } from './request'
import type { ApiResponse } from './types'
import { useUserStore } from '@/stores/user'
import { consumeSseJsonStream } from '@/utils/sse'

export type ApprovalStatus = 'pending' | 'approved' | 'denied' | 'expired' | 'executed' | 'failed'

export interface AgentApproval {
  id: number
  approvalId: string
  taskId?: number
  runId?: number
  userId?: number
  userRole?: string
  traceId?: string
  toolName?: string
  riskLevel?: string
  toolInputHash?: string
  executionTokenStatus?: string
  argumentsSummary?: string
  status: ApprovalStatus
  decidedBy?: number
  decidedAt?: string
  reason?: string
  expiresAt?: string
  createdAt: string
}

/** 审批列表筛选条件 */
export interface ApprovalQuery {
  status?: ApprovalStatus | 'all'
  riskLevel?: string
}

/** 审批决定请求体 */
export interface ApprovalDecisionRequest {
  approvalId: string
  decision: 'approved' | 'denied'
  reason?: string
}

export const listPendingApprovals = (): Promise<ApiResponse<AgentApproval[]>> =>
  get('/agent-task/approvals/pending')

export const listApprovalsByTask = (taskId: number): Promise<ApiResponse<AgentApproval[]>> =>
  get(`/agent-task/${taskId}/approvals`)

export const decideApproval = (
  taskId: number,
  body: ApprovalDecisionRequest,
): Promise<ApiResponse<AgentApproval>> => post(`/agent-task/${taskId}/approve`, body)

/**
 * 订阅当前用户的审批实时流（SSE）。
 *
 * 连接后先收到一条 `snapshot`（当前用户的全部近期审批），随后每当某条
 * 审批状态发生变化（waiting → approved/denied/expired，approved → executed/failed）
 * 都会收到一条 `approval` 事件。断线后由调用方重新 subscribe，服务端会重新下发快照。
 */
export function subscribeApprovalStream(handlers: {
  onSnapshot: (approvals: AgentApproval[]) => void
  onApproval: (approval: AgentApproval) => void
  onError?: (error: Error) => void
}): () => void {
  const userStore = useUserStore()
  const token = userStore.token
  const controller = new AbortController()

  // 解析统一收敛到 utils/sse.ts 的 consumeSseJsonStream（内部复用 SseDataParser）
  void consumeSseJsonStream<AgentApproval[] | AgentApproval>('/api/agent-task/approvals/stream', {
    headers: token ? { satoken: token } : {},
    signal: controller.signal,
    onData: (parsed) => {
      if (parsed.type === 'snapshot' && Array.isArray(parsed.data)) {
        handlers.onSnapshot(parsed.data as AgentApproval[])
      } else if (parsed.type === 'approval' && parsed.data) {
        handlers.onApproval(parsed.data as AgentApproval)
      }
    },
    onError: (error) => {
      handlers.onError?.(error instanceof Error ? error : new Error('审批流连接中断'))
    },
  })

  return () => controller.abort()
}
