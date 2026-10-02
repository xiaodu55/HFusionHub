import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'

import { formatDateOnly, formatDateTime, formatRelativeTime, formatTime, parseServerTime } from '../date'

// 2026-10-10T11:58:12Z。java（Jackson + LocalDateTime）发的是无偏移 ISO，python 的
// datetime.now(UTC).isoformat() 带 +00:00、strftime(...Z) 带 Z、少数 strftime 无偏移——
// 它们指向同一个瞬间，所以断言只能落在瞬时上。
const UTC_MS = Date.UTC(2026, 9, 10, 11, 58, 12)

// tsconfig.app.json 的 types 只有 vite/client（不为此拖进 @types/node），运行时仍是 node。
const nodeEnv = (globalThis as unknown as { process: { env: Record<string, string | undefined> } }).process.env

// node 在第一次构造 Date/Intl 时就缓存了本地时区：之后 `delete process.env.TZ` 并不会
// 回到宿主时区，而是停在最后一次显式设置的值（实测停在 America/New_York）。所以复原必须
// 把宿主时区名**写回去**，否则本文件里跑在最后一个 withTz 之后的用例会在错误的时区下断言。
const HOST_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone

const withTz = (tz: string, fn: () => void) => {
  nodeEnv.TZ = tz
  try {
    fn()
  } finally {
    nodeEnv.TZ = HOST_ZONE
  }
}

const currentZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone

describe('parseServerTime — 契约：无偏移一律按 UTC 解释', () => {
  it('java naive ISO ⇒ UTC 瞬时', () => {
    expect(parseServerTime('2026-10-10T11:58:12')?.getTime()).toBe(UTC_MS)
  })

  it('空格分隔 ⇒ UTC 瞬时', () => {
    expect(parseServerTime('2026-10-10 11:58:12')?.getTime()).toBe(UTC_MS)
  })

  it('python isoformat +00:00 ⇒ 同一瞬时', () => {
    expect(parseServerTime('2026-10-10T11:58:12+00:00')?.getTime()).toBe(UTC_MS)
  })

  it('python strftime Z 后缀 ⇒ 同一瞬时', () => {
    expect(parseServerTime('2026-10-10T11:58:12Z')?.getTime()).toBe(UTC_MS)
  })

  it('自带 +08:00 偏移的串按偏移读，不再叠加位移', () => {
    expect(parseServerTime('2026-10-10T19:58:12+08:00')?.getTime()).toBe(UTC_MS)
  })

  it('无偏移带毫秒：小数部分保留，不参与位移', () => {
    expect(parseServerTime('2026-10-10T11:58:12.500')?.getTime()).toBe(UTC_MS + 500)
  })

  it('数组形式 [y,m,d,h,min,s] 与无偏移字符串同一规则', () => {
    expect(parseServerTime([2026, 10, 10, 11, 58, 12] as unknown as string)?.getTime()).toBe(UTC_MS)
  })

  it('纯日期 2026-10-10 是日历日，不做位移', () => {
    expect(parseServerTime('2026-10-10')?.getTime()).toBe(new Date(2026, 9, 10).getTime())
  })

  it('空值与不可解析返回 null，由调用方决定占位', () => {
    expect(parseServerTime(null)).toBeNull()
    expect(parseServerTime('')).toBeNull()
    expect(parseServerTime('尚未登录')).toBeNull()
  })
})

// 分隔符不在本批断言范围内：本批只修"显示的到底是哪个瞬间"，不改显示格式。
describe('渲染 — 按浏览器本地时区，不写死任何国家偏移', () => {
  it('TZ=Asia/Shanghai 时，无偏移的 UTC 值显示为 +8', () => {
    withTz('Asia/Shanghai', () => {
      expect(formatDateTime('2026-10-10T11:58:12')).toContain('19:58:12')
      expect(formatTime('2026-10-10T11:58:12')).toBe('19:58:12')
    })
  })

  it('TZ=America/New_York 时同一个值显示为 -4（证明没把 +08:00 编进代码）', () => {
    withTz('America/New_York', () => {
      expect(formatDateTime('2026-10-10T11:58:12')).toContain('07:58:12')
    })
  })

  it('纯日期在任何时区都落在同一天', () => {
    for (const tz of ['Asia/Shanghai', 'America/New_York', 'UTC']) {
      withTz(tz, () => {
        const rendered = formatDateOnly('2026-10-10')
        expect(rendered).toMatch(/2026\D10\D10/)
        expect(rendered).not.toContain(':')
      })
    }
  })

  it('空值返回空串，不可解析原样返回而不是 Invalid Date', () => {
    expect(formatDateTime('')).toBe('')
    expect(formatTime(null)).toBe('')
    expect(formatDateTime('尚未登录')).toBe('尚未登录')
  })

  // 上一条断言之后的用例都跑在这个 describe 留下的时区里，所以先钉住"夹具不漏"：
  // 用 delete 复原是假的（node 已缓存本地时区），最后一个 withTz 的时区会留在进程里。
  it('withTz 把时区还给宿主，后续用例不继承上一个用例的时区', () => {
    expect(currentZone()).toBe(HOST_ZONE)
  })
})

describe('formatRelativeTime — 相对量基于瞬时，不是字符串', () => {
  beforeAll(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(Date.UTC(2026, 9, 10, 12, 3, 12)))
  })
  afterAll(() => {
    vi.useRealTimers()
  })

  it('5 分钟前', () => {
    expect(formatRelativeTime('2026-10-10T11:58:12')).toBe('5分钟前')
  })

  it('刚刚', () => {
    expect(formatRelativeTime('2026-10-10T12:02:40')).toBe('刚刚')
  })
})
