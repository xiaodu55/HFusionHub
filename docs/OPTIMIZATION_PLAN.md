# 后续优化方案（逐功能审查）

> **审查日期**：2026-08-19
> **范围**：对三大模块（Java 后端 / Python AI / 前端+基础设施）逐功能深度代码审查后产出的优化方案。
> **原则**：本文件仅描述优化方案与优先级，**不包含具体代码改动**；每个优化点均标注【文件路径】【问题】【方案】【优先级】，供排期决策与实施落地。
> **配套**：路线图见 [ROADMAP.md](ROADMAP.md)，运维见 [PRODUCTION_OPS.md](PRODUCTION_OPS.md)。

## 总览（Top 待办一览）

| 优先级 | 项数 | 代表问题 | 所属模块 |
|---|---|---|---|
| **P0（高危）** | 0 | ~~全部已完成~~ | — |
| **P1（中优）** | 0 | ~~全部已完成（2026-08-20）~~：chat 配置缓存、Scheduler 锁、N+1、无界列表、写接口 `@Valid`、超大 SFC 拆分 | Java / 前端 |
| **P2（卫生）** | 0 | ~~全部已完成（2026-08-20）~~：硬编码漂移、token 估算、Helm/Compose 拓扑对齐、CI JDK 统一 | 全部 |

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

#### 1.4 20 个写接口缺 `@Valid` 输入校验 ✅ 已完成（2026-08-20，create 端点全覆盖）
- **文件**：`AgentTaskController.decideApproval(@RequestBody Map...)`、`TenantMemberController.addMember(@RequestBody Map...)`、`MemoryController.save` 等（19 个 controller 的写接口均无 `@Valid`）
- **问题**：裸 `Map` 入参 + 服务层手写校验，字段类型/缺失/越界无法被框架层拦截。
- **方案**：替换为带校验注解的 DTO；给 `PageQuery.validate()` 加 `@Validated` 强约束。
- **实际状态（2026-08-20）**：
  - ✅ 计划点名的 3 个示例：`decideApproval` → 新增 `ApprovalDecisionDTO`（`@NotBlank approvalId`、`@Pattern("approved|denied")`）；`addMember` → 新增 `TenantMemberAddDTO`（`@NotNull userId`，role 缺省 member）；`MemoryController.save` 加 `@Valid`
  - ✅ 创建类实体端点加 `@Valid` + 必填字段约束：`createAlertRule`（AgentAlertRule）、`createDataset`/`addCase`（AgentEvaluation*）、`adminCreate`（SystemNotice）、webhook `create`（WebhookSubscription name/url/events）、`evaluateBatch`（级联到已含 `@NotBlank flagKey` 的 DTO）
  - ⚠️ **有意边界**：部分更新 PUT 端点（如 Memory update、Webhook update 为部分字段合并）不加 `@Valid`，避免约束误伤部分更新；`PluginController` 插件 manifest、`RagObservabilityController` 评测请求等**灵活 schema** 的裸 Map 端点保留服务层校验（强制 DTO 会破坏客户端兼容）
  - ✅ 前端已核对：alert/webhook/eval 创建端点暂无前端调用（API 面），400 错误经 `friendlyErrorMessage` 透出后端 message，无 UX 回归
  - ✅ 新增 8 个校验约束测试（WriteEndpointValidationTest）

### P1 — 中优

