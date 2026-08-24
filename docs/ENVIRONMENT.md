# 环境变量清单

> Required and optional environment variables for HFusionHub services.

## Quick Reference (Windows PowerShell)

```powershell
# Copy-paste this block and replace placeholder values
$env:MYSQL_ROOT_PASSWORD="replace-with-a-strong-root-password"
$env:MYSQL_PASSWORD="replace-with-a-strong-db-password"
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD=$env:MYSQL_PASSWORD
$env:CALLBACK_SECRET="replace-with-a-long-random-callback-secret"
$env:PYTHON_AI_INTERNAL_TOKEN="replace-with-a-long-random-internal-token"
$env:ADMIN_PASSWORD="replace-with-a-strong-admin-password"
$env:AI_SERVICE_URL="http://localhost:9000"
$env:PYTHON_AI_CALLBACK_BASE_URL="http://localhost:8080/api"
$env:DEEPSEEK_API_KEY="replace-with-your-deepseek-api-key"
```

## Docker Compose (`docker/.env`)

Copy `docker/.env.example` to `docker/.env`:

| Variable | Example | Description |
|----------|---------|-------------|
| `MYSQL_ROOT_PASSWORD` | `root123456` | MySQL root password |
| `MYSQL_PASSWORD` | `hfusionhub123` | MySQL app user password |
| `REDIS_PASSWORD` | `your_redis_password` | Redis `requirepass`。dev compose（`docker/docker-compose.yml`）已通过 `--requirepass` 启用；**设置后 Java 必须注入同名 `REDIS_PASSWORD`**，否则启动报 `NOAUTH Authentication required`（见 2026-08-21 修复 cf07937） |
| `ADMIN_PASSWORD` | `changeme` | Bootstrap admin password |
| `MINIO_ROOT_USER` | `minioadmin` | MinIO object storage username |
| `SCHEDULER_LOCK_FAIL_OPEN` | `false` | 调度锁 Redis 故障时是否退化为无锁执行；默认 false（fail-closed，跳过本轮调度等待下一周期） |
| `ANALYTICS_ENABLED` | `false` | 分析扩展包（HFusionData Analytics）启用标记；/analytics 大屏在未启用时显示空态 |
| `BIGDATA_BATCH_ENABLED` | `false` | 大数据日结调度开关（默认关闭，主产品零依赖） |
| `BIGDATA_BATCH_CRON` | `0 0 4 * * ?` | 日结管线触发时间（UTC 由 JVM 时区决定） |
| `BIGDATA_BATCH_OFFSET_DAYS` | `1` | 日结处理的数据日期偏移（1=T-1） |
| `BIGDATA_JOB_FULL_IMPORT` 等 6 个 | 空 | 日结各步骤命令模板（`{date}` 占位；留空=该步 SKIPPED）。第 6 个 `BIGDATA_JOB_CH_SYNC` 为标准档 ClickHouse 同步（精简档留空）。完整示例见 docs/BIGDATA_ARCHITECTURE.md §5.1 |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | MinIO object storage password |
| `PLUGIN_RUNNER_TOKEN` | *(random)* | Plugin sandbox runner auth token (required — compose fails without it) |

### Production (`deploy/.env`)

Copy `deploy/.env.example` to `deploy/.env` for production Docker Compose:

| Variable | Required | Description |
|----------|----------|-------------|
| `MYSQL_ROOT_PASSWORD` | **Yes** | MySQL root password |
| `MYSQL_PASSWORD` | **Yes** | MySQL app user password |
| `PYTHON_AI_INTERNAL_TOKEN` | **Yes** | Java ↔ Python shared secret |
| `CALLBACK_SECRET` | **Yes** | HMAC secret for Python → Java callbacks |
| `ADMIN_PASSWORD` | **Yes** | Bootstrap admin account |
| `PLUGIN_RUNNER_TOKEN` | **Yes** | Plugin sandbox runner auth |
| `DEEPSEEK_API_KEY` | **Yes** | DeepSeek API key for chat LLM |
| `PLUGIN_RUNNER_DOCKER_HOST` | **Yes** | TLS Docker Engine for plugin isolation |
| `PLUGIN_RUNNER_CA_CERT_FILE` | **Yes** | Path to runner TLS CA cert |
| `PLUGIN_RUNNER_CLIENT_CERT_FILE` | **Yes** | Path to runner TLS client cert |
| `PLUGIN_RUNNER_CLIENT_KEY_FILE` | **Yes** | Path to runner TLS client key |

