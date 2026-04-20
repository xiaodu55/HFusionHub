import { get, post, del } from './request'
import type { ApiResponse } from './types'

/** 系统公告（通知铃铛） */
export interface SystemNotice {
  id: number
  title: string
  content: string
  level: 'info' | 'warning' | 'error'
  publisher: string
  scope: 'all' | 'admin' | 'user'
  expiresAt?: string | null
  createdAt: string
  updatedAt?: string
}

/** 新建公告入参（管理员） */
export interface SystemNoticeInput {
  title: string
  content: string
  level: 'info' | 'warning' | 'error'
  scope: 'all' | 'admin' | 'user'
  expiresAt?: string | null
}

// ── 用户侧 ────────────────────────────────────────────────────────────

/** 我的公告列表（scope=all/admin 且未过期） */
export const listMyNotices = (): Promise<ApiResponse<SystemNotice[]>> => get('/notifications')

/** 未读公告数 */
export const getUnreadNoticeCount = (): Promise<ApiResponse<{ count: number }>> =>
  get('/notifications/unread-count')

/** 标记公告已读 */
export const markNoticeRead = (noticeId: number): Promise<ApiResponse<void>> =>
  post(`/notifications/${noticeId}/read`)

// ── 管理员侧 ──────────────────────────────────────────────────────────

/** 全部公告列表（管理员） */
export const adminListNotices = (): Promise<ApiResponse<SystemNotice[]>> => get('/notifications/admin')

/** 发布公告（管理员） */
export const adminCreateNotice = (input: SystemNoticeInput): Promise<ApiResponse<SystemNotice>> =>
  post('/notifications/admin', input)

/** 删除公告（管理员） */
export const adminDeleteNotice = (noticeId: number): Promise<ApiResponse<void>> =>
  del(`/notifications/admin/${noticeId}`)
