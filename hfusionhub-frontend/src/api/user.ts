import { get, post, put } from './request'
import type { ApiResponse, LoginForm, PageResult, RegisterForm, UserInfo, UserRole } from './types'

// 用户登录
export const login = (data: LoginForm): Promise<ApiResponse<string>> => {
  return post('/user/login', data)
}

// 用户注册
export const register = (data: RegisterForm): Promise<ApiResponse<UserInfo>> => {
  return post('/user/register', data)
}

// 用户登出
export const logout = (): Promise<ApiResponse<void>> => {
  return post('/user/logout')
}

/** SSO/OIDC 提供方信息（前端据此决定是否展示 SSO 登录按钮） */
export interface SsoProviderInfo {
  enabled: boolean
  providerName: string
}

/** 获取 SSO/OIDC 提供方信息 */
export const getSsoProviders = (): Promise<ApiResponse<SsoProviderInfo>> => {
  return get('/user/sso/providers')
}

// 获取当前用户信息
export const getUserInfo = (): Promise<ApiResponse<UserInfo>> => {
  return get('/user/info')
}

// 更新用户信息
export const updateUserInfo = (data: Partial<UserInfo>): Promise<ApiResponse<void>> => {
  return put('/user/info', data)
}

// 根据ID获取用户信息
export const getUserById = (userId: number): Promise<ApiResponse<UserInfo>> => {
  return get(`/user/${userId}`)
}

export const listUsers = (params: {
  page?: number
  pageSize?: number
  keyword?: string
  role?: UserRole | ''
}): Promise<ApiResponse<PageResult<UserInfo>>> => {
  return get('/user/list', params)
}

export const updateUserRole = (userId: number, role: UserRole): Promise<ApiResponse<UserInfo>> => {
  return put(`/user/${userId}/role`, { role })
}

/** 轻量用户搜索结果（用于共享知识库等场景） */
export interface UserSearchResult {
  id: number
  username: string
  nickname?: string
}

/** 按用户名/昵称搜索用户（登录用户可用） */
export const searchUsers = (keyword: string): Promise<ApiResponse<UserSearchResult[]>> => {
  return get('/user/search', { keyword })
}

/** 修改当前用户密码 */
export const changePassword = (data: { oldPassword: string; newPassword: string }): Promise<ApiResponse<void>> => {
  return post('/user/password', data)
}

/** 管理员重置用户密码（忘记密码场景；仅 admin，不可用于自己） */
export const resetUserPassword = (userId: number, data: { newPassword: string }): Promise<ApiResponse<UserInfo>> => {
  return put(`/user/${userId}/password`, data)
}
