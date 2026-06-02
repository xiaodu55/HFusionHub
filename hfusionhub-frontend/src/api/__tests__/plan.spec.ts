import { beforeEach, describe, expect, it, vi } from 'vitest'
import { del, get, post, put } from '../request'
import {
  archiveBidTemplate,
  archivePlan,
  bindPlan,
  createBidTemplate,
  createPlan,
  formatCents,
  getPlanCurrent,
  listAllPlans,
  listBidTemplates,
  listPlatformPlans,
  parseModuleFlags,
  unbindPlan,
  updatePlan,
} from '../plan'

vi.mock('../request', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}))

describe('bid plan API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('parses module_flags JSON with 0/1 and true/false values', () => {
    expect(parseModuleFlags('{"draft":1,"check":0,"docx":true,"openapi":false}')).toEqual({
      draft: true,
      check: false,
      docx: true,
      openapi: false,
    })
    expect(parseModuleFlags('not-json')).toEqual({})
    expect(parseModuleFlags(null)).toEqual({})
  })

  it('formats cents to yuan', () => {
    expect(formatCents(9900)).toBe('¥99')
    expect(formatCents(19900)).toBe('¥199')
    expect(formatCents(12345)).toBe('¥123.45')
    expect(formatCents(null)).toBe('—')
  })

  it('lists platform plans and current tenant overview', () => {
    listPlatformPlans()
    expect(get).toHaveBeenCalledWith('/bid/plan/catalog')

    getPlanCurrent()
    expect(get).toHaveBeenCalledWith('/bid/plan/current')
  })

  it('binds and unbinds a plan with subscriptionId param', () => {
    bindPlan(5)
    expect(post).toHaveBeenCalledWith('/bid/plan/bind', null, { params: { subscriptionId: 5 } })

    unbindPlan(5)
    expect(post).toHaveBeenCalledWith('/bid/plan/unbind', null, { params: { subscriptionId: 5 } })
  })

  it('admin CRUD routes to /bid/plan/admin', () => {
    listAllPlans()
    expect(get).toHaveBeenCalledWith('/bid/plan/admin')

    createPlan({ planCode: 'pro' })
    expect(post).toHaveBeenCalledWith('/bid/plan/admin', { planCode: 'pro' })

    updatePlan({ id: 5, planName: '专业版' })
    expect(put).toHaveBeenCalledWith('/bid/plan/admin', { id: 5, planName: '专业版' })

    archivePlan(5)
    expect(del).toHaveBeenCalledWith('/bid/plan/admin/5')
  })

  it('template market routes with optional industry filter', () => {
    listBidTemplates()
    expect(get).toHaveBeenCalledWith('/bid/template/list', { industry: undefined })

    listBidTemplates('construction')
    expect(get).toHaveBeenCalledWith('/bid/template/list', { industry: 'construction' })

    createBidTemplate({ name: '市政标' })
    expect(post).toHaveBeenCalledWith('/bid/template', { name: '市政标' })

    archiveBidTemplate(9)
    expect(del).toHaveBeenCalledWith('/bid/template/9')
  })
})
