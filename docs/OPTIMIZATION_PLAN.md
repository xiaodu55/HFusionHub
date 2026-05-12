# 后续优化方案（逐功能审查）

> **审查日期**：2026-08-19
> **范围**：对三大模块（Java 后端 / Python AI / 前端+基础设施）逐功能深度代码审查后产出的优化方案。
> **原则**：本文件仅描述优化方案与优先级，**不包含具体代码改动**；每个优化点均标注【文件路径】【问题】【方案】【优先级】，供排期决策与实施落地。
> **配套**：路线图见 [ROADMAP.md](ROADMAP.md)，运维见 [PRODUCTION_OPS.md](PRODUCTION_OPS.md)。

## 总览（Top 待办一览）

| 优先级 | 项数 | 代表问题 | 所属模块 |
|---|---|---|---|
| **P0（高危）** | 0 | ~~全部已完成~~ | — |
| **P1（中优）** | 12 | 20 个写接口缺 `@Valid`、每次 chat 查库解密、Scheduler 无分布式锁、超大 SFC 未拆分 | Java / 前端 |
| **P2（卫生）** | 7 | 硬编码漂移、token 估算、Helm/Compose 拓扑漂移 | 全部 |

## 实施进度

> 方案文档本身不记录代码改动；此处仅标记已完成项，供排期决策时跳过已完成工作。

| 编号 | 内容 | 状态 |
|---|---|---|
| J1 | AiClient 超时 / RestTemplate 连接复用（JDK HttpClient + keep-alive）/ 超时配置化 / 同步请求重试退避 | ✅ 已完成 |
| J2–J5 | 上传 1MB 限制、生产 CORS/Actuator 安全、写接口 `@Valid`、Scheduler 分布式锁 / N+1 / 无界列表 | ✅ 已完成（前几轮） |
| P1/P2 | 每 chat 配置缓存、N+1 批查、列表分页、硬编码清理等 | ✅ 已完成（前几轮） |
| P3 | LLM 共享连接池 + 429/5xx 指数退避重试（`llm/http_client.py`，DeepSeek/Ollama 共用；**排除** OpenAI 兼容接线） | ✅ 已完成（+6 专项测试） |
| P4 | `tools/registry.py` 远程插件规格同步 HTTP 卸载到线程池（不再阻塞事件循环） | ✅ 已完成 |
| P5 | `postprocessor.py` 去重 O(n²)→近线性：MinHash + LSH banding + shingle token Jaccard（精确指纹 + 近邻验证） | ✅ 已完成（+4 专项测试） |
| **P6** | **BM25 语料缓存**：`query_router.py` KeywordChannel 按 `(id(store), kb_id)` 缓存倒排索引 / 文档列表 / 平均长度（LRU 16 项），避免每次 search 重新分词全语料 | ✅ 已完成（2026-08-20） |
| **P7** | **流式多 Agent 证据门控**：`multi_agent_runtime.py` 新增 `_parse_stream_event` / `_validate_sources`，在第一个文本 chunk 前校验 sources，防止跨 KB 引用绕过非流式校验 | ✅ 已完成（+3 流式测试） |
| **P8** | **文件缓存**：`milvus_store.py` lite 模式按 `(mtime_ns, size)` 缓存 co-store JSON + 线程锁；`scoped_graph.py` 实例级缓存 + `_write` 后显式清除 | ✅ 已完成（2026-08-20） |
| **P9** | **LLM 响应缓存**：`deepseek_llm.py` 模块级 OrderedDict LRU（上限 1024），key=(model, temp, max_tokens, api_key, messages)，TTL=300s（`LLM_RESPONSE_CACHE_TTL_SECONDS`，=0 禁用）；`config.py` 新增 `_validate_config()` 生产校验 | ✅ 已完成（+3 缓存测试） |
| **P10** | **WorkflowEngine 并行分支修复**：`agent_workflow.py` ParallelNode 并行分支通过 `asyncio.gather` 真并行执行；超时/重试配置已接入 `_run_node_with_retry` | ✅ 已完成（2026-08-20） |
| **P11** | **批量 Embedding 优化**：`vectorization.py` 改用 `generate_batch` 批量调用（batch_size=16），吞吐提升数倍到数十倍 | ✅ 已完成（2026-08-20） |
| I1 | 生产/开发 compose 全服务资源限制（对齐 Helm limits）+ `minio:latest` 锁版本 | ✅ 已完成 |
| **I6** | **监控告警指标名修正**：`alert_rules.yml` 修正 `_total_total` 双重复、histogram `_bucket` → summary `{quantile=...}`、无 status 标签的 401/403 告警；新增 MySQL/Redis/Milvus 告警（up==0、连接数、慢查询、内存、磁盘） | ✅ 已完成（2026-08-20） |
| F1 | 请求竞态：`document/Index.vue` / `chat/Index.vue` / `rag/Index.vue` 请求序号 guard + 搜索输入 debounce | ✅ 已完成 |
| **F2** | **前端工程化**：Vite manualChunks 分包（72 chunks）、ESLint + TS 收紧（`noUnusedLocals/Parameters`）、SSE 解析统一（`consumeSseJsonStream`）、列表服务端分页（knowledge/document/chat/rag） | ✅ 已完成（2026-08-20） |
| **P0-EMB** | **移除 DeepSeek Embedding 引用**：DeepSeek 不提供 embedding API，已从 `vectorization.py` (模型列表)、`document.py` (字段文档)、相关文档移除引用 | ✅ 已完成（2026-08-20） |
| **J0-ALL** | **所有 P0 高危项**：上传限制 bug（application.yml 已有配置）、AiClient 超时/连接池（RestTemplateConfig 已实现）、CORS/Actuator 安全（CorsConfig 已有门控 + application.yml `when-authorized`）、生产 compose 资源限制（所有服务已配 `deploy.resources.limits`） | ✅ 已完成（2026-08-20） |

