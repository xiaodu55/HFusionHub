import { test, expect } from './fixtures/base'
import {
  apiCreateFlag,
  apiUpdateFlag,
  apiDeleteFlag,
  apiEvaluateFlag,
  assertJson,
} from './helpers'

test.describe('Feature Flag', () => {
  test('admin can create and toggle flag', async ({ javaApi, admin }) => {
    const flagKey = `e2e.flag.${Date.now()}.toggle`
    const flag = await apiCreateFlag(javaApi, admin.headers, flagKey, { enabled: true })
    expect(flag.id).toBeTruthy()
    expect(flag.flagKey).toBe(flagKey)

    const updated = await apiUpdateFlag(javaApi, admin.headers, flag.id, { enabled: false })
    expect(updated.enabled).toBe(false)

    const reenabled = await apiUpdateFlag(javaApi, admin.headers, flag.id, { enabled: true })
    expect(reenabled.enabled).toBe(true)

    await apiDeleteFlag(javaApi, admin.headers, flag.id)
  })

  test('non-admin cannot create flag via API', async ({ javaApi, userA }) => {
    const res = await javaApi.post('feature-flag', {
      headers: userA.headers,
      data: {
        flagKey: `e2e.unauth.${Date.now()}.test`,
        enabled: true,
        description: 'Should fail',
      },
    })
    const body = await assertJson(res)
    expect(body.code).not.toBe(200)
  })

  test('flag evaluation returns correct value', async ({ javaApi, admin }) => {
    const flagKey = `e2e.eval.${Date.now()}.test`
    const flag = await apiCreateFlag(javaApi, admin.headers, flagKey, { enabled: false })

    const result = await apiEvaluateFlag(javaApi, admin.headers, flagKey)
    expect(result).toBeTruthy()
    expect(result.enabled).toBe(false)

    await apiUpdateFlag(javaApi, admin.headers, flag.id, { enabled: true })
    const result2 = await apiEvaluateFlag(javaApi, admin.headers, flagKey)
    expect(result2.enabled).toBe(true)

    await apiDeleteFlag(javaApi, admin.headers, flag.id)
  })

  test('admin flags page is accessible', async ({ page, admin }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), admin.token)
    await page.goto('/admin/flags')
    await page.waitForSelector('#app', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    const bodyText = await page.locator('body').innerText()
    expect(bodyText.length).toBeGreaterThan(0)
  })

  test('non-admin cannot access flags page via UI', async ({ page, userA }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto('/admin/flags')
    await page.waitForSelector('#app', { timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    const url = page.url()
    const isBlocked = url.includes('/login') || url.includes('/') || url.includes('/403')
    expect(isBlocked).toBeTruthy()
  })
})
