# Changelog

All notable changes to HFusionHub are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### 全项目评估修复批次（2026-08-29）：安全与正确性 9 项 + 前端体验（源自全项目评估报告 docs/REPAIR_ROADMAP.md）

#### Fixed（安全/正确性）
- **S1 审批令牌泄露**：`AgentApproval.executionToken`（一次性执行令牌）与 `toolInput`（完整工具参数）加 `@JsonIgnore`——不再经 REST/SSE 下发浏览器（Java→Python 通道走 getter 不受影响）
- **S2 权限绕过**：旧版 `/api/chat/stream` 构建 `AgentExecutionContext`（read_only + kb:read），工具权限/模式门/策略引擎全部生效；内部异常文本不再透传客户端
- **解绑套餐必失败**：前端错传 bindingId（绑定行 id）给按 subscriptionId 查询的后端——改传 subscriptionId，实测解绑成功
- **V76**：`tenant_plan_binding` 补 BaseEntity 全局逻辑删除列 deleted（V70 遗漏），修复 /bid/plan/current 500（套餐中心不可用）
- **M2**：`decideApproval` 加 `@Transactional`（approval/task/run 三表更新原子化）
- **S3/M3 竞态守卫**：deny/approve/expire 三处 run 状态迁移加 waiting_approval 守卫，阻断"刚批准被过期调度覆盖为 FAILED"的双向丢失更新（完整行锁待并发压测）
- **M6**：回调鉴权/签名失败返回 401（此前 200+错误 body 被 Python 回调客户端误当成功），测试断言同步更新

#### Fixed（Python 逻辑）
- **S7 补充检索完全失效**：`_supplement_retrieval` 对 RetrievalResult（非列表）extend 必然 TypeError 被裸 except 吞掉——改取 results 列表，裸 except 改记录日志
- **S8 insufficient_evidence 不可达**：去掉恒 False 的 `not final_answer` 条件
- **S9 潜伏崩溃**：RecursiveCompression 的 `int > None` TypeError 修复；压缩缓存键纳入 target_ratio/max_tokens/preserve_keywords 防参数互串

#### Fixed（前端体验）
- **M1 「只看失败请求」静默失效**：前端 error_only → errorOnly 与后端参数名对齐
- **MCP 服务页**：新增「编辑」（令牌填错此前只能删除重建）；底层错误人性化（HTTP 401 JSON → 可操作中文提示，且不再展示原始错误详情）
- **解绑/MCP 之外**：删除每页右上角装饰 Sparkles 残留；设置引导（导入演示数据）收起改为页面级——刷新自动恢复，不再"点 × 后永远消失"
- **空态示例引导**：智能对话（3 个可点击示例问题，点击直接建对话并预填问题）、知识库/文档（三步引导）、投标项目（四步引导）
- **数据样式**：用量/仪表盘/运行记录大数字 tabular-nums；用量页重设计（彩色指标卡、峰值柱状图、多彩模型占比、斑马纹明细表）；审计日志页重设计（统计卡 + 动作前缀配色 + 时间线布局）

### 冻结名目全部清偿批次（2026-08-29）：LLM 单轨化 + P8 vision-LLM 路线 + P6 cross_encoder 基准解锁

#### Added
- **P8 多模态 vision-LLM 路线**：`MultimodalEvidenceExtractor` 新增 Ollama 视觉模型描述引擎（`RAG_MULTIMODAL_VLM_*`，默认 qwen2.5vl:3b）——内嵌图片 base64 送 `/api/chat`（Ollama images 契约），生成中文描述成为 `kind=image_vlm` 普通文本块进既有检索管道；Tesseract OCR 降级为兜底引擎（VLM 失败自动回落 `image_ocr`），任一引擎失败只跳过该图片永不阻断索引。实测：qwen2.5vl:3b 对含图 docx 准确转写图表全部数字。同时删除从未接线生产的 CLIP 双向量索引实验模块 `multimodal_rag.py`（1367 行）及其 951 行测试
- **P6 reranker 离线基准 `scripts/eval_reranker.py`**：none/lexical/cross_encoder 三臂 A/B（合成语料 220 用例、20 候选），报告落 `evaluation/reports/reranker_ab.json`。实测 recall@10：none 0.832 / lexical 0.843 / **cross_encoder 0.846（最高）**，nDCG@10 0.771（与一阶段持平），CPU ~1.15s/查询。结论：召回优先场景推荐 cross_encoder，默认保持 lexical

#### Changed
- **LLM 链收敛为 ModelGateway 单轨**：`MODEL_GATEWAY_STREAM_ENABLED` 开关、`_build_providers`、`_legacy_chat`/`_legacy_stream` 静默降级、`FailoverLLM`（92 行）及旧链 Ollama 探测机制全部删除。`get_llm()` 单轨返回 GatewayLLM，provider 不可路由时明确报错（此前会静默走旧链）。`DeepSeekLLM`/`OllamaLLM` 具体类保留（gateway 复用其响应缓存；用户级自定义供应商 `build_user_llm` 仍基于它们）

#### Fixed
- **cross_encoder 降级缓存缺陷**：失败实例曾被 `lru_cache` 永久缓存，装好 sentence-transformers 后必须重启进程才生效；改为仅缓存成功构造，失败每次重试，装好依赖即生效

#### Docs
- ENVIRONMENT.md：P6（基准数字 + 治理解除）、P8（vision-LLM 路线 + 治理解除）、`MODEL_GATEWAY_STREAM_ENABLED` 移除；`.env.example` 同步；Flags.vue 精排条目说明更新

### 清单全量清理批次（2026-08-29）：GraphRAG 移除 + 死代码清零 + 文档对账

#### Removed
- **GraphRAG（P7）整体移除**：冻结期治理结论（内存图索引、重启重建、收益不稳定）落地为删除——`scoped_graph.py`（363 行）/ `knowledge_graph.py`（1272 行）/ `GraphChannel` 与 graph 检索通道 / `/api/rag/graph/status` 端点 / 向量化与删除时的图索引钩子 / `RAG_GRAPH_ENABLED`、`RAG_GRAPH_INDEX_PATH` 配置 / `rag.graph.enabled` flag / 前端「图谱检索」文案与开关条目；检索通道收敛为向量 + 关键词混合（P5）。评测框架的 `graph_hit_rate` 指标保留（通用通道指标，历史 trace 仍含 graph 标签）
- **`AgentResponse.agent_status` 废弃字段退役**：`multi_agent_runtime`（3 处）/`workflow_runtime`（2 处）写入点全部改用 `status`，2 处直接断言的测试同步迁移；评测 API 的 `agent_call.agent_status` 为独立局部变量（读 `response.status`），契约不变
- `OLLAMA_MODEL` 迁移告警函数（观察期满）；`getStatusBadge` 从 `format.ts` 合并至 `badge.ts`（统一徽章映射）
- `eval_baseline.py` 移出运行时包（`app/core/rag/` → `scripts/`，6 处引用更新，conftest 补 scripts 路径）

#### 复查结清
- **统一缓存体系（OPTIMIZATION_PLAN 1.9）**：flag 求值缓存已在 R15-16 落地（15s TTL + 写失效）；`UsageLedger` 为预占/结算型账本，原子 SQL 保证配额正确性，不应缓存——该项从半成品清单移除

#### Docs
- `database.md`：迁移历史补全 V58–V75 + 投标业务线 9 张表与商业化表说明（此前停在 V57）
- `ENVIRONMENT.md` P7 / `ARCHITECTURE.md` / README / CLAUDE.md / `java-backend.md` / `PRODUCTION_OPS.md`：Flyway 版本（V1–V75）与测试基线（Java 564 / Python 1339 / 前端 49）全面对齐

### 投标冒烟修复 + 低风险清理批次（2026-08-29）

#### Fixed（正确性）
- **tender_element 唯一键阻断解读（真实缺陷，V75）**：`uk_tender_element (project_id, element_key)` 与解读工作流的数据模型冲突——废标/实质性条款专家为**同类别输出多行**（每条废标条款各一行 `element_key='disqualification_clauses'`），真实招标文件解读落库必撞 `Duplicate entry` 整体 500。新增 `V75__drop_uk_tender_element.sql` 移除该唯一键（幂等由 interpret() 先删后写保证）；本地实测「解读-需求清单非空」由 FAIL 转 PASS，smoke-bid 13 PASS / 0 FAIL
- **smoke-bid.ps1 无法运行（编码）**：文件缺 UTF-8 BOM，Windows PowerShell 5.1 按 ANSI 解析中文注释/字符串直接语法报错；补 BOM 对齐 smoke-test.ps1
- **smoke-bid.ps1 断言 bug**：「招标文件4篇」误用顶层 `importedCount+skippedCount`（含资质库/历史标书库，首跑=7/复跑 skipped=7，永不过）；改取 `sections` 中 `bid_kb` 分节

