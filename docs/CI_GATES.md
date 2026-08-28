# CI 门禁（Phase 2）

> 把 Phase 1 的双轨评测接入 CI：**每个 push/PR 到 main 都跑离线评测门禁**，门禁失败或基线回归即构建失败（阻断合并）；**Nightly 定时跑运行时评测**测量答案层指标。main 已启用 GitHub 分支保护（详见下文「流程强制」），叠加「工作流 + 文档」的流程约定：合并前必须全部 job 通过。

## 门禁架构

| 触发 | 工作流 | 评测 | 是否阻断合并 |
|------|--------|------|--------------|
| push/PR 到 main | `.github/workflows/ci.yml` → `eval-offline` job | 离线轨道（免模型免数据库，确定性） | 是（构建失败） |
| 每日 02:00 UTC + 手动 | `.github/workflows/eval-nightly.yml` | 运行时轨道（真实服务） | 否（Nightly 报告） |

两个评测共享同一固定格式报告与门禁逻辑（`python-ai/app/core/rag/eval_baseline.py`），见 `python-ai/evaluation/README.md`。

## 离线门禁（PR 阻断）

`eval-offline` job 在每次 push/PR 到 main 时执行：

1. **SHA-256 冻结校验**：`verify_suite_integrity` 校验 `cases.jsonl` 与 `suite_manifest.json.cases_sha256` 一致，篡改用例直接失败。
2. **评测门禁**：`python scripts/eval_offline.py --fail-on-regression --minimum-citation-recall 0.85 --minimum-citation-f1 0.70`，默认阈值 Recall@5≥0.85、nDCG@10≥0.75、引用准确率≥0.85、引用忠实度（精确率）≥0.30、引用召回率≥0.85（主套件显式传入）、引用 F1≥0.70（主套件显式传入）、越界检索=0。引用指标为精确率/召回率双报口径，引用窗口按相关性自适应（见 [ADR-006](adr/ADR-006-faithfulness-metric-recalibration.md)）。
3. **基线回归**：`--fail-on-regression` 使基线对比的回归项同样导致失败（而非仅报告）。
4. **产物上传**：`python-ai/evaluation/reports/*`（JSON + Markdown）作为 `eval-offline-report` artifact 上传。上传步骤带 `if: always()`——**门禁失败时报告仍在**，便于排查，而不是在最需要时被跳过。

离线轨道完全在 CI 内部完成，不需要任何外部服务或密钥。基线文件 `evaluation/baseline/offline_baseline.json` 已提交，且绑定 `cases_sha256`——若修改了用例/知识库但未重新冻结基线，门禁会因基线校验失败而报错，不会做无效对比。

### 修改评测内容后如何再冻结基线

1. 修改 `evaluation/kb/docs/*.md` 并重新生成 `kb_manifest.json`；修改 `suite_definitions.py` 并重新运行 `build_suite.py`。
2. 本地执行 `python scripts/eval_offline.py --update-baseline`，把带新 `suite_sha256` 的基线一起提交。
3. 推入 PR，`eval-offline` job 应通过且与基线 diff 全 0。

## Nightly 运行时评测

`eval-nightly.yml` 每日定时（也可 `workflow_dispatch` 手动触发）对**已部署的 live 服务**跑运行时轨道，测量延迟、Token、成本、拒答正确率、工具成功率等答案层指标，并执行运行时门禁（含错误率≤0.02、越界=0）。

### 前置条件

- 目标环境必须以 kb_id=101 索引了合成 KB（文档标题与 `python-ai/evaluation/kb` 一致）。
- 配置仓库级配置：
  - **Secret**：`EVAL_INTERNAL_TOKEN`（Python AI 服务的 `X-Internal-Token`）——**唯一**的令牌来源
  - **Variable**：`EVAL_BASE_URL`（如 `https://staging.example.com:9000`）
- 未配置 `EVAL_INTERNAL_TOKEN`/`EVAL_BASE_URL` 时，nightly 直接以 `::error::` 报错退出（第十五轮对账：eval-nightly.yml 现为硬性要求，不再是步骤级跳过）。
- **防令牌泄露**：`workflow_dispatch` 只允许 `update_baseline` 一个布尔输入，**没有 base_url/token 任何字符串输入**——目标地址唯一来自受控的 `vars.EVAL_BASE_URL`，令牌不会因触发负载被重定向到任意地址。
- 步骤级 guard 一律通过注入的 **`env.EVAL_INTERNAL_TOKEN`/`env.EVAL_BASE_URL`** 判断，不在 `if:` 中直接引用 `secrets.*`（GitHub 的推荐做法，secret 先映射进 env 再用）。

