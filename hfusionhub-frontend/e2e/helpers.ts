import { type APIRequestContext, expect, type APIResponse } from '@playwright/test'

const JAVA_BASE = process.env.JAVA_BASE_URL || 'http://localhost:8080/api'
const PYTHON_BASE = process.env.PYTHON_BASE_URL || 'http://localhost:9000'

let _seq = 0
export const seq = () => ++_seq

export function uid(prefix = 'e2e') {
  return `${prefix}_${Date.now()}_${seq()}`
}

/** Assert the response is JSON (any status), then parse it. */
export async function assertJson(res: APIResponse) {
  const ct = res.headers()['content-type'] || ''
  expect(ct, `Expected JSON content-type but got "${ct}" from ${res.url()}`).toContain('application/json')
  return res.json()
}

/** Assert the response is OK and JSON, then parse it. */
export async function assertOkJson(res: APIResponse) {
  expect(res.ok(), `Expected OK response but got ${res.status()} from ${res.url()}`).toBeTruthy()
  return assertJson(res)
}

// ─── Java Backend API Helpers ───────────────────────────────────────────

export async function apiRegister(
  request: APIRequestContext,
  opts?: { username?: string; password?: string; role?: string },
) {
  const username = opts?.username ?? uid('user')
  const password = opts?.password ?? 'Test1234'
  const res = await request.post(`${JAVA_BASE}/user/register`, {
    data: { username, password, nickname: username },
  })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
  return { username, password, userInfo: body.data }
}

export async function apiLogin(
  request: APIRequestContext,
  username: string,
  password: string,
) {
  const res = await request.post(`${JAVA_BASE}/user/login`, {
    data: { username, password },
  })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
  return body.data as string // token value
}

export async function apiLoginAs(
  request: APIRequestContext,
  username: string,
  password: string,
) {
  const token = await apiLogin(request, username, password)
  return { token, headers: { satoken: token } }
}

export async function apiCreateKB(
  request: APIRequestContext,
  headers: Record<string, string>,
  name?: string,
) {
  const kbName = name ?? uid('kb')
  const res = await request.post(`${JAVA_BASE}/knowledge-base`, {
    headers,
    data: { name: kbName, description: `E2E test KB ${kbName}` },
  })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
  return body.data
}

export async function apiDeleteKB(
  request: APIRequestContext,
  headers: Record<string, string>,
  id: number,
) {
  const res = await request.delete(`${JAVA_BASE}/knowledge-base/${id}`, { headers })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
}

export async function apiUploadDocument(
  request: APIRequestContext,
  headers: Record<string, string>,
  kbId: number,
  fileName: string,
  content: string,
) {
  const res = await request.post(`${JAVA_BASE}/document/upload`, {
    headers,
    multipart: {
      file: { name: fileName, mimeType: 'text/plain', buffer: Buffer.from(content) },
      knowledgeBaseId: kbId.toString(),
      title: fileName,
    },
  })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
  return body.data.id as number // document ID
}

export async function apiParseDocument(
  request: APIRequestContext,
  headers: Record<string, string>,
  documentId: number,
) {
  const res = await request.post(`${JAVA_BASE}/document/${documentId}/parse`, {
    headers,
    data: { model: null },
  })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
}

export async function apiGetDocStatus(
  request: APIRequestContext,
  headers: Record<string, string>,
  documentId: number,
) {
  const res = await request.get(`${JAVA_BASE}/vectorize/${documentId}/status`, { headers })
  const body = await assertJson(res)
  const data = body.data
  if (typeof data === 'string') {
    try { return JSON.parse(data).status as string } catch { return data }
  }
  if (typeof data === 'object' && data !== null) return data.status as string
  return data as string
}

export async function apiCreateConversation(
  request: APIRequestContext,
  headers: Record<string, string>,
  kbId?: number,
  title?: string,
) {
  const res = await request.post(`${JAVA_BASE}/conversation`, {
    headers,
    data: {
      knowledgeBaseId: kbId ?? null,
      title: title ?? uid('conv'),
    },
  })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
  return body.data
}

export async function apiDeleteConversation(
  request: APIRequestContext,
  headers: Record<string, string>,
  id: number,
) {
  await request.delete(`${JAVA_BASE}/conversation/${id}`, { headers })
}

