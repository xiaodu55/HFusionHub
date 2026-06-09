import type { BidProjectStatus, BidRequirement } from '@/api/bid'

/**
 * 全局共享的徽章/状态样式映射。
 * 各页面不再各自维护 *_LABELS / *_CLASS，统一从这里引用，
 * 避免文案或配色调整时需要同步多处。
 */

/** 通用状态色调 → 徽章样式（暗色 UI） */
export type BadgeTone = 'success' | 'danger' | 'warning' | 'progress' | 'neutral'

export const BADGE_TONE_CLASS: Record<BadgeTone, string> = {
  success: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300',
  danger: 'border-rose-400/25 bg-rose-400/10 text-rose-300',
  warning: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
  progress: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200',
  neutral: 'border-white/10 bg-white/5 text-muted-foreground',
}

/** 告警/公告等级（critical|error → danger）→ 徽章样式 */
export const LEVEL_BADGE_CLASS: Record<string, string> = {
  critical: BADGE_TONE_CLASS.danger,
  error: BADGE_TONE_CLASS.danger,
  warning: BADGE_TONE_CLASS.warning,
  info: BADGE_TONE_CLASS.progress,
}

export const levelBadgeClass = (level?: string): string =>
  LEVEL_BADGE_CLASS[level || ''] || 'border-border bg-muted text-muted-foreground'

/** 投标项目状态文案 */
export const BID_PROJECT_STATUS_LABELS: Record<BidProjectStatus, string> = {
  interpreting: '解读中',
  requirements: '需求清单',
  drafting: '撰写中',
  checking: '自检中',
  submitted: '已投标',
  archived: '已归档',
}

/** 投标项目状态 → 徽章样式（浅色底） */
export const BID_PROJECT_STATUS_CLASS: Record<BidProjectStatus, string> = {
  interpreting: 'bg-blue-100 text-blue-700',
  requirements: 'bg-amber-100 text-amber-700',
  drafting: 'bg-purple-100 text-purple-700',
  checking: 'bg-orange-100 text-orange-700',
  submitted: 'bg-emerald-100 text-emerald-700',
  archived: 'bg-slate-100 text-slate-600',
}

export const bidProjectStatusClass = (status: BidProjectStatus): string =>
  BID_PROJECT_STATUS_CLASS[status] || BADGE_TONE_CLASS.neutral

/** 投标需求满足状态 */
export const BID_REQUIREMENT_STATUS_LABELS: Record<BidRequirement['satisfiedStatus'], string> = {
  pending: '待处理',
  drafting: '撰写中',
  checked: '已确认',
  manual_review: '需人工复核',
}

export const BID_REQUIREMENT_STATUS_CLASS: Record<BidRequirement['satisfiedStatus'], string> = {
  pending: 'bg-slate-100 text-slate-600',
  drafting: 'bg-blue-100 text-blue-700',
  checked: 'bg-emerald-100 text-emerald-700',
  manual_review: 'bg-amber-100 text-amber-700',
}

/** 投标需求分类文案 */
export const BID_REQUIREMENT_CATEGORY_LABELS: Record<string, string> = {
  qualification: '资质要求',
  performance: '业绩要求',
  technical: '技术需求',
  commercial: '商务需求',
  format: '格式要求',
  disqualification_risk: '废标风险',
}
