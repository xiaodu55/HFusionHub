import { get, post } from './request'
import type { ApiResponse } from './types'
import { useUserStore } from '@/stores/user'

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

  async function run() {
    try {
      const res = await fetch('/api/agent-task/approvals/stream', {
        headers: token ? { satoken: token } : {},
        signal: controller.signal,
      })
      if (!res.ok || !res.body) throw new Error(`审批流连接失败 (${res.status})`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const raw of lines) {
          const line = raw.endsWith('\r') ? raw.slice(0, -1) : raw
          if (!line.startsWith('data:')) continue
          const data = line.slice(5).trim()
          if (!data) continue
          let parsed: { type?: string; data?: AgentApproval[] | AgentApproval }
          try {
            parsed = JSON.parse(data)
          } catch {
            continue
          }
          if (parsed.type === 'snapshot' && Array.isArray(parsed.data)) {
            handlers.onSnapshot(parsed.data as AgentApproval[])
          } else if (parsed.type === 'approval' && parsed.data) {
            handlers.onApproval(parsed.data as AgentApproval)
          }
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        handlers.onError?.(error instanceof Error ? error : new Error('审批流连接中断'))
      }
    }
  }

  run()

  return () => controller.abort()
}
