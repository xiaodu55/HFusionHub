import { test, expect } from '@playwright/test'

test.describe('Theme Preference', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/login')
    await page.fill('input[type="text"]', 'admin')
    // CI（e2e.yml）种子管理员密码为 admin123；本地跑传 ADMIN_PASSWORD 覆盖
    await page.fill('input[type="password"]', process.env.ADMIN_PASSWORD || 'admin123')
    await page.click('button:has-text("登录")')
    // 登录后跳首页（无 /dashboard 路由）
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 15_000 })
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

    // Reload page and verify theme persists（先挂响应监听再 reload，避免错过事件）
    const userInfoResponse = page.waitForResponse(
      (response) => response.url().includes('/api/user/info') && response.status() === 200,
    )
    await page.reload()
    const userInfo = await (await userInfoResponse).json()
    expect(userInfo.data).toHaveProperty('themePreference')
    await page.waitForLoadState('networkidle')
  })

  test('should sync theme across devices (simulated)', async ({ page, context }) => {
    // Set theme to dark in first session
    await page.goto('http://localhost:3000/settings')
    await page.locator('button:has-text("深色")').click()
    await page.waitForTimeout(500)
    await expect(page.locator('html')).toHaveClass(/dark/)

    // 同 context 新页面共享登录态（模拟另一设备已登录）：
    // 主题偏好已持久化到服务端，新页面加载后应为 dark
    const page2 = await context.newPage()
    await page2.goto('http://localhost:3000/settings')
    await expect(page2.locator('html')).toHaveClass(/dark/)
  })
})