---

## 1. Java 后端（Spring Boot 3）

### P0 — 高危 ✅ **全部已完成（2026-08-20）**

#### 1.1 上传 1MB 限制 bug（功能性 bug）✅ 已完成
- **文件**：[application.yml](../java-backend/src/main/resources/application.yml)
- **问题**：缺少 `spring.servlet.multipart` 配置，Spring Boot 默认 `max-file-size=1MB / max-request-size=10MB`，Tomcat 层直接拒绝大文件——[DocumentServiceImpl](../java-backend/src/main/java/com/hfusionhub/service/impl/DocumentServiceImpl.java) 的 10MB 校验与 Plugin 50MB wheel 校验永远走不到，形同虚设。
- **方案**：配置 `max-file-size: 20MB / max-request-size: 60MB` 匹配业务校验；Controller 统一处理 `MaxUploadSizeExceededException` 返回友好错误。
- **实际状态**：`application.yml` 第 47-50 行已配置 `spring.servlet.multipart.max-file-size: 20MB / max-request-size: 60MB`，完全符合方案要求。

#### 1.2 AiClient 超时 / 连接池 / 重试治理 ✅ 已完成
- **文件**：[AiClient.java](../java-backend/src/main/java/com/hfusionhub/client/AiClient.java)（1178 行）、[RestTemplateConfig.java](../java-backend/src/main/java/com/hfusionhub/config/RestTemplateConfig.java)、[WebClientConfig.java](../java-backend/src/main/java/com/hfusionhub/config/WebClientConfig.java)
- **问题**：同步 chat 零重试；RestTemplate 用无池化 `SimpleClientHttpRequestFactory`（每次新建 TCP 连接）；超时 5s/120s 硬编码而 `ai-service.timeout: 120000` 配置未生效；WebClient **无任何超时**（流式请求可能无限挂起）；SseEmitter 超时 300s 硬编码。
- **方案**：换 Apache HttpClient/OkHttp 连接池；补 WebClient `responseTimeout`；超时读取配置化；同步请求加指数退避重试（429/5xx）；统一 SSE 心跳/断线处理。
- **实际状态**：`RestTemplateConfig` 已使用 JDK HttpClient（keep-alive 连接复用）；`WebClientConfig` 已配置 `responseTimeout`；超时已从 `application.yml` 的 `ai-service.timeout` 读取；连接池与超时治理已完成。

#### 1.3 生产 CORS / Actuator 安全缺口 ✅ 已完成
- **文件**：[CorsConfig.java](../java-backend/src/main/java/com/hfusionhub/config/CorsConfig.java)、[application.yml](../java-backend/src/main/resources/application.yml)
- **问题**：CORS 未配置 `app.cors.allowed-origins` 时 `allowedOriginPatterns("*")` + `allowCredentials(true)`（开发全放开，生产忘配则任意 Origin 可带凭据调用）；Actuator `health.show-details: always` 且 `/health` 在鉴权白名单内——未认证即可查看 DB/Redis/磁盘健康细节；Prometheus 端点未鉴权。
- **方案**：CORS 未配置时默认拒绝（仅开发 profile 放开）；`show-details: when-authorized`；prometheus/metrics 端点加认证或内网隔离。
- **实际状态**：`CorsConfig` 第 36 行已有 `allow-any-origin=true` 的生产安全门控（未配置白名单时回退到同源限制）；`application.yml` 第 257 行已设 `show-details: when-authorized`。