#### Removed（低风险清理，清单见 docs/CLEANUP_BACKLOG.md）
- `AiClient.chatStream()`（@Deprecated 无调用方）及其测试断言；`VectorizationServiceImpl` 两个无人调用的 @Deprecated 私有方法（`toChunkResponse`/`fromJson`）
- `MainLayout.vue` 本地 `formatDateTime`（与 `utils/date.ts` 重复），统一引用 utils 版本
- 根目录残留日志 4 个；`notebooks/rag_evaluation.ipynb` 归档至 `python-ai/scripts/notebooks/`

#### 复查后保留
- `agent.py` 的 `agent_status` 字段：虽标 deprecated，但 `multi_agent_runtime`/`workflow_runtime` 仍写入且有 6 处测试断言维护，删除需连测试一起迁移，暂保留（已记录于清理清单）

### 修复计划 P0/P1 批次（2026-08-29）：测试基线清零 + 管理员密码重置

#### Fixed（正确性）
- **write_note_tool 配置导入 bug（P0）**：`write_note_tool.py:68` 误用 `from app.utils import config`（模块）访问 `config.JAVA_BACKEND_URL`/`INTERNAL_API_TOKEN`（实为 `Config` 实例属性）→ 笔记持久化必然 AttributeError。改为 `from app.utils.config import config`；write_note 全链路（含 scoped grant、registry 注入）补 mock Java 后端的成功路径回归测试
- **postprocessor 证据门控 × reranker 冲突（P0）**：V58 默认启用 lexical reranker 后，reranker 把 `score` 覆写为覆盖率排序信号，postprocessor 证据门控误用它导致强通道分（0.92）结果被 `filtered_low_evidence` 丢弃——违背「使用原始通道分」的设计注释。新增 `_evidence_score_of`：`metadata.evidence_score` → `metadata.pre_rerank_score` → `score` 回退链
- **runtime.py 绕过 Config 边界**：直读 `os.getenv("OLLAMA_MODEL"/"OLLAMA_EMBEDDING_MODEL")` 与 config.py 的「不在别处直读环境变量」约定冲突；`OLLAMA_EMBEDDING_MODEL` 补入 Config 统一管理

#### Tests（20 个存量失败全部清零：1387 → 1407 通过）
- **测试隔离（P0 复盘）**：①`test_config_validation._restore_config` 硬编码重置 `INTERNAL_API_TOKEN=""`，覆盖 conftest 设定并污染后续 internal/mcp 鉴权测试（4 例）→ 改保存-恢复；②本地 `.env` 的 `VECTOR_STORE_MODE=cluster` 泄漏进测试（CI 无 .env 故未复现）→ conftest 强制 `VECTOR_STORE_MODE=lite` hermetic（约 8 例）；③conftest 统一关闭 MODEL_GATEWAY
- **测试漂移修复（14 例）**：agent_v1 契约测试适配 P9/P10 workflow 包装类（`_get_tools` → 公共 `get_tools()`/解包委托）；`_StubResponse` 补 `model` 属性；write_note 断言从「本地持久化失败」改为「mock Java 后端成功」；rag_access stub lambda 兼容 `model` kwarg；runtime overview 测试固定 Ollama 模型名；空知识库文案断言更新
- **CI 根因**：GitHub Actions 账单扣款失败导致全部 job 未启动（3 秒即失败）——20 个失败长期未被发现的根本原因；TODO.md P0-0 登记账单修复；eval-nightly 增加 `ALERT_WEBHOOK_URL` 失败告警（可选 secrets）

#### Added
- **管理员重置用户密码**：`PUT /api/user/{userId}/password`（仅 admin，不可用于自己）+ 前端「账号权限」页「重置密码」入口与对话框——忘记密码不再需要改库
- **Webhook 管理界面**：设置页新增「Webhook 推送」卡片——订阅 CRUD（名称/回调地址/HMAC 签名密钥/5 类事件勾选）、启停、同步测试投递、投递历史查看；此前该子系统仅有 REST API 无任何前端入口

### 评审落地批次（2026-08-29）：前端体验 + 演示门控 + legacy 退役评估

#### Frontend
- **404 兜底路由**：新增 `src/pages/NotFound.vue` + catch-all 路由（主布局内渲染，保留导航），未知路径不再空白
- **index.html 本地化**：`lang="zh-CN"`、标题改「HFusionHub - 企业级 AI Agent 平台」
- **共享徽章工具**：新增 `src/utils/badge.ts`（色调/等级/投标状态映射），替换 bid 四页、agent、approval、MainLayout 中 10+ 处重复的 `*_LABELS`/`*_CLASS` 实现；+4 例 Vitest
- **时序常量**：新增 `src/constants/timing.ts`，收敛 MainLayout/chat Detail/TestSet/useDocumentProcessor 的 6 处轮询与延时魔法数字
- **主布局轮询合并**：待审批（30s）与未读公告（60s）双定时器合并为单一定时器，公告每 2 个周期刷新一次
- **类型与清理**：`api/vectorization.ts` 全量补返回类型（EmbeddingModel/DocumentChunk/ChunkPage）；移除 chat console.log 残留；`catch (e: any)` 全部改为窄化判断

#### Backend
- **演示数据端点门控**：`/demo/*` 全部端点受 `DEMO_ENDPOINTS_ENABLED`（`app.demo.endpoints-enabled`，默认 true 便于开发）门控，关闭时 403；生产 compose（`deploy/docker-compose.prod.yml`）与 `deploy/.env.example` 默认关闭——`/demo/clear` 有数据破坏性
- **legacy 兼容层访问日志**：`model_gateway._legacy_chat/_legacy_stream`（降级路径逐次告警）、`core/tools` 旧 `get_tools()/execute_tool()` 与 `/api/chat/agent-runs`（每进程告警一次，ReAct 热路径防刷屏）、Java `AiClient.chatStream()`——运行一个版本收集流量证据后择大版本移除（见 OPTIMIZATION_PLAN R15 legacy 退役评估）
- **OLLAMA_MODEL 启动告警**：设置该废弃变量时启动提示「仅影响 Ollama 对话兜底，嵌入走 OLLAMA_EMBEDDING_MODEL」；`python-ai/.env.example` 注释说明

#### Docs
- OPTIMIZATION_PLAN 补冻结路线（GraphRAG/多模态 OCR/cross_encoder）重启条件；ENVIRONMENT.md 登记 `DEMO_ENDPOINTS_ENABLED`；api.md 补开放 API 对接示例

### 第十五轮 · P2/P3 批次（2026-08-28）：可维护性/测试 + 文档/运维（R15-20~30）

#### Maintainability / Testing（R15-20~24）
- **R15-20 react.py 保守抽取**：三份复制的 sources 去重实现收敛为 `_dedupe_sources`（行为一致）；三管线大重构按方案标注渐进，不做一次性重写
- **R15-21 API 层契约测试**：新增 `tests/test_api_contract.py` 9 例覆盖此前零测试的 bid/rag 路由（422 校验、错误包装、成功回传）；**抓到并修复真实不一致**——bid 三个端点失败分支响应缺 `project_id`（成功分支有），已补齐
- **R15-22 真实链路集成测试**：新增 `TenantInterceptorIsolationIT`（Testcontainers mysql:8.0，手动生命周期支持外部 MySQL）——真实 MySQL + Flyway 全链 75 迁移 + 生产租户拦截器装配，验证「租户 A 数据对 B 不可见 / 系统作用域跨租户可见」；本地经 mysql8 外部库验证通过（Windows 上 Testcontainers 与新 Docker Desktop 管道探测不兼容，CI Linux 正常）；Testcontainers 依赖 1.19.3→1.20.6
- **R15-23 Java 收敛**：5 处复制粘贴的内部令牌常量时间比较收敛为 `common/utils/InternalTokenGuard`（行为不变，测试无需改）；`allow-circular-references` 关闭验证通过（Spring 上下文可正常启动）；`computeManifestHash` 从歧义的 `key:value` 拼接改为键递归排序的规范化 JSON（值含 ":"/"," 不再碰撞，嵌套 Map 顺序稳定）
- **R15-24 God classes**：ConversationServiceImpl/AgentTaskServiceImpl 等按「随触碰随拆」原则处理（本轮 AgentTaskServiceImpl 批量化、BidWriteServiceImpl 事务拆分均已缩小职责）；整体拆分列为持续项

