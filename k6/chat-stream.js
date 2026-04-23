// k6 负载测试 — 智能对话完整轮次（SSE 流式，测量全链路耗时）
// 运行: docker run --rm -e ADMIN_PASSWORD=xxx -v ${PWD}:/scripts grafana/k6 run /scripts/k6/chat-stream.js
// 注意：每轮完整对话取决于 LLM（Ollama 约 15-30s），VU 不宜过大
import http from 'k6/http'
import { check, sleep } from 'k6'

const HOST = __ENV.HOST || 'http://host.docker.internal:8080'
const BASE = `${HOST}/api`
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || 'changeme'

export const options = {
  scenarios: {
    chat: {
      executor: 'constant-vus',
      vus: 2,
      duration: '60s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.1'],
  },
}

export function setup() {
  const login = http.post(`${BASE}/user/login`, JSON.stringify({ username: 'admin', password: ADMIN_PASSWORD }), {
    headers: { 'Content-Type': 'application/json' },
  })
  const token = JSON.parse(login.body).data
  if (!token) throw new Error(`login failed: ${login.body}`)
  return token
}

export default function (token) {
  const headers = { 'Content-Type': 'application/json', satoken: token }
  const tag = `load_${__VU}_${Date.now()}`

  const create = http.post(`${BASE}/conversation`, JSON.stringify({ title: tag }), { headers })
  const convId = JSON.parse(create.body).data?.id
  if (!convId) {
    check(create, { 'create conversation ok': r => r.status === 200 })
    return
  }

  const started = Date.now()
  const stream = http.post(
    `${BASE}/conversation/message/stream`,
    JSON.stringify({ conversationId: convId, content: '你好，请用一句话介绍你自己', requestId: tag }),
    { headers, responseType: 'text' },
  )
  const turnMs = Date.now() - started

  const ok = stream.status === 200 && stream.body.includes('[DONE]')
  check(stream, { 'stream [DONE] received': r => ok })
  console.log(`chat turn done: status=${stream.status} ok=${ok} ${turnMs}ms body=${stream.body.length}B`)

  http.del(`${BASE}/conversation/${convId}`, null, { headers })
  sleep(1)
}
