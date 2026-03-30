import { test, expect } from './fixtures/base'
import {
  apiCreateKB,
  apiDeleteKB,
  apiUploadDocument,
  apiDeleteDocument,
  apiGetRecycleBin,
  apiRestoreDocument,
  pollRecycleBinHasDoc,
  uid,
  assertJson,
} from './helpers'

test.describe('Document Delete & Restore', () => {
  test('delete document moves to recycle bin', async ({ javaApi, userA }) => {
    test.setTimeout(240_000)
    const kb = await apiCreateKB(javaApi, userA.headers)
    const docId = await apiUploadDocument(
      javaApi,
      userA.headers,
      kb.id,
      `${uid('del')}.txt`,
      'Document to be deleted and restored',
    )

    await apiDeleteDocument(javaApi, userA.headers, docId)

    const recycled = await pollRecycleBinHasDoc(javaApi, userA.headers, docId)
    expect(recycled).toBeTruthy()

    // Cleanup — purge from recycle bin
    const purgeRes = await javaApi.delete(`document/${docId}/purge`, {
      headers: userA.headers,
    })
    const purgeBody = await assertJson(purgeRes)
    expect(purgeBody.code).toBe(200)

    await apiDeleteKB(javaApi, userA.headers, kb.id)
  })

  test('restore document makes it visible again', async ({ javaApi, userA }) => {
    test.setTimeout(480_000)
    const kb = await apiCreateKB(javaApi, userA.headers)
    const docId = await apiUploadDocument(
      javaApi,
      userA.headers,
      kb.id,
      `${uid('restore')}.txt`,
      'Document to restore from recycle bin',
    )

    await apiDeleteDocument(javaApi, userA.headers, docId)
    await pollRecycleBinHasDoc(javaApi, userA.headers, docId)
    await apiRestoreDocument(javaApi, userA.headers, docId)

    const res = await javaApi.get(`document/${docId}`, {
      headers: userA.headers,
    })
    const body = await assertJson(res)
    expect(body.code).toBe(200)
    expect(body.data.id).toBe(docId)

    // Cleanup — delete again, try to purge (best-effort), then delete KB
    await apiDeleteDocument(javaApi, userA.headers, docId)
    try {
      await pollRecycleBinHasDoc(javaApi, userA.headers, docId, { timeoutMs: 180_000 })
      await javaApi.delete(`document/${docId}/purge`, { headers: userA.headers })
    } catch {
      // Cleanup is best-effort; KB deletion will cascade if purge didn't complete
    }
    await apiDeleteKB(javaApi, userA.headers, kb.id)
  })

  test('recycle bin page is accessible', async ({ page, userA }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto('/document/recycle-bin')
    await page.waitForSelector('#app', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    const bodyText = await page.locator('body').innerText()
    expect(bodyText.length).toBeGreaterThan(0)
  })
})
