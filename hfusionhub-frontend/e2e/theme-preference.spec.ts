import { test, expect } from '@playwright/test'

test.describe('Theme Preference', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/login')
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', process.env.ADMIN_PASSWORD || 'test123')
    await page.click('button:has-text("登录")')
    await page.waitForURL('**/dashboard')
  })

  test('should switch theme and persist to server', async ({ page }) => {
    // Navigate to settings
    await page.goto('http://localhost:3000/settings')
    await expect(page.locator('h1:has-text("设置")')).toBeVisible()

    // Find theme toggle buttons
    const lightBtn = page.locator('button:has-text("浅色")')
    const darkBtn = page.locator('button:has-text("深色")')
    const systemBtn = page.locator('button:has-text("跟随系统")')

    // Switch to dark
    await darkBtn.click()
    await page.waitForTimeout(500)
    await expect(page.locator('html')).toHaveClass(/dark/)

    // Switch to light
    await lightBtn.click()
    await page.waitForTimeout(500)
    await expect(page.locator('html')).not.toHaveClass(/dark/)

    // Switch to system
    await systemBtn.click()
    await page.waitForTimeout(500)

    // Reload page and verify theme persists
    await page.reload()
    await page.waitForLoadState('networkidle')

    // Theme should be restored from server
    const userInfoResponse = await page.waitForResponse(response =>
      response.url().includes('/api/user/info') && response.status() === 200
    )
    const userInfo = await userInfoResponse.json()
    expect(userInfo.data).toHaveProperty('themePreference')
  })

  test('should sync theme across devices (simulated)', async ({ page, context }) => {
    // Set theme to dark in first session
    await page.goto('http://localhost:3000/settings')
    await page.locator('button:has-text("深色")').click()
    await page.waitForTimeout(500)

    // Open new page (simulating different device)
    const page2 = await context.newPage()
    await page2.goto('http://localhost:3000/login')
    await page2.fill('input[type="text"]', 'admin')
    await page2.fill('input[type="password"]', process.env.ADMIN_PASSWORD || 'test123')
    await page2.click('button:has-text("登录")')
    await page2.waitForURL('**/dashboard')

    // Theme should be dark (from server)
    await expect(page2.locator('html')).toHaveClass(/dark/)
  })
})
