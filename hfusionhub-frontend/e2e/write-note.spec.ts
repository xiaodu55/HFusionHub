import { test, expect } from './fixtures/base'
import { assertJson, assertOkJson } from './helpers'

/**
 * Write-note closed loop (写笔记闭环):
 *   1. write_note 工具在 Python 工具注册表可见
 *   2. Agent 内部回调端点保存笔记（X-Internal-Token）→ note 落库
 *   3. 用户笔记 API 可读回该笔记
 *   4. 权限隔离：其他用户读不到
 */
test.describe('Write Note Flow', () => {
  test('write_note tool is registered in the tool registry', async ({ playwright }) => {
    const pyToken = process.env.PYTHON_AI_INTERNAL_TOKEN
    test.skip(!pyToken, 'PYTHON_AI_INTERNAL_TOKEN 未配置，跳过 Python 侧检查')

    const pyApi = await playwright.request.newContext({
      baseURL: (process.env.PYTHON_BASE_URL || 'http://localhost:9000') + '/',
      extraHTTPHeaders: {
        'X-Internal-Token': pyToken,
        'X-Tenant-Id': '1',
      },
    })
    try {
      const res = await pyApi.get('api/tools/registry?tenant_id=1')
      const body = await assertOkJson(res)
      const names = (body.tools || []).map((t: any) => t.name)
      expect(names).toContain('write_note')
      expect(names).toContain('search_knowledge_base')
    } finally {
      await pyApi.dispose()
    }
  })

  test('internal note endpoint persists a note and user can read it back', async ({ javaApi, admin }) => {
    const pyToken = process.env.PYTHON_AI_INTERNAL_TOKEN
    test.skip(!pyToken, 'PYTHON_AI_INTERNAL_TOKEN 未配置，跳过内部回调检查')

    // 1) Python 侧回调 Java 内部端点（模拟 write_note 工具执行）
    const content = `E2E write-note 内容 ${Date.now()}`
    const internal = await javaApi.post('internal/notes', {
      headers: { 'X-Internal-Token': pyToken },
      data: {
        user_id: 1,
        knowledge_base_id: null,
        title: '',
        content,
        source: 'agent_write_note',
      },
    })
    const internalBody = await assertOkJson(internal)
    expect(internalBody.code).toBe(200)
    const noteId = internalBody.data.note_id
    expect(noteId).toBeGreaterThan(0)

    // 2) 管理员读回笔记
    const list = await javaApi.get('note/my?limit=50', { headers: admin.headers })
    const listBody = await assertOkJson(list)
    expect(listBody.code).toBe(200)
    const found = (listBody.data as any[]).find((n) => n.id === noteId)
    expect(found).toBeTruthy()
    expect(found.content).toBe(content)
  })

  test('notes are isolated per user (permission isolation)', async ({ javaApi, userA, admin }) => {
    // 管理员建一条笔记，userA 不应读到
    const created = await javaApi.post('note', {
      headers: admin.headers,
      data: { title: 'isolation-test', content: `private ${Date.now()}` },
    })
    const createdBody = await assertOkJson(created)
    const noteId = createdBody.data.id

    const other = await javaApi.get('note/my?limit=200', { headers: userA.headers })
    const otherBody = await assertOkJson(other)
    const ids = new Set((otherBody.data as any[]).map((n) => n.id))
    expect(ids.has(noteId)).toBe(false)

    // 直接读他人笔记应失败（HTTP 4xx + 业务码非 200）
    const direct = await javaApi.get(`note/${noteId}`, { headers: userA.headers })
    const directBody = await assertJson(direct)
    expect(directBody.code).not.toBe(200)

    // 清理
    await javaApi.delete(`note/${noteId}`, { headers: admin.headers })
  })
})
