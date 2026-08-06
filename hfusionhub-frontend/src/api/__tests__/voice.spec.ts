import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { synthesizeSpeech, transcribeAudio } from '../voice'

const fetchMock = vi.fn()

describe('voice API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('transcribes audio bytes with language hint and returns text', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ code: 200, data: { text: '你好' } }), { status: 200 }),
    )

    const text = await transcribeAudio(new Blob(['audio']), 'rec.webm', 'zh-CN')

    expect(text).toBe('你好')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/voice/transcribe?language=zh-CN')
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/octet-stream')
    expect(init.headers['X-Audio-Filename']).toBe('rec.webm')
  })

  it('omits the language param when not provided', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ code: 200, data: { text: 'hi' } }), { status: 200 }),
    )

    await transcribeAudio(new Blob(['audio']))

    expect(fetchMock.mock.calls[0][0]).toBe('/api/voice/transcribe')
  })

  it('throws a readable error on non-ok response', async () => {
    fetchMock.mockResolvedValue(new Response('disabled', { status: 503 }))

    await expect(transcribeAudio(new Blob(['audio']))).rejects.toThrow('语音识别失败（HTTP 503）')
  })

  it('synthesizes speech into a blob object URL', async () => {
    const createObjectURL = vi.fn(() => 'blob:mock-audio')
    vi.stubGlobal('URL', { createObjectURL })
    fetchMock.mockResolvedValue(
      new Response(new Blob(['mp3']), { status: 200, headers: { 'Content-Type': 'audio/mpeg' } }),
    )

    const url = await synthesizeSpeech('你好', 'alloy')

    expect(url).toBe('blob:mock-audio')
    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ text: '你好', voice: 'alloy' })
  })
})
