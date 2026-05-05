import { test, expect } from '@playwright/test'

test.describe('Quota Display', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/login')
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', process.env.ADMIN_PASSWORD || 'test123')
    await page.click('button:has-text("登录")')
    await page.waitForURL('**/dashboard')
  })

  test('should display quota panel in cost page', async ({ page }) => {
    // Navigate to cost page
    await page.goto('http://localhost:3000/cost')
    await expect(page.locator('h1:has-text("用量与费用")')).toBeVisible()

    // Wait for quota API response
    const quotaResponse = await page.waitForResponse(response =>
      response.url().includes('/api/quota/summary') && response.status() === 200
    )
    const quota = await quotaResponse.json()

    if (quota.data && quota.data.tokenQuota > 0) {
      // Quota panel should be visible
      await expect(page.locator('text=租户配额')).toBeVisible()

      // Check for usage bar
      const usageBar = page.locator('[role="progressbar"]').first()
      await expect(usageBar).toBeVisible()

      // Check for percentage display
      const percentageText = await page.textContent('text=/\\d+%/')
      expect(percentageText).toBeTruthy()
    } else {
      // No quota configured - panel might show different state
      await expect(page.locator('text=租户配额')).toBeVisible()
    }
  })

  test('should show warning color when quota exceeds 70%', async ({ page, context }) => {
    // Mock high usage quota
    await context.route('**/api/quota/summary', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          data: {
            tokenQuota: 1000000,
            tokenUsed: 750000,
            storageQuotaMb: 1024,
            storageUsedMb: 100,
            hasUnlimitedTokens: false,
            hasUnlimitedStorage: false
          }
        })
      })
    })

    await page.goto('http://localhost:3000/cost')
    await page.waitForLoadState('networkidle')

    // Usage bar should show amber/red warning color
    const usageBar = page.locator('[role="progressbar"]').first()
    const barClass = await usageBar.getAttribute('class')
    expect(barClass).toMatch(/bg-(amber|red)/)
  })

  test('should disable send button when token quota exceeded', async ({ page, context }) => {
    // Mock exceeded quota
    await context.route('**/api/quota/summary', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          data: {
            tokenQuota: 1000000,
            tokenUsed: 1000000,
            storageQuotaMb: 1024,
            storageUsedMb: 100,
            hasUnlimitedTokens: false,
            hasUnlimitedStorage: false
          }
        })
      })
    })

    await page.goto('http://localhost:3000/chat')
    await page.waitForLoadState('networkidle')

    // Send button should be disabled
    const sendButton = page.locator('button:has-text("发送")')
    await expect(sendButton).toBeDisabled()

    // Should show quota exceeded warning
    await expect(page.locator('text=/配额.*已用尽/')).toBeVisible()
  })
})