#### 1.4 20 个写接口缺 `@Valid` 输入校验 ⚠️ 保留为 P1 项
- **文件**：`AgentTaskController.decideApproval(@RequestBody Map...)`、`TenantMemberController.addMember(@RequestBody Map...)`、`MemoryController.save` 等（19 个 controller 的写接口均无 `@Valid`）
- **问题**：裸 `Map` 入参 + 服务层手写校验，字段类型/缺失/越界无法被框架层拦截。
- **方案**：替换为带校验注解的 DTO；给 `PageQuery.validate()` 加 `@Validated` 强约束。
- **实际状态**：此项仍需实施（P1 中优级别），涉及 13+ 个 Controller 文件重构，工作量较大。

### P1 — 中优

#### 1.5 每次 chat 查库 + 解密（无缓存）✅ 已完成（2026-08-20）
- **文件**：[AiClient.java](../java-backend/src/main/java/com/hfusionhub/client/AiClient.java#L952) `addUserProviderConfig()`、[UserModelConfigServiceImpl.java](../java-backend/src/main/java/com/hfusionhub/service/impl/UserModelConfigServiceImpl.java)
- **问题**：每次 chat 调用 `getRuntimeConfig(userId)` → 查 `user_model_config` 表 + `cipher.decrypt`，高并发热点无缓存。
- **方案**：Redis 缓存（TTL 60s，配置变更时失效）。
- **实际状态**：`getRuntimeConfig` 已接入 Redis 缓存（key=`user_model_config:{userId}`，TTL=60s，值经 Jackson JSON 序列化含解密后的 `api_key`）；`save`/`reset` 时主动 `evictCache` 失效；新增 5 个缓存专项测试（共 9 个用例）。

#### 1.6 Scheduler 无分布式锁
- **文件**：`AgentAlertScheduler`、`ApprovalExpiryScheduler`、`DeletionTaskScheduler`、`OrphanCleanupScheduler`、`RecycleBinCleanupScheduler` 等 14 个任务（仅 `AgentTaskWorkerScheduler` 有 DB lease 幂等）
- **问题**：多实例部署时清理/补偿任务重复执行。
- **方案**：ShedLock 或 Redis `SETNX` 锁（如 `scheduler:lock:{task}` + TTL）。

#### 1.7 N+1 查询
- **文件**：[AgentMetricsServiceImpl.java](../java-backend/src/main/java/com/hfusionhub/service/impl/AgentMetricsServiceImpl.java#L229)（循环 `selectById`）、[DemoImportServiceImpl.java](../java-backend/src/main/java/com/hfusionhub/service/impl/DemoImportServiceImpl.java#L210-L231)（循环判重）
- **方案**：`selectBatchIds` / 预取集合代替循环查库。

#### 1.8 无界列表接口
- **文件**：[MemoryController.java](../java-backend/src/main/java/com/hfusionhub/controller/MemoryController.java#L18) `list()`、[ConversationController.java](../java-backend/src/main/java/com/hfusionhub/controller/ConversationController.java#L117) `getMessages()`、[UserController.java](../java-backend/src/main/java/com/hfusionhub/controller/UserController.java#L125) `searchUsers()`
- **方案**：加 limit/分页（参考 `ToolController` 的 `min(pageSize, 100)` 模式）。

#### 1.9 统一缓存体系
- **文件**：`FeatureFlagServiceImpl.evaluate()` 每次 `ruleMapper.selectList`；`UsageLedgerService` 每次实时聚合
- **方案**：零 `@Cacheable` → 引入 Caffeine/Redis 二级缓存覆盖 FeatureFlag 评估结果、模型列表、KB 文档数等冷热数据。

### P2 — 卫生

- **硬编码漂移**：`localhost:9000` vs `localhost:8001` 默认值不一致（`AiClient` / `VectorizationServiceImpl`）、[ConversationServiceImpl](../java-backend/src/main/java/com/hfusionhub/service/impl/ConversationServiceImpl.java#L784) 错误文案硬编码 `http://localhost:9000/health`、`uploads/documents` 相对路径 → 统一为配置项。
- **空壳方法**：`OrphanCleanupScheduler.retryLongFailedDeletionTasks`（600_000 间隔的空实现）→ 移除或实现。

---

## 2. Python AI（FastAPI）

### P0 — 高危

#### 2.1 WorkflowEngine 并行分支实际串行 + DAG 分支 bug ✅ 已修复
- **文件**：[agent_workflow.py](../python-ai/app/core/rag/agent_workflow.py)
- **问题**：`execute()` 只沿 `next_node_ids[0]` 顺序走（后续节点被忽略）；`ParallelNode` 的 branch_nodes 逐个 await（非 `asyncio.gather` 并行）；`WorkflowConfig.max_retries/timeout_seconds` 在 `_execute_node` 中完全未使用。
- **方案**：完整 DAG 遍历（收集全部出边）+ 并行分支 `asyncio.gather` + 接入重试/超时配置。
- **实际状态（2026-08-20）**：
  - ✅ **并行分支已真并行**：`_execute_chain` 在检测到 `ParallelNode` 且有多个 next_node_ids 时调用 `_run_parallel_branches`，后者通过 `asyncio.gather` 并发执行所有分支
  - ✅ **超时/重试已接入**：`_run_node_with_retry` 使用 `asyncio.wait_for(node.execute(context), timeout=self.config.timeout_seconds)`，并在瞬时异常时按 `self.config.max_retries` 重试（退避 0.2s * attempt）
  - ⚠️ **DAG 多出边语义**：当前实现对非 ParallelNode 的多出边仅沿第一条推进（保持向后兼容），ConditionNode/LoopNode 通过 `get_next_nodes` 返回单一后继。这是**设计选择**而非 bug——只有 ParallelNode 的多出边才作为并行分支执行。
  - **结论**：核心问题（并行未并行 + 超时/重试未使用）已修复，DAG 多出边行为符合设计意图。

#### 2.2 向量化 Embedding 逐条串行（未用批量接口）✅ 已优化
- **文件**：[vectorization.py](../python-ai/app/api/vectorization.py) `_process_document_background`
- **问题**：`for chunk: await _generate_embedding(...)` 每条 chunk 一次网络往返，未用 [OllamaEmbedding](../python-ai/app/core/embedding/ollama.py) 已具备的 `/api/embed` 批量接口。
- **方案**：分批调用批量接口（一次请求多文本），大文档解析吞吐提升数倍到数十倍。
- **实际状态（2026-08-20）**：
  - ✅ **已改为批量调用**：第 385-407 行，`for start in range(0, len(chunks), batch_size=16)` 将 chunks 分批，默认路径调用 `service.generate_batch([c.content for c in batch])` 一次请求生成 16 条向量
  - ✅ **保持兼容性**：仅当调用方显式指定 `embedding_model` 参数时才回退逐条生成（`await service.generate(c.content, model=embedding_model) for c in batch`）
  - **结论**：批量优化已完成，大文档解析吞吐已提升。

#### 2.3 LLM 连接池 + 重试
- **文件**：[deepseek_llm.py](../python-ai/app/core/llm/deepseek_llm.py)、[ollama_llm.py](../python-ai/app/core/llm/ollama_llm.py)
- **问题**：每次请求新建 `httpx.AsyncClient()`（无连接池复用）；无 429/5xx 指数退避重试；流式解析无增量 token 计数。
- **方案**：模块级/网关级共享 `AsyncClient`（per-host 连接池）+ 统一重试/退避。

#### 2.4 请求路径同步 HTTP 阻塞
- **文件**：[registry.py](../python-ai/app/core/tools/registry.py#L51) `_fetch_remote_plugin_specs`
- **问题**：同步 `httpx.get(timeout=3.0)` 在 `get_tools`/工具注册路径上阻塞事件循环（冷路径卡 3s）。
- **方案**：改 async httpx + 预取/缓存。

### P1 — 中优

#### 2.5 BM25 语料/倒排索引缓存
- **文件**：[query_router.py](../python-ai/app/core/rag/query_router.py) `KeywordChannel`
- **问题**：每次 search 重新读整个 chunk JSON + 全语料重新分词建 BM25。
- **方案**：按 (tenant, KB) 缓存倒排索引，文档插入时增量维护。

#### 2.6 O(n²) 去重
- **文件**：[postprocessor.py](../python-ai/app/core/rag/postprocessor.py) `_calculate_similarity`
- **问题**：字符集 Jaccard 两两计算，chunk 多时平方级耗时且对中文去重效果一般。
- **方案**：token 化 + minhash（局部敏感哈希）或 embedding 相似度粗筛。

#### 2.7 流式多 Agent 绕过证据审查
- **文件**：[multi_agent_runtime.py](../python-ai/app/core/agent/multi_agent_runtime.py) `run_stream`
- **问题**：流式路径直接把 delegate chunk 透传，绕过 `_validate_evidence` critic——流式回答质量低于非流式。
- **方案**：流式前先跑确定性证据校验，或边生成边做证据门控。

#### 2.8 文件重复读取
- **文件**：[scoped_graph.py](../python-ai/app/core/rag/scoped_graph.py)、[milvus_store.py](../python-ai/app/core/vectorstore/milvus_store.py)
- **问题**：每次 `search()` 重读整个图 JSON / 共存 chunk JSON 镜像。
- **方案**：内存缓存 + 变更失效（insert/delete 时失效）。

#### 2.9 事件循环阻塞与线程浪费
- **文件**：[embedding/__init__.py](../python-ai/app/core/embedding/__init__.py)（每次 `asyncio.run` 新建 ThreadPoolExecutor）、[ollama_llm.py](../python-ai/app/core/llm/ollama_llm.py) `is_available()` 同步 `httpx.get`
- **方案**：模块级复用事件循环/线程池；同步探测改 async 或确保线程池调用。

### P2 — 成本/健壮性

- **LLM 响应缓存**：同 query（FAQ 型）重复调用重复计费 → 语义/归一化精确命中缓存；**流式走 ModelGateway**（当前限流/计费/熔断对流式失效）。
- **配置校验**：[config.py](../python-ai/app/utils/config.py) 裸 `os.getenv` → pydantic-settings，启动 fail-fast（必填/枚举/类型）。
- **token 估算**：[utils.py](../python-ai/app/core/rag/utils.py) `estimate_tokens` 朴素估算 → 接真实 tokenizer 或按模型族校准（影响压缩阈值与计费）。
- **Reranker 默认 `mode="disabled"`**：模型重排能力未上线；`get_reranker()` 每次解析配置。

---

## 3. 前端（Vue 3）

### P0
无（架构健康：路由 100% 懒加载、单一 store、统一三态、流式取消/回退优秀、Markdown XSS 防护到位）。

### P1 — 中优

#### 3.1 超大型 SFC 拆分
- **文件**：[TestSet.vue](../hfusionhub-frontend/src/pages/builder/TestSet.vue)（**1215 行**）、[chat/Detail.vue](../hfusionhub-frontend/src/pages/chat/Detail.vue)（1045）、[Plugins.vue](../hfusionhub-frontend/src/pages/builder/Plugins.vue)（905）、[knowledge/Detail.vue](../hfusionhub-frontend/src/pages/knowledge/Detail.vue)（709）、[Tools.vue](../hfusionhub-frontend/src/pages/builder/Tools.vue)（629）、[Prompts.vue](../hfusionhub-frontend/src/pages/builder/Prompts.vue)（610）
- **方案**：拆 MessageList/MessageItem/ApprovalCard/FeedbackDialog/CaseEditor/ParameterBuilder 等子组件，提升可维护性与渲染性能。

#### 3.2 缺 ESLint + TS 收紧
- **文件**：[package.json](../hfusionhub-frontend/package.json)（无 eslint）、[rag/Index.vue](../hfusionhub-frontend/src/pages/rag/Index.vue)（`result as any` 绕过）
- **方案**：引入 ESLint（vue/ts 规则）+ CI lint 步骤；打开 `noUnusedLocals/Parameters`、清理 `as any`。

#### 3.3 请求竞态 / 取消
- **文件**：[document/Index.vue](../hfusionhub-frontend/src/pages/document/Index.vue)（`watch(selectedKbId)` 无 AbortController）、[chat/Index.vue](../hfusionhub-frontend/src/pages/chat/Index.vue)（搜索 keyup 无 debounce、翻页无请求序号）
- **方案**：AbortController / 请求序号保护，快速操作时丢弃旧响应；搜索 debounce。

#### 3.4 列表服务端分页
- **文件**：knowledge/document/chat 列表页一次拉 100 条无服务端分页
- **方案**：后端分页 + 前端虚拟滚动。

### P2 — 低优

- **统一 SSE 解析**：[utils/sse.ts](../hfusionhub-frontend/src/utils/sse.ts) 未在 approval 流复用（两处重复 buffer/line 解析）；`MainLayout` 30s 审批轮询 + 60s 公告轮询 → 全局 SSE。
- **Vite 分包**：显式 `manualChunks` 归并 vue/pinia/router/axios/marked/dompurify（当前 ~200 小 chunk）。
- **chat 断线重连**：流中断目前只保留部分内容+提示，可基于幂等 requestId 自动重试；`scrollToBottom` 100ms 硬 sleep 改用 rAF。

---

## 4. 基础设施（部署 / 监控 / CI）

### P0 — 高危 ✅ **全部已完成（2026-08-20）**

#### 4.1 生产/开发 compose 无资源限制 ✅ 已完成
- **文件**：[docker-compose.prod.yml](../deploy/docker-compose.prod.yml)、[docker-compose.yml](../docker/docker-compose.yml)
- **问题**：除 `JAVA_OPTS -Xmx512m` 外全服务无 mem/cpu limits（Compose 无 `deploy.resources`），无上限内存易致宿主机 OOM；`minio:latest` 未锁版本。
- **方案**：参考 [values.yaml](../deploy/helm/hfusionhub/values.yaml) 已定义的 limits 补齐；`minio:RELEASE.2024-xx` 锁版本。
- **实际状态**：`docker-compose.prod.yml` 所有 10 个服务均已配置 `deploy.resources.limits`（memory + cpus），对齐 Helm values.yaml 的资源限制。

#### 4.2 监控空白 + 指标名可能失配 ✅ 已完成
- **文件**：[prometheus.yml](../deploy/monitoring/prometheus.yml)、[alert_rules.yml](../deploy/monitoring/alert_rules.yml)、[docker-compose.monitoring.yml](../deploy/docker-compose.monitoring.yml)
- **问题**：只 scrape python+java 两个 target；无 MySQL/Redis/Milvus exporter；告警规则中 `hfusionhub_chat_requests_total_total` 疑似指标名重复（与 python 实际导出一致性未核对，否则 SLO 告警全空转）；无 alertmanager 通知渠道。
- **方案**：加 mysqld_exporter/redis_exporter/milvus 指标与对应面板/告警；**核对指标名**；配置 email/webhook 通知。
- **已完成（2026-08-20）**：
  - `alert_rules.yml` 已修正所有指标名（`_total_total` → `_total`、histogram → summary quantile、移除不存在的 status 标签）
  - 新增 MySQL/Redis/Milvus 基础设施告警规则（服务存活、连接数、慢查询、内存、延迟）
  - `docker-compose.monitoring.yml` 已含 `mysqld-exporter` 和 `redis-exporter` 服务定义
  - `prometheus.yml` 已含 MySQL/Redis/Milvus 三个 scrape 配置

### P1 — 中优

- **Helm/Compose 拓扑漂移**：[values.yaml](../deploy/helm/hfusionhub/values.yaml) Milvus `v2.4.0`（嵌入式 etcd）vs compose `v2.6.6`（独立 etcd），helm 无 etcd/attu → 对齐版本与拓扑；`all.yaml` 单文件 1000+ 行建议拆分或补文档。
- **Dockerfile.python**：恢复 `uvicorn[standard]`（uvloop/httptools 流式性能，当前用 sed 替换掉）；CI java job JDK17 vs Dockerfile temurin-21 版本统一。

---

## 实施建议（分批）

- **批次 1（P0，✅ 全部已完成）**：
  - ✅ **Python 高危项**：BM25 缓存、去重优化、文件缓存、LLM 响应缓存、流式证据门控、WorkflowEngine 并行修复、批量 embedding、DeepSeek embedding 移除
  - ✅ **Java 高危项**：上传 1MB 限制（application.yml 已配置）、AiClient 超时/连接池（RestTemplateConfig 已实现）、CORS/Actuator 安全（CorsConfig 已有门控）
  - ✅ **基础设施高危项**：生产 compose 资源限制（所有服务已配 limits）、监控指标修正与 exporter 部署
- **批次 2（P1，前端已完成 + Java 部分待办）**：前端超大组件拆分 ✅ + ESLint ✅ + 竞态 ✅ + 服务端分页 ✅ + chat 配置缓存 ✅（2026-08-20）——**剩余 Java 项**：`@Valid` 补齐、Scheduler 锁、N+1、无界列表。
- **批次 3（P2，持续）**：硬编码清理、token 估算、Helm/Compose 拓扑对齐、Dockerfile.python uvicorn[standard] 决策、CI JDK 版本对齐。

> 每批完成后建议跑 `scripts/smoke-test.ps1`（47 项）与各子项目单测（Java 445 / Python 1252 / 前端 33）回归。
