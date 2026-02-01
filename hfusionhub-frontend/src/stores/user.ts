import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo } from '@/api/types'
import * as userApi from '@/api/user'

export const useUserStore = defineStore('user', () => {
  // State
  const token = ref<string>(localStorage.getItem('satoken') || '')
  const userInfo = ref<UserInfo | null>(null)

  // Getters
  const isLoggedIn = computed(() => !!token.value)
  const username = computed(() => userInfo.value?.username || '')
  const nickname = computed(() => userInfo.value?.nickname || '')

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

  const register = async (data: { username: string; password: string; nickname?: string }) => {
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
    setToken,
    clearToken,
    login,
    register,
    logout,
    getUserInfo,
    updateUserInfo,
  }
})
