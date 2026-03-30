import { test, expect } from './fixtures/base'
import {
  apiCreateKB,
  apiDeleteKB,
  apiUploadDocument,
  apiParseDocument,
  apiDeleteDocument,
  pollDocIndexing,
  uid,
  assertJson,
} from './helpers'

test.describe('Document Upload & Indexing', () => {
  test('upload document shows in list', async ({ page, userA, javaApi }) => {
    const kb = await apiCreateKB(javaApi, userA.headers)
    const docId = await apiUploadDocument(
      javaApi,
      userA.headers,
      kb.id,
      `${uid('doc')}.txt`,
      'This is test content for E2E document upload test.',
    )

    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto(`/knowledge-base/${kb.id}`)
    await page.waitForSelector('#app', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    await expect(page.locator('body')).toContainText(/\.txt/, { timeout: 15_000 })

    await apiDeleteDocument(javaApi, userA.headers, docId)
    await apiDeleteKB(javaApi, userA.headers, kb.id)
  })

  test('document indexing completes with mock LLM', async ({ javaApi, userA }) => {
    test.setTimeout(120_000)
    const kb = await apiCreateKB(javaApi, userA.headers)
    const docId = await apiUploadDocument(
      javaApi,
      userA.headers,
      kb.id,
      `${uid('idx')}.txt`,
      'Knowledge base content for indexing test. This document contains important information about AI agents and retrieval augmented generation.',
    )

    await apiParseDocument(javaApi, userA.headers, docId)

    const status = await pollDocIndexing(javaApi, userA.headers, docId, {
      timeoutMs: 60_000,
    })
    expect(status).toBe('COMPLETED')

    await apiDeleteDocument(javaApi, userA.headers, docId)
    await apiDeleteKB(javaApi, userA.headers, kb.id)
  })

  test('upload to different KBs are isolated', async ({ javaApi, userA }) => {
    const kb1 = await apiCreateKB(javaApi, userA.headers)
    const kb2 = await apiCreateKB(javaApi, userA.headers)

    const doc1 = await apiUploadDocument(javaApi, userA.headers, kb1.id, 'kb1_doc.txt', 'Content for KB1')
    const doc2 = await apiUploadDocument(javaApi, userA.headers, kb2.id, 'kb2_doc.txt', 'Content for KB2')

    const res1 = await javaApi.get(`document/${doc1}`, { headers: userA.headers })
    const body1 = await assertJson(res1)
    expect(body1.data.knowledgeBaseId).toBe(kb1.id)

    const res2 = await javaApi.get(`document/${doc2}`, { headers: userA.headers })
    const body2 = await assertJson(res2)
    expect(body2.data.knowledgeBaseId).toBe(kb2.id)

    await apiDeleteDocument(javaApi, userA.headers, doc1)
    await apiDeleteDocument(javaApi, userA.headers, doc2)
    await apiDeleteKB(javaApi, userA.headers, kb1.id)
    await apiDeleteKB(javaApi, userA.headers, kb2.id)
  })
})