#### Docs / Ops（R15-25~30）
- **R15-25 文档对账**：README badge/正文/ROADMAP 测试计数（445/1220+/33→554/1380+/45）、database.md 与 README 的 Flyway V57→V74、CI_GATES 分支保护自相矛盾与 eval-nightly 描述、ARCHITECTURE flag 表（2026-08-19 过时值）、ACCESS_MAP/TODO runner 状态、CHANGELOG 三重 `[Unreleased]` 合并、P1-3 编号缺位说明
- **R15-26 生产安全脚本**：新增 `scripts/rotate-secrets.sh`（全套密钥生成 + 两侧同步清单 + 重启顺序 + 弱默认值 `--check` 扫描）与 `deploy/nginx-https.conf.example`（Let's Encrypt 全流程 + SSE 透传 + HSTS + 内部端口不对外清单）；PRODUCTION_OPS §0 与 TODO P0 项旁注接上脚本
- **R15-27 eval-nightly 隧道**：ROADMAP 补固定子域名/Windows 服务注册落地指引
- **R15-28 P2-8 最小落地**：新增 `app/core/llm/judge_gate.py`——`MODEL_GATEWAY_NO_EXTERNAL_JUDGE=true`（私有部署）时 LLM-as-judge 一律强制走 `MODEL_GATEWAY_INTERNAL_JUDGE_MODEL` 内网模型，未配置则 fail-closed 拒绝评测；接入 answer_quality_evaluator 两条 LLM 评测策略；+4 例单测
- **R15-29 前端遗留**：chat 流式断线自动重试（无内容 + 网络错误时同一 requestId 幂等重发一次）；scrollToBottom 100ms sleep 改 requestAnimationFrame
- **R15-30 staging 真机验证**：TODO 补执行清单（rehearsal + 两套 e2e 脚本），待 staging 机器执行

#### Testing
- Java：全量过 + `TenantInterceptorIsolationIT` 2 例（真实 MySQL 全链）；Python：全量过 + API 契约 9 例 + judge_gate 4 例；前端 build + vitest 45

### 第十五轮 · P1 性能批次（2026-08-28）：检索并行化 + 索引补齐 + 连接治理（R15-10~19）

> P0 缺陷批次之上的 P1 性能批次，9 项全部落地。方案与验收标准见 [docs/OPTIMIZATION_PLAN.md](docs/OPTIMIZATION_PLAN.md) 第十五轮章节。

#### Performance（R15-10~19）
- **R15-10 招投标检索并行化**：撰写（最多 7×N 次串行检索）与解读工作流的语料检索改 `asyncio.gather` + 信号量并发（深度 6/5），有序合并保持去重（首见优先）与 MAX_CHUNKS 截断语义不变——分节生成的串行语义有意保留
- **R15-11 撰写事务拆分**：`BidWriteServiceImpl.write` 不再整个方法 `@Transactional`（旧实现同步 AI 调用 120s 超时占住 Hikari 连接，少量并发撰写耗尽连接池）——拆为读取（自动提交）→ 事务外调 AI → `TransactionTemplate` 短事务落库，对齐 ConversationServiceImpl 阶段划分
- **R15-12 V74 迁移**：补齐 10 张表的 `tenant_id` 前导索引（agent_alert_rule/agent_alert_event/agent_evaluation_dataset/prompt_test_set/prompt_test_set_run/app_call_log/audit_log/note/webhook_subscription；本地库验证全部就位）；核查发现 app_api_key/kb_share/rag_intent_node/user_model_config 已有索引、feature_flag_rule 无 tenant_id 列（scope_value 语义），均不在范围
- **R15-13 co-store 写锁**：`_save_to_co_store`/`delete_document_chunks` 的读-改-写持 `self._lock`——旧实现写路径无锁，并发索引/删除互相覆盖丢文档
- **R15-14 httpx 连接池收敛**：9 处散建 `AsyncClient`（用量 flush/探活/插件配额/容器 runner×4/声明式工具/执行令牌）收敛到 `get_shared_client` 按属主分池；声明式工具的 SSRF 语义（禁跟随重定向）以请求级参数保留
- **R15-15 Milvus/embedding 治理**：search 热路径去掉每查询 `load_collection`（lite+cluster，改为「not loaded」异常时 load 重试一次）；embedding 探活 TTL 化（60s，Ollama 启动后恢复可用不再需要重启进程）
- **R15-16 FeatureFlag 评估缓存（最小落地）**：evaluate 路径的 selectByKey/loadRules 加 15s TTL 缓存 + 全部写路径失效钩子（5 处）；每 agent/工具调用省 2 次 DB 查询
- **R15-17 N+1 批量化**：`expireApprovals` 批量读取 task/run（旧实现每条审批 2 次单查）；插件审计回调 eventId 去重改单次 IN 查询；`VectorReconciliationService.reconcileAll` 全表实体载入改 chunk_id 游标分页（只取两列）
- **R15-18 审计 flush 批量化**：单次批量 POST 替代逐条（50 条积压 50 次往返→1 次）；批量失败回退逐条保留 dead-letter 语义
- **R15-19 声明式插件端点 SSRF 加固**：安装时校验从「仅拦 localhost/.local」扩展到 IPv4 私网/CGNAT/保留段、IPv6 ULA/link-local/IPv4-mapped、域名解析后全地址校验（无法解析一律拒绝 fail-closed）；+5 例字面量单测

#### Testing
- Java 全量 `mvn test`：**555+ passed / 0 failures**（+`PluginServiceImplSsrfTest` 5 例）
- Python 全量 `pytest -q tests`：全过（bid_workflow 检索并行语义 11 例、milvus 28 例、审计/配额/网关/容器相关全绿）
- e2e：`scripts/plugin-builtins-e2e.ps1` **17 项全过**（新 dind sidecar 引擎全链路）；`scripts/static-checks.py` 全绿；V74 经 Flyway 干净重放验证（success=1，索引就位）
- 运维注意：本地 dind sidecar 镜像改用 `docker:dind`（与 rehearsal 同镜像，避免代理依赖）；代理软件未运行时 `docker compose up dind` 无法拉取新镜像属预期

### 第十五轮 · 全面复审优化（2026-08-28）：P0 正确性/安全批次 + 四层优化路线图

> P0–P2 十四轮交付后的三路全面复审（文档路线图 / Java 后端 / Python AI）发现一批**真实缺陷**。本轮实施 P0 批次全部 9 项；P1 性能 / P2 可维护性 / P3 文档运维共 21 项写入 [docs/OPTIMIZATION_PLAN.md](docs/OPTIMIZATION_PLAN.md) 第十五轮章节（R15-1~30）供后续排期。

#### Fixed（P0 批次，R15-1~9）
- **容器插件 agent 链路不可用（R15-1）**：`registry.py` 在 async 方法内同步调 `execute_plugin_tool`，container 模式在已有事件循环的线程里 `run_until_complete` → RuntimeError 被 fail-closed 吞掉，静默返回 `container_runner_unavailable`。改为 `asyncio.to_thread` 派发 + `_run_container_coroutine` 双路径（无循环线程 `asyncio.run`/有循环线程单线程执行器）；补 registry 级 container-mode 回归测试
- **跨租户语料缓存泄漏（R15-2）**：lite co-store 缓存 key 只含 `(mtime_ns, size)` 而值是租户作用域语料，双租户交替读取时后到租户命中前租户数据。改为按租户分键 LRU（上限 8）；补双租户隔离/签名失效/无租户上下文 4 例测试
- **OpenAPI key 解析租户 bug（R15-3）**：`/openapi/**` 无会话租户，行拦截器把查询缺省填 `tenant_id=1`，非 1 租户 key 永远 401。`resolvePublishedApp` 改 `TenantContext.runAsSystem`（key hash 全局唯一），业务仍按 `runAs(app.tenantId)`；补跨租户解析测试
- **内部插件审计租户错标（R15-4）**：审计回调无租户上下文，行全落 tenant_id=1 且去重查询漏跨租户行。整体系统作用域 + 从插件解析结果显式写 `tenant_id` 列（`PluginAuditLog` 补实体字段；平台内建插件归 1）
- **流式聊天绕过输出守卫（R15-5）**：SSE 路径此前明确不做 `guard_model_output`。新增 `_content_guarded_sse` 包装全部 4 条流式端点（增量透传 + 流末对累计回答守卫），命中时在 [DONE] 前发 `content_replace` 矫正事件；Java 桥接（重置 responseBuilder + 转发 replace）与前端（Detail.vue 替换语义）同步支持；补 4 例守卫测试
- **插件子进程沙箱 fail-open（R15-6）**：manifest 无 sandbox 段 = 无网络/文件限制。改为 default-deny：网络空白名单 = 全部拒绝，文件系统未声明仅放行插件目录 + 系统临时目录；Windows 资源限制跳过改为显式 warning；补真实子进程沙箱拒绝测试 3 例
- **plugin-runner 阻塞与 fail-open 解析（R15-7）**：async 处理器内同步 Docker SDK 调用冻结事件循环串行化全部执行 → 全部 `asyncio.to_thread`；容器正常退出但输出不符契约 JSON 时旧实现报 `success=True` raw_output → 改 fail-closed `tool_output_unparseable`
- **密钥与暴露面治理（R15-8）**：`MODEL_CREDENTIAL_ENCRYPTION_KEY` 不再回退复用 `PYTHON_AI_INTERNAL_TOKEN`（未配置 fail-fast；曾以内部令牌加密的历史数据需重新录入）；`PLUGIN_RUNNER_TOKEN` 移除弱默认值；CORS `allow-any-origin` 默认翻转 false（显式开启时 loud warning）；Actuator 移独立管理端口 `:9092`（移出 Sa-Token 覆盖，Prometheus 抓取目标同步改 `java-backend:9092/actuator/prometheus`，compose 仅 expose 不发布宿主机，`restart-modules.ps1` 健康检查 URL 同步）
- **feature_flag 降级语义（R15-9）**：后端不可达时可用性旗标直接返回 True 但注释声称「保留 env 配置」——改为按旗标回退 env 派生值（hybrid/graph/reranker/multi-agent），无映射旗标保持原默认

