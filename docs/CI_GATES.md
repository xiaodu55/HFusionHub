# CI 门禁（Phase 2）

> 把 Phase 1 的双轨评测接入 CI：**每个 push/PR 到 main 都跑离线评测门禁**，门禁失败或基线回归即构建失败（阻断合并）；**Nightly 定时跑运行时评测**测量答案层指标。main 已启用 GitHub 分支保护（详见下文「流程强制」），叠加「工作流 + 文档」的流程约定：合并前必须全部 job 通过。

## 门禁架构

| 触发 | 工作流 | 评测 | 是否阻断合并 |
|------|--------|------|--------------|
| push/PR 到 main | `.github/workflows/ci.yml` → `eval-offline` job | 离线轨道（免模型免数据库，确定性） | 是（构建失败） |
| 每日 02:00 UTC + 手动 | `.github/workflows/eval-nightly.yml` | 运行时轨道（真实服务） | 否（Nightly 报告） |

两个评测共享同一固定格式报告与门禁逻辑（`python-ai/scripts/eval_baseline.py`），见 `python-ai/evaluation/README.md`。

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

### 冻结摘要按内容算，不按行尾算（第九十二批）

`cases.jsonl` 是提交进仓库的数据文件，它的**字节**取决于两件事：当年在哪个平台跑 `build_suite.py`
（`write_text` 默认把 `\n` 翻译成本地换行），以及检出它的那个人 `core.autocrlf` 是什么。第九十二批之前，
钉进 `suite_manifest.json` 的是 Windows 上那份 CRLF 字节的 SHA-256，而 git blob 与 Linux runner 检出的是
同一内容的 LF 字节 ⇒ 摘要必然不同：**四个 `Verify frozen suite integrity` 步骤在 CI 恒红、在本地恒绿**，
它实际测的是这台机器的换行风格，不是"用例被改过没有"。

契约现在是三层，缺一不可：

| 层 | 位置 | 作用 |
|----|------|------|
| 摘要规则只写一遍 | `eval_baseline.suite_content_digest()`（CRLF→LF 后取 SHA-256），`verify_suite_integrity` 与 `eval_retrieval_live.compute_cases_sha` 都走它 | 任何检出形态读出同一个内容摘要 |
| 生成侧不再翻译换行 | 四份 `build_suite.py` 的 `emit_cases(..., newline="\n")` | 重跑冻结产出的字节与平台无关 |
| 检出侧钉成 LF | `.gitattributes` 的 `*.jsonl text eol=lf` | 工作副本不会插回 CR |

判据在 `python-ai/tests/test_eval_suite_eol_binding.py`（25 例）：钉住的 `cases_sha256` 与六份基线的
`suite_sha256` 必须等于行尾无关摘要；把真数据摆成 LF/CRLF 两种形态都要过 `verify_suite_integrity`；
**内容变了仍必须红**（规范化行尾不等于放弃篡改检测）；`emit_cases` 的输出不得含 CR。

两条后果要预先知道：

- 重跑 `build_suite.py` 只做再绑定，不动用例内容。第九十二批实测：四份 `cases.jsonl` 重建后与
  `HEAD` 的 blob **逐字节相同**，`git add` 后暂存区零变更，变的只有 manifest 里那一行哈希。
- 运行时轨的 cache 键带 cases 哈希（`runtime-baseline-<cases 哈希>-…`）。哈希换了前缀 ⇒ 下一次
  Nightly ** restore 落空、无基线可比**，需要在真机跑通后勾选 `update_baseline` 重冻结一次；
  仓内 `runtime_baseline.json` 与 `retrieval_baseline.json` 本批只把绑定字段从 `b02b9dd3…` 换成
  `15b0ea64…`，**指标仍是 2026-09-09 真机跑批的值**（用例内容未变，这是再绑定不是重测）。

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

## 非评测门禁：CI 自己的三处自伤（第九十批、第九十三批）

上面那张表之外的 job（`docker-compose-validate`、`python-container`、`java`、`frontend`）不评测量，
但同样会阻断合并。本节记录三条判据——它们的共同点是**红的是 CI 自己，不是产品**。

### 1. `docker-compose-validate` 的变量供给必须与 compose 文件成对

三个 compose 文件用 `${VAR:?…}` 硬要求密钥，`docker compose config -q` 在**第一个**缺失变量处即报错，
于是那一步从未真正渲染过整张图。供给集必须**从文件本身派生**，不能手抄：

| 校验的文件 | 文件里 `${VAR:?}` 要求 | 修复前 CI 供给 | 缺 |
|---|---|---|---|
| `docker/docker-compose.yml` | ADMIN_PASSWORD, CALLBACK_SECRET, MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD, PLUGIN_RUNNER_TOKEN, PYTHON_AI_INTERNAL_TOKEN | 只有 MYSQL×2 + REDIS | 4 |
| `deploy/docker-compose.prod.yml` | 11 个 | 11 个 | — |
| `deploy/docker-compose.monitoring.yml` | MYSQL_ROOT_PASSWORD | 无 | 1 |

