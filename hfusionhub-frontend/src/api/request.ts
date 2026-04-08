import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import { useUserStore } from '@/stores/user'
import router from '@/router'

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
    const res = response.data
    if (res.code === 200) {
      return res
    } else if (res.code === 401) {
      if (isHandling401) return Promise.reject(new Error(res.message || '登录已过期'))
      isHandling401 = true
      const userStore = useUserStore()
      // 先同步清除 token，确保后续请求不再携带旧 token
      userStore.clearToken()
      router.push('/login')
      setTimeout(() => { isHandling401 = false }, 1000)
      return Promise.reject(new Error(res.message || '登录已过期'))
    } else {
      return Promise.reject(new Error(res.message || '请求失败'))
    }
  },
  (error) => {
    if (error.response?.status === 401) {
      if (isHandling401) {
        return Promise.reject(new Error('登录已过期'))
      }
      isHandling401 = true
      const userStore = useUserStore()
      // 先同步清除 token，确保后续请求不再携带旧 token
      userStore.clearToken()
      router.push('/login')
      setTimeout(() => { isHandling401 = false }, 1000)
    }
    const data = error.response?.data
    const message =
      data?.message ||
      data?.detail?.message ||
      data?.error ||
      error.message ||
      '请求失败'
    return Promise.reject(new Error(message))
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