#### Testing
- Java 全量 `mvn test`：**555 passed / 0 failures**（+OpenApiServiceImplTest 跨租户解析 1 例）
- Python 全量 `pytest -q tests`：全过（新增 `test_plugin_sandbox_runner.py` 11 例、`test_co_store_tenant_cache.py` 4 例、`test_chat_stream_guard.py` 4 例、feature_flag env 降级 2 例）
- 前端：`npm run build` 成功 + vitest **45 passed**
- e2e：`scripts/plugin-builtins-e2e.ps1` **17 项全过**（验证 to_thread 重构后 runner 全链路）；`scripts/static-checks.py` 全绿；dev/prod compose 校验通过

### 第十四轮 · 招投标商业化 P2（2026-08-28）：计费套餐 + 行业方案售卖 + 开放 API

> P0/P1 领域闭环之上，P2 完成商业化骨架：订阅数据模型（套餐目录 + 租户绑定）、工作流 plan 模块开关、三档计费坐席校验、行业方案包评测与免费试用样例、前端套餐中心/套餐管理/模板商城、开放 API 结算。全链路复用既有租户/配额/幂等账本/评测基座。

#### Added
- **P2-1 订阅数据模型**：Flyway `V69__bid_subscription.sql`（plan_code/plan_type tier|industry/max_projects/max_seats/char_quota/module_flags JSON 0/1 + status active|archived，平台目录）+ `V70__tenant_plan_binding.sql`（租户绑定，多套餐叠加授权）；`BidSubscriptionService.getCurrent` 聚合出当前档位与已绑定套餐，`tier` 对齐既有 `tenant.plan_tier` 驱动每日限额引擎
- **P2-2 工作流 plan 模块开关**：`BidPlanGateService` 组合门禁 `module_enabled = tenant_plan_binding.module_flags（套餐授权）AND feature_flag（bid.module.{draft/check/docx/openapi} 运营开关）`；未授权模块抛 `PLAN_MODULE_DISABLED`，撰写/自检/开放 API 全链路生效；坐席门禁 = 有效 tier 绑定 maxSeats 最大值 vs `tenant_member` 在职成员数
- **P2-3 平台内建插件上架**：Flyway `V73__bid_plugin_builtins.sql`（`plugin.tenant_id` 改可空 = 平台内建，种子注册 `bid_docx@1.0.0` / `bid_quote@1.0.0`，含 sandbox_config + tool_specs + container_image）+ 插件租户可见性服务层过滤（`plugin` 入 `TENANT_IGNORE_TABLES`，平台内建全租户可见 / 自有仅本租户 / 跨租户按不存在处理）；`python-ai/plugins/` 插件源码（bid_quote 复用 `bid_calc_scoring` 确定性评分）+ `build_wheel.py` 确定性 wheel 构建（`.sha256` sidecar）+ `sign_wheels.py` 平台 Ed25519 签名（`.sig` + 信任策略注册，加载器强制校验）+ `app/core/plugin/builtins.py` 启动加载；dev 沙箱解锁：compose `dind` sidecar（TLS 证书卷 + `dind-data` 持久化）+ runner `tcp://dind:2376` + python-ai `PLUGIN_BUILTIN_WHEELS_DIR`/`HFUSIONHUB_PLUGIN_TRUST_DIR` 接线（compose 与 `restart-modules.ps1` 双路径）；`scripts/plugin-provision.sh` 一键上架（构建→签名→镜像→dind 载入→`image_digest` 回填）+ `scripts/plugin-builtins-e2e.ps1` e2e 验收（17 项：docx/xlsx 真实渲染、报价/评分数学、digest fail-closed）；MCP 第三方工具路径核验（`mcp_client.call_tool` 独立于插件沙箱路径，不受本轮改动影响）
- **P2-7 商业化核心**：三档计费（按项目 `bid_projects` / 按字符 `bid_draft_chars` / 按坐席 `tenant_member`）全走 V35 幂等账本，超额抛 `QUOTA_EXCEEDED`；**行业方案包** = 平台级 `bid_template` + 预置行业知识（只读授权）+ 专属评测报告，按 `tenant_plan_binding` 授权售卖；开放 API 新增 `POST /openapi/bid/check`（复用 App/AppApiKey key-auth：sha256(key_hash) → 发布 App → Redis 限流 → AppCallLog + ModelUsageRecord 结算）
- **P2-4 行业方案包评测**：`evaluation/kb_bid_construction/`（蓉城市政道路提升改造 CJ-2026-0721，预算 8600 万）+ `evaluation/kb_bid_it/`（云谷智慧园区数据中心 YG-2026-0908，预算 5800 万）两套行业语料（KB_ID 202/203）+ 各 24 用例 `suite_bid_{industry}`；冻结 `bid_construction_baseline.json` / `bid_it_baseline.json`（四项领域指标全 1.0）；CI `eval-offline` 并行「构造门禁 + IT 门禁」（SHA-256 完整性 + 0.9 阈值 + fail-on-regression）作为行业方案售卖质量凭证
- **P2-6 免费试用样例**：每行业包内置 3 份脱敏公开招标样例（`demo/bid/industry/{construction,it}/`，与评测语料同源）；`POST /demo/import-bid-industry`（admin，幂等）一键建库（KB category=tender）+ 导入 3 文档 + 建示例投标项目
- **P2-5 前端**：`/bid/billing` 套餐中心（当前档位/模块生效徽标/已绑定套餐解绑/今日用量配额条/套餐目录与模板商城双 tab，套餐卡含绑定 + admin 免费试用样例导入）+ `/admin/plans` 套餐管理（平台目录 CRUD + 模块开关 + 归档 ConfirmDialog）；`api/plan.ts`（parseModuleFlags/formatCents/listPlatformPlans/getPlanCurrent/bind/unbind/admin CRUD/template 市场）+ `api/demo.ts` 新增 `importBidIndustrySamples`

#### Changed
- `docs/ACCESS_MAP.md`：Java 接口 252→267（+8 套餐 +5 模板 +1 开放 API +1 demo）、前端路由 40→42（+套餐中心 +套餐管理）；Python 路由保持 70
- `docs/PLUGIN_RUNNER_TLS.md` 重写（dev compose dind sidecar 默认解锁，宿主 daemon TLS 降级为备选）+ 新增 `docs/PLUGIN_BUILTINS.md`（内建插件 provision 管线 / 租户可见性 / MCP 第三方工具路径对比）；README 文档索引同步

#### Testing
- Java 全量 `mvn test`：**554 passed / 0 failures / 1 skipped**（本轮新增 `BidPlanGateServiceImplTest` 等 + P2-3 `PluginServiceImplTenantVisibilityTest` 3 例，`BidDemoImportServiceImplTest` 扩展至行业导入用例）
- Python 全量 `pytest -q tests`：**1382 collected 全过**（P2-3 新增 `test_plugin_builtins.py` 6 例；MCP client/server/auth 27 例通过，核验第三方工具路径不受插件改动影响）
- e2e 验收：`scripts/plugin-builtins-e2e.ps1` **17 项全过**（bid_docx .docx / bid_quote .xlsx 真实沙箱渲染、报价/评分数学、错误与缺失 digest fail-closed）；`scripts/static-checks.py` 全绿（含 plugin 入 TENANT_IGNORE_TABLES 后的租户列完整性）
- 前端：`npm run build` 成功 + vitest **45 passed**（新增 `api/__tests__/plan.spec.ts` 6 例）
- 评测门禁：`scripts/eval_offline.py` 三个门禁全绿 —— 构造/IT 行业包（四项领域指标 1.0）+ bid 撰写/自检工作流（9 项指标 1.0），--fail-on-regression 无回归

