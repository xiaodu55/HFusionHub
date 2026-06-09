import { describe, expect, it } from 'vitest'
import {
  BADGE_TONE_CLASS,
  BID_PROJECT_STATUS_LABELS,
  BID_PROJECT_STATUS_CLASS,
  BID_REQUIREMENT_CATEGORY_LABELS,
  BID_REQUIREMENT_STATUS_CLASS,
  BID_REQUIREMENT_STATUS_LABELS,
  bidProjectStatusClass,
  levelBadgeClass,
} from '../badge'

describe('badge 工具', () => {
  it('每种色调都有对应样式', () => {
    for (const tone of ['success', 'danger', 'warning', 'progress', 'neutral'] as const) {
      expect(BADGE_TONE_CLASS[tone]).toBeTruthy()
    }
  })

  it('等级徽章：critical/error 用危险色，未知等级回退中性样式', () => {
    expect(levelBadgeClass('critical')).toBe(BADGE_TONE_CLASS.danger)
    expect(levelBadgeClass('error')).toBe(BADGE_TONE_CLASS.danger)
    expect(levelBadgeClass('warning')).toBe(BADGE_TONE_CLASS.warning)
    expect(levelBadgeClass('info')).toBe(BADGE_TONE_CLASS.progress)
    expect(levelBadgeClass('unknown')).toContain('bg-muted')
    expect(levelBadgeClass(undefined)).toContain('bg-muted')
  })

  it('投标项目状态文案与样式一一对应', () => {
    expect(Object.keys(BID_PROJECT_STATUS_LABELS)).toEqual(
      Object.keys(BID_PROJECT_STATUS_CLASS),
    )
    expect(BID_PROJECT_STATUS_LABELS.interpreting).toBe('解读中')
    expect(bidProjectStatusClass('submitted')).toBe(BID_PROJECT_STATUS_CLASS.submitted)
    expect(bidProjectStatusClass('nonexistent' as never)).toBeTruthy()
  })

  it('投标需求满足状态与分类文案已定义', () => {
    expect(BID_REQUIREMENT_STATUS_LABELS.pending).toBe('待处理')
    expect(Object.keys(BID_REQUIREMENT_STATUS_CLASS)).toEqual(
      Object.keys(BID_REQUIREMENT_STATUS_LABELS),
    )
    expect(BID_REQUIREMENT_CATEGORY_LABELS.disqualification_risk).toBe('废标风险')
  })
})
