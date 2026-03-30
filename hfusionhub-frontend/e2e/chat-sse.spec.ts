import { test, expect } from './fixtures/base'
import {
  apiCreateKB,
  apiDeleteKB,
  apiCreateConversation,
  apiDeleteConversation,
  uid,
  assertJson,
} from './helpers'

test.describe('Chat SSE', () => {
  test('send message and receive SSE response', async ({ javaApi, userA, page }) => {
    test.setTimeout(120_000)
    const kb = await apiCreateKB(javaApi, userA.headers)
    const conv = await apiCreateConversation(javaApi, userA.headers, kb.id)

    await page.goto('/')
    const text = await page.evaluate(async ({ token, convId }) => {
      const res = await fetch('http://localhost:8080/api/conversation/message/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'satoken': token,
        },
        body: JSON.stringify({
          conversationId: convId,
          content: 'Hello, this is an E2E test message',
          requestId: `sse_${Date.now()}`,
        }),
      })
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let result = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        result += decoder.decode(value)
        if (result.includes('[DONE]')) break
      }
      return result
    }, { token: userA.token, convId: conv.id })

    expect(text).toContain('data:')

    const msgsRes = await javaApi.get(`conversation/${conv.id}/messages`, {
      headers: userA.headers,
    })
    const msgsBody = await assertJson(msgsRes)
    expect(msgsBody.code).toBe(200)
    expect(msgsBody.data.length).toBeGreaterThanOrEqual(1)

    await apiDeleteConversation(javaApi, userA.headers, conv.id)
    await apiDeleteKB(javaApi, userA.headers, kb.id)
  })

  test('SSE response contains [DONE] marker', async ({ javaApi, userA }) => {
    const conv = await apiCreateConversation(javaApi, userA.headers)

    const response = await javaApi.post('conversation/message/stream', {
      headers: {
        ...userA.headers,
        'Accept': 'text/event-stream',
      },
      data: {
        conversationId: conv.id,
        content: 'Test SSE done marker',
        requestId: uid('sse_done'),
      },
      timeout: 120_000,
    })

    const text = await response.text()
    expect(text).toContain('[DONE]')

    await apiDeleteConversation(javaApi, userA.headers, conv.id)
  })

  test('chat detail page renders', async ({ page, userA, javaApi }) => {
    const conv = await apiCreateConversation(javaApi, userA.headers)

    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto(`/chat/${conv.id}`)
    await page.waitForSelector('#app', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    const bodyText = await page.locator('body').innerText()
    expect(bodyText.length).toBeGreaterThan(0)

    await apiDeleteConversation(javaApi, userA.headers, conv.id)
  })
})
