import { test, expect } from './fixtures/base'

test.describe('AI ability center', () => {
  test('explains capabilities with examples on desktop and mobile', async ({ page, admin }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), admin.token)
    await page.goto('/builder/tools')

    await expect(page.getByRole('heading', { name: 'AI 能帮你做什么' })).toBeVisible()
    await expect(page.getByText('怎么使用', { exact: true })).toBeVisible()
    await expect(page.getByText('搜索知识库', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('示例问法')).toHaveCount(0)
    await expect(page.getByText('第 1 / 2 页')).toBeVisible()

    const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(desktopOverflow).toBeLessThanOrEqual(1)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: 'test-results/tools-desktop.png', fullPage: true })

    await page.getByRole('button', { name: /^知识库\s+\d+$/ }).click()
    await expect(page.getByText('搜索知识库', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('数学计算', { exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: /搜索知识库/ }).first().click()
    await expect(page.getByText('示例问法')).toBeVisible()

    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: 'http://localhost:3000' })
    await page.getByRole('button', { name: '复制搜索知识库示例' }).click()
    await expect(page.getByText('示例问题已复制，可以到智能对话中直接使用')).toBeVisible()

    await page.getByText('技术详情').first().click()
    await expect(page.getByText('内部名称：').first()).toBeVisible()

    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    await expect(page.getByRole('heading', { name: 'AI 能帮你做什么' })).toBeVisible()
    const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(mobileOverflow).toBeLessThanOrEqual(1)
    await page.screenshot({ path: 'test-results/tools-mobile.png', fullPage: true })
  })

  test('new tool opens the low-code plugin builder', async ({ page, admin }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), admin.token)
    await page.route('**/api/tool/registry**', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { tools: [], version: '1.0' } }),
    }))
    await page.route('**/api/tool/calls**', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { records: [], total: 0 } }),
    }))
    await page.route('**/api/plugin/list**', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { records: [], total: 0, page: 1, pageSize: 20 } }),
    }))

    await page.goto('/builder/tools')
    await page.getByRole('button', { name: '新建工具' }).click()
    await expect(page).toHaveURL(/\/builder\/plugins\?create=tool/)
    await expect(page.getByRole('heading', { name: '新建插件' })).toBeVisible()
  })
})
