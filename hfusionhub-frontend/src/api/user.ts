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
