import { afterEach, describe, expect, it, vi } from 'vitest'
import { SseDataParser, consumeSseJsonStream } from '../sse'

afterEach(() => {
  vi.unstubAllGlobals()
})

function sseResponse(...chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(stream, { status: 200 })
}

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

describe('consumeSseJsonStream', () => {
  it('reuses the parser to deliver JSON SSE events', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse('data: {"type":"snapshot","data":[{"id":1}]}\ndata: {"type":"approval","data":{"id":2}}\n'),
      ),
    )
    const onData = vi.fn()
    await consumeSseJsonStream('/test', { onData })
    expect(onData).toHaveBeenCalledTimes(2)
    expect(onData).toHaveBeenNthCalledWith(1, { type: 'snapshot', data: [{ id: 1 }] })
    expect(onData).toHaveBeenNthCalledWith(2, { type: 'approval', data: { id: 2 } })
  })

  it('buffers lines split across network chunks', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(sseResponse('data: {"type":"snap', 'shot","data":[1]}\ndata: {"type":"approval"}\n')),
    )
    const onData = vi.fn()
    await consumeSseJsonStream('/test', { onData })
    expect(onData).toHaveBeenCalledTimes(2)
    expect(onData).toHaveBeenNthCalledWith(1, { type: 'snapshot', data: [1] })
    expect(onData).toHaveBeenNthCalledWith(2, { type: 'approval' })
  })

  it('filters events by eventType', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse('data: {"type":"snapshot","data":[]}\ndata: {"type":"approval","data":{"id":2}}\n'),
      ),
    )
    const onData = vi.fn()
    await consumeSseJsonStream('/test', { eventType: 'approval', onData })
    expect(onData).toHaveBeenCalledTimes(1)
    expect(onData).toHaveBeenCalledWith({ type: 'approval', data: { id: 2 } })
  })

  it('ignores non-JSON lines and fires onDone on [DONE]', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(sseResponse('data: keepalive\ndata: {"type":"approval"}\ndata: [DONE]\n')),
    )
    const onData = vi.fn()
    const onDone = vi.fn()
    await consumeSseJsonStream('/test', { onData, onDone })
    expect(onData).toHaveBeenCalledTimes(1)
    expect(onData).toHaveBeenCalledWith({ type: 'approval' })
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('fires onError for failed connections', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 500 })))
    const onError = vi.fn()
    await consumeSseJsonStream('/test', { onError, onData: () => {} })
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('does not fire onError when aborted externally', async () => {
    const controller = new AbortController()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((_url: string, _init?: RequestInit) => {
        controller.abort()
        return Promise.reject(new DOMException('Aborted', 'AbortError'))
      }),
    )
    const onError = vi.fn()
    await consumeSseJsonStream('/test', { signal: controller.signal, onError, onData: () => {} })
    expect(onError).not.toHaveBeenCalled()
  })
})
