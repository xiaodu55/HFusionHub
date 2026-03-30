import { test, expect } from './fixtures/base'
import { uid, assertJson } from './helpers'

test.describe('Permission Isolation', () => {
  test('user A cannot read user B knowledge base via API', async ({ javaApi, userA, userB }) => {
    const createRes = await javaApi.post('knowledge-base', {
      headers: userA.headers,
      data: { name: uid('kb_a'), description: 'Private KB for user A' },
    })
    const kbBody = await assertJson(createRes)
    expect(kbBody.code).toBe(200)
    const kbId = kbBody.data.id

    const res = await javaApi.get(`knowledge-base/${kbId}`, {
      headers: userB.headers,
    })
    const body = await assertJson(res)
    expect(body.code).not.toBe(200)

    await javaApi.delete(`knowledge-base/${kbId}`, { headers: userA.headers })
  })

  test('user A cannot read user B documents via API', async ({ javaApi, userA, userB }) => {
    const kbRes = await javaApi.post('knowledge-base', {
      headers: userA.headers,
      data: { name: uid('kb_a_doc'), description: 'KB' },
    })
    const kbBody = await assertJson(kbRes)
    const kbId = kbBody.data.id

    const docRes = await javaApi.post('document/upload', {
      headers: userA.headers,
      multipart: {
        file: { name: 'private.txt', mimeType: 'text/plain', buffer: Buffer.from('secret') },
        knowledgeBaseId: kbId.toString(),
        title: 'private.txt',
      },
    })
    const docBody = await assertJson(docRes)
    const docId = docBody.data.id

    const res = await javaApi.get(`document/${docId}`, {
      headers: userB.headers,
    })
    const body = await assertJson(res)
    expect(body.code).not.toBe(200)

    await javaApi.delete(`document/${docId}`, { headers: userA.headers })
    await javaApi.delete(`knowledge-base/${kbId}`, { headers: userA.headers })
  })

  test('user A cannot read user B conversations via API', async ({ javaApi, userA, userB }) => {
    const convRes = await javaApi.post('conversation', {
      headers: userA.headers,
      data: { title: uid('conv_a') },
    })
    const convBody = await assertJson(convRes)
    const convId = convBody.data.id

    const res = await javaApi.get(`conversation/${convId}`, {
      headers: userB.headers,
    })
    const body = await assertJson(res)
    expect(body.code).not.toBe(200)

    await javaApi.delete(`conversation/${convId}`, { headers: userA.headers })
  })

  test('user A cannot delete user B knowledge base', async ({ javaApi, userA, userB }) => {
    const kbRes = await javaApi.post('knowledge-base', {
      headers: userA.headers,
      data: { name: uid('kb_del'), description: 'KB' },
    })
    const kbBody = await assertJson(kbRes)
    const kbId = kbBody.data.id

    const res = await javaApi.delete(`knowledge-base/${kbId}`, {
      headers: userB.headers,
    })
    const body = await assertJson(res)
    expect(body.code).not.toBe(200)

    const checkRes = await javaApi.get(`knowledge-base/${kbId}`, {
      headers: userA.headers,
    })
    const checkBody = await assertJson(checkRes)
    expect(checkBody.code).toBe(200)

    await javaApi.delete(`knowledge-base/${kbId}`, { headers: userA.headers })
  })

  test('user A sees only own KBs in list', async ({ javaApi, userA, userB }) => {
    const kbA = await javaApi.post('knowledge-base', {
      headers: userA.headers,
      data: { name: uid('kb_list_a'), description: 'A' },
    })
    const kbB = await javaApi.post('knowledge-base', {
      headers: userB.headers,
      data: { name: uid('kb_list_b'), description: 'B' },
    })
    const kbABody = await assertJson(kbA)
    const kbAId = kbABody.data.id
    const kbBBody = await assertJson(kbB)
    const kbBId = kbBBody.data.id

    const listRes = await javaApi.get('knowledge-base/my', {
      headers: userA.headers,
      params: { page: 1, pageSize: 50 },
    })
    const listBody = await assertJson(listRes)
    expect(listBody.code).toBe(200)

    const ids = listBody.data.records.map((r: any) => r.id)
    expect(ids).toContain(kbAId)
    expect(ids).not.toContain(kbBId)

    await javaApi.delete(`knowledge-base/${kbAId}`, { headers: userA.headers })
    await javaApi.delete(`knowledge-base/${kbBId}`, { headers: userB.headers })
  })
})
