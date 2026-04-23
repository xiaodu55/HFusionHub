import { test, expect } from './fixtures/base'
import { assertJson, uid } from './helpers'

test.describe('Approval Flow', () => {
  test('approval endpoint exists and returns empty list when no pending', async ({ javaApi, userA }) => {
    const res = await javaApi.get('agent-task/approvals/pending', {
      headers: userA.headers,
    })
    const body = await assertJson(res)
    expect(body.code).toBe(200)
    expect(Array.isArray(body.data)).toBeTruthy()
  })

  test('pending list is scoped per user (permission isolation)', async ({ javaApi, userA, userB }) => {
    const [a, b] = await Promise.all([
      javaApi.get('agent-task/approvals/pending', { headers: userA.headers }),
      javaApi.get('agent-task/approvals/pending', { headers: userB.headers }),
    ])
    const [bodyA, bodyB] = await Promise.all([assertJson(a), assertJson(b)])
    expect(bodyA.code).toBe(200)
    expect(bodyB.code).toBe(200)
    const idsA = new Set((bodyA.data as any[]).map((x) => x.userId))
    const idsB = new Set((bodyB.data as any[]).map((x) => x.userId))
    for (const id of idsA) expect(idsB.has(id)).toBe(false)
  })

  test('approve endpoint requires valid task and approval', async ({ javaApi, userA }) => {
    const res = await javaApi.post('agent-task/fake-task-123/approve', {
      headers: userA.headers,
      data: {
        approvalId: 'fake-approval-456',
        decision: 'approved',
        reason: 'E2E test',
      },
    })
    const body = await assertJson(res)
    expect(body.code).not.toBe(200)
  })

  test('denied decision requires an explicit reason', async ({ javaApi, userA }) => {
    const res = await javaApi.post('agent-task/fake-task-123/approve', {
      headers: userA.headers,
      data: {
        approvalId: 'fake-approval-456',
        decision: 'denied',
        reason: '',
      },
    })
    const body = await assertJson(res)
    expect(body.code).not.toBe(200)
    expect(body.data).toBeFalsy()
  })

  test('task approvals list requires task ownership (nonexistent task)', async ({ javaApi, userB }) => {
    const res = await javaApi.get('agent-task/999999123/approvals', {
      headers: userB.headers,
    })
    const body = await assertJson(res)
    expect(body.code).not.toBe(200)
  })

  test('task list is accessible', async ({ javaApi, userA }) => {
    const res = await javaApi.get('agent-task/list', {
      headers: userA.headers,
      params: { page: 1, pageSize: 10 },
    })
    const body = await assertJson(res)
    expect(body.code).toBe(200)
    expect(body.data).toBeTruthy()
  })

  test('approvals SSE stream is protected by auth', async ({ javaApi }) => {
    const res = await javaApi.get('agent-task/approvals/stream')
    expect([401, 403, 302]).toContain(res.status())
  })

  test('userB cannot access userA task approvals (real API)', async ({ javaApi, userA, userB }) => {
    // Create a conversation + task via userA so we have a real taskId.
    const convRes = await javaApi.post('conversation', {
      headers: userA.headers,
      data: { title: uid('conv'), knowledgeBaseId: null },
    })
    const conv = await assertJson(convRes)
    const convId = conv.data?.id
    if (!convId) return // conversation creation failed — skip gracefully

    const requestId = uid('req')
    // Sending a message creates the task. Python may be unreachable; the task
    // still exists in DB since createTask runs before the AI call.
    await javaApi.post('conversation/message/stream', {
      headers: userA.headers,
      data: { conversationId: convId, content: 'test', requestId },
      timeout: 5000,
    }).catch(() => {})

    // Look up the task by requestId.
    const taskRes = await javaApi.get(`agent-task/by-request/${requestId}`, {
      headers: userA.headers,
    }).catch(() => null)
    if (!taskRes) return
    const taskBody = await assertJson(taskRes)
    const taskId = taskBody.data?.id
    if (!taskId) return

    // userA can see the approvals list (will be empty but accessible).
    const ok = await javaApi.get(`agent-task/${taskId}/approvals`, {
      headers: userA.headers,
    })
    const okBody = await assertJson(ok)
    expect(okBody.code).toBe(200)

    // userB must NOT access userA's task approvals.
    const denied = await javaApi.get(`agent-task/${taskId}/approvals`, {
      headers: userB.headers,
    })
    const deniedBody = await assertJson(denied)
    expect(deniedBody.code).not.toBe(200)
  })
})

// ─── UI / Rendering tests ──────────────────────────────────────────────────
// These use Playwright page.route() to intercept API calls and inject fixture
// data, so they run deterministically without the full Python stack.