### 第十三轮 · 招投标垂直化 P1（2026-08-25）：标书撰写 + 废标自检全链路

> P0 解读闭环之上，P1 打通「撰写 → 逐节审批 → 自检 → critical 确认」闭环。领域层全部复用既有多租户 / Agent 运行时 / RAG / 评测 / 配额基座，新增撰写/自检工作流、分节流式 SSE、强制人工审批、确定性评测门禁。

#### Added
- *（编号说明：第十三轮规划含 P1-3，实施时未单独立项，编号保留空缺；相关内容见 P1-4 评测深化。）*
- **P1-1 数据模型扩展**：Flyway V66–V68 新增 `bid_draft`（分节长文 + 状态 drafting/approved/rejected + version 幂等重写 + approved_by 审批人）、`bid_template`（tenant_id 可空 = 平台模板）、`bid_check_report`（严重度 critical/warning/info + evidence + suggested_fix）；`extractor.py` 支持多文件合并（主招标文件 + 澄清/补遗，来源标签可追溯）与 XLSX 评分表解析（openpyxl 可选依赖，缺失时降级）
- **P1-2 撰写 + 自检多智能体**：`write_workflow.py`（商务/技术/资质/格式分节生成，每节以 `bid_requirement` 为输入、三 KB 检索并产出 `[N]` 证据引用 → chunk_id）+ `check_workflow.py`（确定性规则：保证金/截止开标 critical、废标条款 warning、评分点 info + LLM 语义复核）；SSE 新增 `bid_section_started/completed` 事件（`POST /api/bid/write/stream` 流式逐节生成）；Java `AiClient.bidWriteStream` + `BidWriteServiceImpl.writeStream`（请求线程捕获租户上下文，Reactor 回调经 `TenantContext.runAs` 落库）
- **P1-4 评测深化**：新增免 LLM 的确定性工作流门禁 `app/core/bid/eval_gate.py`（9 项指标：requirement_coverage / section_routing_accuracy / section_completeness / citation_faithfulness / bond_recall / deadline_recall / disqualification_recall / substantive_recall / false_positive_free，阈值全 1.0）+ `scripts/eval_bid_workflow.py` CLI 出 JSON 报告；CI `eval-offline` job 新增「招投标撰写/自检工作流门禁」（`bid_*` 改动必须过此门禁）
- **P1-5 前端**：新增 `/bid/projects/:id/requirements` 需求确认页（按类别分组 + manual_review 低置信琥珀标记 + 逐项确认）、`/bid/projects/:id/draft` 撰写工作台（分节流式生成 + 逐节通过/驳回审批 + 全部通过便捷入口 + 自检 tab 内嵌）、`CheckReport.vue`（严重度分组 + 确认风险/已修复 + 定位章节 + 修复建议）
- **P1-6 冷启动扩展**：`/demo/import-bid` 一键导入三类知识库共 7 篇种子（招标文件 4 + 企业资质库 1 + 历史标书库 2）+ 示例投标项目；撰写自动并入项目创建者的资质库/历史标书库（`BidWriteServiceImpl.loadKnowledgeBaseIds` 按 userId + category + status 过滤），演示「历史标书复用撰写」
- **P1-7 计费补全**：`UsageMeter` 新增 `BID_DRAFT_CHARS`（撰写产出字符）/ `BID_CHECK_REPORTS`，走 V35 幂等账本 reserve+settle，超额抛 `QUOTA_EXCEEDED` 回滚本次撰写/自检
- **P1-8 合规**：撰写每节强制审批（记录 approved_by）+ 自检 critical 级强制人工确认 + 三处免责 Banner + 证据引用追溯；新增 `docs/BID_COMPLIANCE.md`（机密性 / 准确性 / 审计 / 私有部署四节）

#### Changed
- 撰写检索范围由单知识库扩展为「招标文件库 + 本人资质库/历史标书库」多 KB（Python 侧按 chunk 去重）
- `docs/ACCESS_MAP.md`：Java 接口 246→252（+6 撰写/自检）、Python 路由 67→70（+3 bid 路由）、前端路由 38→40；README 文档索引新增 [docs/BID_COMPLIANCE.md](docs/BID_COMPLIANCE.md)

#### Testing
- Java 全量 `mvn test`：**505 passed / 0 failures / 1 skipped**（本轮新增 `BidWriteServiceImplTest`(6) + `BidCheckServiceImplTest`(5)，`BidDemoImportServiceImplTest` 扩展至 3KB/7 文档）
- Python 全量：**1347 passed / 21 failed（与第十一轮基线同清单，均为既有安全/观测类环境依赖用例）/ 8 skipped，零新增失败**（已核验：同 8 个失败用例文件在含/不含本轮改动下失败数一致 17/17；full-suite 独有 4 例可单独通过，属测试并发干扰）。bid 领域单测 **27 passed**（本轮新增 `test_bid_write_check`(11) + `test_eval_bid_gate`(6)）；`scripts/eval_bid_workflow.py` 9 项指标全 1.0 通过
- 前端：`npm run build` 成功 + vitest **39 passed**

### 第十二轮 · 招投标垂直化 P0（2026-08-25）：招标文件智能解读 MVP 落地

> 方向性里程碑：HFusionHub 由横向通用 AI Agent 平台垂直化为**招投标智能助手 SaaS**（B 端多租户）。P0 跑通「招标入库 → 要素解读 → 需求清单」闭环，全部复用既有多租户 / Agent 运行时 / RAG / 评测 / 配额五大基座，仅新增领域层（`python-ai/app/core/bid/`、`java-backend/…/bid/`、`hfusionhub-frontend/src/pages/bid/`）。

#### Added
- **P0-1 领域数据模型**：Flyway V61–V65 新增 `bid_project`（状态机 interpreting→requirements→drafting→checking→submitted/archived）、`tender_element`（evidence_chunk_ids 证据引用 + confidence）、`bid_scoring_method`（综合评分法/最低价法 + points_json）、`bid_requirement`（需求清单 + satisfied_status）、`knowledge_base.category`（tender/qualification/bid_history/general 三类私有库）；全表含 `tenant_id`
- **P0-2 领域多智能体解读**：`BidInterpretWorkflow`（要素抽取/评分办法/废标条款/需求清单专家并行 + 合成），Python 产出 JSON + 证据 → Java `BidProjectServiceImpl.interpret()` 幂等落三表；`BidProjectController` 8 个 `/bid/project/*` 接口
- **P0-3 领域内建工具**：`app/core/bid/tools.py` 注册 `bid_calc_scoring`/`bid_list_requirements`/`bid_render_template`（确定性、可评测；插件化留 P1）
- **P0-4 领域评测与门禁**：种子语料 `evaluation/kb_bid/` + `suite_bid/`；新增 `qualification_recall`/`disqualification_clause_recall`/`scoring_point_accuracy`/`bid_terminology_accuracy` 指标并冻结基线（当前全 1.0），CI `eval-offline` 对 `bid_*` 改动回归
- **P0-5 前端领域化**：`/bid/projects` 投标项目工作台 + `/bid/projects/:id/interpret` 解读看板（要素卡片/评分办法/需求清单/证据引用），`api/bid.ts` 7 个接口，MainLayout 新增「投标项目」菜单
- **P0-6 冷启动种子**：`BidDemoImportService` 内置 4 份脱敏招标文件 + 示例项目，`POST /demo/import-bid` 一键建库建索引导入、`POST /demo/clear-bid` 清理；`scripts/smoke-bid.ps1` 冒烟脚本（LLM 可用性门控解读步骤）
- **P0-7 商业化骨架**：`UsageMeter` 新增 `BID_PROJECTS`/`TENDER_ELEMENTS`，创建项目/解读按量计量（reserve+settle 幂等账本，超额抛 QUOTA_EXCEEDED 回滚），前端 `/cost` 自动出现
- **P0-8 风险合规**：解读看板免责声明 + 每要素 `evidence_chunk_ids` 引用；低置信（<0.6）需求强制 `manual_review` 人工确认兜底

#### Testing
- Java 全量 `mvn test`：**494 passed / 0 failures / 1 skipped**（新增 `BidProjectServiceImplTest`(6) + `BidDemoImportServiceImplTest`(5)）
- Python：bid 领域单测 **36 passed**；离线评测门禁 4 项 bid 指标全 1.0、无回归、无 gate_failures（exit 0）
- 前端：`npm run build` + vitest **39 passed**

