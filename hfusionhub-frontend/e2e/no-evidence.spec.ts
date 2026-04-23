import { test, expect } from './fixtures/base'
import {
  apiCreateKB,
  apiDeleteKB,
  apiCreateConversation,
  apiDeleteConversation,
  assertJson,
} from './helpers'

test.describe('No-evidence Answer', () => {
  // 无知识库会话走 Python /api/chat 全链路，实测单次响应约 37~46s；
  // 全量套件并发时可能更慢。60s 请求超时/90s 用例超时曾导致偶发失败，故放宽。
  test.setTimeout(180_000)

  test('empty KB returns response without sources', async ({ javaApi, userA }) => {
    const kb = await apiCreateKB(javaApi, userA.headers)
    const conv = await apiCreateConversation(javaApi, userA.headers, kb.id)

    const response = await javaApi.post('conversation/message', {
      headers: userA.headers,
      data: {
        conversationId: conv.id,
        content: 'What is the meaning of life?',
      },
      timeout: 120_000,
    })

    const body = await assertJson(response)
    expect(body.code).toBe(200)

    const assistantMsg = body.data
    expect(assistantMsg).toBeTruthy()
    expect(assistantMsg.role).toBe('assistant')

    await apiDeleteConversation(javaApi, userA.headers, conv.id)
    await apiDeleteKB(javaApi, userA.headers, kb.id)
  })

  test('chat with no KB returns response without sources', async ({ javaApi, userA }) => {
    const conv = await apiCreateConversation(javaApi, userA.headers)

    const response = await javaApi.post('conversation/message', {
      headers: userA.headers,
      data: {
        conversationId: conv.id,
        content: 'Tell me about quantum computing',
      },
      timeout: 120_000,
    })

    const body = await assertJson(response)
    expect(body.code).toBe(200)

    const msg = body.data
    expect(msg).toBeTruthy()

    await apiDeleteConversation(javaApi, userA.headers, conv.id)
  })
})
