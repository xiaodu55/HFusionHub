import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RegisterForm, UserInfo, UserRole } from '@/api/types'
import * as userApi from '@/api/user'

export const useUserStore = defineStore('user', () => {
  // State
  const token = ref<string>(localStorage.getItem('satoken') || '')
  const userInfo = ref<UserInfo | null>(null)

  // Getters
  const isLoggedIn = computed(() => !!token.value)
  const username = computed(() => userInfo.value?.username || '')
  const nickname = computed(() => userInfo.value?.nickname || '')
  const role = computed<UserRole>(() => userInfo.value?.role || 'pending')
  const isPending = computed(() => role.value === 'pending')
  const isApproved = computed(() => role.value === 'user' || role.value === 'builder' || role.value === 'admin')
  const isAdmin = computed(() => role.value === 'admin')
  const isBuilder = computed(() => role.value === 'builder' || role.value === 'admin')
  const hasAnyRole = (roles: UserRole[]) => roles.includes(role.value)

  // Actions
  const setToken = (newToken: string) => {
    token.value = newToken
    localStorage.setItem('satoken', newToken)
  }

  const clearToken = () => {
    token.value = ''
    localStorage.removeItem('satoken')
  }

  const login = async (username: string, password: string) => {
    const res = await userApi.login({ username, password })
    setToken(res.data)
    await getUserInfo()
    return res
  }

  const register = async (data: RegisterForm) => {
    return await userApi.register(data)
  }

  const logout = async () => {
    try {
      await userApi.logout()
    } catch (error) {
      // 即使登出失败也要清除本地状态
    } finally {
      clearToken()
      userInfo.value = null
    }
  }

  const getUserInfo = async () => {
    const res = await userApi.getUserInfo()
    userInfo.value = res.data
    return res
  }

  const updateUserInfo = async (data: Partial<UserInfo>) => {
    const res = await userApi.updateUserInfo(data)
    await getUserInfo()
    return res
  }

  return {
    token,
    userInfo,
    isLoggedIn,
    username,
    nickname,
    role,
    isPending,
    isApproved,
    isAdmin,
    isBuilder,
    hasAnyRole,
    setToken,
    clearToken,
    login,
    register,
    logout,
    getUserInfo,
    updateUserInfo,
  }
})