## Java Backend (`java-backend/`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_USERNAME` | No | `hfusionhub` | MySQL username |
| `DB_PASSWORD` | **Yes** | — | MySQL password (must match `MYSQL_PASSWORD`) |
| `SPRING_DATASOURCE_URL` | Container | local MySQL URL | MySQL JDBC URL; required when Java runs in Docker/K8s |
| `SPRING_DATA_REDIS_HOST` | Container | `127.0.0.1` | Redis host; set to `redis7`/service name in containers |
| `SPRING_DATA_REDIS_PORT` | No | `6379` | Redis port |
| `PYTHON_AI_INTERNAL_TOKEN` | **Yes** | — | Shared secret for Java ↔ Python |
| `CALLBACK_SECRET` | **Yes** | — | HMAC secret for Python → Java callbacks |
| `ADMIN_PASSWORD` | **Yes** | — | Bootstrap admin account password |
| `AI_SERVICE_URL` | No | `http://localhost:9000` | Python AI service URL |
| `PYTHON_AI_CALLBACK_BASE_URL` | Container | `http://localhost:8080/api` | Java callback base URL reachable from Python |
| `AI_SERVICE_TIMEOUT` | No | `120000` | Timeout in ms |
| `RAG_INDEX_STALE_AFTER_MINUTES` | No | `30` | Index job recovery threshold |
| `RAG_INDEX_MAX_ATTEMPTS` | No | `3` | Max indexing retries |
| `TRUSTED_PROXY_HEADERS` | No | `false` | Enable X-Forwarded-For (reverse proxy only) |
| `DEMO_ENDPOINTS_ENABLED` | No | `true`（dev）/ `false`（prod compose） | `/demo/*` 演示数据端点总开关（import/clear/import-bid 等）；关闭时返回 403。生产默认关闭——`/demo/clear` 有数据破坏性；生产 compose 与 `deploy/.env.example` 已默认 `false` |
| `SPRINGDOC_API_DOCS_ENABLED` | No | `true`（dev）/ `false`（prod compose） | OpenAPI `/v3/api-docs` 开关。生产默认关闭（上线检查清单 P0） |
| `SPRINGDOC_SWAGGER_UI_ENABLED` | No | `true`（dev）/ `false`（prod compose） | Swagger UI 开关。生产默认关闭；临时开启在 `deploy/.env` 显式设置 |
| `APP_CORS_ALLOWED_ORIGINS` | No | ``（fail-closed 同源） | Java CORS 白名单（逗号分隔，如 `https://hub.example.com`）。生产 compose 读取 `CORS_ALLOWED_ORIGINS`；**禁止 `*`**（allowCredentials=true 拒绝通配且属安全隐患）；留空时仅同源。开发/内网穿透用 `APP_CORS_ALLOW_ANY_ORIGIN=true` 显式放行 |
| `AGENT_STATUS_EVENT_SSE_POLL_THREADS` | No | `0`（自动） | 任务 SSE 轮询线程池大小；0 = max(4, CPU/2)。慢连接不再拖垮全局轮询（M8） |
| `APP_AVATAR_DIR` | No | `uploads/avatars` |
| `TRACING_ENABLED` | No | `false` | 分布式追踪总开关（默认关，零开销）。开启后 RestTemplate/WebClient 调 Python 自动携带 `traceparent`，span 经 OTLP 导出到 Tempo（监控栈）；实测见 CHANGELOG 第二十批 |
| `TRACING_SAMPLING` | No | `1.0` | 追踪采样率（0–1）；高流量生产可调 0.1 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | `http://localhost:4318/v1/traces` | OTLP HTTP 导出端点；监控栈 Tempo 为 `http://tempo:4318/v1/traces`（容器内）/ `127.0.0.1:4318`（宿主机直跑） | 用户头像落盘目录（相对应用工作目录；Docker 下在 uploads-data 卷内持久化）。上传接口校验 JPG/PNG/WEBP/GIF 魔数、≤2MB |