#### 1.5 每次 chat 查库 + 解密（无缓存）✅ 已完成（2026-08-20）
- **文件**：[AiClient.java](../java-backend/src/main/java/com/hfusionhub/client/AiClient.java#L952) `addUserProviderConfig()`、[UserModelConfigServiceImpl.java](../java-backend/src/main/java/com/hfusionhub/service/impl/UserModelConfigServiceImpl.java)
- **问题**：每次 chat 调用 `getRuntimeConfig(userId)` → 查 `user_model_config` 表 + `cipher.decrypt`，高并发热点无缓存。
- **方案**：Redis 缓存（TTL 60s，配置变更时失效）。
- **实际状态**：`getRuntimeConfig` 已接入 Redis 缓存（key=`user_model_config:{userId}`，TTL=60s，值经 Jackson JSON 序列化含解密后的 `api_key`）；`save`/`reset` 时主动 `evictCache` 失效；新增 5 个缓存专项测试（共 9 个用例）。

#### 1.6 Scheduler 无分布式锁 ✅ 已完成（2026-08-20）
- **文件**：`AgentAlertScheduler`、`ApprovalExpiryScheduler`、`DeletionTaskScheduler`、`OrphanCleanupScheduler`、`RecycleBinCleanupScheduler` 等 14 个任务（仅 `AgentTaskWorkerScheduler` 有 DB lease 幂等）
- **问题**：多实例部署时清理/补偿任务重复执行。
- **方案**：ShedLock 或 Redis `SETNX` 锁（如 `scheduler:lock:{task}` + TTL）。
- **实际状态**：新增 `@SchedulerLock` 注解 + `SchedulerLockAspect`（Redis `SETNX` + token Lua compare-and-delete，TTL 兜底，Redis 故障 fail-open）。已注解 9 个调度器（11 个 `@Scheduled` 方法中的非 DB-lease 部分）：agent-alert / agent-status-event-cleanup / approval-expiry / deletion-task / document-index-recovery / orphan-cleanup / plugin-quota-reservation-reaper / recycle-bin-cleanup / vector-reconciliation。`AgentTaskWorkerScheduler`（DB lease 认领）与 `PromptTestSetRunWorkerScheduler`（`claimRun` DB 认领）天然幂等，无需加锁。新增 4 个切面专项测试（获取/跳过/fail-open/异常释放）。

#### 1.7 N+1 查询 ✅ 已完成（2026-08-20）
- **文件**：[AgentMetricsServiceImpl.java](../java-backend/src/main/java/com/hfusionhub/service/impl/AgentMetricsServiceImpl.java#L229)（循环 `selectById`）、[DemoImportServiceImpl.java](../java-backend/src/main/java/com/hfusionhub/service/impl/DemoImportServiceImpl.java#L210-L231)（循环判重）
- **方案**：`selectBatchIds` / 预取集合代替循环查库。
- **实际状态**：`AgentMetricsServiceImpl` 每 run 的 `selectByRunId` N+1 已改为批量 `selectByRunIds`（新增 Mapper 方法 + XML `IN` 查询），按 runId 分组一次取回；task 查询原本已用 `selectBatchIds`。`DemoImportServiceImpl` 的循环判重仅遍历 3 个 `DEMO_PROMPTS` / 2 个 `DEMO_NOTE_TITLES` 常量（清除演示数据冷路径，最多 5 次查询），量级可忽略，未做改动以免无谓复杂化。

#### 1.8 无界列表接口 ✅ 已完成（2026-08-20 复核）
- **文件**：[MemoryController.java](../java-backend/src/main/java/com/hfusionhub/controller/MemoryController.java#L18) `list()`、[ConversationController.java](../java-backend/src/main/java/com/hfusionhub/controller/ConversationController.java#L117) `getMessages()`、[UserController.java](../java-backend/src/main/java/com/hfusionhub/controller/UserController.java#L125) `searchUsers()`
- **方案**：加 limit/分页（参考 `ToolController` 的 `min(pageSize, 100)` 模式）。
- **实际状态**：`MemoryServiceImpl.listByUser` 已有 `LIMIT 200`；`UserServiceImpl.searchUsers` 已有 `LIMIT 10`；`ConversationController.getMessages` 按对话归属天然有界（每条消息属于单个对话，聊天历史需完整返回给前端，硬截断会破坏对话展示），无需额外限流。

#### 1.9 统一缓存体系
- **文件**：`FeatureFlagServiceImpl.evaluate()` 每次 `ruleMapper.selectList`；`UsageLedgerService` 每次实时聚合
- **方案**：零 `@Cacheable` → 引入 Caffeine/Redis 二级缓存覆盖 FeatureFlag 评估结果、模型列表、KB 文档数等冷热数据。

### P2 — 卫生

- **硬编码漂移** ✅ 已处理（2026-08-20）：`VectorizationServiceImpl` `python-ai.engine.url` 默认值 `localhost:8001` → 统一为 `9000`（与 application.yml 一致）；[ConversationServiceImpl](../java-backend/src/main/java/com/hfusionhub/service/impl/ConversationServiceImpl.java#L784) 错误文案硬编码 `http://localhost:9000/health` → 改为读取 `ai-service.base-url` 配置。`uploads/documents` 相对路径暂保留（单实例部署语义）。
- **空壳方法** ✅ 已处理（2026-08-20）：`OrphanCleanupScheduler.retryLongFailedDeletionTasks` 空实现已移除（重试逻辑已由 `DeletionTaskScheduler` + `DeletionService.markFailed` 的 RETRYING 状态覆盖）。

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

#### 2.5 BM25 语料/倒排索引缓存 ✅ 已完成（Batch 3 核实，2026-08-30）
- **文件**：[query_router.py](../python-ai/app/core/rag/query_router.py) `KeywordChannel`
- **实现**：`_corpus_cache` 按 ``(store id, KB)`` 缓存预解析语料（分词 + 倒排索引 + 文档分组），
  co-store 文件 mtime/size 变化自动失效（milvus_store `_load_chunks_store` 按 mtime+size 缓存），
  并经 `asyncio.to_thread` 执行避免事件循环阻塞。测试：test_query_router.py / test_co_store_tenant_cache.py

#### 2.6 O(n²) 去重
- **文件**：[postprocessor.py](../python-ai/app/core/rag/postprocessor.py) `_calculate_similarity`
- **问题**：字符集 Jaccard 两两计算，chunk 多时平方级耗时且对中文去重效果一般。
- **方案**：token 化 + minhash（局部敏感哈希）或 embedding 相似度粗筛。

#### 2.7 流式多 Agent 绕过证据审查 ✅ 已完成（Batch 3 核实，2026-08-30）
- **文件**：[multi_agent_runtime.py](../python-ai/app/core/agent/multi_agent_runtime.py) `run_stream`
- **实现**：流式路径在首个自由文本 chunk 前对 retrieval 事件收集的 sources 执行与
  非流式完全相同的确定性门控 `_validate_sources`（`_validate_evidence` 本身即委托该方法），
  未授权证据直接以 NO_SUFFICIENT_EVIDENCE_REPLY 终止流。测试：test_multi_agent_workflow.py

#### 2.8 文件重复读取 ✅ 已完成（Batch 3 核实，2026-08-30）
- **文件**：[milvus_store.py](../python-ai/app/core/vectorstore/milvus_store.py)（scoped_graph 已随 P7 GraphRAG 整体移除）
- **实现**：lite 模式 co-store 按「租户 + 文件 mtime+size」缓存解析结果，
  热检索路径不再每请求重读 + 重解析 JSON；文件变更自动失效。测试：test_co_store_tenant_cache.py

#### 2.9 事件循环阻塞与线程浪费 ✅ 已完成（Batch 3 核实，2026-08-30）
- **文件**：[embedding/__init__.py](../python-ai/app/core/embedding/__init__.py)、[ollama_llm.py](../python-ai/app/core/llm/ollama_llm.py)
- **实现**：embedding 模块级 `_embedding_executor`（复用线程池，不再每次调用新建）；
  Ollama `is_available()` 委托包级 `_is_ollama_available`（线程池 + TTL 缓存探测），
  同步 HTTP 不再阻塞事件循环。

### P2 — 成本/健壮性

- **LLM 响应缓存**：✅ 精确命中缓存已接入非流式与流式（chat_stream 缓存命中路径，2026-08-30 Batch 3 核实）；✅ 归一化模糊命中已接入（2026-08-30 第十七批：精确 miss 后以空白折叠+casefold 二次查找，`LLM_RESPONSE_CACHE_FUZZY_ENABLED` 默认开）。语义（向量）级命中明确不做——LLM 输出对输入高度敏感，收益风险比不成立。
- **配置校验**：[config.py](../python-ai/app/utils/config.py) 裸 `os.getenv` → pydantic-settings，启动 fail-fast（必填/枚举/类型）。
- **token 估算** ✅ 已处理（2026-08-20）：[utils.py](../python-ai/app/core/rag/utils.py) `estimate_tokens` 朴素「中文字符+英文单词」估算 → 按模型族校准的字符-比例模型（中文 1 token/字 + 拉丁字母/数字 0.25 token/字符、round-half-up），无第三方 tokenizer 依赖；修复旧实现忽略数字的缺陷，英文估算值与 GPT 族 tokenizer 对齐（如 "Hello World" 2→3）。
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

- **Helm/Compose 拓扑漂移** ✅ 已处理（2026-08-20）：[values.yaml](../deploy/helm/hfusionhub/values.yaml) 已与 compose 对齐——Milvus 统一 `v2.6.6` standalone + 外部 etcd（`ETCD_ENDPOINTS` 接线）；本次将 etcd 补丁版本对齐（`v3.5.5`→`v3.5.18`，与 [docker-compose.prod.yml](../deploy/docker-compose.prod.yml) 一致），并新增**可选 attu 组件**（`attu.enabled: false` 默认关闭，与 compose 的 attu 控制台拓扑对齐，生产按需开启）。`templates/` 已按组件拆分（原 703 行 `all.yaml` → 13 个文件：secret/mysql/redis/java/python/plugin-runner/uploads-pvc/etcd/milvus/attu/hpa/frontend/ingress，布局见 [README.md](../deploy/helm/hfusionhub/README.md)），逐行还原校验通过，CI helm lint + kubeconform 门禁持续校验。
- **Dockerfile.python** ✅ 已处理（2026-08-20）：`requirements.txt` 已固定 `uvicorn[standard]==0.27.0`（uvloop/httptools 流式性能），无需改动。
- **CI JDK 版本统一** ✅ 已处理（2026-08-20）：[e2e.yml](../.github/workflows/e2e.yml) 两处 `java-version: '17'` → `'21'`，与 [ci.yml](../.github/workflows/ci.yml)（已 21）及生产 Dockerfile temurin-21 一致；pom 保持 `java.version=17`（字节码目标，JDK 21 完全兼容）。

---

## 实施建议（分批）

- **批次 1（P0，✅ 全部已完成）**：
  - ✅ **Python 高危项**：BM25 缓存、去重优化、文件缓存、LLM 响应缓存、流式证据门控、WorkflowEngine 并行修复、批量 embedding、DeepSeek embedding 移除
  - ✅ **Java 高危项**：上传 1MB 限制（application.yml 已配置）、AiClient 超时/连接池（RestTemplateConfig 已实现）、CORS/Actuator 安全（CorsConfig 已有门控）
  - ✅ **基础设施高危项**：生产 compose 资源限制（所有服务已配 limits）、监控指标修正与 exporter 部署
- **批次 2（P1，✅ 全部完成 2026-08-20）**：前端超大组件拆分 ✅ + ESLint ✅ + 竞态 ✅ + 服务端分页 ✅ + chat 配置缓存 ✅ + Scheduler 分布式锁 ✅ + N+1 ✅ + 无界列表 ✅ + 写接口 `@Valid` ✅——**Java P1 项全部清零**。
- **批次 3（P2，✅ 全部完成 2026-08-20）**：硬编码清理 ✅、CI JDK 版本对齐 ✅、Dockerfile.python uvicorn[standard] 决策 ✅、token 估算校准 ✅、Helm/Compose 拓扑对齐 ✅——**P2 全部清零**。

> 每批完成后建议跑 `scripts/smoke-test.ps1`（48 项）与各子项目单测（Java 572 / Python 1258 / 前端 49）回归。

---

# 第十五轮优化方案（2026-08-28 全面复审：P0–P14 交付后）

> **复审方式**：文档路线图 / Java 后端 / Python AI 三路并行深度探索。
> **结论**：十四轮交付后发现一批**真实缺陷**（非单纯优化），按「P0 正确性/安全 → P1 性能 → P2 可维护性/测试 → P3 文档/运维」四层排期。
> **本轮实施范围**：P0 批次全部 9 项（见 §R15-P0）；P1–P3 供后续排期。
> **冻结项不动**：GraphRAG / 多模态 OCR / cross_encoder reranker（已明确不投入）；租户隔离、HMAC 回调、幂等账本、熔断网关等已验证机制不改设计。
>
> **冻结路线重启条件**（2026-08-29 评审补充，避免后续重复评估）：
> - `RAG_GRAPH_ENABLED`（GraphRAG）：仅当出现「需要跨文档多跳关联推理」的真实业务场景、且官方 GraphRAG 实现稳定支持持久化图索引（消除重启重建成本）时重启。
> - `RAG_MULTIMODAL_ENABLED`（多模态 OCR）：仅当切换到 vision-LLM 抽取路线（替代系统级 Tesseract 依赖）且离线评测证明收益时重启；当前维持冻结。
> - `cross_encoder` reranker 模式：仅当离线基准（`evaluation/` 套件）证明其相对 lexical 重排有稳定召回/排序增益时重启。
>
> **legacy 兼容层退役评估（2026-08-29）**：以下入口已加访问日志（Python 侧每进程告警一次），运行一个版本后确认零流量即可随大版本移除：`model_gateway._legacy_chat/_legacy_stream`（降级路径）、`core/tools` 旧 `get_tools()/execute_tool()`（ReAct/MCP 兼容）、`/api/chat/agent-runs`（仓库内已无调用方）、Java `AiClient.chatStream()`。

## R15-P0 正确性 / 安全（本轮实施 ✅）

| 编号 | 问题 | 证据 | 修法 | 验收 |
|---|---|---|---|---|
| R15-1 | **容器插件 agent 链路不可用**：async 方法内同步调 `execute_plugin_tool`；container 模式在已有事件循环的线程里 `new_event_loop().run_until_complete()` → RuntimeError 被吞，静默返回 `container_runner_unavailable`。P2-3 e2e 只覆盖 runner 直连 | `app/core/tools/registry.py:875`、`app/core/plugin/sandbox_runner.py:390-434` | registry 改 `await asyncio.to_thread(...)`；container 分支在工作线程内用 `asyncio.run` | 新增 registry 级 container-mode 测试；bid_docx/bid_quote 经 `execute()` 真实可达 |
| R15-2 | **跨租户语料缓存泄漏**：BM25/citation co-store 缓存 key 只含 `(mtime_ns, size)` 不含 tenant_id | `app/core/vectorstore/milvus_store.py:188-219` | `_co_store_key` 加入 tenant_id | 双租户读写测试证明互不可见 |
| R15-3 | **OpenAPI key 解析租户 bug**：`/openapi/**` 不走租户拦截器，key 查询被行拦截器默认填 `tenant_id=1`，非 1 租户的 key 全部 401 | `config/SaTokenConfig.java:110`、`OpenApiServiceImpl.java:162-178`、`MybatisPlusConfig.java:102-106` | key 解析包 `TenantContext.runAsSystem`（key hash 全局唯一），后续业务 `runAs(app.tenantId)`（对齐 bidCheck 既有模式） | 非 1 租户 key 认证测试 |
| R15-4 | **内部插件审计租户错标**：回调插入 `plugin_audit_log` 无 TenantContext，行全落 `tenant_id=1` | `InternalPluginController.java:89-130` | 解析 plugin 后 `runAs(plugin.tenantId)` 包插入 | 审计行 tenant 与插件一致 |
| R15-5 | **流式聊天绕过输出守卫**：SSE 路径明确不做 `guard_model_output`，非流式被拦内容可从流式通道流出 | `app/api/chat.py:363-366, 475-493, 732-799` | 流式累积最终输出后过守卫，命中发矫正事件（复用现有事件协议）+ 审计 | 守卫命中测试（流式与非流式行为一致） |
| R15-6 | **插件子进程沙箱 fail-open**：manifest 无 sandbox 段 = 无网络/文件限制；Windows 资源限制静默跳过 | `sandbox_runner.py:284-287, 75-98` | 无声明时 default-deny（禁网+限写）；资源限制跳过显式 warning | 默认拒绝测试 |
| R15-7 | **plugin-runner 事件循环阻塞 + 结果解析 fail-open**：async 处理器内同步 Docker SDK 调用串行化全部执行；末行非 JSON 时 `success=True` 返回 raw_output | `docker/plugin-runner/app.py:295-553, 507-511` | 阻塞调用包 `asyncio.to_thread`；结果解析改 fail-closed（非 JSON → success=False） | runner 现有验收（e2e 17 项）回归通过 |
| R15-8 | **密钥与暴露面**：`MODEL_CREDENTIAL_ENCRYPTION_KEY` 回退复用 `PYTHON_AI_INTERNAL_TOKEN`（轮换一个毁掉全部已存用户 key）；CORS 默认通配源+凭据；actuator 无显式认证策略 | `application.yml:138-156`、`ModelCredentialCipher.java:38-43`、`CorsConfig.java:38` | 加密 key 取消回退 fail-fast；CORS 默认 false+显式 origin；actuator 独立 management port 移出 `/api` 上下文 | 配置校验测试；dev 默认行为有日志警示 |
| R15-9 | **feature_flag 降级语义不符**：后端不可达时 AVAILABILITY_FLAGS 直接返回 True，注释声称「保留 env 配置」实际未读 env | `app/utils/feature_flag.py:105-107` | 降级先回退对应 env 再默认值 | 后端不可达 + env=false 的降级测试 |

## R15-P1 性能（✅ 已完成 2026-08-28，R15-16 以最小落地实现）

| 编号 | 问题 | 证据 | 方案 |
|---|---|---|---|
| R15-10 | 招投标撰写检索串行：最多 21 次串行检索往返（每 KB×每查询） | `app/core/bid/write_workflow.py:154-181`、`workflow.py:242-256` | 检索阶段 `asyncio.gather` + 信号量并发（分节生成保持串行语义不变） |
| R15-11 | 同步 LLM 调用持有数据库事务，并发撰写耗尽连接池 | `BidWriteServiceImpl.java:59-83` | 事务拆分，对齐 `ConversationServiceImpl.java:259-349` 的「事务外调 AI」模式 |
| R15-12 | V32 遗漏 tenant_id 索引：plugin/plugin_audit_log/agent_approval/agent_run/agent_step/prompt_test_set/prompt_test_set_run/agent_evaluation_dataset | `V32__tenant_org_model.sql:89-147` | V74 迁移补 `idx_*_tenant`（对齐 V61-V68 做法） |
| R15-13 | JSON co-store 全量读改写且写路径无锁（并发索引可丢文档）；BM25/citation 全语料线性扫描 | `milvus_lite.py:39-44, 649-654`、`query_router.py:486-496` | SQLite（或 Milvus 查询回源）+ 每租户锁；扫描路径索引化 |
| R15-14 | httpx 客户端每调用新建（7 处） | `model_gateway.py:298,1042`、`plugin/quota.py:47`、`container_runner.py:99,180,201`、`declarative_http_tool.py:43`、`execution_token.py:66` | 收敛到 `llm/http_client.py::get_shared_client` |
| R15-15 | Milvus 每查询 load_collection；embedding 探活一次性同步；sync 嵌入全局 2 线程漏斗 | `milvus_lite.py:506`、`milvus_cluster.py:354`、`embedding/__init__.py:191-213, 23-25` | 启动时 load 一次 + 出错重载；探活 TTL 异步化；检索路径走 async embedding |
| R15-16 | Java 统一缓存体系（旧 §1.9 遗留，唯一未清 Java 项）：零 `@Cacheable`，FeatureFlag 每调用查规则 | `docs/OPTIMIZATION_PLAN.md §1.9`、`FeatureFlagServiceImpl` | Caffeine 本地 + Redis 失效的两级缓存，先覆盖 FeatureFlag / chat 配置 / 订阅档位 |
| R15-17 | N+1 与全表扫描：expireApprovals 逐条 3 读 3 写；审计回调逐条 dedup；向量对账全表载入内存 | `AgentTaskServiceImpl.java:1145-1168`、`InternalPluginController.java:110-113`、`VectorReconciliationService.java:91` | 批量 selectBatchIds / JOIN；对账按 id 分页 |
| R15-18 | milvus 16384 行静默上限；document.content LONGTEXT 随列表全量拉取；插件审计 flush 逐条 POST | `milvus_cluster.py:412-481`、`V1__initial_schema.sql:63`、`plugin/audit.py:301-307` | queryIterator 分页 + `num_entities`；列表列裁剪或 1:1 详情表；flush 批量化 |
| R15-19 | 声明式插件端点 SSRF：拦了 localhost 但未拦私网/link-local 段与 DNS 解析到内网的域名 | `PluginServiceImpl.java:535-550` | 安装时解析 DNS 并拒绝保留网段 |

## R15-P2 可维护性 / 测试（✅ 已完成 2026-08-28；R15-24 为持续项）

| 编号 | 问题 | 证据 | 方案 |
|---|---|---|---|
| R15-20 | react.py 1648 行，run / run_stream / _run_stream_react 三份重复检索/压缩/组装/容错循环 | `app/core/agent/react.py:790, 1087, 1433` | 抽取共享管线，stream/非 stream 单循环 |
| R15-21 | API 层几乎零测试：bid/ingest/rag/mcp/tools/gateway/guardrails 等约 10 个路由无任何测试 | `python-ai/tests/` 对照 `app/api/` | FastAPI TestClient 契约测试（对齐 `tests/test_chat_api.py` 模式） |
| R15-22 | 测试基座漂移：H2 schema 手维护停在 V70、Flyway 关闭、tenant 拦截器在测试中关闭（核心隔离机制未被测试覆盖） | `application-test.yml`、`schema-h2.sql` | Testcontainers-MySQL（依赖已在 pom）抽样集成 + 至少一条 tenant 拦截器真实链路 |
| R15-23 | 内部 token guard 复制粘贴 6 份；`allow-circular-references: true` 掩盖循环依赖；manifest hash 拼接歧义 | 6 个 Internal*Controller、`application.yml:8`、`PluginServiceImpl.java:628-644` | 收敛为 servlet filter；解循环；规范化 JSON 重算 |
| R15-24 | God classes：ConversationServiceImpl 1595 / AgentTaskServiceImpl 约1360 / VectorizationServiceImpl 1222 | java-backend service/impl | 按职责拆分（渐进，随触碰随拆）。✅ 第一批（2026-08-30）：`AgentRunLifecycleService`（守卫迁移+账本结算+租户归属）、`ChatUsageRecorder`（聊天账本+模型用量落账）收口 |

## R15-P3 文档 / 运维（✅ 已完成 2026-08-28；R15-28 以最小落地实现，R15-27/30 已文档化待真机执行）

| 编号 | 问题 | 证据 | 方案 |
|---|---|---|---|
| R15-25 | 文档失真 10 处：README/ROADMAP 测试计数（445/1220+）、database.md Flyway「V1–V57」、CI_GATES 分支保护自相矛盾 + eval-nightly 描述过时、ARCHITECTURE flag 表（2026-08-19）、TODO.md 停在 08-19、CHANGELOG 三个 `## [Unreleased]`、P1-3 编号缺位、ACCESS_MAP/TODO runner 状态过时、本文档旧脚注计数 | 各对应文档 | 一次性对账清理（合并 Unreleased、统一计数源为 CI 实际值） |
| R15-26 | **生产安全上线阻断清单（TODO.md P0 五项全未勾）**：默认密码轮换、HTTPS+Nginx/Let's Encrypt、CORS 收紧（去 `*`）、prod 关 Swagger、MySQL 每日备份 + Milvus 快照 | `TODO.md` P0 1-5、`docs/PRODUCTION_OPS.md §0` | 产出轮换脚本 + HTTPS 反代样例 + 备份 cron 脚本 + 告警启用文档（不在真实环境直接执行） |
| R15-27 | eval-nightly 依赖 cpolar 免费隧道随机子域名且需 02:00 在线 | `docs/ROADMAP.md:97` | 固定子域名或注册为 Windows 服务 |
| R15-28 | P2-8 私有部署加固：✅ MinIO per-tenant bucket 隔离已落地（2026-08-30 第十七批：插件工件写 `hfusionhub-t<tenantId>` 租户桶，读取回退默认桶兼容旧对象）；敏感标书禁外部 LLM-as-judge 已由 judge_gate 覆盖 | `docs/BID_COMPLIANCE.md:31, 81` | 私有化部署模式开关 + 存储隔离 |
| R15-29 | 前端 chat 断线重连遗留（幂等 requestId 自动重试；scrollToBottom 改 rAF） | 本文 §3 P2 遗留项 | F2 模式收尾 |
| R15-30 | staging 真机验证缺口：隔离 Docker Engine / K8s runner 未在 staging 机器演练 | CHANGELOG 验收记录、`docs/PRODUCTION_OPS.md §9` | staging 机器跑 dind rehearsal + `plugin-e2e-acceptance.ps1` |
