import { describe, expect, it } from 'vitest'
import { SseDataParser } from '../sse'

describe('SseDataParser', () => {
  it('parses data lines with a space after the colon', () => {
    const parser = new SseDataParser()

    expect(parser.push('data: hello\n')).toEqual([
      { type: 'data', data: 'hello' },
    ])
  })

  it('parses data lines without a space after the colon', () => {
    const parser = new SseDataParser()

    expect(parser.push('data:hello\n')).toEqual([
      { type: 'data', data: 'hello' },
    ])
  })

  it('keeps JSON payloads intact', () => {
    const parser = new SseDataParser()

    expect(parser.push('data: {"content":"Hello"}\n')).toEqual([
      { type: 'data', data: '{"content":"Hello"}' },
    ])
  })

  it('buffers a line split across network chunks', () => {
    const parser = new SseDataParser()

    expect(parser.push('data: {"content":"Hel')).toEqual([])
    expect(parser.push('lo"}\n')).toEqual([
      { type: 'data', data: '{"content":"Hello"}' },
    ])
  })

  it('returns multiple events from one network chunk', () => {
    const parser = new SseDataParser()

    expect(parser.push('data: one\ndata: two\n')).toEqual([
      { type: 'data', data: 'one' },
      { type: 'data', data: 'two' },
    ])
  })

  it('recognizes the stream completion marker', () => {
    const parser = new SseDataParser()

    expect(parser.push('data: [DONE]\n')).toEqual([{ type: 'done' }])
  })

  it('ignores comments, event fields, blank data, and blank lines', () => {
    const parser = new SseDataParser()

    expect(parser.push(': keepalive\nevent: message\ndata:\n\n')).toEqual([])
  })

  it('supports CRLF-delimited streams', () => {
    const parser = new SseDataParser()

    expect(parser.push('data: hello\r\ndata: [DONE]\r\n')).toEqual([
      { type: 'data', data: 'hello' },
      { type: 'done' },
    ])
  })

  it('flushes a final line when the stream closes without a newline', () => {
    const parser = new SseDataParser()

    expect(parser.push('data: final')).toEqual([])
    expect(parser.flush()).toEqual([{ type: 'data', data: 'final' }])
    expect(parser.flush()).toEqual([])
  })
})
