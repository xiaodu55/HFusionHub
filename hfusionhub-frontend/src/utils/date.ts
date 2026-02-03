/**
 * 日期工具函数
 * 后端已存储北京时间（UTC+8），无需额外时区转换
 */

/**
 * 将后端日期字符串转为本地 Date 对象
 * 支持格式：ISO 字符串、数组格式 [y, m, d, h, min, s]
 */
export const parseServerTime = (dateStr: string | null | undefined): Date | null => {
  if (!dateStr) return null
  try {
    // 处理数组格式
    if (Array.isArray(dateStr)) {
      const [y, m, d, h = 0, min = 0, s = 0] = dateStr
      return new Date(y, m - 1, d, h, min, s)
    }

    // 提取时间部分（避免时区转换）- 支持 T 分隔符和空格分隔符
    const match = String(dateStr).match(/(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/)
    if (match) {
      const [, y, m, d, h, min, s] = match
      return new Date(Number(y), Number(m) - 1, Number(d), Number(h), Number(min), Number(s))
    }
    // 尝试直接解析
    return new Date(dateStr)
  } catch {
    return null
  }
}

/**
 * 格式化为完整的日期时间字符串
 * 示例：2026/07/21 15:36:42
 */
export const formatDateTime = (dateStr: string | null | undefined): string => {
  if (!dateStr) return ''
  const date = parseServerTime(dateStr)
  if (!date) return dateStr
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  const s = String(date.getSeconds()).padStart(2, '0')
  return `${y}/${m}/${d} ${h}:${min}:${s}`
}

/**
 * 格式化为时间字符串
 * 示例：15:36:42
 */
export const formatTime = (dateStr: string | null | undefined): string => {
  if (!dateStr) return ''
  const date = parseServerTime(dateStr)
  if (!date) return dateStr
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  const s = String(date.getSeconds()).padStart(2, '0')
  return `${h}:${min}:${s}`
}

/**
 * 格式化为相对时间
 * 示例：刚刚、5分钟前、2小时前、昨天
 */
export const formatRelativeTime = (dateStr: string | null | undefined): string => {
  if (!dateStr) return ''
  const date = parseServerTime(dateStr)
  if (!date) return dateStr

  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (seconds < 60) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  return formatDateTime(dateStr)
}
