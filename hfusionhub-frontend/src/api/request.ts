import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import { useUserStore } from '@/stores/user'
import router from '@/router'
import { friendlyErrorMessage } from '@/utils/errorMessage'

// 创建 axios 实例
const service: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 防止 401 处理重入——避免登出 API 调用自身再次触发 401 导致无限循环
let isHandling401 = false

/**
 * 统一的 401 处理（M9）：清除 token 并跳转登录页。
 * axios 拦截器与绕过 axios 的 SSE/fetch 流式路径（chat/Detail.vue、utils/sse.ts）
 * 共用，保证 token 过期时登出体验一致。
 */
export function handleUnauthorized401(message = '登录已过期'): Error {
  if (isHandling401) return new Error(message)
  isHandling401 = true
  const userStore = useUserStore()
  // 先同步清除 token，确保后续请求不再携带旧 token
  userStore.clearToken()
  router.push('/login')
  setTimeout(() => { isHandling401 = false }, 1000)
  return new Error(message)
}

// 请求拦截器
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const userStore = useUserStore()
    if (userStore.token) {
      config.headers['satoken'] = userStore.token
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  (response: AxiosResponse) => {
    // 二进制响应（如头像图片）直接透传，无 R 结构可解析
    if (response.config.responseType === 'blob' || response.data instanceof Blob) {
      return response.data
    }
    const res = response.data
    // 空响应体（204/空字符串）：无 R 结构可解析，直接放行
    if (res === null || res === undefined || res === '') {
      return res
    }
    if (res.code === 200) {
      return res
    } else if (res.code === 401) {
      return Promise.reject(handleUnauthorized401(res.message || '登录已过期'))
    } else {
      return Promise.reject(new Error(res.message || '请求失败'))
    }
  },
  (error) => {
    if (error.response?.status === 401) {
      return Promise.reject(handleUnauthorized401('登录已过期'))
    }
    // 统一的「可操作化」错误提示（网络断开 / 超时 / 服务不可用等）
    return Promise.reject(new Error(friendlyErrorMessage(error)))
  }
)

// 封装请求方法
export const get = <T = any>(url: string, params?: any, config?: AxiosRequestConfig): Promise<T> => {
  return service.get(url, { params, ...config })
}

export const post = <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
  return service.post(url, data, config)
}

export const put = <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
  return service.put(url, data, config)
}

export const del = <T = any>(url: string, config?: AxiosRequestConfig): Promise<T> => {
  return service.delete(url, config)
}

export const upload = <T = any>(url: string, formData: FormData, config?: AxiosRequestConfig): Promise<T> => {
  return service.post(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
    ...config,
  })
}

export default service