> Redis 密码：dev compose 已在 `docker/docker-compose.yml` 通过 `redis-server ... --requirepass "$REDIS_PASSWORD"` 启用（2026-08-21 起生效）。Java 侧 `application.yml` 读取 `REDIS_PASSWORD`，**两端必须一致**，否则 Java 启动报 NOAUTH。生产若 Redis 关闭 requirepass，将 `REDIS_PASSWORD` 留空即可。

### SSO/OIDC 单点登录（Java Backend，默认关闭）

通用 OIDC 客户端（授权码流程），经 `app.oidc.*` 对接外部 IdP（Keycloak / Google / Azure AD / 企业微信 等）。完整接入步骤见 [docs/OIDC.md](OIDC.md)。

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `OIDC_ENABLED` | 是 | `false` | `true` 时登录页展示 SSO 入口 |
| `OIDC_PROVIDER_NAME` | 否 | `generic` | 存入 `sys_user.oauth_provider` |
| `OIDC_AUTHORIZATION_ENDPOINT` | 是 | — | IdP 授权端点 |
| `OIDC_TOKEN_ENDPOINT` | 是 | — | IdP 令牌端点 |
| `OIDC_USERINFO_ENDPOINT` | 是 | — | IdP 用户信息端点 |
| `OIDC_CLIENT_ID` | 是 | — | 在 IdP 注册的 client id |
| `OIDC_CLIENT_SECRET` | 是 | — | client secret（机密） |
| `OIDC_REDIRECT_URI` | 是 | — | 本应用回调地址（需在 IdP 白名单注册） |
| `OIDC_FRONTEND_REDIRECT_URI` | 否 | — | 登录成功后前端落地地址（携带 `?token=`） |
| `OIDC_SCOPES` | 否 | `openid profile email` | 授权范围 |
| `OIDC_USERNAME_CLAIM` / `OIDC_EMAIL_CLAIM` / `OIDC_NAME_CLAIM` | 否 | `preferred_username` / `email` / `name` | userinfo 声明名映射 |
| `OIDC_AUTO_PROVISION` | 否 | `true` | 首次 SSO 登录自动开户（role=pending） |
| `OIDC_LINK_BY_EMAIL` | 否 | `true` | 允许按已验证邮箱关联既有账号 |

## Python AI (`python-ai/.env`)

