# 冗余功能与死代码清理清单

> 2026-08-29 前端主题统一改造时盘点生成。本次**只登记不删除**，逐项评估后处理。
> 删除前先确认测试基线（Java 572 · Python 1258 · 前端 49）仍全绿。

## A. 冻结的实验功能（治理决策：保留代码，待后续补强）

来源：[ENVIRONMENT.md](ENVIRONMENT.md) 冻结区块。

| 功能 | Flag | 代码位置 | 治理决策（2026-08-29） |
| --- | --- | --- | --- |
| ~~P7 ScopedGraphRAG~~ | `RAG_GRAPH_ENABLED` | ~~scoped_graph.py / knowledge_graph.py~~ | ✅ **已移除（2026-08-29）**：代码、测试、`/api/rag/graph/status`、GraphChannel、配置项、前端「图谱检索」文案全部删除；检索通道收敛为向量+关键词 |
| ~~P8 多模态 OCR~~ | `RAG_MULTIMODAL_*` | ~~multimodal_rag.py~~ | ✅ **vision-LLM 路线已实现（2026-08-29）**：Ollama 视觉模型（qwen2.5vl）图片描述引擎 + Tesseract 兜底，产普通文本块进既有管道；未接线的 CLIP 实验模块 multimodal_rag.py（1367 行）及其 951 行测试已删除 |
| ~~cross_encoder 重排~~ | `RAG_RERANKER_MODE` | 重排器分支（P6） | ✅ **基准已解锁（2026-08-29）**：三臂 A/B（`scripts/eval_reranker.py`）实测 recall@10 最高 0.846，加载失败自动回落且失败实例不缓存；默认仍 lexical，召回优先场景可启用 |

注意：`/rag` 页与 admin/Flags 的「冻结」标注 UI 依赖这些 flag 的展示逻辑，若未来删除 GraphRAG 代码需同步。

## B. 死代码

- [x] ~~`AiClient.chatStream()`~~ — 已删除（含 `AiClientTest` 对应断言，2026-08-29）。
- [x] ~~`VectorizationServiceImpl` 两个 `@Deprecated` 私有方法 `toChunkResponse()` / `fromJson()`~~ — 已删除（2026-08-29）。
- [x] ~~`agent.py` 的 `agent_status` 字段~~ — 已退役（2026-08-29）：写入点全部改为 `status`，2 处直接断言的测试迁移完成；评测 API 的 `agent_call.agent_status` 为独立局部变量，不受影响。

## C. 新旧双轨实现（待稳定后收敛）

- [x] ~~LLM 调用链双轨~~ — **已收敛（2026-08-29）**：`MODEL_GATEWAY_STREAM_ENABLED` 与 `_build_providers`/`_legacy_chat`/`_legacy_stream`/`FailoverLLM` 全部删除，`get_llm()` 单轨返回 GatewayLLM（不可路由时明确报错）；`DeepSeekLLM`/`OllamaLLM` 保留（响应缓存与用户级自定义供应商仍用）。
- [x] ~~前端状态徽章双份~~ — **已收敛（2026-08-30 核实）**：`getStatusBadge` 仅存于 `src/utils/badge.ts`（`format.ts` 现仅含 `formatFileSize`/`getKnowledgeBaseStatusText` 格式化函数），前端主题统一重构时已完成合并，无残留。
- [x] ~~前端日期格式化重复~~ — `MainLayout.vue` 本地 `formatDateTime` 已删除，统一引用 `src/utils/date.ts`（2026-08-29）。

## D. 仓库卫生

- [x] ~~根目录日志文件~~（`debug.log`、`frontend.log`、`java-backend.log`、`python-ai.log`）— 已删除；`.gitignore` 的 `*.log` 规则此前已存在（2026-08-29）。
- [x] ~~`notebooks/rag_evaluation.ipynb`~~ — 已 `git mv` 至 `python-ai/scripts/notebooks/`（2026-08-29）。
- [x] ~~`python-ai/app/core/rag/eval_baseline.py`~~ — 已 `git mv` 至 `python-ai/scripts/eval_baseline.py`，引用（4 脚本 + 2 测试文件）已更新（2026-08-29）。

## E. 半成品

- [x] ~~统一缓存体系（OPTIMIZATION_PLAN.md 1.9）~~ — **已结清（2026-08-29 复查）**：flag 求值缓存已在 R15-16 落地（15s TTL + 写失效，`FeatureFlagServiceImpl` 头部）；`UsageLedger` 为预占/结算型账本（原子 SQL 保证配额正确性），加缓存反而有害，维持实时。