export async function apiGetMessages(
  request: APIRequestContext,
  headers: Record<string, string>,
  conversationId: number,
) {
  const res = await request.get(`${JAVA_BASE}/conversation/${conversationId}/messages`, { headers })
  const body = await assertJson(res)
  return body.data as any[]
}

export async function apiDeleteDocument(
  request: APIRequestContext,
  headers: Record<string, string>,
  documentId: number,
) {
  const res = await request.delete(`${JAVA_BASE}/document/${documentId}`, { headers })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
}

export async function apiRestoreDocument(
  request: APIRequestContext,
  headers: Record<string, string>,
  documentId: number,
) {
  const res = await request.post(`${JAVA_BASE}/document/${documentId}/restore`, { headers })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
}

export async function apiGetRecycleBin(
  request: APIRequestContext,
  headers: Record<string, string>,
) {
  const res = await request.get(`${JAVA_BASE}/document/recycle-bin`, {
    headers,
    params: { page: 1, pageSize: 50 },
  })
  const body = await assertJson(res)
  return body.data
}

export async function pollRecycleBinHasDoc(
  request: APIRequestContext,
  headers: Record<string, string>,
  documentId: number,
  opts?: { timeoutMs?: number; intervalMs?: number },
) {
  const timeout = opts?.timeoutMs ?? 180_000
  const interval = opts?.intervalMs ?? 500
  const deadline = Date.now() + timeout

  while (Date.now() < deadline) {
    const bin = await apiGetRecycleBin(request, headers)
    const found = bin.records?.find((r: any) => r.id === documentId)
    if (found) return found
    await new Promise(r => setTimeout(r, interval))
  }
  throw new Error(`Document ${documentId} not found in recycle bin after ${timeout}ms`)
}

// ─── Feature Flag Helpers ───────────────────────────────────────────────

export async function apiCreateFlag(
  request: APIRequestContext,
  headers: Record<string, string>,
  flagKey: string,
  opts?: { enabled?: boolean; description?: string },
) {
  const res = await request.post(`${JAVA_BASE}/feature-flag`, {
    headers,
    data: {
      flagKey,
      enabled: opts?.enabled ?? true,
      description: opts?.description ?? `E2E test flag ${flagKey}`,
    },
  })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
  return body.data
}

export async function apiUpdateFlag(
  request: APIRequestContext,
  headers: Record<string, string>,
  flagId: number,
  data: Record<string, any>,
) {
  const res = await request.put(`${JAVA_BASE}/feature-flag/${flagId}`, {
    headers,
    data,
  })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
  return body.data
}

export async function apiDeleteFlag(
  request: APIRequestContext,
  headers: Record<string, string>,
  flagId: number,
) {
  const res = await request.delete(`${JAVA_BASE}/feature-flag/${flagId}`, { headers })
  const body = await assertJson(res)
  expect(body.code).toBe(200)
}

export async function apiEvaluateFlag(
  request: APIRequestContext,
  headers: Record<string, string>,
  flagKey: string,
  context?: Record<string, any>,
) {
  const res = await request.post(`${JAVA_BASE}/feature-flag/evaluate`, {
    headers,
    data: { flagKey, context: context ?? {} },
  })
  const body = await assertJson(res)
  return body.data
}

// ─── Polling Helpers ────────────────────────────────────────────────────

export async function pollDocIndexing(
  request: APIRequestContext,
  headers: Record<string, string>,
  documentId: number,
  opts?: { timeoutMs?: number; intervalMs?: number },
) {
  const timeout = opts?.timeoutMs ?? 60_000
  const interval = opts?.intervalMs ?? 2_000
  const deadline = Date.now() + timeout

  while (Date.now() < deadline) {
    const status = await apiGetDocStatus(request, headers, documentId)
    if (status === 'COMPLETED' || status === 'FAILED') return status
    await new Promise(r => setTimeout(r, interval))
  }
  throw new Error(`Document ${documentId} indexing timed out after ${timeout}ms`)
}

// ─── Admin Helpers ──────────────────────────────────────────────────────

export async function ensureAdmin(request: APIRequestContext) {
  const adminUser = process.env.ADMIN_USERNAME || 'admin'
  const adminPass = process.env.ADMIN_PASSWORD || 'admin123'
  try {
    return await apiLoginAs(request, adminUser, adminPass)
  } catch {
    // Admin might not exist yet; register it
    await apiRegister(request, { username: adminUser, password: adminPass })
    return await apiLoginAs(request, adminUser, adminPass)
  }
}
