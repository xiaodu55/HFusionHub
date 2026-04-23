// k6 负载测试 — API 混合基线（健康/文档/会话）
// 运行: docker run --rm -e ADMIN_PASSWORD=xxx -v ${PWD}:/scripts grafana/k6 run /scripts/k6/api-mix.js
// 容器内通过 host.docker.internal 访问宿主机服务（Docker Desktop 需 add-host=host.docker.internal:host-gateway）
import http from 'k6/http'
import { check, sleep } from 'k6'

const HOST = __ENV.HOST || 'http://host.docker.internal:8080'
const BASE = `${HOST}/api`
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || 'changeme'

export const options = {
  scenarios: {
    api_mix: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '15s', target: 5 },
        { duration: '30s', target: 5 },
        { duration: '10s', target: 0 },
      ],
      gracefulStop: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<3000'],
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

  const health = http.get(`${HOST}/api/actuator/health`)
  check(health, { 'health 200': r => r.status === 200 })

  const docs = http.get(`${BASE}/document/list?page=1&pageSize=5`, { headers })
  check(docs, { 'document list 200': r => r.status === 200 })

  const convs = http.get(`${BASE}/conversation/my?page=1&pageSize=5`, { headers })
  check(convs, { 'conversation list 200': r => r.status === 200 })

  const kbs = http.get(`${BASE}/knowledge-base/my?page=1&pageSize=5`, { headers })
  check(kbs, { 'kb list 200': r => r.status === 200 })

  sleep(0.5)
}
