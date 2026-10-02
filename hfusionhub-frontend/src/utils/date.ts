/**
 * 时间显示的唯一入口。
 *
 * 服务端契约（2026-10-10 实测，见 CHANGELOG 第九十五批）：
 * - java：实体字段全是 LocalDateTime，Jackson 出的是**无偏移** ISO（`2026-10-10T11:58:12`），
 *   而 java 容器里 `ZoneId.systemDefault()` 实测为 GMT ⇒ 无偏移串要按 UTC 读。
 * - python：`datetime.now(UTC).isoformat()` 带 `+00:00`、`strftime(...Z)` 带 `Z`、
 *   另有少数 `strftime("%Y-%m-%dT%H:%M:%S")` 是无偏移 UTC —— 有偏移的按偏移读，无偏移的仍按 UTC。
 * - 纯日期（`2026-10-10`，无时分秒）是日历日：按当地零点构造、不做位移——位移会让它在
 *   西区浏览器落到前一天。
 *
 * 渲染一律用浏览器本地时区：不把任何国家偏移写进代码（国内浏览器自然得到 +8）。
 */

const NAIVE_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.(\d+))?$/
const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/

const pad = (value: number) => String(value).padStart(2, '0')

/**
 * 把服务端时间转成瞬时。
 *
 * 支持格式：ISO 字符串（带或不带偏移）、`Z` 后缀、空格分隔、数组格式 [y, m, d, h, min, s]。
 */
export const parseServerTime = (value: string | number[] | null | undefined): Date | null => {
  if (value === null || value === undefined || value === '') return null

  if (Array.isArray(value)) {
    const [y, m, d, h = 0, min = 0, s = 0] = value
    return new Date(Date.UTC(y, m - 1, d, h, min, s))
  }

  const text = String(value).trim()

  // 纯日期：按本地日历日构造，避免"UTC 零点在西区浏览器落到前一天"
  const dateOnly = DATE_ONLY_RE.exec(text)
  if (dateOnly) {
    const [, y, m, d] = dateOnly
    return new Date(Number(y), Number(m) - 1, Number(d))
  }

  // 无偏移：按 UTC 构造瞬时（服务端写的就是 UTC 墙钟）
  const naive = NAIVE_RE.exec(text)
  if (naive) {
    const [, y, m, d, h, min, s, fraction] = naive
    const millis = fraction ? Number(fraction.slice(0, 3).padEnd(3, '0')) : 0
    return new Date(Date.UTC(Number(y), Number(m) - 1, Number(d), Number(h), Number(min), Number(s ?? 0), millis))
  }

  // 带偏移（+00:00 / Z / +08:00）：原生解析即尊重偏移
  const parsed = new Date(text)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

/**
 * 格式化为完整的日期时间（本地时区）
 * 示例：2026/10/21 15:36:42
 */
export const formatDateTime = (dateStr: string | number[] | null | undefined): string => {
  if (!dateStr) return ''
  const date = parseServerTime(dateStr)
  if (!date) return String(dateStr)
  const y = date.getFullYear()
  const m = pad(date.getMonth() + 1)
  const d = pad(date.getDate())
  const h = pad(date.getHours())
  const min = pad(date.getMinutes())
  const s = pad(date.getSeconds())
  return `${y}/${m}/${d} ${h}:${min}:${s}`
}

/**
 * 格式化为日历日期（本地时区），不带时分秒
 */
export const formatDateOnly = (dateStr: string | number[] | null | undefined): string => {
  if (!dateStr) return ''
  const date = parseServerTime(dateStr)
  if (!date) return String(dateStr)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

/**
 * 格式化为时间字符串（本地时区）
 * 示例：15:36:42
 */
export const formatTime = (dateStr: string | number[] | null | undefined): string => {
  if (!dateStr) return ''
  const date = parseServerTime(dateStr)
  if (!date) return String(dateStr)
  const h = pad(date.getHours())
  const min = pad(date.getMinutes())
  const s = pad(date.getSeconds())
  return `${h}:${min}:${s}`
}

/**
 * 格式化为相对时间
 * 示例：刚刚、5分钟前、2小时前、昨天
 */
export const formatRelativeTime = (dateStr: string | number[] | null | undefined): string => {
  if (!dateStr) return ''
  const date = parseServerTime(dateStr)
  if (!date) return String(dateStr)

  const diff = Date.now() - date.getTime()
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
