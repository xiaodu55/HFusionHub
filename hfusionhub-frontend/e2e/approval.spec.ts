import { test, expect } from './fixtures/base'
import { assertJson } from './helpers'

test.describe('Approval Flow', () => {
  test('approval endpoint exists and returns empty list when no pending', async ({ javaApi, userA }) => {
    const res = await javaApi.get('agent-task/approvals/pending', {
      headers: userA.headers,
    })
    const body = await assertJson(res)
    expect(body.code).toBe(200)
    expect(Array.isArray(body.data)).toBeTruthy()
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

  test('task list is accessible', async ({ javaApi, userA }) => {
    const res = await javaApi.get('agent-task/list', {
      headers: userA.headers,
      params: { page: 1, pageSize: 10 },
    })
    const body = await assertJson(res)
    expect(body.code).toBe(200)
    expect(body.data).toBeTruthy()
  })
})
