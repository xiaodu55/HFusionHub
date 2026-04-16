import { test, expect } from './fixtures/base'

async function openBuilder(page: any, token: string) {
  await page.goto('/')
  await page.evaluate((value: string) => localStorage.setItem('satoken', value), token)
  await page.goto('/builder/plugins')
  await expect(page.getByRole('heading', { name: '插件与工具' })).toBeVisible()
  await page.getByRole('button', { name: '新建插件' }).click()
  await page.getByRole('button', { name: '使用示例' }).click()
  await expect(page.getByLabel(/显示名称/)).toHaveValue('天气查询助手')
  await expect(page.getByLabel(/接口地址/)).toHaveValue('https://api.open-meteo.com/v1/forecast')
}

test.describe('Plugin builder visual acceptance', () => {
  test('desktop and mobile creation flows do not overflow', async ({ page, admin }) => {
    await page.setViewportSize({ width: 1440, height: 960 })
    await openBuilder(page, admin.token)
    const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(desktopOverflow).toBeLessThanOrEqual(1)
    await page.screenshot({ path: 'test-results/plugin-builder-desktop.png', fullPage: true })

    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    await page.getByRole('button', { name: '新建插件' }).click()
    await page.getByRole('button', { name: '使用示例' }).click()
    await expect(page.getByLabel(/显示名称/)).toHaveValue('天气查询助手')
    const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(mobileOverflow).toBeLessThanOrEqual(1)
    await page.screenshot({ path: 'test-results/plugin-builder-mobile.png', fullPage: true })
  })
})