### 基线持久化

> **口径注记（2026-09-09，R16-1 重冻结）**：runtime 基线以
> `2026-09-09T03:06:39Z` 全量跑批重冻结（220 用例，真机栈）。与
> 2026-09-06 旧冻结相比：拒答正确率 0.625→0.9625（旧值为 ACL 落地前
> 口径，permission 类 0/30 被答出；现 30/30 拒答 + injection/refusal
> 基本满分）；Recall/nDCG/引用指标 0.85→0.55 量级下移——其中
> permission 类 30 例按 ACL 语义拒答后不再贡献检索召回（口径变化），
> 残余差异伴随单任务 token 1582→774（答案变短），疑为模型侧行为漂移，
> 与本轮代码改动无关（检索路径仅 embedding 缓存与空内容加固；reranker
> lexical/disabled 对照实验无差异）。runtime 轨为非阻断监测轨，残余
> 差异归因挂 eval-nightly 持续监测（对齐 ADR-006 门阈值校准红线）。
> **归因已闭环（2026-09-09，`python-ai/scripts/eval_retrieval_live.py`
> 纯检索直测）**：绕过答案层的纯检索 OVERALL recall@5 = **0.830**
> （normal 0.986 / cross_document 0.983 / long_document 1.0 / tool 0.9 /
> injection 0.84 / refusal 1.0 / permission 0——ACL 正确拦截；permission
> 按 admin 老口径 = 1.0），与旧基线检索水平（0.856，其中 permission 老口径
> 满贡献）一致——**检索栈健康**。runtime 0.550 与纯检索 0.830 的差值在
> **答案层丢 sources**（与单任务 token 1582→774 同源的模型侧行为漂移）。
> 另：本机 pymilvus 曾漂移至 2.4.15（锁定 3.0.0），导致 milvus-lite
> 写读 content 为 null——已按锁恢复，4 个既有失败测试转绿。

运行时基线无法入库（依赖具体环境的真实指标），用**可版本化的 cache 键**在 Nightly 之间持久化，避免固定键命中后不可覆盖的问题：

- **restore**：`actions/cache/restore`，主键 `runtime-baseline-<cases 哈希>-<run_id>`（每次运行唯一），`restore-keys` 用前缀 `runtime-baseline-<cases 哈希>-` 恢复**最近一次**成功保存的版本。
- **save**：仅当手动触发勾选 `update_baseline` 且本次运行**全部通过**（`success()`）时执行 `actions/cache/save`，键同样带 `run_id`——新基线写入新键，后续 restore 拿到的是最新版本，不会被旧固定键覆盖。定时运行只对比、绝不改写基线。
- 套件（`cases.jsonl`）变化后前缀哈希改变，旧基线自然失效，需手动再冻结。
- cache 可能被平台清理：此时无基线可比，报告提示「无基线可对比」，门禁仍按绝对阈值执行，不影响合并判定。

### 报告上传

评测失败（exit 1）时报告文件已落盘，Nightly 的 `eval-runtime-report` 上传步骤同样带 `if: always()`，失败也能下载到报告。

## 流程强制（GitHub + 文档）

main 已启用 branch protection（规则通过 GitHub API 创建）：

- **必需状态检查**：`eval-offline` — 未通过则 PR/直接推送均无法合并。
- **管理员不可绕过**：`enforce_admins: true`，包括仓库所有者在内的管理员同样必须通过 CI。
- **阻止 force push 和删除**：不允许通过 force push 或分支删除绕过规则。

在此基础上的补充约定：

- Nightly 运行时评测失败时在对应 action 中查看 `eval-runtime-report` artifact 定位问题。
- 离线门禁失败时必须修复或按流程再冻结基线，不得带着失败合并。

## 相关文件

- `.github/workflows/ci.yml` — push/PR 主 CI（含 `eval-offline` 门禁 job）
- `.github/workflows/eval-nightly.yml` — 运行时 Nightly 评测
- `python-ai/scripts/eval_offline.py`、`python-ai/scripts/eval_runtime.py` — 双轨评测入口
- `python-ai/app/core/rag/eval_baseline.py` — 共享报告 / 门禁 / 基线逻辑
- `python-ai/evaluation/README.md` — 评测系统设计、用例、双轨与基线流程
