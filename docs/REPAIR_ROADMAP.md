# 全项目评估修复路线图（源自用户桌面方案.md，2026-08-29 入库跟踪）

> **修复状态（2026-08-29 第一批）**：S1、S2、S7、S8、S9、M1、M2、M6、S3/M3 守卫已完成；
> 遗留：S4/S5（需 V77 唯一索引 + 并发测试，单独批次）、M4、M5、M7-M13、Low 批、批次 F 运维项。
> 逐项状态见文末「修复进度」标注。

# HFusionHub 全项目功能评估 + 修复路线图 + 关键链路实测

## Context（为什么做这次评估）

用户要求对 HFusionHub 做一次**全项目功能评估**：找出「AI 服务（python-ai）/ 后端模块（java-backend）/ 前端及各条链路」中**实际有问题的功能**。交付物为：

1. **评估报告**（按严重度分组的问题清单，附代码锚点）
2. **修复路线图**（按批次组织的修法建议）
3. **关键链路实测**（获批后运行冒烟测试 + 定向探测验证）
4. **不修改任何代码**

本次评估方法：3 个并行探索代理分别深挖 python-ai / java-backend / 前端+跨层契约，共覆盖全部核心链路；随后本人对 8 处最高危发现逐一**代码级抽查验证**，全部属实。当前环境所有服务健康运行（Java:8080、Python:9000、前端:3000、8 个 Docker 容器 UP），实测可行。

> 背景：项目已历经 15 轮深度优化（docs/OPTIMIZATION_PLAN.md R15 于 2026-08-28/29 交付 P0-P14），整体工程质量高。本次评估聚焦**遗留的真实缺陷与风险**，而非重复已修项。

------

## 一、评估报告（按严重度分组）

### 🔴 严重（High）— 9 项

