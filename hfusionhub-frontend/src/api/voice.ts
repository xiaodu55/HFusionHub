import { get } from './request'
import type { ApiResponse } from './types'

/** 语音能力开关（Batch 10，VOICE_ENABLED 默认关闭时按钮不渲染） */
export interface VoiceStatus {
  enabled: boolean
  stt: boolean
  tts: boolean
}

export const getVoiceStatus = (): Promise<ApiResponse<VoiceStatus>> => get('/voice/status')

/** 语音转文本：上传原始音频字节（octet-stream），返回识别文本 */
export const transcribeAudio = async (
  audio: Blob,
  filename = 'audio.webm',
  language?: string,
): Promise<string> => {
  const response = await fetch(
    `/api/voice/transcribe${language ? `?language=${encodeURIComponent(language)}` : ''}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-Audio-Filename': filename,
      },
      body: audio,
    },
  )
  if (!response.ok) {
    throw new Error(`语音识别失败（HTTP ${response.status}）`)
  }
  const result = (await response.json()) as ApiResponse<{ text: string }>
  return result.data?.text ?? ''
}

/** 文本转语音：返回可播放的音频 Blob URL（调用方负责 revoke） */
export const synthesizeSpeech = async (text: string, voice?: string): Promise<string> => {
  const response = await fetch('/api/voice/synthesize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice }),
  })
  if (!response.ok) {
    throw new Error(`语音合成失败（HTTP ${response.status}）`)
  }
  const blob = await response.blob()
  return URL.createObjectURL(blob)
}
