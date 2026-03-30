import { test, expect } from './fixtures/base'
import { apiCreateKB, apiDeleteKB, uid, assertJson } from './helpers'

test.describe('Knowledge Base Management', () => {
  test('create KB appears in list', async ({ page, userA, javaApi }) => {
    const kbName = uid('kb')
    const kb = await apiCreateKB(javaApi, userA.headers, kbName)

    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto('/knowledge-base')
    await page.waitForSelector('#app', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    // Use heading selector to avoid strict mode violation (name appears in both heading and description)
    await expect(page.getByRole('heading', { name: kbName })).toBeVisible({ timeout: 15_000 })

    await apiDeleteKB(javaApi, userA.headers, kb.id)
  })

  test('non-owner cannot access KB detail via API', async ({ javaApi, userA, userB }) => {
    const kb = await apiCreateKB(javaApi, userA.headers)

    const res = await javaApi.get(`knowledge-base/${kb.id}`, {
      headers: userB.headers,
    })
    const body = await assertJson(res)
    expect(body.code).not.toBe(200)

    await apiDeleteKB(javaApi, userA.headers, kb.id)
  })

  test('KB detail page shows KB info', async ({ page, userA, javaApi }) => {
    const kbName = uid('kb_detail')
    const kb = await apiCreateKB(javaApi, userA.headers, kbName)

    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto(`/knowledge-base/${kb.id}`)
    await page.waitForSelector('#app', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    await expect(page.getByRole('heading', { name: kbName })).toBeVisible({ timeout: 15_000 })

    await apiDeleteKB(javaApi, userA.headers, kb.id)
  })

  test('KB list page loads', async ({ page, userA }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto('/knowledge-base')
    await page.waitForSelector('#app', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    const bodyText = await page.locator('body').innerText()
    expect(bodyText.length).toBeGreaterThan(0)
  })
})