### 第十一轮优化（2026-08-24）：Reranker 上线 + 流式治理 + 多 Agent 解锁

#### Added
- **Reranker 二级重排上线**：`RAG_RERANKER_MODE=lexical` 默认启用（零依赖确定性），Flyway V58 将 `rag.reranker.enabled` 默认置 TRUE，前端「能力开关」页可关
- **LLM 响应缓存流式走 ModelGateway**：agent/chat 的 LLM 调用（含流式）经 `get_llm()` → `GatewayLLM`，限流/熔断/计费/响应缓存对流式同样生效（`MODEL_GATEWAY_STREAM_ENABLED=true` 默认）；新增 `tests/test_llm_gateway_stream.py` 15 项回归（缓存命中不重复计费、限流拒绝、熔断、流中首 chunk 前 failover、legacy 降级无递归等）
- **事件循环阻塞清理**：`embedding/__init__.py` 同步包装改用模块级共享线程池（不再每次 `asyncio.run` 新建），Ollama `is_available` 已线程池 + TTL 缓存
- **多 Agent 协作解锁**：Flyway V59 将 `agent.multi_agent.enabled` 默认置 TRUE；前端「能力开关」页由冻结改为实验态，「复杂任务」预设同步开启
- **Plugin Runner TLS**：`scripts/generate-runner-tls.{sh,py}` + `deploy/runner-tls/` 证书链 + `docs/PLUGIN_RUNNER_TLS.md`（主机级 Docker daemon TLS 为文档化手动步骤）
- **SSO/OIDC 单点登录**：通用 OIDC 客户端（授权码流程）`/user/sso/authorize` + `/callback`（Redis 一次性 state 防 CSRF → code 换 token → userinfo → 按 (provider,subject) 查找/邮箱关联/自动开户 → Sa-Token 登录）；`sys_user` 增 `oauth_provider/oauth_subject` 唯一绑定列（V60）；登录页 SSO 按钮 + `/sso/callback` 落地页；`docs/OIDC.md` 接入指南；`OidcServiceTest`(9) + `SsoControllerTest`(4) 全绿。默认关闭，经 `app.oidc.*` 对接外部 IdP 启用
- **eval-nightly 启用（进行中）**：cpolar 内网穿透暴露 Python AI（`/health` 200、`/api/chat` 鉴权生效），`vars.EVAL_BASE_URL` 已设；`secrets.EVAL_INTERNAL_TOKEN` 待用户在 GitHub UI 填入

#### Changed
- **docs/ENVIRONMENT.md**：新增 `MODEL_GATEWAY_STREAM_ENABLED`；P10 状态由冻结改 Beta；`RAG_MULTI_AGENT_ENABLED` 行注明 V59 默认开启

#### Testing
- Python 全量回归：21 失败（基线同清单）+ 1319 passed（基线 1298 + 新增 21），**零新增失败**

### 第十轮优化（2026-08-19）：文档体系整合

#### Documentation
- **合并 5 份文档为 3 份唯一权威**：
  - `WHITEPAPER.md` → `ARCHITECTURE.md`（架构全景 + 白皮书原理合并为单一架构文档）
  - `PROJECT_ASSESSMENT.md` → `ROADMAP.md`（2026-08-18 评估快照存档为路线图附录）
  - `PRODUCTION_CHECKLIST.md` + `DR_VECTORS.md` → `PRODUCTION_OPS.md`（上线检查清单 + 向量库容灾并入运维手册，**移除明文密码**）
  - `PERFORMANCE_BASELINE.md` → `SCALING.md`（性能基线并入扩容手册，清理 6 个不存在的基准脚本引用）
- **删除**：`PROJECT_SUMMARY.md`（内容被 CHANGELOG + TODO 覆盖）
- **更新**：`startup-guide.md`（V35→V57、去占位符提示）、`java-backend.md`（V35→V57）、`database.md`（补 V57 主题偏好迁移）、`python-ai.md`/`ENVIRONMENT.md`（`RAG_AGENT_WORKFLOW_ENABLED` 实际已启用、`OLLAMA_EMBEDDING_MODEL` 默认 `bge-m3:latest`）、`SWAGGER_UI.md`（移除硬编码密码、修复 API_STANDARDS.md 死链）、`TROUBLESHOOTING.md`（统一数据库名 `hfusionhub`）、`CHANGELOG.md`（修正 `DELETE /api/demo` → `POST /api/demo/clear`）
- **README.md**：新增「文档索引」章节，逐份说明 `docs/` 下每个文档的作用；修正徽章测试数（Java 445 / Frontend 33）与过时表述

#### Notes
- 事实统一基线：Java 445 测试、Python 1220+、Frontend 33、Flyway 当前 V57、DeepSeek key 已配置

### 第九轮优化（2026-08-19）：主题系统 + 配额展示 + 空状态统一 + 演示数据清理 + 文档体系完善

#### Added
- **主题系统三档切换 + 服务端同步**：`sys_user.theme_preference`（V57 迁移，枚举 `light`/`dark`/`system`）；`PATCH /api/user/theme-preference` 持久化到数据库；`GET /api/user/info` 下发主题偏好；前端 `useTheme` composable 登录时优先采用远端配置（换设备自动应用），设置页三档切换器
- **租户配额展示**：`QuotaController` + `QuotaSummaryDTO`（`GET /api/quota/summary`）→ `/cost` 页新增租户配额面板，用量条 70%/90% 分级告警色（琥珀/红色），超额时禁用对话发送按钮
- **演示数据清理**：`POST /api/demo/clear` 清空当前租户下的演示知识库、文档、回答方案、笔记、记忆、应用、公告（保留用户账号和其他真实数据）；设置页新增「清空演示数据」区块，确认对话框 + 操作反馈
- **EmptyState 组件统一**：12 个页面迁移至统一 `EmptyState.vue` 组件（支持图标、标题、描述、可选 CTA 按钮）——`/admin/audit-logs`、`/admin/notices`、`/builder/apps`、`/builder/plugins`、`/builder/mcp-servers`、`/notes`、`/memory`、`/document`、`/knowledge/detail`、`/knowledge/chunks`；受控 Dialog 模式（`v-model:open`）确保 EmptyState CTA 可正常打开对话框

#### Changed
- **页面标题样式统一**：`/settings` 和 `/cost` 页面标题改为 `<h1 class="flex items-center gap-2 text-xl font-semibold">` + 内联图标，移除厚重的 border/shadow 包装

#### Fixed
- **Plugins.vue 零宽字符编译错误**：EmptyState 组件属性中混入 U+200B（零宽空格）导致 TypeScript 编译失败，已清理并重写

#### Testing
- 所有测试通过：Java 445 passed（含 `QuotaController` 断言）、Python 1220+ passed、Frontend 33 passed + build 成功
- E2E 测试覆盖：主题切换/持久化（3 场景）、配额展示/限流（3 场景）、演示数据导入/清空（4 场景）

#### Documentation
- 新增 `docs/PRODUCTION_CHECKLIST.md` — 生产环境检查清单（安全、备份、监控、合规）
- 新增 `docs/SWAGGER_UI.md` — API 文档访问与安全配置指南
- 新增 `docs/PERFORMANCE_BASELINE.md` — 性能基线测试方法与目标
- 新增 `docs/TROUBLESHOOTING.md` — 故障排查手册（P0-P3 分级，覆盖常见问题）
- 新增 `docs/SCALING.md` — 扩容与性能优化指南（垂直/水平扩容、K8s 部署）
- 新增 `scripts/run-all-benchmarks.ps1` — 自动化性能基线测试脚本
- 新增 `TODO.md` — 完整操作清单（P0-P3 优先级，含时间估算）
- 新增 `PROJECT_SUMMARY.md` — 项目推进总结与下一步行动计划

#### Notes
- `/cost` 页配额面板仅展示 `usage_quota` 表已有数据，租户配额初始化由管理员在管理端设置（未来可接入计费系统）

### 第八轮优化（2026-08-19）：各菜单一键导入示例数据

#### Added
- **演示数据一键导入升级**：`POST /demo/import` 从仅导入演示知识库扩展为覆盖 6 个菜单——知识库文档（3 篇）、回答方案（客服答疑/文档总结/代码审查 3 个已发布模板，与前端内置示例文案一致）、我的笔记（周会纪要 + RAG 调优笔记 2 篇，`demo/notes/` classpath 资源）、我的记忆（1 条偏好 + 1 条实体事实）、应用发布（1 个绑定演示 KB 的草稿应用）、公告管理（1 条欢迎公告，通知铃铛全员可见）；全部按「用户 + 名称/标题」判重幂等，`DemoImportResultDTO` 新增 `sections` 分项计数
- **MCP 服务示例预填**：添加对话框新增「填入示例」按钮（Notion MCP 官方端点示例），空状态提示更新

