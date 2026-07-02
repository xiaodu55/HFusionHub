import { test, expect } from '@playwright/test'
import type { QuotaSummary } from '../src/api/quota'

// 用 route mock 构造确定的配额数据（真实环境无法安全地制造 70%/90% 用量）
const mockQuota = (percent: number): QuotaSummary[] => [
  {
    meter: 'chat_tokens',
    label: '对话 Token',
    unit: 'tokens',
    committed: 0,
    reserved: 0,
    used: Math.round(percent * 100),
    dailyLimit: 10000,
    remaining: 10000 - Math.round(percent * 100),
    percent,
  },
]

const installQuotaMock = async (page: import('@playwright/test').Page, percent: number) => {
  await page.route('**/api/quota/summary*', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'ok', data: mockQuota(percent) }) })
  })
  // 其余数据源放行真实后端
  await page.route('**/api/cost/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'ok', data: { totalCost: 0, totalTokens: 0, totalRequests: 0, currentMonthCost: 0, estimatedMonthCost: 0 } }) })
  })
  await page.route('**/api/cost/daily*', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'ok', data: [] }) })
  })
  await page.route('**/api/cost/models*', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'ok', data: [] }) })
  })
  await page.route('**/api/model-usage/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'ok', data: { records: [], total: 0 } }) })
  })
}

test.describe('Quota Display', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/login')
    await page.fill('input[type="text"]', 'admin')
    // CI（e2e.yml）种子管理员密码为 admin123；本地跑传 ADMIN_PASSWORD 覆盖
    await page.fill('input[type="password"]', process.env.ADMIN_PASSWORD || 'admin123')
    await page.click('button:has-text("登录")')
    // 登录后跳首页（无 /dashboard 路由）
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 15_000 })
  })

  test('should display quota cards on cost page', async ({ page }) => {
    await installQuotaMock(page, 10)
    await page.goto('http://localhost:3000/cost')
    await expect(page.locator('h1:has-text("用量与费用")')).toBeVisible()

    // 配额区：标题 + 配额卡（label + 百分比 + 用量条）
    await expect(page.locator('text=今日配额')).toBeVisible()
    await expect(page.locator('text=对话 Token')).toBeVisible()
    const usageBar = page.locator('.h-full.rounded-full').first()
    await expect(usageBar).toBeVisible()
    await expect(page.getByText('10%', { exact: true })).toBeVisible()
  })

  test('should show amber bar when quota exceeds 70%', async ({ page }) => {
    await installQuotaMock(page, 75)
    await page.goto('http://localhost:3000/cost')
    await expect(page.locator('text=今日配额')).toBeVisible()

    // >=70% 琥珀进度条（quotaBarClass: bg-amber-500）
    await expect(page.locator('.bg-amber-500.h-full')).toBeVisible()
  })

  test('should show red warning when quota exceeds 90%', async ({ page }) => {
    await installQuotaMock(page, 95)
    await page.goto('http://localhost:3000/cost')
    await expect(page.locator('text=今日配额')).toBeVisible()

    // >=90% 红条 + 「即将超限」提示
    const redBar = page.locator('.bg-rose-500.h-full')
    await expect(redBar).toBeVisible()
    await expect(page.locator('text=即将超限')).toBeVisible()
  })
})