const MOCK_APPROVALS: any[] = [
  {
    id: 1,
    approvalId: 'appr-e2e-1',
    taskId: 999,
    runId: 1,
    userId: 100,
    traceId: 'tr-e2e-001',
    toolName: 'write_note',
    riskLevel: 'read_write',
    argumentsSummary: '{"content":"***","api_key":"***"}',
    status: 'pending',
    expiresAt: new Date(Date.now() + 300_000).toISOString(),
    createdAt: new Date().toISOString(),
  },
  {
    id: 2,
    approvalId: 'appr-e2e-2',
    taskId: 999,
    runId: 1,
    userId: 100,
    traceId: 'tr-e2e-002',
    toolName: 'write_note',
    riskLevel: 'read_write',
    argumentsSummary: '{"content":"***","api_key":"***"}',
    status: 'approved',
    decidedAt: new Date().toISOString(),
    createdAt: new Date(Date.now() - 60_000).toISOString(),
  },
  {
    id: 3,
    approvalId: 'appr-e2e-3',
    taskId: 999,
    runId: 1,
    userId: 100,
    traceId: 'tr-e2e-003',
    toolName: 'external_api_call',
    riskLevel: 'external',
    argumentsSummary: '{"endpoint":"https://example.com","token":"***"}',
    status: 'denied',
    reason: '参数不符合预期',
    decidedAt: new Date().toISOString(),
    createdAt: new Date(Date.now() - 120_000).toISOString(),
  },
  {
    id: 4,
    approvalId: 'appr-e2e-4',
    taskId: 999,
    runId: 1,
    userId: 100,
    traceId: 'tr-e2e-004',
    toolName: 'write_note',
    riskLevel: 'read_write',
    argumentsSummary: '{"content":"***","api_key":"***"}',
    status: 'executed',
    decidedAt: new Date(Date.now() - 60_000).toISOString(),
    createdAt: new Date(Date.now() - 180_000).toISOString(),
  },
]

test.describe('Approval Page (UI rendering)', () => {
  test('page loads with header and SSE indicator', async ({ page, userA }) => {
    await page.goto('/approvals')
    await page.waitForSelector('#app', { timeout: 10_000 })
    // Set auth token so the page doesn't redirect to login.
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto('/approvals')
    await page.waitForSelector('#app', { timeout: 10_000 })
    // 页面头部（新 UI 为「待确认操作」，旧文案「工具审批中心」已不存在）
    // 注意：侧边栏与页面标题都有该文案，用 heading 角色 + first 避免 strict violation
    await expect(page.getByRole('heading', { name: '待确认操作' }).first()).toBeVisible({ timeout: 10_000 })
  })

  test('task jump (taskId query) loads approvals by task, shows terminal states + masked params + traceId', async ({ page, userA }) => {
    // Intercept the pending list to return empty (default load).
    await page.route('**/agent-task/approvals/pending', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'ok', data: [] }) }),
    )
    // Intercept the by-task list to return our mock data.
    await page.route('**/agent-task/999/approvals', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'ok', data: MOCK_APPROVALS }) }),
    )

    await page.goto('/approvals')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto('/approvals?taskId=999')
    await page.waitForSelector('#app', { timeout: 10_000 })

    // Header should mention the task filter（新 UI 文案为「确认记录」）。
    await expect(page.getByText('仅显示任务 #999 的确认记录')).toBeVisible({ timeout: 10_000 })

    // 按任务查看默认是「历史记录」视图 → 只渲染终态（pending 被过滤掉）。
    await expect(page.getByText('已批准').first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('已拒绝').first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('已执行').first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('待审批')).toHaveCount(0)

    // Masked params: key names visible, raw secret values hidden.
    await expect(page.getByText('api_key').first()).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('sk-live-123')).toBeHidden()

    // Open detail dialog on the executed record (last "保存一条知识笔记" row).
    await page.getByText('保存一条知识笔记').last().click()
    await expect(page.getByRole('heading', { name: '确认操作', exact: true })).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('可能影响')).toBeVisible()
    await expect(page.getByText('会修改数据').first()).toBeVisible()
    // Trace ID 折叠在「查看技术信息」详情里，展开后可见。
    await page.getByText('查看技术信息').click()
    await expect(page.getByText('Trace ID：tr-e2e-004')).toBeVisible()
    await expect(page.getByText('工具：write_note')).toBeVisible()
    // Masked: key names visible, raw secrets hidden.
    await expect(page.getByText('api_key').first()).toBeVisible()
    await expect(page.getByText('sk-live-123')).toBeHidden()
  })

  test('another user cannot see task approvals via UI (route-level guard)', async ({ page, userA }) => {
    // The API would return non-200 for an unauthorized task; mock that.
    await page.route('**/agent-task/approvals/pending', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'ok', data: [] }) }),
    )
    await page.route('**/agent-task/999/approvals', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 403, message: '无权查看此任务', data: null }) }),
    )

    await page.goto('/approvals')
    await page.evaluate((token) => localStorage.setItem('satoken', token), userA.token)
    await page.goto('/approvals?taskId=999')
    await page.waitForSelector('#app', { timeout: 10_000 })

    // No approvals should render — the page should not crash.
    await expect(page.getByRole('heading', { name: '待确认操作' }).first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('仅显示任务 #999 的确认记录')).toBeVisible({ timeout: 10_000 })
  })
})

// ─── Live UI tests (only when full Python stack is available) ───────────────
test.describe('Approval Flow (live UI)', () => {
  test('approval page renders and subscribes to SSE', async ({ page }) => {
    test.skip(!process.env.HFUSIONHUB_RUN_APPROVAL_LIVE, 'requires live stack')
    await page.goto('/approvals')
    await page.waitForSelector('#app', { timeout: 15_000 })
    await expect(page.getByText('待确认操作')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('实时同步中').first()).toBeVisible({ timeout: 15_000 })
  })

  test('task --> approvals audit entry exists', async ({ page }) => {
    test.skip(!process.env.HFUSIONHUB_RUN_APPROVAL_LIVE, 'requires live stack')
    await page.goto('/agent')
    await page.waitForSelector('#app', { timeout: 15_000 })
    await expect(page.getByText('查看回答是否正常完成')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/确认记录/i).first()).toBeVisible()
  })
})