判据：`python-ai/tests/test_ci_workflow_gates.py::TestComposeValidateEnvPairing` 用
`REQUIRED_VAR` 正则从 compose 原文抽必填集，与 workflow 里那一步的 `env:` 键集合做双向差集
（缺变量判红，喂了文件不引用的变量也判红——后者是假配置面的兄弟形态）。

**本地复现红侧的钥匙**：开发机上 `docker/.env`、`deploy/.env` 存在，compose 会自动按目录加载它，
所以直接跑 `config -q` 永远是绿的——缺陷只在"没有 `.env` 的 CI"发作。用空 env-file 顶掉这次自动加载：

```bash
: > /tmp/empty.env
MYSQL_ROOT_PASSWORD=ci-test-root MYSQL_PASSWORD=ci-test-pass REDIS_PASSWORD=ci-test-redis \
  docker compose --env-file /tmp/empty.env -f docker/docker-compose.yml config -q
# 修复前：required variable ADMIN_PASSWORD is missing a value（exit 1）
# 补齐全 6 个变量后：exit 0
```

CI 里供给的一律是 `ci-test-*` 形态的良性占位值，绝不出现任何真实密钥。

### 2. `python-container` 的"任何 skip 即失败"门禁

这条 P0 门禁的语义原本是**反的**：`set -euo pipefail` 下
`skipped=$(echo "$output" | grep -oE '[0-9]+ skipped' | …)` 在**没有任何 skip**时 `grep` 返回 1，
`pipefail` 让赋值失败，`set -e` 直接打死步骤——套件跑得越干净越必然红。
计数逻辑于是移出 workflow，落到 `scripts/ci/check_container_skips.sh`，退出码即契约：

| 退出码 | 含义 |
|---|---|
| 0 | 有汇总行且 0 skipped |
| 1 | 有 N 条 skipped（条数打进 stdout） |
| 2 | 读不到汇总行（采集阶段就崩），绝不当成"0 skipped" 放过去 |

只数**汇总行**：`-rs` 的逐条原因行里同样含 `1 skipped` 字样，按行全查会重复计数。

步骤体本身也是被测对象。`TestContainerGateStepExecution` 把 ci.yml 里那段 shell **原样落盘**、
用一个 `python` 桩喂给它、按 GitHub `shell: bash` 的真实起手（`--noprofile --norc -eo pipefail`）
执行五种形态并断言退出码。本批正是靠它抓到：`pytest_status=${PIPESTATUS[0]}` 与
`gate_status=${PIPESTATUS[2]}` 分成两条赋值时，第二条读到的 `PIPESTATUS` 已经是第一条赋值
**自己**的状态 ⇒ `gate_status` 为空 ⇒ `[ "$gate_status" -ne 0 ]` 报
`integer expression expected` ⇒ **有 6 条 skip 也判绿**。
正确写法是先用数组接住整组状态：`statuses=("${PIPESTATUS[@]}")`，之后再下标。

> 文本判据对这类缺陷完全无感。凡是"CI 步骤里带 shell 逻辑"的，都要有一段把它真跑一次的判据；
> Windows 上执行时 `subprocess` 传 `"bash"` 会命中 App Execution Alias 而落到 WSL bash
> （看不见仓库路径），必须用 `shutil.which("bash")` 返回的绝对路径。

### 3. `java` 的 `spotless:check`：红的是格式化，但"只是格式化"必须被证明（第九十三批）

`java` job 的第一步是 `mvn --batch-mode spotless:check`（`.github/workflows/ci.yml:337-338`），
它自 2026-08-16 插件引入起就没绿过。取数（`maven:3.9-eclipse-temurin-17`，离线复用 `.m2` 卷）：
**128 / 532 个 java 文件不合格**，`spotless:apply` 产出 **+1383/−1264**。CI 日志被截断时只显式列出
前几条，原文是 "Violations also present in 125 other files"——按日志字面读会数错。

配置是 `palantirJavaFormat 2.39.0` + `removeUnusedImports`（`java-backend/pom.xml:303-314`），
后者**不是**纯空白操作，所以"这只是格式化"不能靠直觉说，判据是逐文件的两次比较：

| 比较 | 口径 | 结果 |
|---|---|---|
| 代码体是否被动过 | 丢掉所有 `import` 行、再删掉全部空白，HEAD 与工作副本逐字节比 | **128/128 相同**，即没有一条语句被改写 |
| import 块里做了什么 | 比较 import 语句**集合**（不是顺序） | 107 个文件只是重排/分组；21 个文件删掉 32 条未引用 import；**新增 0 条、通配符 0 处** |

两条保护由此成立：改动面 = 空白重排 + 未引用 import；而 `removeUnusedImports` 只认代码用法，
所以还要单独查一遍"被删的 import 是否在 Javadoc 散文里仍有指代"——32 条里只有 1 条命中，命中的是
`VectorizationServiceImpl.java` 那行"故意不加 `@Transactional`"的说明文字（讲的就是它的缺席），
且 `pom.xml` 里没有 `maven-javadoc-plugin`，没有可被打破的 javadoc 构建。

