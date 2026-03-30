import { test, expect } from './fixtures/base'
import {
  apiCreateKB,
  apiDeleteKB,
  apiCreateConversation,
  apiDeleteConversation,
  assertJson,
} from './helpers'

test.describe('No-evidence Answer', () => {
  test('empty KB returns response without sources', async ({ javaApi, userA }) => {
    const kb = await apiCreateKB(javaApi, userA.headers)
    const conv = await apiCreateConversation(javaApi, userA.headers, kb.id)

    const response = await javaApi.post('conversation/message', {
      headers: userA.headers,
      data: {
        conversationId: conv.id,
        content: 'What is the meaning of life?',
      },
      timeout: 60_000,
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
      timeout: 60_000,
    })

    const body = await assertJson(response)
    expect(body.code).toBe(200)

    const msg = body.data
    expect(msg).toBeTruthy()

    await apiDeleteConversation(javaApi, userA.headers, conv.id)
  })
})
