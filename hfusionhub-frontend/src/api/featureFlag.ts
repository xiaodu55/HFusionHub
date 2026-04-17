import { get, put } from './request'
import type { ApiResponse } from './types'

export interface FeatureFlagInfo {
  id: number
  flagKey: string
  flagType: string
  description?: string
  enabled: boolean
  updatedAt?: string
}

export interface FeatureFlagUpdate {
  enabled: boolean
  reason?: string
}

export const listFeatureFlags = (): Promise<ApiResponse<FeatureFlagInfo[]>> =>
  get('/feature-flag/all')

export const updateFeatureFlag = (
  id: number,
  data: FeatureFlagUpdate,
): Promise<ApiResponse<FeatureFlagInfo>> => put(`/feature-flag/${id}`, data)
