# 招投标合规与责任边界（P1-8）

> 招投标智能助手涉及**企业机密标书内容**与**可能带来经济/法律后果的准确性责任**。本文档定义产品在
> 机密性、准确性、审计三方面的合规基线，以及必须向客户明示的责任边界。配套代码见
> `java-backend/…/bid/`、`python-ai/app/core/bid/`、`hfusionhub-frontend/src/pages/bid/`。

## 1. 责任边界与免责（必须明示）

AI 生成内容不构成法律意见或专业投标咨询，标书发出前的**最终审核与法律责任由企业用户承担**。
产品在以下位置内置免责提示（后端渲染 + 前端 Banner）：

| 位置 | 提示内容 |
|---|---|
| 需求确认页 `Requirements.vue` | 需人工复核低置信（manual_review）需求条目后进入撰写 |
| 撰写工作台 `DraftEditor.vue` | 标书由 AI 生成可能出错，须逐节审批并核对引用来源 |
| 自检报告 `CheckReport.vue` | critical 级风险必须人工确认后才能放行 |

私有部署客户可在部署协议中增加 SLA 与免责条款（见第 5 节）。

## 2. 机密性（Confidentiality）

| 控制点 | 现状 | 位置 |
|---|---|---|
| **租户强制隔离** | 所有 bid 表（V61–V68）均含 `tenant_id`，由 MyBatis Plus `TenantLineInnerInterceptor` 全自动注入过滤，新表必须含 `tenant_id`（CI `scripts/static-checks.py` 校验） | `MybatisPlusConfig` |
| **所有者校验** | 撰写/自检/审批/清单接口对投标项目执行 `requireOwnedProject`（创建者校验），非本人一律 403 | `BidWriteServiceImpl` / `BidCheckServiceImpl` |
| **SSE 仅同租户** | 流式撰写在请求线程捕获 `TenantContext.requireTenantId()`，所有 Reactor 回调落库均以 `TenantContext.runAs(streamTenantId, …)` 恢复租户上下文，杜绝跨租户写库 | `BidWriteServiceImpl.writeStream` |
| **知识库边界** | 撰写检索范围 = 项目绑定的招标文件库 + **项目创建者本人**的资质库/历史标书库（`loadKnowledgeBaseIds` 按 `userId` + `category` + `status=normal` 过滤），绝不跨用户检索 | `BidWriteServiceImpl` |
| **存储** | 投标项目/要素/需求/草稿/自检报告全部落 MySQL（tenant_id 行级隔离）；演示文档落本地 uploads 目录 | — |
| **私有部署** | 单租户部署可彻底关闭多租户暴露面（见第 5 节）；平台插件制品存于 MinIO（object key 命名空间化，当前不承载投标正文内容） | `MinioArtifactStore` |

> 平台级 MinIO 桶按租户隔离属 P2-8 私有部署加固项；当前插件制品不含投标内容，投标正文一律走
> MySQL（tenant_id）与本地文件。

## 3. 准确性（Accuracy）—— 强制人工审批兜底

### 3.1 撰写：每节强制审批

`BidDraft` 状态机 `drafting → approved/rejected`，**任何一节未审批通过不得进入自检/导出**：

- 前端 `DraftEditor.vue`：每节卡片提供「通过 / 驳回」，并有「全部通过」便捷入口——但**每次审批动作都记录
  `approved_by`**（审批人 userId），不会因批量入口跳过审计痕迹。
- 后端 `updateDraftStatus` 仅接受 `approved`/`rejected`，审批时写 `approved_by`。
- 重写幂等：按 `project_id + section_key` 版本递增（`version +1`），保留历史版本供追溯。

### 3.2 自检：critical 级强制人工确认

`BidCheckReport` 严重度 `critical / warning / info`，状态机 `open → confirmed / fixed`：

- **critical 级风险（废标/保证金/截止时间/实质性响应等）必须人工「确认风险」或「已修复」**，
  前端对含未确认 critical 的报告给出放行阻断提示（“critical 级风险必须人工确认后才能放行”）。
- 每个 finding 附 `evidence`（引用章节）+ `suggested_fix`（修复建议），人工确认基于证据而非模型自述。

### 3.3 需求清单：低置信强制人工复核

解读产出的需求 `satisfied_status = manual_review`（置信度 <0.6）在需求确认页以琥珀色标记
「需人工复核」，全部确认后才放行进入撰写（`Requirements.vue`）。

### 3.4 引用追溯（证据链）

- 解读：`tender_element` / `bid_requirement` 每行带 `evidence_chunk_ids`（指向 `document_chunk`）。
- 撰写：生成正文内嵌 `[N]` 引用索引 → `evidence_chunk_ids` 解析 → 前端渲染为可点选引用来源。
- 自检：`bid_check_report` 的 `evidence` 定位到具体章节。
- 检索门禁：多 KB 检索经 `BoundedMultiAgentWorkflow._validate_sources` 引用门禁校验，未命中证据的
  断言会被拒（保障“引用内容必须来自检索库”）。

## 4. 审计与追溯

| 维度 | 实现 |
|---|---|
| 审批人 | `bid_draft.approved_by`（每节）+ 审批时间戳落库 |
| 版本 | `bid_draft.version` 递增，历史版本保留 |
| 状态机 | `bid_project`: interpreting→requirements→drafting→checking→submitted/archived，每次推进可审计 |
| 计量 | 撰写字符/自检报告走 V35 幂等账本（`reserve`+`settle`），超额抛 `QUOTA_EXCEEDED` 回滚 |
| 多 Agent 链路 | 解读/撰写/自检全程走 `agent_task/run/step`，步骤级可观测 |

## 5. 可选私有部署（增强隔离）

对机密性要求更高的客户（央国企、总包），支持单租户私有部署形态：

- 单租户模式无多租户暴露面，DB/对象存储/模型网关全链路仅在客户内网。
- 敏感标书**禁止外部 LLM-as-judge**（P2-8 上线 `model_gateway` 强制 + 审计），全部推理走
  `MODEL_GATEWAY` 内网模型。
- 部署见 `deploy/helm` + `deploy/docker-compose.prod.yml`。

## 6. 验收清单（P1 合规）

- [x] 撰写每节审批记录 `approved_by`（`BidWriteServiceImplTest.updateDraftStatusApprovesAndRecordsApprover`）
- [x] 非本人操作投标项目一律 403（`writeRejectsProjectNotOwned` 等）
- [x] 流式撰写 SSE 回调以请求租户上下文落库（`TenantContext.runAs`）
- [x] 撰写检索范围不含跨用户知识库（`writeIncludesQualificationAndHistoryKbs` 仅并入本人资质/历史库）
- [x] 前端：逐节审批 + critical 人工确认 + 三处免责 Banner + 引用来源展示
- [ ] 冒烟回归 `scripts/smoke-bid.ps1`（随全栈启动验收执行）