#### Fixed
- `notes/Index.vue` 新建笔记 `rows="8"` 字符串传入 number 类型 prop 导致 `vue-tsc` 构建失败（预存问题，`:rows="8"` 修复）

#### Notes
- 模型用量/运行记录/待确认/回答效果等真实运行数据页**不**注入演示数据（与此前移除仪表盘假趋势的决策一致）
- 测试：Java 443 全过（`DemoImportServiceImplTest` 扩展为 3 场景 × 6 分项断言）；前端 build 通过 + Vitest 33/33

### 第七轮优化（2026-08-18）：写笔记闭环 + 全栈验证修复 + 工程化补课

#### Added
- **写笔记闭环（P0–P4 全链路）**：`note` 表（Flyway V55）+ `NoteController` 用户笔记 CRUD + `InternalNoteController`（Python write_note 回调，X-Internal-Token 保护）；Python `write_note_tool` 从占位实现改为真实持久化（回调 Java `/api/internal/notes`）；前端聊天"需要你的确认"审批卡片 + 「我的笔记」页面（列表/查看/下载/删除）；E2E `e2e/write-note.spec.ts`（3 项通过）
- **工程化脚本**：`scripts/smoke-test.ps1`（全功能冒烟，41 项全过）、`scripts/static-checks.py`（租户列完整性 + internal token 键一致性，接入 CI `static-consistency` job）、`scripts/verify-agent-workflow.ps1`（Agent 工作流回归验证）
- **管理端审计视图**：`AuditController`（`GET /admin/audit-logs/operations` + `/cross-tenant`）
- **开放 API 用量打通**：`OpenApiServiceImpl` 成功调用额外落 `model_usage_record`（/cost 页面可见开放 API 用量）
- **模型用量链路接通**：`ConversationServiceImpl`/`AgentTaskServiceImpl` 聊天与 Agent 完成时写 `model_usage_record`（此前 `record()` 无调用方，/cost 永远为空）
- **web_search 工具修复**：嵌套 Topics 展开 + lite HTML 搜索 fallback（Instant Answer 空结果不再返回空）；`agent.web_search.enabled=1`
- **意图分类写操作**：OPERATION 关键词补"保存/写入/整理成笔记/保存到"等 + LLM 分类提示词增强（"把结论整理成笔记保存到知识库"→ operation/tool_execution）

#### Fixed
- **`kb_share` / `app_api_key` 缺 `tenant_id` 列（V56）**：两表被租户拦截器注入 `WHERE tenant_id=?` 导致整表功能 500（知识库共享、开放 API Key 管理从 V52/V53 建表起不可用）——补列 + 回填 + 索引
- **`FeatureFlagInternalController` token 键错误**：`${app.internal-token}`（未定义）→ `${python-ai.internal-token}`；Python 从 0 flags → 8 flags
- **Agent workflow 工具白名单漏 write_note**：`get_agent` 的 `ToolExecutionPolicy`/`SingleAgentWorkflow.allowed_tools` 仅含 3 只读工具导致 write_note 永不可见——approval_write 能力时放行
- **workflow 状态映射缺失**：`waiting_approval` 被映射为 completed，已修复
- **SaTokenConfig**：`/internal/notes/**` 加入登录白名单

#### Docs
- 新增 `docs/PROJECT_ASSESSMENT.md`（全栈评估报告）、`docs/PRODUCTION_CHECKLIST.md`（生产核对清单）、`docs/PLUGIN_RUNNER_TLS.md`（Runner TLS 指引）；重写 `docs/database.md`（V1–V56 全迁移表）；`AGENTS.md`/`CLAUDE.md` 迁移版本更新至 V56 + 新表说明；英文文档标题中文化（api/architecture/database/env/java/python/roadmap/whitepaper/dr_vectors）

#### Notes
- feature flags 现状：`agent.enabled=1`、`agent.write_tools.enabled=1`、`agent.web_search.enabled=1`、`approval.required_for_write=1`（`agent.multi_agent.enabled=0` 保持冻结）；`RAG_AGENT_WORKFLOW_ENABLED=true`
- `DEEPSEEK_API_KEY` 已配置真实 key（2026-08-19 配置后聊天默认 DeepSeek 优先，流式实测通过）
- Plugin Runner 在本机仍 unhealthy（Docker daemon TLS 需主机级配置，见 `docs/PLUGIN_RUNNER_TLS.md`）

### 第六轮优化（2026-08-17）：应用化发布 + 知识摄入扩展 + 治理收口

#### Added
- **应用发布（B1/C4）**：`app` + `app_api_key` + `app_call_log` 表（Flyway V52）；应用 CRUD/发布/撤回；API Key SHA-256 哈希存储、明文仅创建时展示一次；公开端点 `POST /openapi/chat`（`Authorization: Bearer hf_xxx`），Redis 固定窗口限流（60/min/Key）+ 按 Key 计费日志
- **表格/网页知识摄入（A3）**：CSV/XLSX 解析器（纯标准库，表格语义化 chunking）+ 注册进解析器工厂；`POST /api/ingest/url` 网页抓取（SSRF 防护、HTTPS-only、2MB 上限、HTML→正文抽取）；Java `POST /document/from-url`；文档页新增"上传文件 / 网页地址"双模式
- **联网搜索（B4）**：web_search 工具支持 DuckDuckGo（免 Key）/ Tavily / Serper（`WEB_SEARCH_*` 环境变量）；`agent.web_search.enabled` flag 门控暴露给 V1 Agent，执行仍受策略引擎（生产禁外网/模式/审批）约束
- **MCP Client 管理（B5）**：运行时注册/重连/移除外部 MCP 服务器，持久化到 `mcp_servers.json`；新页面"MCP 服务"
- **知识库共享（C2）**：`kb_share` 表（V53）；所有者共享/撤销、共享给我的列表；共享用户可对共享 KB 创建对话（Java 侧 4 处 KB 只读校验统一放行）
- **操作审计（C1）**：`audit_log` 表（V54）；公告发布/删除、应用发布/撤回/删除、API Key 创建/删除、KB 共享/撤销均记录审计
- **在线答案评测（C3）**：`POST /api/rag/evaluate/answer-judge` LLM-as-judge 打分（无标准答案模式），Java 代理 `/rag/observability/evaluate/judge`
- **OpenAI 兼容备用供应商（B2）**：`OPENAI_COMPATIBLE_*` 环境变量加入 FailoverLLM 链（通义/Kimi/OpenAI 兼容端点）
- **公告管理（A1）**：管理员公告发布页 + `GET/POST/DELETE /notifications/admin`；通知铃铛接入真实 AgentAlertEvent（此前为待办）
- **实验特性三档治理（A2）**：能力开关页新增"稳定 / 实验 / 冻结"三档；GraphRAG / 多模态 OCR / Multi-Agent / cross_encoder 重排标记冻结；ENVIRONMENT.md 同步

#### Tests
- Java：+20 用例（AppServiceImpl 7、OpenApiServiceImpl 5、KbShareServiceImpl 6、RagObservabilityController judge 2）→ 443
- Python：+34 用例（CSV/XLSX 9、URL 摄入 16、web_search 门控 6、在线评测 3）→ 1266 通过

#### Fixed
- Java 测试环境与本地 `.env`（VECTOR_STORE_MODE=cluster）冲突导致的 4 个环境相关失败已定位为环境差异（CI 无 .env 时通过），非代码回归

### 第五轮优化（2026-08-16）：发布就绪 + Milvus 数据库化 + 仓库清理

#### Added
- **Milvus 数据库化**：Milvus Standalone（2.6.6）+ 外部 etcd（3.5.18）+ Attu 网页控制台（:8000）纳入 dev/prod Compose；数据存于 Docker 卷 `<project>_milvus-data`，`VECTOR_STORE_MODE=cluster` 成为默认
- **发布流水线**：`.github/workflows/release.yml` — 打 `v*` tag 自动构建并推送 4 个镜像到 GHCR（`hfusionhub-{java,python,plugin-runner,frontend}`）+ 生成 GitHub Release；版本升至 `1.0.0`
- **一键启动**：`scripts/init-env.{ps1,sh}`（自动生成随机密钥）与 `scripts/setup.{ps1,sh}`（依赖检查 → 初始化 → 基础设施启动 → 健康等待；`-FullStack` 全容器化）
- **演示数据导入**：`POST /api/demo/import`（admin）一键创建"演示知识库"并向量化 3 篇内置文档；前端 Dashboard 新增 SetupChecklist 引导
- **安全文档**：`SECURITY.md`、`CODE_OF_CONDUCT.md`、`NOTICE`、`.github/dependabot.yml`；CI 增加 gitleaks 与 ruff + pip-audit 门禁；Python 镜像改为非 root 用户
- **前端**：`src/utils/errorMessage.ts` 友好错误提示、`src/api/system.ts` AI 健康检查、Dashboard 展示 AI 服务状态

