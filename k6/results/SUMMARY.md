# k6 主平台压测汇总(2026-09-02,单机宿主 16GB,Java 本地进程 + 13 容器 analytics 栈共存)

## api-mix(健康/文档/会话/知识库混合,ramping 1→5 VU,约 85s)

| 指标 | 实测 | 阈值(k6) | docs/SCALING.md 目标 |
|---|---|---|---|
| checks | 1412/1412 = 100% | - | - |
| http_req_failed | 0.00% (0/1413) | < 5% | - |
| http_req_duration avg | 30.41ms | - | - |
| http_req_duration med | 28.81ms | - | - |
| http_req_duration p(95) | **69.17ms** | < 3000ms | P95 < 100ms ✓ |
| http_req_duration max | 190.34ms | - | - |

## chat-stream(SSE 流式对话全链路,constant 2 VU × 60s,真实 LLM 生成)

| 指标 | 实测 | 阈值(k6) |
|---|---|---|
| checks | 80/80 = 100%(含 stream [DONE] 完整收尾) | - |
| http_req_failed | 0.00% (0/241) | < 5% |
| http_req_duration p(95) | 298.46ms(HTTP 层,< 3000ms) | < 3000ms |
| iteration_duration p(95) | 2.6s(含真实 LLM 生成) | - |
| data_received | 184 kB(3.0 kB/s 流式吐出) | - |

原始文件:api-mix_*.json(机器可读汇总)+ api-mix_*.log / chat-stream_*.log(全量输出)。

## 运行方式(复现)

```bash
NEW_PW=$(grep "^ADMIN_PASSWORD=" docker/.env | cut -d= -f2)
MSYS_NO_PATHCONV=1 docker run --rm --add-host=host.docker.internal:host-gateway \
  -e HOST=http://host.docker.internal:8080 -e ADMIN_PASSWORD="$NEW_PW" \
  -v "$(pwd -W)/k6:/scripts" -v "$(pwd -W)/k6/results:/results" \
  grafana/k6:latest run --summary-export=/results/api-mix_<时间戳>.json /scripts/api-mix.js
```

注意:
- MSYS_NO_PATHCONV=1 + `pwd -W`:Git Bash 会把 `/scripts/...` 改写为 Windows 安装路径,导致 k6 找不到脚本。
- api-mix 的探活端点是 `/api/health`(公开);`/api/actuator/health` 已迁至 9092 管理端口且受认证,401 会被计为失败请求。
- Grafana/k6 镜像的 entrypoint 即 k6,进入 shell 调试需 `--entrypoint sh`。