| #    | 层              | 问题                                                         | 锚点                                                         |
| :--- | :-------------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| S1   | 前端/安全       | **审批执行令牌 + 完整工具参数经 REST+SSE 下发到浏览器**。`AgentApproval` 实体 `executionToken`（一次性执行令牌）与 `toolInput`（完整工具参数 JSON）无 `@JsonIgnore`；`getApprovals`/`listPendingApprovals` 与 `ApprovalEventSseManager` 两处 SSE 事件都序列化整个实体。UI 却标注「敏感信息已隐藏」只展示脱敏摘要 `argumentsSummary`。令牌本应只走 Java→Python 服务端通道（前端仅提交 `{approvalId, decision, reason}`）。 | [AgentApproval.java:50,63](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/entity/AgentApproval.java#L50)、[AgentTaskController.java:99,130](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/controller/AgentTaskController.java#L99)、[ApprovalEventSseManager.java:60-77](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/ApprovalEventSseManager.java#L60) |
| S2   | Python/权限     | **旧版 /api/chat/stream 绕过权限/策略门禁**：调用 `get_agent(...)` 未传 `execution_context`，导致 `ToolRegistry.execute()` 的权限校验、模式门（read_only）、策略引擎、guardrail 输入检查、scoped grant 全部跳过（仅名称白名单兜底）；且 `:861` 把内部原始异常 `str(e)` 返回给客户端（信息泄露）。 | [chat.py:816](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/api/chat.py#L816)、[chat.py:861](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/api/chat.py#L861)、[registry.py:590](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/tools/registry.py#L590) |
| S3   | Java/竞态       | **审批过期调度 vs 审批通过——双向丢失更新**：`expireApprovals` 将过期审批的 **run 无条件置 FAILED**（task 有 `STATUS_WAITING_APPROVAL` 守卫但 run 没有）；`decideApproval` 批准路径同样无行锁/版本守卫。用户刚批准的任务可能被 60s 过期调度覆盖为 FAILED（用量按 FAILED 结算），反之已过期任务被"复活"。 | [AgentTaskServiceImpl.java:1172-1178](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/impl/AgentTaskServiceImpl.java#L1172)（run 无守卫）vs [788-796](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/impl/AgentTaskServiceImpl.java#L788) |
| S4   | Java/竞态       | **入队/重试 TOCTOU 双重入队**：`enqueueRun`/`retryTask`/`requeueTask` 的状态检查→attempt 计算→INSERT 非原子（虽有 `@Transactional` 但无行锁）。并发（双击重试 / 重试与死信恢复同时）会插入两个相同 attempt 的 PENDING run，都被 worker 执行 → 重复调用 AI、双重预占/结算。 | [AgentTaskServiceImpl.java:564-614](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/impl/AgentTaskServiceImpl.java#L564) |
| S5   | Java/竞态       | **文档向量化重处理无锁并发**：允许对 PROCESSING 文档重处理，supersede 旧 job→释放旧 chunk→插入新 job 全程无锁；`countByDocumentId()+1` 算 attempt 也是 TOCTOU。双击重处理/重处理与恢复调度并发 → 旧 chunk 重复释放、两个活跃 PROCESSING job、重复解析成本。 | [VectorizationServiceImpl.java:115-148](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/impl/VectorizationServiceImpl.java#L115) |
| S6   | Python/一致性   | **/api/parse 回调失败 → 孤立索引**：chunks 已插入 Milvus/co-store 后若 Java 回调未确认，直接 `raise RuntimeError` → 任务 FAILED 但向量已落库。Java 侧重试 → 同一文档重复插入；对账漂移（"索引存在但任务失败"）。插入与状态无回滚/补偿。 | [vectorization.py:447-458](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/api/vectorization.py#L447) |
| S7   | Python/逻辑     | **反思「补充检索」完全失效**：`_supplement_retrieval` 对 `retriever.retrieve()` 返回的 `RetrievalResult`（非可迭代）直接 `extend` → 必然 TypeError，被裸 `except:` 吞掉，函数恒返回 `""`；`:438` 同样裸吞。无测试覆盖。 | [self_reflector.py:955-963](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/rag/self_reflector.py#L955) |
| S8   | Python/状态     | **insufficient_evidence 状态不可达**：`if groundedness_failed and not final_answer` 恒 False（`groundedness_failed` 前提是产出过非空 final_answer）。Agent V1 的"证据不足"语义实际不可用，前端/Java 无法据此提示。 | [react.py:1076-1078](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/agent/react.py#L1076) |
| S9   | Python/潜伏崩溃 | **RecursiveCompressionStrategy 默认配置必崩**：`CompressionConfig.max_tokens` 默认 None，`while current_tokens > config.max_tokens` 抛 `int > None` TypeError。生产走 EXTRACTIVE 未暴露，属潜伏地雷；缓存 key 也不含 `target_ratio`/`max_tokens`（参数不同互串缓存）。 | [context_compressor.py:685-710](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/rag/context_compressor.py#L685) |

### 🟠 中等（Medium）— 13 项

| #    | 层            | 问题                                                         | 锚点                                                         |
| :--- | :------------ | :----------------------------------------------------------- | :----------------------------------------------------------- |
| M1   | 跨层          | **RAG「只看失败请求」筛选静默失效**：前端发送 `error_only`，后端参数名是 `errorOnly`（Spring 按名绑定）→ 恒为默认 false。开关、失败记录查看、CSV/JSON 导出全部静默不生效，无报错。 | [rag.ts:89](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/hfusionhub-frontend/src/api/rag.ts#L89) vs [RagObservabilityController.java:68,104](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/controller/RagObservabilityController.java#L68) |
| M2   | Java/事务     | **decideApproval 无事务边界**：approval/task/run 三条更新逐条自动提交；进程崩溃 → approval=approved 但 run 卡在 waiting_approval（过期调度只扫 pending，不收敛）。 | [AgentTaskServiceImpl.java:739-796](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/impl/AgentTaskServiceImpl.java#L739) |
| M3   | Java/竞态     | **approve 后 resume 失败的收敛逻辑可覆盖成功**：重读 run 后 `if (!TERMINAL)` 置 FAILED，若重读与写入之间 run 已真实完成会把 SUCCEEDED 覆盖为 FAILED。与 S3 同源（run 状态迁移全缺锁）。 | [AgentTaskServiceImpl.java:852-895](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/impl/AgentTaskServiceImpl.java#L852) |
| M4   | Java/部署     | **4 个自管理调度器无分布式锁**（Worker/Recovery/RecoveryManager/PromptTestSetRun）：自管 `ScheduledExecutorService`，不经过 `@SchedulerLock` 切面；`requeueOrphan`（AgentRunMapper.xml:147-165）无状态守卫。多实例会重复派发/覆盖 run_uuid。 | [AgentTaskWorkerScheduler.java:42-68](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/scheduler/AgentTaskWorkerScheduler.java#L42)、[AgentRunMapper.xml:147-165](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/resources/mapper/AgentRunMapper.xml#L147) |
| M5   | Java/一致性   | **afterCommit 中文件提交抛异常**：`Files.move` 失败 → 先 markUploadFailed 再抛 BusinessException；DB 已提交、temp 已删、final 路径不存在（悬空 file_path），HTTP 响应不确定。DB 与文件落盘无对账。 | [DocumentServiceImpl.java:515-557](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/impl/DocumentServiceImpl.java#L515) |
| M6   | Java/安全     | **回调密钥/HMAC 校验失败返回 HTTP 200**：`return R.fail(...)`（200 + 错误 body）。Python 若按非 2xx 触发重试，签名错误的回调被静默丢弃、文档卡 PROCESSING 至多 30 分钟；认证失败语义上应 401/403。 | [VectorizationController.java:100-113](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/controller/VectorizationController.java#L100) |
| M7   | Java/体验     | **非流式 sendMessage 配额预占在 try 之外**：超配额抛 400，但用户消息已落库 → "有问无答"孤立消息。 | [ConversationServiceImpl.java:288-289](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/impl/ConversationServiceImpl.java#L288) |
| M8   | Java/性能     | **SSE 轮询共享固定 2 线程池**：所有任务 SSE 连接的 DB 轮询挂在 2 线程调度器，高并发时慢连接拖累其他连接。 | [TaskEventSseManager.java:39](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/service/TaskEventSseManager.java#L39) |
| M9   | 前端/体验     | **聊天/审批 SSE 绕过 axios 401 拦截器**：`chat/Detail.vue:191-204` 直接 fetch、`approval.ts:70-83` 走 `consumeSseJsonStream`，均不过 `request.ts` 的 401 统一登出 → token 过期时两种登出体验割裂。 | [chat/Detail.vue:191](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/hfusionhub-frontend/src/pages/chat/Detail.vue#L191)、[approval.ts:70](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/hfusionhub-frontend/src/api/approval.ts#L70) |
| M10  | Python/可观测 | **检索失败被伪装成"无证据"**：`_retrieve_context` 吞一切异常返回空，Milvus 宕机/embedding 失败被当"没有相关资料"，无降级告警。叠加 S7/S8，用户无法区分"真无资料"与"服务故障"。 | [retriever.py:177](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/rag/retriever.py#L177)、[react.py:441-443](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/agent/react.py#L441) |
| M11  | Python/一致性 | **工作流超时/异常伪装成"证据不足"文本流入 SSE**：`workflow_runtime.py:349,355` 把 `NO_SUFFICIENT_EVIDENCE_REPLY`/`SERVICE_UNAVAILABLE_REPLY` 当普通内容 chunk yield 给前端，与 `run()` 返回 timeout/tool_error 状态不一致。 | [workflow_runtime.py:349,355](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/agent/workflow_runtime.py#L349) |
| M12  | Python/流式   | **/api/chat/stream 旧端点 vs /api/agent/v1/chat/stream 行为分叉**：旧端点（S2）无权限门禁；且 `run_stream` 无条件走查询分解而 `run()` 先查 `needs_decomposition`，同一问题两路径检索行为不一致；groundedness 状态在 run/run_stream 处理也不同。 | [react.py:1209,1211](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/agent/react.py#L1209) |
| M13  | Python/内存   | **多处无界缓存/线程泄漏**：`intent_classifier.classify_sync` 每次新建 ThreadPoolExecutor 不关闭；`LLMClassificationStrategy._cache`、`_task_status_store`（只增不删）、`conversation_memory` 的 `_sessions`/`_embedding_cache`、`answer_quality_evaluator` 缓存均无界增长；`conversation_memory` "持久化"是空壳（`enable_persistence`/`storage_path` 从未被读取，重启即失），Ollama 嵌入失败降级为随机向量。 | [intent_classifier.py:218-222](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/rag/intent_classifier.py#L218)、[conversation_memory.py:691](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/rag/conversation_memory.py#L691)、[vectorization.py:57](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/api/vectorization.py#L57) |

### 🟡 轻微（Low）— 一批

- **Python LLM 层**：DeepSeek 流式解析只捕获 JSONDecodeError（空 choices → IndexError 直接抛，与 ModelGateway 行为不一致）[deepseek_llm.py:278](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/llm/deepseek_llm.py#L278)；网关流式缓存 get 用 `resolved_model` / put 用 `candidate_model` 键错位 [model_gateway.py:536 vs 590](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/llm/model_gateway.py#L536)；成本记账 `chars//4` 低估中文 token。
- **Python 资源/健壮性**：回调通知无重试且每次新建 httpx Client（未复用共享池）[vectorization.py:656,699](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/api/vectorization.py#L656)；`get_chunks` 硬编码 `index=0` 分页语义丢失 [vectorization.py:546-552](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/api/vectorization.py#L546)；Milvus cluster 对账 `limit=16384` 截断（大库对账虚低）[milvus_cluster.py:465-469](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/vectorstore/milvus_cluster.py#L465)；`get_chunk_detail` 返回原始 metadata 字符串（与 search 行为不一致）；非流式 chat 无超时；`EMBEDDING_MODEL` 默认 `"unknown"`（误开 fallback 会污染索引）；自定义供应商 `_validated_base_url` 放行私网段（SSRF 面偏松）。
- **Python 死代码/装饰性**：`execute_tool` 的 registry 分支永远不命中 [tools/**init**.py:207](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/core/tools/__init__.py#L207)；`agent_workflow.LoopNode` 与 `visited_nodes` 防环语义冲突；`get_workflow_engine` 无生产引用；Feature flag 刷新无锁可多线程并发写缓存 [feature_flag.py:161-176](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/python-ai/app/utils/feature_flag.py#L161)。
- **Java 轻微**：`AiClient.onStatus` 把 Python 原始错误 body 透传客户端（信息泄露）[AiClient.java:592-597](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/java/com/hfusionhub/client/AiClient.java#L592)；`internalApiToken` 为空时全 AI 调用 500 无启动校验；`TaskEventSseManager:51` 对 null userId NPE；`SchedulerLockAspect` fail-open（已文档化）；V32 迁移 `agent_alert_rule/event` 无 user 的行 tenant_id 为 NULL（租户过滤下不可见）[V32__tenant_org_model.sql:114-115](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/java-backend/src/main/resources/db/migration/V32__tenant_org_model.sql#L114)。
- **前端/类型**：`uploadDocument`/`createKnowledgeBase` 返回类型 `Promise<number>` 与后端 `R<DTO>` 不符（当前调用方不消费返回值，运行时无害）；文档轮询终止条件缺 `SUPERSEDED`（防御缺口）[useDocumentProcessor.ts:194](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/hfusionhub-frontend/src/composables/useDocumentProcessor.ts#L194)；`cost.ts` 别扭泛型；`request.ts:37` 对空响应体不健壮。

### 🟢 已核实健康（正向结论）

- **Java**：租户隔离框架（67 表 tenant_id 列全齐）、用量账本幂等（reserve/settle/release + 幂等键）、任务队列认领/续租/死信 SQL 守卫、回调签名常量时间比较、Flyway V76 无缺列。
- **Python**：Agent V1 执行上下文/注册表/scoped grant/执行令牌 fail-closed 设计、Milvus 维度校验、生产配置 fail-fast、共享 httpx 池 + 429/5xx 重试、feature flag 三态降级。
- **前端/跨层**：聊天 SSE、审批 SSE、文档轮询三条动态链路的事件格式/字段命名/状态枚举**全部一致**；15+ API 模块路径参数匹配；无 TODO/console.log/@ts-ignore 残留；列表页有请求序号竞态防护。

### ⚠️ 运维/交付状态（非代码功能，但影响可用性）

1. **CI 全红**（GitHub Actions 因账单/额度问题 3 秒即失败，2026-08-29 确认，[TODO.md](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/TODO.md) P0#0）——PR 门禁（含 eval-offline 阻断）实际失效，合并需本地全量测试兜底。
2. **TODO.md P0 生产上线安全项未做**：默认密码轮换、HTTPS+Nginx、CORS 收紧（仍 `*`）、prod 关 Swagger、MySQL 每日备份 + Milvus 快照。

------

## 二、修复路线图（按批次，供后续排期——本轮**不实施**）

> 每条均以修复上述锚点为目标，沿用项目既有风格（Flyway V77+、pytest/vitest/JUnit 补测试、不走 R15 冻结的路线）。

**批次 A — 安全优先（S1, S2, M6 + 相关透传）**

- A1：`AgentApproval` 的 `executionToken`/`toolInput` 加 `@JsonIgnore`（或 DTO 脱敏）；SSE 事件只序列化脱敏视图。令牌仅存服务端（Java→Python 透传不变）。
- A2：旧版 `/api/chat/stream` 收敛到 V1 端点的 `AgentExecutionContext` 路径（权限/策略/guardrail 全生效）；`:861` 异常改友好错误，不泄内部文本。
- A3：回调签名校验失败返回 401/403（Python 侧据非 2xx 重试）；`AiClient.onStatus` 剥离 Python 原始错误 body。
- A4：自定义供应商 SSRF 校验补私网段拦截；`internalApiToken` 启动期 fail-fast 校验。

**批次 B — Agent 状态机竞态（S3, S4, M2, M3）【单根因：run/task 状态迁移无锁】**

- B1：引入行级锁（`SELECT ... FOR UPDATE`）或乐观版本号统一守卫 run 状态迁移；`expireApprovals` 的 run 更新加 `STATUS_WAITING_APPROVAL` 守卫 + 条件 UPDATE（`UPDATE ... WHERE status=...`）。
- B2：`enqueueRun`/`retryTask`/`requeueTask` 用唯一约束（task_id+attempt）或 CAS 状态迁移实现幂等入队。
- B3：`decideApproval` 补 `@Transactional`；resume 失败收敛改为条件 UPDATE 防覆盖成功。
- B4：自管理调度器并入 `@SchedulerLock` 或为 `requeueOrphan` 补状态守卫；文档化多实例部署前提。

**批次 C — 文档处理与 AI 链路一致性（S5, S6, S7, S8, S9, M10, M11, M12）**

- C1：向量化重处理加文档级锁（分布式锁或唯一活跃 job 约束）。
- C2：`/api/parse` 回调失败改为「索引已落库 + 回调待重试/对账补偿」而非直接 FAILED（插入与状态解耦）；回调通知加重试与共享 httpx 池。
- C3：修 `_supplement_retrieval`（取 `RetrievalResult.docs`）+ 补测试；移除裸 `except`。
- C4：修复 `insufficient_evidence` 判断逻辑，使其可达；统一 run/run_stream 的分解与 groundedness 行为。
- C5：`RecursiveCompressionStrategy` 默认 `max_tokens` 给安全默认值；缓存 key 纳入压缩参数。
- C6：检索失败与"无证据"区分（错误码/告警而非伪装）；工作流超时/工具错误以专用状态帧透传 SSE。
- C7：DeepSeek 流式解析对齐 ModelGateway 异常处理；修缓存键错位；中文 token 估算校准。

**批次 D — 跨层契约（M1, M9 + 类型）**

- D1：RAG `error_only` → `errorOnly` 对齐（前端参数名或后端 `@RequestParam("error_only")`）。
- D2：SSE 链路接入统一 401 处理（复用 `request.ts` 拦截或 SSO 共享登出逻辑）。
- D3：修正 `uploadDocument`/`createKnowledgeBase` 返回类型；文档轮询补 `SUPERSEDED`；`cost.ts` 泛型、`request.ts` 空响应健壮性。

**批次 E — 资源与卫生（M13, M8 + Low 批）**

- E1：无界缓存加容量上限/LRU（LLM 分类缓存、task_status_store、conversation_memory、answer_quality_evaluator）；`classify_sync` 复用线程池；`get_chunks` 分页语义修正。
- E2：Milvus cluster 对账改分页迭代（去 16384 截断）；`get_chunk_detail` metadata 解析对齐；SSE 轮询池扩容或改每连接独立。
- E3：conversation_memory 持久化落地或明确移除"跨会话记忆"文案；清理死代码（`execute_tool` registry 分支、`agent_workflow` LoopNode 语义、`get_workflow_engine` 引用）。
- E4：V32 回填补齐无 user 行 tenant_id；`TaskEventSseManager` null userId 防护。

**批次 F — 运维/交付（非代码）**

- F1：恢复 GitHub CI（处理账单/额度）；恢复后确认 CI 门禁（java/python/eval-offline/helm）全绿。
- F2：按 [TODO.md](vscode-webview://1sobop0oo60auejirs9tmmvj0ii84fagm5mc6e7456n8pe06hj11/TODO.md) P0 完成生产上线安全项（密码轮换、HTTPS、CORS 收紧、关 Swagger、备份）。
- F3：补齐测试盲区（react 全流程、retriever 主链、/api/parse 回调、model_gateway 容错、递归压缩、_supplement_retrieval）。

**修复顺序建议**：A → B → C → D → E → F（安全 > 竞态/计费正确性 > 链路一致性 > 契约 > 资源 > 运维）。

------

## 三、关键链路实测计划（获批后执行，不改代码）

> 环境已确认全部健康。以下为获批后的实测动作：

1. **全量冒烟**：`scripts/smoke-test.ps1`（31+ API + Python 端点 + 前端 + 文档上传→解析→向量化→检索核心链路），预期 47 PASS。

2. 定向探测（验证高危发现）

   ：

   - 实测 RAG「只看失败请求」开关：构造含失败 trace 后勾选开关，确认 `error_only` 未生效（验证 M1）。
   - 实测审批 SSE 负载：拉取 `getApprovals`/SSE snapshot，确认响应含 `executionToken`/`toolInput`（验证 S1）。
   - 实测旧版 `/api/chat/stream` 与 V1 端点权限差异（验证 S2 行为分叉）。
   - 实测文档重处理并发（双击触发）观察是否产生重复 PROCESSING（验证 S5）。

3. **基线测试**：Java `mvn test` / Python `pytest -q tests` / 前端 `npx vitest run`（确认当前基线绿、锚定修复前状态）。

4. **交付**：汇总实测结果，产出最终评估报告（含实测证据），提交给用户审阅。

> 注：批次的修复实施不在本次交付范围（用户要求不修改代码）；路线图供后续排期。

------

## 验证与交付检查

-  实测结果与探索报告一致（S1/M1/S2/S5 有实测证据）
-  三大模块测试基线确认（Java ~563 / Python ~1407 / 前端 ~49）
-  评估报告覆盖全部 9 严重 + 13 中等 + Low 批，锚点可点击
-  修复路线图按「安全→竞态→一致性→契约→资源→运维」排期

------

## 修复进度标注（2026-08-29 第一批实施）

| 项 | 状态 | 说明 |
|---|---|---|
| S1 | ✅ | `AgentApproval.executionToken` / `toolInput` 加 `@JsonIgnore`（REST 与 SSE 序列化均隐藏；Java→Python 令牌经 getter 传递不受影响） |
| S2 | ✅ | 旧版 `/api/chat/stream` 构建 `AgentExecutionContext`（read_only + kb:read 权限），内部异常不再透传（统一友好文案） |
| S7 | ✅ | `_supplement_retrieval` 改取 `RetrievalResult.results`；裸 `except` 改记录日志 |
| S8 | ✅ | `insufficient_evidence` 判断去掉恒 False 的 `not final_answer` 条件 |
| S9 | ✅ | `RecursiveCompressionStrategy` 的 None 比较修复；压缩缓存键纳入 target_ratio/max_tokens/preserve_keywords |
| M1 | ✅ | 前端 `error_only` → `errorOnly`（rag.ts + rag/Index.vue），「只看失败请求」恢复生效 |
| M2 | ✅ | `decideApproval` 加 `@Transactional` |
| M6 | ✅ | 回调鉴权/签名失败返回 401（Python 客户端本就按 ≥400 判失败）；对应测试断言同步更新 |
| S3/M3 | ✅（守卫级） | deny/approve/expire 三处 run 状态迁移加 `waiting_approval` 守卫，防止双向覆盖终态；完整行锁方案待并发压测后评估 |
| S4 | ⏳ | 需 V77 唯一索引 (task_id, attempt) + 先排查存量重复数据，单独批次 |
| S5 | ⏳ | 需文档级锁/唯一活跃 job 约束，单独批次 |
| 其余 M/Low/批次 F | ⏳ | 按路线图排期 |
