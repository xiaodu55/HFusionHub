import { test, expect } from '@playwright/test'

test.describe('Demo Data Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/login')
    await page.fill('input[type="text"]', 'admin')
    // CI（e2e.yml）种子管理员密码为 admin123；本地跑传 ADMIN_PASSWORD 覆盖
    await page.fill('input[type="password"]', process.env.ADMIN_PASSWORD || 'admin123')
    await page.click('button:has-text("登录")')
    // 登录后跳首页（无 /dashboard 路由）
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 15_000 })
  })

  test('should import demo data successfully', async ({ page }) => {
    await page.goto('http://localhost:3000/')

    // Find and click import demo data button
    const importButton = page.getByRole('button', { name: '导入演示数据', exact: true })
    await expect(importButton).toBeVisible()
    await importButton.click()

    // Wait for import API response
    const importResponse = await page.waitForResponse(response =>
      response.url().includes('/api/demo/import') && response.status() === 200
    )
    const result = await importResponse.json()

    // Verify success: per-section result panel renders (新增/已存在 counts)
    await expect(page.locator('li:has-text("知识库文档")')).toBeVisible({ timeout: 10000 })

    // Check sections are reported
    expect(result.data.sections).toBeDefined()
    expect(result.data.sections.length).toBeGreaterThan(0)
  })

  test('should show demo data in various pages after import', async ({ page }) => {
    // Import demo data first
    await page.goto('http://localhost:3000/')
    await page.getByRole('button', { name: '导入演示数据', exact: true }).click()
    await page.waitForResponse(response =>
      response.url().includes('/api/demo/import') && response.status() === 200
    )
    await page.waitForTimeout(2000)

    // Check knowledge base has demo data
    await page.goto('http://localhost:3000/knowledge-base')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: '演示知识库', exact: true })).toBeVisible({ timeout: 5000 })

    // Check prompts have demo templates
    await page.goto('http://localhost:3000/builder/prompts')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('客服答疑').first()).toBeVisible({ timeout: 5000 })

    // Check notes have demo entries
    await page.goto('http://localhost:3000/notes')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('周会纪要').first()).toBeVisible({ timeout: 5000 })

    // Check memory has demo entries
    await page.goto('http://localhost:3000/memory')
    await page.waitForLoadState('networkidle')
    const memoryCards = page.locator('[class*="rounded"]').filter({ hasText: /偏好|实体/ })
    await expect(memoryCards.first()).toBeVisible({ timeout: 5000 })
  })

  test('should clear demo data with confirmation', async ({ page }) => {
    // First import demo data
    await page.goto('http://localhost:3000/')
    await page.getByRole('button', { name: '导入演示数据', exact: true }).click()
    await page.waitForResponse(response =>
      response.url().includes('/api/demo/import') && response.status() === 200
    )
    await page.waitForTimeout(2000)

    // Click clear demo data button（当前 UI 直接执行，无确认对话框）
    // 先等导入的 refresh 完成（分项面板渲染 = importing 已复位），再点清除
    await expect(page.locator('li:has-text("知识库文档")')).toBeVisible({ timeout: 20_000 })
    const clearButton = page.getByRole('button', { name: '清除演示数据', exact: true })
    await expect(clearButton).toBeEnabled({ timeout: 30_000 })
    await clearButton.click()

    // Wait for delete API response
    // 清除走 POST /demo/clear（非 DELETE）
    await page.waitForResponse(response =>
      response.url().includes('/api/demo/clear') &&
      response.request().method() === 'POST' &&
      response.status() === 200
    )

    // Verify demo KB is removed from the list
    await page.goto('http://localhost:3000/knowledge-base')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: '演示知识库', exact: true })).not.toBeVisible({ timeout: 5000 })
  })
})
