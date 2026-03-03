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