判权最后交给同一次 `mvn -B spotless:check test`（容器 `maven:3.9-eclipse-temurin-17`，
离线复用 `.m2` 卷）：重排后越过 check 进入编译，`Tests run: 711, Failures: 0, Errors: 0, Skipped: 52`，
与在 HEAD 上跑同一条命令的结果**逐字相同**。再加 JaCoCo 计数器作第三方对照：

| 计数器 | HEAD | 重排后 | 差 |
|---|---|---|---|
| LINE | 5529 / 13765 = 0.4017 | 5528 / 13798 = 0.4006 | 总数 +33（换行把语句分到更多行），覆盖 −1 |
| BRANCH | 1892 / 6071 = 0.3116 | 1890 / 6071 = 0.3113 | 总数不变 |
| INSTRUCTION | 25525 / 63978 | 25423 / 63978 | 总数不变，覆盖 −102 |

LINE 总数 +33 是格式化的直接后果，但它不是"覆盖变差"而是"同一批语句摊到更多行"。
INSTRUCTION/METHOD/BRANCH 的**覆盖**那几点差异格式化解释不了（总数完全没动），只能来自两次执行的
路径差异——这同时给出一条口径：**这道棘轮不该被当作 0.1 个百分点精度的量**，本仓库的实测噪声就有这个量级。

**同一批把下一处红挖了出来（只登记，本批不修）**：`jacoco:check` 绑在 **`test` 阶段**
（`java-backend/pom.xml:269-298`），本地实测 0.40 / 0.31，低于下限 0.46 / 0.34。这条与格式化无关
（HEAD 上同命令同红），且它**从未在 CI 上被评估过**：`spotless:check` 是 java job 的第一步
（`.github/workflows/ci.yml:337-338`）且自 2026-08-17 起恒红，而这两道下限分别设于 2026-08-31 与
2026-09-08（第三十九批）——也就是说下限是在一条已经跑不到 `mvn test` 的流水线上调的。
`pom.xml:276-280` 那句"本机口径：IT 类无 Docker 跳过；CI 含 IT 会更高"是有依据的推测，但从未被任何
一次运行验证：本地这 711 例里有 **52 例是 docker 门控的 IT，全部跳过**。修不修、怎么修，见第九十三批
的遗留条目。

**为什么不新加门禁**：`spotless:check` 自己就是门禁，且它在 CI 里已经在跑（只是恒红）。
再加一层"用正则数违规文件"的文本判据，是第九十一批 `vue-tsc` 那条口径的同一形态——工具链已经拥有
这个契约时，判据应该去执行它，而不是复制它的结论。本批的判据是**命令本身**：改前 exit 1（红），
改后在同一次运行里越过 check 进入编译。

可复现性另有三条：`git ls-files --eol` 显示 532 个 java 文件在 apply 前后都是 `i/lf w/lf`，
所以这 +1383/−1264 不是行尾重写（第九十二批那一类缺陷在此不适用）；本批现采的补丁与第九十批留档的
`b90_spotless.patch` 除 index 行外**逐字节相同**——两次独立 apply（相隔一天、两次容器会话）得到同一个补丁；
`git apply -R` 退回 HEAD 跑完对照再 `git apply` 回来，产出的 diff 与补丁文件本身**逐字节相同**——
所以"对照实验"与"待提交内容"之间不存在第三种状态。

全仓重排会污染 `git blame`，故重排单独一笔提交，其 sha 记在 `.git-blame-ignore-revs`，
每人 clone 执行一次 `git config blame.ignoreRevsFile .git-blame-ignore-revs`（见 `CONTRIBUTING.md`）。
这条配置**不写进仓库脚本**：改 git config 属用户侧动作，且 CI 不需要它。

## 相关文件

- `.github/workflows/ci.yml` — push/PR 主 CI（含 `eval-offline` 门禁 job）
- `.github/workflows/eval-nightly.yml` — 运行时 Nightly 评测
- `python-ai/scripts/eval_offline.py`、`python-ai/scripts/eval_runtime.py` — 双轨评测入口
- `python-ai/scripts/eval_baseline.py` — 共享报告 / 门禁 / 基线逻辑（2026-08-29 由 `app/core/rag/` `git mv` 而来，见 `docs/CLEANUP_BACKLOG.md:34`）
- `python-ai/evaluation/README.md` — 评测系统设计、用例、双轨与基线流程
- `scripts/ci/check_container_skips.sh` — 容器专项 skip 计数门禁（0/1/2 退出码契约）
- `python-ai/tests/test_ci_workflow_gates.py` — 上述两条非评测门禁的判据（含真执行 workflow 步骤体）
- `python-ai/tests/test_eval_suite_eol_binding.py` — 冻结摘要与行尾无关的判据（钉值、两种检出形态、篡改仍红、emit 写 LF）
- `.git-blame-ignore-revs` + `CONTRIBUTING.md`「Java code style (spotless)」— 全仓重排那一笔如何不污染 `git blame`
