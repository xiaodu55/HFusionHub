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

---

## B4 爬坡场景（2026-09-05，k6 v1.8.1 本机直连，混合读端点 4 个/迭代）

| VU 档 | p50 | p90 | p95 | 失败率 | 结论 |
|---|---|---|---|---|---|
| 10 | 33ms | 113ms | **138ms** | 0% | 轻松 |
| 50 | 312ms | 1312ms | **1423ms** | 0% | 延迟开始放大（×10） |
| 100 | 605ms | 2902ms | **3018ms** | 0% | p95 首破 3s 门禁 |

- **拐点 = 延迟而非错误**：100 VU（约 80 req/s）仍零失败，排队特征明显
  （p90 远高于 p50），首要瓶颈嫌疑 = Hikari 池 40 连接 + 单实例 Tomcat；
- 爬坡全程留档：`ramp-mixed_20260905-*.log/json`（带 VU 标签跑）+
  `ramp_{10,50,100}vu_20260905.json`（恒定 VU 分档）；
- 两次 ramp-mixed 全量跑 p95 2.6s→3.0s（阈值越线 exit 99），本机波动属正常。

## B2 chat-stream 实测（2026-09-05，DeepSeek-v4-flash 全生成）

| 场景 | 完整轮次（SSE 全流） | 备注 |
|---|---|---|
| 固定提示词（旧脚本） | med=41ms | **测量陷阱**：命中 LLM 响应缓存，数字无效 |
| 变化提示词（已修脚本） | **1.0~1.6s/轮** | DeepSeek 全生成 + SSE 全链路 |

- 历史 298ms（9/2）为缓存命中/旧脚本口径，不可直接对比；
- 待办（B2 收尾）：OTel 未开（Tempo 查询为空）——开启后拉 trace 做分段
  （首包 vs 生成 vs Java→Python 转发），或用 SSE 首包探测脚本定位。

## B2 分段定位（2026-09-05，SSE 探测脚本 probe_sse.py，n=4 成对）

| 链路 | 首包 TTFB（中位） | 全流（中位） |
|---|---|---|
| Python 直连（/api/chat stream） | **2.5s** | 2.5s（=TTFB，真流式：检索事件 2.8s → token 流 3.9s 起） |
| Java 转发（/conversation/message/stream） | **4.6s** | 4.9s |
| **Java 桥额外开销** | **~2s** | —— |

- Python 端真流式已验证（逐 token SSE 事件）；Java 桥代码（bodyToFlux +
  逐元素 emitter.send）也无缓冲算子；
- 但实测 Java 链路首包仍晚 ~2s（缓冲点在 WebClient 接收 → SseEmitter
  发送链路的更深层，需 OTel trace 或 Reactor 调试继续定位）；
- 另注：round 0 出现 13.7s 离群首包（熔断/冷启动嫌疑）。

## 后续工作清单（按优先级）
1. B2 收尾：开启 OTel（OTEL_ENABLED=true + OTEL_EXPORTER_OTLP_ENDPOINT）
   拉 Tempo trace 定位 Java 桥内 2s 缓冲点，或 Reactor 调试逐算子计时；
2. 主体级 ACL（权限类拒答 0/30 的机制解，设计见 ADR-006）；
3. 业务工具集（8 个演示工具 + 沙箱端点）；
4. PromptTestSet Awaitility 化 + Cost 每类独立库（C1 后续）；
5. k6 正式加入 PATH（当前用 d:/college/development/k6-v1.8.1-windows-amd64/k6.exe）。
