/**
 * 统一的「可操作化」错误提示：
 * 把后端原始错误/网络错误转换为带解决方向的中文提示，
 * 供 axios 拦截器、流式请求与各页面共用。
 */

interface AnyError {
  code?: string
  message?: string
  response?: {
    status?: number
    data?: {
      message?: string
      detail?: { message?: string }
      error?: string
    }
  }
}

const AI_SERVICE_HINT = '（AI 服务不可用？请在「设置」中查看 AI 服务状态）'

export const friendlyErrorMessage = (error: unknown, fallback = '请求失败，请稍后重试'): string => {
  const err = (error ?? {}) as AnyError

  // 1. 后端返回的业务错误优先展示（信息最准确）
  const data = err.response?.data
  const serverMsg = data?.message || data?.detail?.message || data?.error
  if (serverMsg) return serverMsg

  // 2. 无响应：网络层问题
  if (!err.response) {
    const raw = err.message || ''
    if (err.code === 'ECONNABORTED' || /timeout|timed out/i.test(raw)) {
      return '请求超时，请稍后重试'
    }
    if (/network|Network|fetch failed/i.test(raw)) {
      return `无法连接服务器，请确认 Java 后端服务已启动${AI_SERVICE_HINT}`
    }
    return `无法连接服务器，请检查网络或确认服务已启动${AI_SERVICE_HINT}`
  }

  // 3. 有响应：按 HTTP 状态码给出引导
  const status = err.response.status ?? 0
  if (status === 401) return '登录已过期，请重新登录'
  if (status === 403) return '没有权限执行该操作'
  if (status === 404) return '请求的接口不存在，请确认版本一致'
  if (status === 502 || status === 503) return `服务暂不可用，请稍后重试${AI_SERVICE_HINT}`
  if (status >= 500) return '服务器内部错误，请稍后重试'

  return err.message || fallback
}

export default friendlyErrorMessage
