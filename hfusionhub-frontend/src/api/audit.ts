import { get } from './request'
import type { ApiResponse } from './types'

export interface AuditLogEntry {
  id: number
  operatorId?: number
  tenantId?: number
  action?: string
  targetType?: string
  targetId?: string
  detail?: string
  createdAt?: string
}

export interface CrossTenantAuditEntry {
  id: number
  operatorId?: number
  fromTenant?: number
  toTenant?: number
  action?: string
  createdAt?: string
}

export const listOperationAudits = (params: { limit?: number; operatorId?: number; action?: string } = {}): Promise<ApiResponse<AuditLogEntry[]>> =>
  get('/admin/audit-logs/operations', params)

export const listCrossTenantAudits = (limit = 50): Promise<ApiResponse<CrossTenantAuditEntry[]>> =>
  get('/admin/audit-logs/cross-tenant', { limit })
