export type SseDataEvent =
  | { type: 'data'; data: string }
  | { type: 'done' }

export class SseDataParser {
  private buffer = ''

  push(chunk: string): SseDataEvent[] {
    this.buffer += chunk
    const lines = this.buffer.split('\n')
    this.buffer = lines.pop() || ''
    return lines.flatMap((line) => this.parseLine(line))
  }

  flush(): SseDataEvent[] {
    if (!this.buffer) return []
    const line = this.buffer
    this.buffer = ''
    return this.parseLine(line)
  }

  private parseLine(rawLine: string): SseDataEvent[] {
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine
    if (!line.startsWith('data:')) return []

    const data = line.slice(5).trim()
    if (!data) return []
    if (data === '[DONE]') return [{ type: 'done' }]
    return [{ type: 'data', data }]
  }
}

/** JSON 化 SSE 数据事件：解析结果传给 onData；类型不匹配/非 JSON 行被忽略。 */
export interface SseJsonEvent<T = unknown> {
  type?: string
  data?: T
}

export interface ConsumeSseStreamOptions<T> {
  /** 附加请求头（如鉴权 token） */
  headers?: Record<string, string>
  /** 外部取消信号（主动 abort 不触发 onError） */
  signal?: AbortSignal
  /**
   * 仅当 JSON 事件体的 type 字段等于该值时回调 onData。
   * 留空则所有 JSON 事件都回调。
   */
  eventType?: string
  /** 每条匹配的 JSON 数据事件回调 */
  onData: (event: SseJsonEvent<T>) => void
  /** 流正常结束（收到 [DONE] 或服务端断开）回调 */
  onDone?: () => void
  /** 非主动取消的错误回调 */
  onError?: (error: Error) => void
}

/**
 * 统一的 SSE 消费入口：负责 fetch/reader/文本解码/行缓冲，
 * 行解析复用 {@link SseDataParser}，再把 JSON 数据事件分发到 onData。
 *
 * 与 chat 流共用同一套解析器（SseDataParser 行为不变），避免各调用方
 * 手写 buffer/line 解析（approval 流曾重复实现）。
 */
export async function consumeSseJsonStream<T = unknown>(
  url: string,
  options: ConsumeSseStreamOptions<T>,
): Promise<void> {
  const parser = new SseDataParser()
  try {
    const res = await fetch(url, {
      headers: options.headers,
      signal: options.signal,
    })
    if (!res.ok || !res.body) throw new Error(`SSE 连接失败 (${res.status})`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      const events = parser.push(decoder.decode(value, { stream: true }))
      for (const event of events) {
        if (event.type === 'done') {
          options.onDone?.()
          return
        }
        if (event.type !== 'data') continue
        const text = event.data
        if (!text) continue
        let parsed: unknown
        try {
          parsed = JSON.parse(text)
        } catch {
          continue // 非 JSON 数据行（如心跳）忽略
        }
        if (options.eventType && (parsed as SseJsonEvent<T>).type !== options.eventType) continue
        options.onData(parsed as SseJsonEvent<T>)
      }
    }

    options.onDone?.()
  } catch (error) {
    if (options.signal?.aborted) return // 主动取消不视为错误
    options.onError?.(error instanceof Error ? error : new Error('SSE 连接中断'))
  }
}
