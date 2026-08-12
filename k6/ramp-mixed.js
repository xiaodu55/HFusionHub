// k6 负载测试 — B4 爬坡场景：10/50/100 VU 找系统拐点
// 运行: k6 run -e ADMIN_PASSWORD=xxx k6/ramp-mixed.js
// 本机 k6.exe 直接访问 localhost:8080（无需 docker host 映射）
import http from 'k6/http'
import { check, sleep } from 'k6'

const HOST = __ENV.HOST || 'http://localhost:8080'
const BASE = `${HOST}/api`
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || 'changeme'

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 10 },   // 爬坡 10 VU
        { duration: '40s', target: 10 },   // 10 VU 稳态
        { duration: '30s', target: 50 },   // 爬坡 50 VU
        { duration: '40s', target: 50 },   // 50 VU 稳态
        { duration: '30s', target: 100 },  // 爬坡 100 VU
        { duration: '40s', target: 100 },  // 100 VU 稳态
        { duration: '15s', target: 0 },
      ],
      gracefulStop: '20s',
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
  // B4 拐点分析：按当前 VU 数打标签，summary-export 可按 {vu:xx} 分组出每档 p95
  const tags = { vu: `${__VU}` }
  const headers = { 'Content-Type': 'application/json', satoken: token }

  const health = http.get(`${BASE}/health`, { tags })
  check(health, { 'health 200': r => r.status === 200 })

  const kbs = http.get(`${BASE}/knowledge-base/my?page=1&pageSize=10`, { headers, tags })
  check(kbs, { 'kb list 200': r => r.status === 200 })

  const convs = http.get(`${BASE}/conversation/my?page=1&pageSize=10`, { headers, tags })
  check(convs, { 'conversation list 200': r => r.status === 200 })

  const docs = http.get(`${BASE}/document/list?page=1&pageSize=10`, { headers, tags })
  check(docs, { 'document list 200': r => r.status === 200 })

  sleep(0.2)
}
