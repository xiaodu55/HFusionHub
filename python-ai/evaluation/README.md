# HFusionHub 评测系统（Phase 1：评测基线）

双轨评测：**PR/CI 使用离线评测器**做可重复的检索、引用与安全门禁；**Nightly/Staging
使用运行时 Agent 级评测**采集真实 P95 延迟、Token、成本与工具成功率。两条轨道输出
**同一固定格式报告**，可直接与已冻结基线对比差异。

## 目录结构

```
evaluation/
├── kb/                       # 合成业务知识库（已提交，冻结）
│   ├── kb_manifest.json      # KB 版本 + 文档/分块清单（生成后提交）
│   ├── build_kb_manifest.py  # 从 Markdown `## [slug]` 标题生成 manifest
│   └── docs/*.md             # 10 篇中文业务文档（HR/售后/物流/信息安全…）
├── suite/                    # 评测用例集（已提交，冻结）
│   ├── suite_definitions.py  # 用例数据源（7 类，220 条）
│   ├── build_suite.py        # 校验引用 + 生成 cases.jsonl / suite_manifest.json
│   ├── cases.jsonl           # 冻结后的用例（评测实际消费产物）
│   └── suite_manifest.json   # 套件版本、KB 版本、类别数、cases 的 SHA-256
├── baseline/                 # 基线（已提交）
│   └── offline_baseline.json # 离线轨道基线指标
└── reports/                  # 生成报告（gitignore，不提交）
```

## 用例 Schema（cases.jsonl）

每条用例字段：

| 字段 | 说明 |
|------|------|
| `id` | 唯一 ID（nq-/cd-/rf-/pt-/pi-/tl-/ld- 前缀） |
| `category` | `normal`/`cross_document`/`refusal`/`permission`/`injection`/`tool`/`long_document` |
| `query` | 问题 |
| `kb_id` | 合成知识库 ID（101） |
| `expected_chunk_ids` | 期望命中分块（`{doc}#{section}`，由 build_suite 校验存在性） |
| `expected_document_names` | 期望文档标题（运行时按标题匹配真实检索来源） |
| `key_facts` | 该问题对应的关键事实（供评审与运行时答案校验） |
| `refusal` | `none` 或 `required`（无答案/敏感内容必须拒答） |
| `risk_labels` | `permission`/`injection`/`confidentiality` |
| `tool` | tool 类用例期望的工具（`{"name": ...}`） |

## 固定格式报告（两条轨道相同）

`Recall@5、nDCG@10、引用准确率、引用忠实度、拒答正确率、工具成功率、
P95/P50/平均延迟、单任务 Token、单任务成本、错误率、越界检索数`。

- 离线轨道：检索/引用指标为确定性数值；拒答正确率、工具成功率、延迟、Token、成本
  属答案层/运行时属性，报告为 `N/A`（由运行时轨道填充）。
- 运行时轨道：全部指标真实测量。引用/召回按**文档标题**匹配真实检索来源，且每条来源携带
  **`knowledge_base_id`**（可区分同名文档是否来自其它知识库）；引用忠实度要求答案文本
  **确实陈述**了 key_facts **且**该事实得到被引用文档正文支撑（双重判定，确定性）；拒答
  正确率依据回答文本的关键词与 `status` 启发式判定；成本由 `token_usage` 与可配置单价推算。

## 运行时契约测试

`tests/test_eval_runtime_contract.py`（35 项）以 mock 覆盖运行时轨道全部关键契约：
SHA-256 冻结校验（匹配/篡改/缺失 pin）、跨 KB 越界来源检测（含同名跨 KB 泄露）、基线
suite-SHA 绑定、请求异常处理、拒答检测（拒答文本 / `insufficient_evidence` / 泄露）、工具
成功/失败/未调用、成本计算、由 key_facts 支撑且校验回答内容的引用忠实度，以及门禁失败
列表与退出码语义。

## 修改知识库或用例的流程

1. 编辑 `kb/docs/*.md`，保持 `## [slug]` 分块标题；更新 KB 版本。
2. 运行 `python evaluation/kb/build_kb_manifest.py` 重新生成并提交 `kb_manifest.json`。
3. 编辑 `evaluation/suite/suite_definitions.py` 增删用例。
4. 运行 `python evaluation/suite/build_suite.py`：校验所有分块引用、类别覆盖，
   输出 `cases.jsonl` + `suite_manifest.json`（含 SHA-256），一起提交。
5. 重新运行离线评测并 `--update-baseline` 更新基线。

任何对 `cases.jsonl` 的无意改动都会被 `suite_manifest.cases_sha256` 捕获，并且两个评测
脚本在运行前都会执行 `verify_suite_integrity` 做 SHA-256 校验：**篡改用例后脚本直接
退出（exit 1）并提示差异**，不会带着旧哈希继续运行。

## 离线评测（PR 门禁，免模型免数据库）

```bash
python scripts/eval_offline.py
# 结果: 无门禁失败则 exit 0；低于阈值或（--fail-on-regression）检出回归则 exit 1
python scripts/eval_offline.py --update-baseline          # 记录/更新基线
python scripts/eval_offline.py --minimum-recall 0.90      # 自定义阈值
```

门禁默认值：Recall@5≥0.85、nDCG@10≥0.75、引用准确率≥0.85、引用忠实度≥0.30、
越界检索=0。离线检索由 `app/core/rag/synthetic_index.py` 的确定性 BM25 完成，
跨机器/CI 结果一致，且只检索 kb_id=101。

## 运行时评测（Nightly/Staging）

要求合成 KB 已以 kb_id=101 索引到目标环境，且文档标题与 `evaluation/kb` 一致。
KB 播种使用 `scripts/seed_eval_kb.py`：受控文档（`security-policy` /
`employee-privacy-policy` / `permissions-matrix` / `it-support-runbook`）以
`visibility=confidential` 上传（主体级 ACL，V85），其余为 `general`。

**双主体执行**：`permission` 类用例以最低权限主体（`X-User-Clearance: general`）
执行，其余用例以 admin（全 clearance）执行——同一 section 的"必答/必拒"矛盾由
主体区分化解（如 cd-025 管理员可引用安全文档应答，pt-007 低权限主体因受控文档
被 ACL 检索过滤而正确拒答）。用例数据保持冻结（cases.jsonl / baseline SHA 不变），
主体策略由 `eval_runtime.subject_for_case` 在运行时轨道落地。

```bash
python scripts/eval_runtime.py --token <internal-token> \
    --base-url http://localhost:9000 \
    --concurrency 4 \
    --prompt-price-per-1m 0.10 --completion-price-per-1m 0.40 \
    --update-baseline
```

运行时轨道的保证与门禁：

- 运行前同样执行 `verify_suite_integrity`（SHA-256 冻结校验）。
- **跨 KB 泄露检测**：凡引用来源携带权威 `knowledge_base_id` 且不等于当前用例
  `kb_id`（101）即计为越界——即使该来源的文档标题与合成 KB 内某文档**同名**也会被识别；
  未携带 kb_id 的来源退回标题检查（标题缺失或不在合成 KB 文档集内计越界）。
  `scope_violations` 受 `--maximum-scope-violations`（默认 0）门禁约束。
- **错误率门禁**：`--maximum-error-rate`（默认 0.02），大量请求失败时 exit 1。
- **引用忠实度＝答案断言 × 引用支撑**：对每条 `key_facts`，按确定性 CJK bigram 分词，
  要求该事实（a）确实出现在回答文本中（`--answer-threshold` 默认 0.5）**且**（b）出现在
  所引用文档的正文中（`--support-threshold` 默认 0.5），两者同时满足才算该事实忠实。
  即使回答引用正确文档、但内容完全编造或答非所问（未陈述该事实），忠实度仍为 0。
  仅比较「返回文档标题属于预期标题」不构成忠实度。
- **受限并发**：`--concurrency`（默认 4）通过 `asyncio.Semaphore` 限制并发请求数。
- 拒答正确率依据回答文本关键词与 `status` 启发式判定；工具成功率依据
  `tool_calls_count`/`failed_tool`/`status`；成本由 `token_usage` 与可配置单价推算。
- 引用/召回类指标按**文档标题**匹配；拒答类（`refusal == "required"`）用例从引用
  聚合中剔除（正确拒答本身不含引用），其行为由拒答正确率衡量。

## 基线对比与回归检测

`eval_baseline.py::diff_against_baseline` 对基线与本次逐项比较：

- 质量类指标（Recall/nDCG/引用/拒答/工具）：绝对下降 > 0.03 视为回归。
- 延迟：相对上升 > 20% 视为回归。
- Token/成本：相对上升 > 15% 视为回归。
- 越界检索/错误率：上升即回归。

缺失一侧值（如离线轨道的 `N/A`）不参与比较。无基线时报告提示首次运行可写入基线。

**基线绑定冻结套件**：基线文件记录录制时的 `cases_sha256`。两脚本在对比前会校验该值与
当前 `suite_manifest.cases_sha256` 一致；不一致或未钉入哈希的旧基线会**拒绝对比**并提示
（exit 1），避免「更新用例后仍拿旧基线做无效对比」。`--update-baseline` 是显式再冻结操作，
会绕过该校验并写入新哈希——修改 KB/用例后必须重新执行它以再冻结基线。

## CI 集成（Phase 2）

- **PR 门禁**：`.github/workflows/ci.yml` 的 `eval-offline` job 在每次 push/PR 到 main 时执行
  `python scripts/eval_offline.py --fail-on-regression`（SHA-256 冻结校验 → 门禁 → 基线回归
  判定），失败即构建失败阻断合并；报告上传为 `eval-offline-report` artifact。
- **Nightly 运行时**：`.github/workflows/eval-nightly.yml` 每日 02:00 UTC（可 `workflow_dispatch`
  手动触发）对 live 服务跑运行时轨道，需要仓库 Secret `EVAL_INTERNAL_TOKEN` 与 Variable
  `EVAL_BASE_URL`，且目标环境已以 kb_id=101 索引合成 KB。
- **基线再冻结**：离线基线修改用例后本地 `--update-baseline` 提交；运行时基线经
  `actions/cache` 持久化，手动触发时勾选 `update_baseline`。

详见 `docs/CI_GATES.md`。

## 分阶段设计说明

### P7 GraphRAG guardrails

`RAG_GRAPH_ENABLED` 默认 `false`。图索引在分块入库后构建，存
`knowledge_base_id`、`document_id`、`chunk_id` 证据，使用确定性共现抽取，
可复现且不增加入库 LLM 调用。启用基准评测时先重建该 KB 的索引，再与现有
指标和 `graph_hit_rate` 对比；图候选仅当源分块仍存在时才合法，缺失/过期数据
被丢弃而非回退全局图。

### P8 multimodal evidence guardrails

P8 使用普通 scoped 分块索引而非全局图像索引。原生 DOCX/Markdown 表格与可选 OCR
输出作为带 `kind`、图像哈希、DOCX 部件或 PDF 页元数据的常规分块存储，保持现有
引用、KB 作用域、删除与调试追踪保证。默认禁用，基准评测时启用相关标志并重建索引，
将 `multimodal_hit_rate` 与现有 Recall@k/MRR 对比后再决定是否保留。
