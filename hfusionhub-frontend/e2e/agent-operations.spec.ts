import { test, expect } from './fixtures/base'

const createdAt = new Date('2026-08-09T12:00:00').toISOString()
const tasks = Array.from({ length: 12 }, (_, index) => ({
  id: index + 1,
  requestId: `req-${index + 1}`,
  query: index === 0 ? '生成项目报告' : `知识库问题 ${index + 1}`,
  status: index === 0 ? 'FAILED' : index < 3 ? 'RUNNING' : 'SUCCEEDED',
  currentRunId: index + 100,
  createdAt,
  updatedAt: createdAt,
}))

async function mockAgentApis(page: any) {
  await page.route('**/agent-task/list**', (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 200, data: { records: tasks, total: tasks.length, page: 1, pageSize: 50 } }),
  }))
  await page.route('**/agent-task/*/events**', (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 200, data: [{ id: 1, eventType: '执行失败', status: 'FAILED', payload: { message: '模型服务连接失败' }, createdAt }] }),
  }))
  await page.route('**/agent-observability/metrics/tasks/*', (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 200, data: { totalDurationMs: 8300, stepCount: 2, toolCallsCount: 1, totalTokens: 320, model: 'deepseek-chat', errorDetail: 'Connection refused by model service' } }),
  }))
  await page.route(/\/agent-task\/\d+$/, (route: any) => {
    const id = Number(route.request().url().match(/agent-task\/(\d+)$/)?.[1] || 1)
    const task = tasks.find(item => item.id === id) || tasks[0]
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          ...task,
          userId: 1,
          conversationId: 88,
          runs: [{ id: task.currentRunId, attemptNumber: 1, status: task.status, durationMs: 8300, model: 'deepseek-chat', errorDetail: task.status === 'FAILED' ? 'Connection refused by model service' : null, steps: [] }],
        },
      }),
    })
  })
}

test.describe('AI task records', () => {
  test('explains usage and supports search, paging and mobile layout', async ({ page, userA }) => {
    await mockAgentApis(page)
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto('/agent')

    await expect(page.getByRole('heading', { name: '查看回答是否正常完成' })).toBeVisible()
    await expect(page.getByText('什么时候使用这个页面？')).toBeVisible()
    await expect(page.getByText('回答显示失败')).toBeVisible()
    await expect(page.getByText('AI 等待你的确认')).toBeVisible()
    await expect(page.getByText('AI 服务当前不可用')).toBeVisible()
    await expect(page.getByRole('button', { name: '重新执行', exact: true })).toBeVisible()
    await expect(page.getByText('第 1 / 2 页')).toBeVisible()
    await page.screenshot({ path: 'test-results/agent-operations-desktop.png', fullPage: true })

    await page.getByPlaceholder('搜索问题内容或任务编号').fill('知识库问题 12')
    await expect(page.locator('button').filter({ hasText: '知识库问题 12' })).toHaveCount(1)
    await expect(page.locator('button').filter({ hasText: '生成项目报告' })).toHaveCount(0)

    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    await expect(page.getByRole('heading', { name: '查看回答是否正常完成' })).toBeVisible()
    await page.getByPlaceholder('搜索问题内容或任务编号').fill('生成项目报告')
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(1)
    await page.locator('main').evaluate((element) => { element.scrollTop = 0 })
    await page.screenshot({ path: 'test-results/agent-operations-mobile.png', fullPage: true })
  })
})