Copy `python-ai/.env.example` to `python-ai/.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | **Yes** | — | DeepSeek API key for chat LLM calls |
| `DEEPSEEK_BASE_URL` | No | `https://api.deepseek.com` | DeepSeek API endpoint |
| `DEEPSEEK_MODEL` | No | `deepseek-v4-flash` | Model name (chat only, DeepSeek does not provide embedding API) |
| `LLM_HTTP_TIMEOUT_SECONDS` | No | `120` | 共享 HTTP 客户端单请求上游超时（P3） |
| `LLM_MAX_RETRIES` | No | `3` | 429/5xx/连接错误的额外重试次数（首次调用后的重试上限，P3） |
| `LLM_RETRY_BACKOFF_SECONDS` | No | `0.5` | 指数退避基础秒数（每次翻倍 + jitter，P3） |
| `LLM_RESPONSE_CACHE_TTL_SECONDS` | No | `300` | LLM 响应缓存 TTL（P9）；设为 0 禁用缓存 |
| `LLM_RESPONSE_CACHE_FUZZY_ENABLED` | No | `true` | LLM 响应缓存归一化模糊命中（精确 miss 后按空白折叠+casefold 二次查找）；设为 false 仅精确匹配 |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama URL for local LLM fallback and embeddings |
| `OLLAMA_EMBEDDING_MODEL` | No | `bge-m3:latest` | Ollama embedding model (**use this**, not the deprecated `OLLAMA_MODEL`；当前 `.env` 使用 `bge-m3:latest`） |
| `OPENAI_COMPATIBLE_API_KEY` | No | `` | OpenAI 兼容备用供应商（B2）：加入 FailoverLLM 链，主供应商故障时切换 |
| `OPENAI_COMPATIBLE_BASE_URL` | No | `` | 同上，chat-completions 兼容端点（OpenAI/通义/Kimi 等） |
| `OPENAI_COMPATIBLE_MODEL` | No | `` | 同上，模型名（空则用 DEEPSEEK_MODEL） |
| `WEB_SEARCH_PROVIDER` | No | `duckduckgo` |
| `OTEL_ENABLED` | No | `false` | Python 侧 OpenTelemetry 开关（`app/utils/telemetry.py`；未装 otel 包时优雅降级 no-op）。开启且带 `traceparent` 的请求（Java 传来）会并入同一调用链 |
| `CHAT_MULTIMODAL_INPUT_ENABLED` | No | `false` | **对话图片输入**（实验档）：开启后聊天消息可携带图片（≤4 张、单张 ≤5MB），经 Ollama 视觉模型（`RAG_MULTIMODAL_VLM_MODEL`，默认 qwen2.5vl）转中文描述并入提问上下文；关闭时带图请求返回 400 |
| `RAG_QA_GENERATION_ENABLED` | No | `false` | **知识库 QA 对生成**（实验档）：文档解析入库时用对话 LLM 从分块生成问答对（≤4 条/问答块，`RAG_QA_MAX_PER_DOC` 总量上限）并并入索引，提升"用户问法≠原文表述"场景的召回率；生成失败只跳过，不阻断索引 |
| `RAG_QA_MAX_PER_DOC` | No | `20` | 单文档 QA 分块总量上限 |
| `RAG_SEMANTIC_CHUNK_ENABLED` | No | `false` | **语义分块**（实验档）：入库时按相邻句 embedding 余弦相似度找语义断点（`RAG_SEMANTIC_SIM_THRESHOLD`），替代固定窗口切分；句子永不切断，单句超长硬切兜底；embedding 失败自动回退固定窗口，ingestion 不因实验特性失败。TABLE 块保持行对齐不受影响。需重传文档才生效（分块发生在入库时） |
| `RAG_SEMANTIC_SIM_THRESHOLD` | No | `0.55` | 语义断点的相邻句余弦相似度阈值（低于即断开） |
| `RAG_SEMANTIC_MIN_CHUNK` | No | `120` | 语义断点允许的最小块长度（字符），避免过碎 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | —（console） | OTLP HTTP 导出端点；留空退化为控制台输出。监控栈 Tempo 为 `http://tempo:4318/v1/traces` | 联网搜索后端：`duckduckgo`（免 Key）/ `tavily` / `serper` |
| `WEB_SEARCH_API_KEY` | No | `` | Tavily / Serper 的 API Key |
| `WEB_SEARCH_BASE_URL` | No | `` | 搜索 API 地址覆盖（可选） |
| `MCP_SERVERS_CONFIG` | No | `` | MCP 客户端启动配置（JSON 数组）；运行时变更持久化到 `MCP_SERVERS_CONFIG_FILE` |
| `LLM_ALLOW_MOCK` | No | `false` | Enables mock LLM for development/testing only |
| `SERVER_HOST` | No | `0.0.0.0` | FastAPI bind address |
| `SERVER_PORT` | No | `9000` | FastAPI port |
| `CORS_ORIGINS` | No | `http://localhost:5173,...` | Allowed CORS origins |
| `JAVA_BACKEND_URL` | No | `http://localhost:8080` | Callback target |
| `CHUNK_SIZE` | No | `500` | Text chunk size |
| `CHUNK_OVERLAP` | No | `50` | Chunk overlap |
| `EMBEDDING_DIMENSION` | No | `1024` | Vector dimension |
| `EMBEDDING_ALLOW_FALLBACK` | No | `false` | Enables random-vector fallback for development/testing only |
| `EMBEDDING_QUERY_CACHE_TTL_SECONDS` | No | `600` | Query-embedding cache TTL; document chunks never enter the cache. `0` disables (R16-5) |
| `EMBEDDING_QUERY_CACHE_MAX_ENTRIES` | No | `256` | Query-embedding cache LRU capacity |
| `EMBEDDING_DOC_BATCH_SIZE` | No | `32` | Document-indexing embedding batch size (Ollama request timeout is 60s — raise cautiously on CPU) |
| `EMBEDDING_DOC_BATCH_CONCURRENCY` | No | `2` | Concurrent embedding batches during document indexing |

DeepSeek does not provide the embedding API used here. For document indexing outside tests, configure Ollama or another real embedding provider; keep `EMBEDDING_ALLOW_FALLBACK=false` in production.

The frontend dev server runs on `http://localhost:3000`. Normal browser traffic goes through the Vite `/api` proxy to Java, so Python CORS is usually not involved. If a browser client calls Python directly, include `http://localhost:3000` in `CORS_ORIGINS`.

### Feature Flags (Python AI)

All advanced RAG features are gated via environment variables in `python-ai/.env` (or runtime-synced from the Java backend via `/api/feature-flag/all` when `JAVA_BACKEND_URL` is set). See `python-ai/.env.example` for the complete list.

| Flag | Default | Status | Dependencies |
|------|---------|--------|--------------|
| `RAG_HYBRID_ENABLED` | `true` | ✅ Stable | None |
| `RAG_RERANKER_MODE` | `lexical` | ✅ 稳定（默认启用；`rag.reranker.enabled` 已默认开启，前端「能力开关」页可关） | `lexical` 零依赖；`cross_encoder` 需 `pip install -r requirements-reranker.txt` + 模型下载（失败自动降级，装好后无需重启） |
| `RAG_MULTIMODAL_ENABLED` | `false` | ❄️ Frozen | Tesseract OCR + `pip install -r requirements-multimodal.txt` |
| `RAG_AGENT_WORKFLOW_ENABLED` | `true` | 🧪 Beta | None (pure Python)；当前 `.env` 已启用 |
| `RAG_MULTI_AGENT_ENABLED` | `false` | 🧪 Beta（V59 起 flag 默认开启） | Requires P9 enabled + selected KB（运行时由 `agent.multi_agent.enabled` flag 控制） |
| `MEMORY_LONG_TERM_ENABLED` | `false` | 🧪 Beta（运行时由 `memory.long_term.enabled` flag 统一治理，V80 默认 FALSE） | LLM 调用（记忆抽取）+ Java `/internal/memory/*` 通道 |
| `AGENT_NATIVE_TOOL_CALLS_ENABLED` | `false` | 🧪 Beta（运行时由 `agent.native_tool_calls.enabled` flag 统一治理，V81 默认 FALSE） | provider 原生 tool-calls（DeepSeek / OpenAI 兼容 / Ollama ≥0.4）；不支持自动降级文本 ReAct |

**长期记忆接线（2026-08-30 Batch 1）**

- 触发：每 `MEMORY_CONSOLIDATE_EVERY_TURNS` 轮对话收尾后台抽取一次；会话删除前由 Java
  异步回调 `POST /api/internal/memory/consolidate` 携带消息快照做最终抽取。
- 存储：抽取结果经 `POST /api/internal/memory/entries` 落 Java `memory_entry` 表
  （Java 侧按 user+content 去重，单批 ≤50）。
- 注入：Agent 组装上下文前经 `GET /api/internal/memory/relevant` 拉取相关记忆
  （Java 按重要性+词命中排序），以「非指令」标注块拼入 system prompt。
- 关联 env：`MEMORY_CONSOLIDATE_EVERY_TURNS`（默认 6，下限 2）、
  `MEMORY_CONTEXT_MAX_ENTRIES`（默认 8，注入条数上限）、
  `MEMORY_CONTEXT_MAX_TOKENS`（默认 600，注入块粗略 token 预算）、
  `MEMORY_INTERNAL_TIMEOUT_SECONDS`（默认 5）。
- 全链路失败静默降级：flag 关闭/后端不可达时零网络调用、零抽取，不阻塞聊天主链路。
**语音 STT/TTS（2026-08-30 Batch 10）**

- `VOICE_ENABLED`：`false`（默认）| `true`。开启需同时配置
  `VOICE_OPENAI_BASE_URL` / `VOICE_OPENAI_API_KEY` / `VOICE_STT_MODEL` /
  `VOICE_TTS_MODEL`（OpenAI 兼容 /v1/audio/* 端点）。
- 前端聊天页经 `GET /voice/status` 决定按钮渲染；STT 收原始音频字节
  （≤10MB，X-Audio-Filename 头标注格式），TTS 返回 mp3 二进制。
- 关闭时端点 503、按钮不渲染；引擎不可用 503 不做静默降级。

**知识库资源级授权矩阵（2026-08-30 Batch 10）**

- `kb_share.permission` 两档生效：`read`（只读）| `read_write`（可上传文档）；
  删除/管理等操作仍为所有者专属。
- 查询入口：`KbShareService.getEffectivePermission(userId, kbId)` →
  `"owner" | "read_write" | "read" | null`。
- 共享 API `POST /knowledge-base/share` 增加 `permission` 字段（默认 read，
  重复共享=档位更新）；前端知识库详情页分享对话框提供权限选择。

**Embedding 多通道（2026-08-30 Batch 5）**

- `EMBEDDING_PROVIDER`：`ollama`（默认本地）/ `openai_compatible`（通义/OpenAI 等
  `/v1/embeddings` 端点）。openai_compatible 配置齐全时优先使用，失败自动回落 Ollama。
- 关联 env：`EMBEDDING_OPENAI_BASE_URL` / `EMBEDDING_OPENAI_API_KEY` /
  `EMBEDDING_OPENAI_MODEL` / `EMBEDDING_OPENAI_DIMENSION`（默认 1024）。
- 维度 fail-closed：模型返回维度 ≠ 配置维度即抛错（Milvus collection 以固定维度建表，
  切换供应商必须重建向量索引）。
- 检索元数据过滤（同批）：`retriever.retrieve(..., metadata_filter={"field": "value"})`
  等值过滤贯穿向量/关键词双通道与 `/api/rag/debug/search`、`/api/rag/eval`、
  `search_knowledge_base` 工具；存储层超额召回 + 谓词后过滤，无 schema 变更。

**原生 function calling（2026-08-30 Batch 2）**

- ReAct Agent 每步优先以原生 tool-calls 调用 provider（`tools`/`tool_choice` 经
  ModelGateway 透传；Ollama 的 dict arguments 归一化为 OpenAI JSON 字符串形态）。
- provider 报错（不支持 tools 的旧版模型/网关）自动降级回文本 Thought/Action 协议，
  flag 关闭时完全走文本路径，零行为变化。
- ReAct 步数上限改为配置驱动：`RAG_AGENT_MAX_STEPS`（默认 5 → **12**），
  ReactAgent 未显式传 max_steps 时回落该配置；`max_tool_steps` 请求字段上限放宽到 24。
- 关联 env：`AGENT_NATIVE_TOOL_CALLS_ENABLED`（降级回退值，默认 false）。

**P5: Hybrid Retrieval (Vector + BM25) — ✅ Stable**

Default: enabled. Combines Milvus vector search with BM25 keyword search via Reciprocal Rank Fusion (RRF). This is the recommended retrieval mode and is fully tested.

**P7: Scoped GraphRAG — 🗑️ 已移除（2026-08-29）**

> **治理状态**：冻结期间收益不稳定（内存图索引、重启重建、不推荐 >10,000 文档知识库），已按清理决策整体移除代码与测试（`scoped_graph.py` / `knowledge_graph.py` / GraphChannel / `/api/rag/graph/status`）。检索通道收敛为向量 + 关键词混合（P5）。历史 trace 中 `source=graph` 的记录仅作展示保留。

**P6: Second-Stage Reranking — ✅ 稳定（lexical 默认）+ cross_encoder 基准解锁（2026-08-29）**

对一阶段融合候选做二次打分后进入 LLM 上下文。

Modes:
- `disabled` — 不重排
- `lexical` — 确定性词法重排（无额外依赖）✅ 默认模式
- `cross_encoder` — 神经交叉编码器重排（BAAI/bge-reranker-base，sentence-transformers）✅ 基准已解锁

> **治理状态（2026-08-29）**：cross_encoder 冻结解除。`scripts/eval_reranker.py` 三臂离线 A/B 基准（220 用例合成语料，20 候选）实测：recall@10 = none 0.832 / lexical 0.843 / **cross_encoder 0.846（最高）**；nDCG@10 = none 0.776 / lexical 0.760 / cross_encoder 0.771（与一阶段持平）；代价 CPU 上 ~1.15s/查询。报告：`evaluation/reports/reranker_ab.json`。结论：**召回优先场景推荐 cross_encoder，默认保持 lexical（零依赖零延迟）**。加载失败自动回落一阶段排序（失败实例不缓存，装好依赖即生效、无需重启）。

Env:
| 变量 | 默认 | 说明 |
|---|---|---|
| `RAG_RERANKER_MODE` | `lexical` | `lexical` / `cross_encoder` / `disabled` |
| `RAG_RERANKER_MODEL` | `BAAI/bge-reranker-base` | cross_encoder 模型 |
| `RAG_RERANK_CANDIDATE_COUNT` | `20` | 重排启用时的一阶段召回候选数 |

**P8: Multimodal Evidence — ✅ 恢复投入（vision-LLM 路线已实现，2026-08-29）**

默认关闭。从 PDF/DOCX 提取内嵌图片，产出普通文本块进入既有检索管道（`multimodal` metadata 标记来源），两个引擎按序尝试：

1. **vision-LLM（推荐，新增）**：Ollama 视觉模型（如 `qwen2.5vl:3b`）生成中文图片描述（`kind=image_vlm`），图表/照片语义理解远强于 OCR。先 `ollama pull qwen2.5vl:3b`。
2. **Tesseract OCR（兜底）**：文字截图转写（`kind=image_ocr`），也是 VLM 不可用时的降级路径。

> **治理状态**：Tesseract-only 时代的冻结解除。原 CLIP 双向量索引实验模块（`multimodal_rag.py`，从未接线生产）已删除；现实现与 P8 设计哲学一致——图片证据变普通文本块，KB 隔离/引用/删除/trace 全走既有路径，任一引擎失败只跳过该图片，永不阻断文本索引。

Env:
| 变量 | 默认 | 说明 |
|---|---|---|
| `RAG_MULTIMODAL_ENABLED` | `false` | 总开关 |
| `RAG_MULTIMODAL_VLM_ENABLED` | `false` | vision-LLM 描述引擎 |
| `RAG_MULTIMODAL_VLM_MODEL` | `qwen2.5vl:3b` | Ollama 视觉模型 |
| `RAG_MULTIMODAL_VLM_BASE_URL` | OLLAMA_BASE_URL | VLM 服务地址 |
| `RAG_MULTIMODAL_VLM_TIMEOUT_SECONDS` | `90` | 单图描述超时 |
| `RAG_MULTIMODAL_OCR_*` | — | Tesseract 兜底（command/language/timeout 等） |

**P9: Bounded Single-Agent Workflow — 🧪 Beta（当前已启用）**

默认开启（当前 `.env` 为 `true`）。为 ReAct Agent 增加超时（45s）、重试（1 次，0.2s 延迟）与运行追踪。仅白名单工具可被调用。

**P10: Multi-Agent Collaboration — 🧪 Beta（默认开启）**

默认开启（Flyway V59 起 `agent.multi_agent.enabled` 默认 TRUE）。并发专家 Agent（检索/分析/校验/综合）+ 确定性证据校验器；输出缓冲至 citations 通过本地范围校验。

> **治理状态（2026-08-24）**：已按用户要求解除冻结（V59）。实验性、增加延迟、critic 仅单库校验；仍可在前端「能力开关」页按需关闭。

## Critical: PYTHON_AI_INTERNAL_TOKEN

This token **must be identical** in both:
1. Java backend terminal (`$env:PYTHON_AI_INTERNAL_TOKEN="..."`)
2. Python AI terminal (`$env:PYTHON_AI_INTERNAL_TOKEN="..."`)

If they differ, all Java → Python requests will fail with 401/403.

## Critical: DB_PASSWORD = MYSQL_PASSWORD

The Java `DB_PASSWORD` must match the `MYSQL_PASSWORD` used when starting Docker. Using Docker:
```powershell
# docker/.env (or inline env)
MYSQL_PASSWORD=mysecurepassword

# Java backend terminal
$env:DB_PASSWORD="mysecurepassword"
```

## Security Notes

- **Never commit** `.env` files or hardcoded secrets to Git
- Use `docker/.env.example` and `python-ai/.env.example` as templates
- For production, use a secrets manager (Vault, AWS Secrets Manager, etc.) or K8s Secrets
