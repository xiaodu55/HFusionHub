# 冗余功能与死代码清理清单

> 2026-08-29 前端主题统一改造时盘点生成。本次**只登记不删除**，逐项评估后处理。
> 删除前先确认测试基线（Java 563 · Python 1407 · 前端 49）仍全绿。

## A. 已冻结的实验功能（代码+测试仍在维护，文档已宣布不再投入）

来源：[ENVIRONMENT.md](ENVIRONMENT.md) 冻结区块。

| 功能 | Flag | 代码位置 | 建议 |
| --- | --- | --- | --- |
| P7 ScopedGraphRAG | `RAG_GRAPH_ENABLED=false` | `python-ai/app/core/rag/scoped_graph.py`、`knowledge_graph.py` 及对应测试 | 确认无数据依赖后整体移除（含前端「检索能力」文案里的图谱通道描述） |
| P8 多模态 OCR | `RAG_MULTIMODAL_ENABLED=false` | `python-ai/app/core/rag/multimodal_rag.py` | 移除；等 vision-LLM 路线重启时按新架构重写 |
| cross_encoder 重排 | `RAG_RERANKER_MODE=cross_encoder` | 重排器分支 | 若离线基准长期无法证明收益，删除该分支并固化 lexical |

注意：`/rag` 页与 admin/Flags 的「冻结」标注 UI 依赖这些 flag 的展示逻辑，删除代码时需同步。

## B. 死代码（低风险，可直接删）

- `java-backend/.../client/AiClient.java:611-625` — `chatStream()` 标 `@Deprecated` 且注释明确"仓库内已无调用方"，每次调用打 warn。删除方法与流量日志。
- `java-backend/.../service/impl/VectorizationServiceImpl.java:1084-1102` — 两个 `@Deprecated` 私有方法 `toChunkResponse()` / `fromJson()`，已被 `toChunkDTO` / `fromJsonList` / `fromJsonMap` 取代，无人可调。
- `python-ai/app/core/agent/agent.py:46` — `agent_status` 字段注释 "deprecated — prefer `status`"；确认序列化输出无消费方后移除。
- `OLLAMA_MODEL` 环境变量 — 已废弃用于 embedding（`python-ai/app/utils/config.py:254-265` 保留迁移告警）；观察一个发布周期后删除告警函数。

## C. 新旧双轨实现（待稳定后收敛）

- **LLM 调用链**：新 ModelGateway 与旧 `get_llm()` 并存，`MODEL_GATEWAY_STREAM_ENABLED` 切换。ModelGateway 稳定运行一个周期后删除旧链及其 fallback 分支。
- **前端状态徽章**：`src/utils/badge.ts`（`levelBadgeClass`）与 `src/utils/format.ts`（`getStatusBadge`）职责重叠，合并到 badge.ts。
- **前端日期格式化**：`MainLayout.vue` 内保留了一份本地 `formatDateTime`（截断式），与 `src/utils/date.ts` 的 `formatDateTime` 并存；统一引用 utils 版本。

## D. 仓库卫生

- 根目录日志文件（约 170KB）：`debug.log`、`frontend.log`、`java-backend.log`、`python-ai.log` — 加入 `.gitignore` 并 `git rm --cached`。
- `notebooks/rag_evaluation.ipynb` — 临时评测产物，归档到 `python-ai/scripts/` 或移出仓库。
- `python-ai/app/core/rag/eval_baseline.py`（641 行）— 运行时零引用，仅被 `python-ai/scripts/eval_offline.py` 与测试使用；移到 scripts 侧或标注为评测专用模块。

## E. 半成品

- **统一缓存体系**（[OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md) 1.9，唯一未完成的 P0/P1/P2 项）：`FeatureFlagServiceImpl` 每次查库、`UsageLedger` 实时聚合，无 `@Cacheable`。