#### Changed
- **文档合并**：`docs/启动重启1.md` 与 `docs/startup-guide.md` 合并为单一双语 `docs/startup-guide.md`；`docs/FEATURE_FLAGS.md` 并入 `docs/ENVIRONMENT.md`；删除已完成的 `docs/MILVUS_MIGRATION.md`；刷新 ROADMAP/ARCHITECTURE/WHITEPAPER/DR_VECTORS/README/AGENTS/CLAUDE 中过时的 Milvus Lite 表述与测试数
- **脚本清理**：删除一次性阶段性脚本 `scripts/archive/*`（git 历史保留）；修复 `backup_milvus.sh`/`restore_milvus.sh` 的卷名推导（`${COMPOSE_PROJECT_NAME:-deploy}_milvus-data`，原硬编码 `hfusionhub_milvus-data` 与实际不符）
- **本地数据清理**：删除根目录 `uploads/` 残留、过期日志、`chunks_store.json.tmp`、构建/测试产物与全部 `__pycache__`；本地 Milvus Lite 文件（`milvus_data*.db`）已废弃删除，向量数据全部在 Milvus 容器卷中

#### Fixed
- Attu 连接：`MILVUS_URL` 指向 `127.0.0.1:19530`（避免浏览器 `localhost` 走 IPv6 导致 "No connection established"）
- Milvus 2.6 不支持嵌入式 etcd：改用独立 etcd 服务（`ETCD_ENDPOINTS=http://etcd:2379`）

### 第四轮优化（2026-08-07）：Bug 修复与设置页完善

#### Fixed
- **成本仪表板**：修复"最近使用记录"表格永远不会渲染数据行的问题——重构为"模型用量明细"表格，正确遍历 `modelBreakdown` 数据并展示每模型 Token/费用/占比
- **Python runtime API**：`_probe_ollama()` 从同步 `httpx.get()` 改为 `async httpx.AsyncClient`，消除 FastAPI event loop 阻塞；同步更新 `_status_payload()` 和路由处理器为 async/await
- **LLM 探活**：`_is_ollama_available()` 在 async 上下文中通过 `ThreadPoolExecutor` 执行 HTTP 探活，避免阻塞 event loop
- **ReactAgent**：`run()` 和 `_handle_operation()` 中 `assistant_text` / `response` 在 ReAct 循环前初始化为 `None`，消除 `max_steps=0` 时 NameError 风险
- **安全护栏页面**：顶部添加"演示模式"横幅，统计卡片标注"模拟数据 · 非实时"，消除用户将模拟数据误认为真实数据的风险
- **PII 脱敏预览**：正则新增 IPv4 地址匹配

#### Added
- **设置页 → AI 供应商状态卡片**：展示所有已发现供应商（DeepSeek/Ollama/Embedding）的名称、状态徽章、模型和连通性指示；LLM/Embedding/向量库三合一摘要行；刷新按钮 + 最近检查时间

### 验收记录（发布门禁复验）
- **Docker Compose config**：`docker/docker-compose.yml`、`deploy/docker-compose.prod.yml`、`deploy/docker-compose.monitoring.yml` 三个 `config -q` 全部通过
- **Frontend 镜像构建**：`docker build --target build -f deploy/Dockerfile.frontend .` 通过；CI `docker-build` job 的 frontend 改用仓库根 context（`context: .`），Java（`java-backend`）、Python（`python-ai`）context 不变且复验通过
- **代码回归**：Java `mvn test` 397 通过 0 失败；Python `pytest -q` 1219 通过 2 跳过（`tests/test_plugin_container.py` 40 通过）；Frontend `vitest` 32 通过 + `vue-tsc && vite build` 成功
- **Staging 演练**：`scripts/staging-rehearsal.ps1 -NoDind` 退出码 3——mysql8/redis7/milvus/java-backend/plugin-runner/python-ai/frontend 全部 healthy；java/python/frontend 端点 200
- **已知预期**：`-NoDind`（无隔离 Docker Engine）下 runner `/health` 返回 503 属预期（fail-closed）；真实隔离 Docker Engine / Kubernetes 环境留到 staging 机器验证

### Added
- **MCP Protocol**: JSON-RPC 2.0 endpoint at `/mcp` with 4 tools (search, calculate, time, web_search)
- **Persistent Memory**: `memory_entry` table (V8), entity facts, summaries, user preferences
- **System Diagnostics**: `/system/ai-health` preflight endpoint
- **Notifications**: `system_notice` + `notice_recipient` tables (V9), unread count, mark-read API
- **Prometheus Metrics**: `/metrics` endpoint with request counts, latency histograms
- **Jupyter Notebook**: `notebooks/rag_evaluation.ipynb` for RAG evaluation
- **Production Docker**: `deploy/docker-compose.prod.yml`, Dockerfiles, Helm chart
- **Frontend shared components**: `EmptyState`, `LoadingSkeleton`, `ErrorState`
- **Java test coverage**: Expanded from 39 to 79 cases across document ownership and lifecycle, vectorization callbacks and durable job state, and authentication boundaries
- **Frontend test coverage**: Expanded from 12 to 32 cases across chat SSE parsing, document upload requests, and login state flows
- **PR Template**: `.github/PULL_REQUEST_TEMPLATE.md`
- **LICENSE**: Apache-2.0
- Comprehensive project documentation (17 files)

### Changed
- **SSE streaming**: Unified to `WebClient`-based `AiClient.streamChat()` with line-buffered parsing
- Frontend chat streaming now uses a tested incremental SSE parser that preserves split frames and flushes a final line without a trailing newline
- `AiClient.chatStream()` deprecated
- Dashboard: removed fake trend percentages, timeline, and static progress values
- RAG page: fixed-height trend chart, scrollable detail panel with `line-clamp-3`
- Admin flags page renamed to "AI 能力配置说明"
- Feature flags: `LLM_ALLOW_MOCK` defaults to `false` (production-safe)
- Java `application.yml`: datasource URL and Redis host configurable via env vars

### Fixed
- Python chunk detail API: correct `get_document_chunks()` return structure parsing
- Streaming evaluation: buffered chunks into `final_answer` for accurate RAG quality metrics
- Document content update: auto-marked `PENDING` to trigger re-index
- Frontend re-parse: added `processingDocs` tracking for completed documents
- Production Docker: shared upload volume, callback URL, healthcheck commands
- Multiple README broken links and API doc path errors
- MCP security: internal token required for `tools/call`, KB-ID header for search

## [0.1.0] — Initial Release

### Core Platform
- Java Spring Boot 3.2.5 backend with MyBatis Plus, Sa-Token JWT auth
- Python FastAPI AI service with DeepSeek API integration
- Vue 3 + TypeScript + Vite 8 frontend with Radix Vue + Tailwind CSS
- MySQL 8.0 + Redis 7 via Docker Compose
- Flyway database migrations (V1–V8)

### Features
- User authentication (JWT via Sa-Token)
- Knowledge base CRUD with per-user permission management
- Document upload (PDF, DOCX, TXT, Markdown) with Apache Tika parsing
- Semantic text chunking (500 chars, 50 overlap)
- Vector embedding + Milvus Lite storage (1024-dim FLOAT_VECTOR, COSINE)
- ReAct Agent with tool calling (search, calculator, time)
- Multi-channel RAG: Vector (Milvus) + BM25 keyword + Reciprocal Rank Fusion
- Intent classification, query decomposition, context compression, self-reflection
- SSE chat streaming with source citation
- Stream cancellation with idempotency (request_id)
- RAG observability dashboard with debug search and trace viewing
- Offline retrieval evaluation against ground-truth cases

### Advanced (Feature-Flagged)
- P6: Second-stage reranking (cross-encoder or lexical)
- P7: Scoped GraphRAG with entity co-occurrence
- P8: Multimodal evidence (OCR, image enrichment)
- P9: Bounded single-agent workflow with timeout/retry
- P10: Evidence-reviewed multi-agent collaboration with deterministic critic

### Engineering
- HMAC-signed callbacks (Python → Java document processing)
- Durable outbox pattern (deletion_task table)
- Idempotent indexing (index_version-based duplicate rejection)
- Document index recovery scheduler (30-min stale threshold)
- 655+ Python tests, 40 Java tests, 12 frontend tests, CI pipeline (GitHub Actions, 4 parallel jobs)
