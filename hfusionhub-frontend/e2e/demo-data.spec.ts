import { test, expect } from '@playwright/test'

test.describe('Demo Data Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/login')
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', process.env.ADMIN_PASSWORD || 'test123')
    await page.click('button:has-text("登录")')
    await page.waitForURL('**/dashboard')
  })

  test('should import demo data successfully', async ({ page }) => {
    await page.goto('http://localhost:3000/settings')

    // Find and click import demo data button
    const importButton = page.locator('button:has-text("导入演示数据")')
    await expect(importButton).toBeVisible()
    await importButton.click()

    // Wait for import API response
    const importResponse = await page.waitForResponse(response =>
      response.url().includes('/api/demo/import') && response.status() === 200
    )
    const result = await importResponse.json()

    // Verify success message
    await expect(page.locator('text=/导入成功/')).toBeVisible({ timeout: 10000 })

    // Check sections are reported
    expect(result.data.sections).toBeDefined()
    expect(result.data.sections.length).toBeGreaterThan(0)
  })

  test('should show demo data in various pages after import', async ({ page }) => {
    // Import demo data first
    await page.goto('http://localhost:3000/settings')
    await page.locator('button:has-text("导入演示数据")').click()
    await page.waitForResponse(response =>
      response.url().includes('/api/demo/import') && response.status() === 200
    )
    await page.waitForTimeout(2000)

    // Check knowledge base has demo data
    await page.goto('http://localhost:3000/knowledge')
    await page.waitForLoadState('networkidle')
    const kbCards = page.locator('[data-testid="kb-card"], .rounded-xl:has-text("演示")')
    await expect(kbCards.first()).toBeVisible({ timeout: 5000 })

    // Check prompts have demo templates
    await page.goto('http://localhost:3000/prompt')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('text=/客服答疑|文档总结|代码审查/')).toBeVisible({ timeout: 5000 })

    // Check notes have demo entries
    await page.goto('http://localhost:3000/notes')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('text=/周会纪要|RAG/')).toBeVisible({ timeout: 5000 })

    // Check memory has demo entries
    await page.goto('http://localhost:3000/memory')
    await page.waitForLoadState('networkidle')
    const memoryCards = page.locator('[class*="rounded"]').filter({ hasText: /偏好|实体/ })
    await expect(memoryCards.first()).toBeVisible({ timeout: 5000 })
  })

  test('should clear demo data with confirmation', async ({ page }) => {
    // First import demo data
    await page.goto('http://localhost:3000/settings')
    await page.locator('button:has-text("导入演示数据")').click()
    await page.waitForResponse(response =>
      response.url().includes('/api/demo/import') && response.status() === 200
    )
    await page.waitForTimeout(2000)

    // Click clear demo data button
    const clearButton = page.locator('button:has-text("清空演示数据")')
    await expect(clearButton).toBeVisible()
    await clearButton.click()

    // Confirmation dialog should appear
    await expect(page.locator('text=/确认清空演示数据/')).toBeVisible()

    // Confirm deletion
    const confirmButton = page.locator('button:has-text("确认清空")')
    await confirmButton.click()

    // Wait for delete API response
    await page.waitForResponse(response =>
      response.url().includes('/api/demo') &&
      response.request().method() === 'DELETE' &&
      response.status() === 200
    )

    // Success message should appear
    await expect(page.locator('text=/清空成功/')).toBeVisible({ timeout: 10000 })

    // Verify data is cleared - check knowledge base is empty or only has non-demo data
    await page.goto('http://localhost:3000/knowledge')
    await page.waitForLoadState('networkidle')
    const demokb = page.locator('text="演示知识库"')
    await expect(demokb).not.toBeVisible({ timeout: 5000 })
  })

  test('should cancel clear operation when dialog is dismissed', async ({ page }) => {
    await page.goto('http://localhost:3000/settings')

    // Click clear demo data button
    const clearButton = page.locator('button:has-text("清空演示数据")')
    await clearButton.click()

    // Dismiss dialog by clicking cancel or X
    const cancelButton = page.locator('button:has-text("取消")')
    await cancelButton.click()

    // Dialog should close
    await expect(page.locator('text=/确认清空演示数据/')).not.toBeVisible()
  })
})
