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

## 非评测门禁：CI 自己的五处自伤（第九十、九十三、九十四、九十七批）

上面那张表之外的 job（`docker-compose-validate`、`python-container`、`java`、`frontend`）不评测量，
但同样会阻断合并。本节记录五条判据——它们的共同点是**红的是 CI 自己，不是产品**。

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

### 4. 覆盖率棘轮的"口径"与 it profile 的宿主时区假设（第九十四批）

第九十三批留下一个只有真实 MySQL 才能回答的问题：`jacoco:check` 的下限
（LINE 0.46 / BRANCH 0.34，`pom.xml:269-298`）到底是在哪个口径上钉的。
用 `AbstractItMySQLTest` 自带的外部库通道（`HFH_IT_JDBC_URL`）把 54 例 docker 门控
IT 真跑起来，两个口径同时有了数：

| 口径 | LINE | BRANCH | 对下限 |
| --- | --- | --- | --- |
| 含 IT（CI 口径） | 6622/13798 = **0.4799** | 2161/6071 = **0.3560** | 两条都过，余量 +275 行 / +97 分支 |
| IT 整类跳过（本机无库） | 5529/13765 = **0.4017** | 1892/6071 = **0.3116** | 两条都不过 ⇒ `mvn test` BUILD FAILURE |

`pom.xml:279` 那句"CI 含 IT 会更高"第一次被实测（+7.8 pp），同一句里的
"本机口径：IT 类无 Docker 跳过"则被实测成**低于自己的下限**——所以本机跑绿
`mvn test` 的前提是给测试库，这条已写进 `CONTRIBUTING.md`「Running Tests」。
`pom.xml:278` 声称 2026-09-08 在跳过口径上实测过 46.15%，今天同一口径只能测到
40.17%：那句保留为历史脉络，不当作现行依据。

同一轮取数撞出一个**活的缺陷**。`application-it.yml` 当年为"对齐 JVM"写了
`connection-init-sql: SET time_zone='+08:00'`，前提是跑测试的机器 JVM 在 +8
（ADR-008 第 3 条原话）。CI 的 ubuntu runner 和 maven 容器里 JVM 是 UTC，
于是这个偏移不再是零，而是凭空造出 8 小时：`DocumentMapperRecycleTest` 里
`recycle_expires_at = now + 1h` 的"未过期"行被库判成过期，
`expected: <1> but was: <2>`——**这一步在 CI 里从未跑过**，因为第九十三批之前
`spotless:check` 恒红，java job 走不到第 2 步。

判据先红，再按四个"宿主 JVM × 会话时区"组合逐个取数：

| JVM | it 会话 | 结果 |
| --- | --- | --- |
| UTC | +08:00（改前） | 1 failed（上面那条断言） |
| UTC | 不偏移（改后） | 713 / 0 fail / 1 skip，`All coverage checks have been met` |
| +08（`TZ=Asia/Shanghai`） | 不偏移 | 713 / 0 fail / 1 skip，checks met |
| −05（`TZ=America/New_York`） | 不偏移，未过期余量 1h | **又红**：同一条断言、同一句消息 |

第四行说明撤掉 +08 只解决了一半：配置能撤，判据里"过期侧留 1 天、未过期侧只留
1 小时"的不对称余量还在，凡是**库比 JVM 快**的宿主都会红。于是把未过期余量也取
1 天（`DocumentMapperRecycleTest.java:95` 与 `:105`，仍不改 mapper 语义），
第五行（UTC + 不偏移 + 1 天余量）全量复跑 = 713 / 0 fail / 1 skip + BUILD SUCCESS。
两侧余量都 >14 小时（地球上任意宿主的偏移上限），四个组合从此与宿主无关。

顺带否掉第九十三批登记的一条怀疑：`ci.yml:365-368` 的冒烟步骤
`mvn test -Dtest=PythonEngineSmokeTest` **不是**潜在红。jacoco 的
`prepare-agent` 默认 `append=true`，同一 `target/jacoco.exec` 会累积，所以那一步的
check 重述的是第 2 步的数据——实测单独跑 8 例的类报 `All coverage checks have been met`，
而加 `-Djacoco.append=false` 重跑同一条命令则 `ratio is 0.00` + 两条 `Rule violated`。
代价是这条 check 在那一步不增加任何信息；若要它成为每次运行的度量，
冒烟步骤得显式 `-Djacoco.skip=true`，属部署面/CI 行为变更，本批不修，只登记。

不新增门禁：时区偏移的判据就是那 53 例真跑在真库上的 IT 本身，
而"会话不额外偏移"是配置缺省态——给它加一条文本判据，
只会复制第九十一批 `vue-tsc` 那种"把工具的结论再抄一遍"的形态。

### 5. `run:` 写成行内标量时，那道门禁从未执行过（第九十七批）

`eval-offline` job 里现在有**四道**离线门（主套件 + 招投标三竖门），但推送 `ad92367e` 那轮 CI
只有一道在跑。三个竖门的写法是：

```yaml
- name: Run bid offline evaluation gate
  run: python scripts/eval_offline.py \
    --cases evaluation/suite_bid/cases.jsonl \
    --fail-on-regression
```

`run:` 后面不带 `|` 时，整段是 YAML 的**plain 多行标量**：折叠规则把换行变成**一个空格**，
`\` 于是留在原地，shell 看到的不是续行而是"一个被转义的空格"。把同一份文本按这套规则拼出来
再交给 bash 打印 argv，得到的是 `' --cases'`（带前导空格），argparse 认不出它是选项 ⇒
`unrecognized arguments` ⇒ 退出码 2。CI 日志（run 38099630611，job 114352691081）里那段错误
正好是两倍空格的样子，与本地复现一致。

按出生时间算，这三道门**自 2026-08-25 起一次也没跑过**（`aabd3df6` 引入 bid 门、`f684d6bb` 引入
施工/IT 门，形态从第一天就是错的）。这类缺陷的形态决定了它不会被发现：步骤失败会被下一次
成功的运行冲淡，而"门在但从未生效"根本不产生失败信号——**门禁消失比门禁变红更安静**。

同轮否掉了"是不是评测退化了"这个猜测：把三套件在本地按正确引法各跑一遍，退出码 0 且
`gate_failures: []`，红的一直是引号而不是指标。

判据分两层，都不重复第九十二批那份摘要绑定（`test_eval_suite_eol_binding.py` 管内容）：

| 层 | 位置 | 查什么 |
|---|---|---|
| 形状 + 存在性 | `scripts/static-checks.py` 检查 14（`--workflow-run-scalars`，已并入默认全跑档） | 扫 `.github/workflows/*.yml` 全部 81 个 `run` 步骤：行内值以 `\` 收尾、或有"比键更缩进又不是 key/列表项"的折行 ⇒ 红；另钉四道门仍在 ci.yml 调用、`--cases` 指向的用例文件在位、入口脚本在位 |
| 语义 | `python-ai/tests/test_workflow_run_scalars.py`（15 例） | 用 PyYAML（生产码只用标准库，判据故意换一个 oracle）把 ci.yml 解析成 shell 实际收到的脚本，断言四道门各有独立的 `--cases` token 且无带前导空格的 token；断言门里每个 `--flag` 都在 `eval_offline.py` 的 argparse 里声明过；断言历史折叠形态真会产生 `' --cases'` |

存在性那一半不是多余的：主门当时靠 argparse 默认值取用例，`--cases` 字样不出现在 ci.yml 里，
检查 14 第一版就误报"ci.yml 不再调用离线套件 suite"。修法是**把主门也显式写出
`--cases evaluation/suite/cases.jsonl`**（与 `eval_offline.py:46,53` 的默认值逐字相同，
行为中性），而不是把门禁放宽成"数一下调用次数"。

三条诚实的边界：检查 14 只回答"这行命令到没到 shell"和"门还在不在"，**不保证门里的断言会过**；
它也不解释 YAML——是照 YAML 的折叠规则做文本判断，所以真解析器（上面那层语义判据）必须和它并
存，否则规则背错了也没人知道；`run:` 里那段 shell **逻辑**对不对仍归 `test_ci_workflow_gates.py`
那类"把步骤体落盘真跑"的判据，本批没有把它们推广到评测步骤。

顺带纠正一处文档声称：本文第 3 行"每个 push/PR 到 main 都跑离线评测门禁"在第九十七批之前只对
主套件成立，`README.md:49` 的"CI push 阻断门禁"同样只覆盖主套件；三竖门自出生起未阻断过任何
合并。手工核对记录（不靠门禁）：修复后用 PyYAML 把 ci.yml 解析成 shell 实际收到的脚本、交给
bash 打印 argv，四个门各自都是"前导空格 token 数 0、退出码 0"；三个竖门的套件另在本地按正确
引法各跑一遍为绿。

**本地 argv 只是必要条件，不是本批的判定标准**——真正的标准是"CI 上这一步确实被 shell 执行了"，
它只能从 runner 日志取。推送 `d3d31f36` 后（run 38115360383，job 114399072071，`eval-offline`
**success**——本批修法上线后的第一轮）取到的四条执行证据：

| 时间戳（runner 时钟） | 步骤 | 日志中的独立证据 |
|---|---|---|
| `05:47:11.2899680Z` | Run offline evaluation gate（主门） | `##[group]Run python scripts/eval_offline.py --cases evaluation/suite/cases.jsonl …` 单行 |
| `05:47:12.9625378Z` | Run bid offline evaluation gate | `##[group]Run python scripts/eval_offline.py \` + 缩进续行，续行由 runner 逐条回显（块标量） |
| `05:47:13.9317179Z` | Run construction offline evaluation gate | 同上 |
| `05:47:14.8539778Z` | Run IT offline evaluation gate | 同上 |

四步各打出自己的报告，且 `suite_sha256` **互不相同**（主门 `15b0ea64…`、bid `135114f4…`、
施工 `6d8a045b…`、IT `f23c8bf0…`）——这一步排除了"四行日志其实重复跑了同一个套件"的假绿。
报告是真算的：bid 门 `case_count: 27`、`category_counts.normal: 27`；主门的
`citation_recall 0.8942 / citation_f1 0.7409` 落在 0.85 / 0.70 两条下限之上；三条竖门的
`qualification_recall / disqualification_clause_recall / scoring_point_accuracy /
bid_terminology_accuracy` 聚合值均为 `1.0`。四份报告末尾都是 `"gate_failures": []`，且
`diffs` 块逐项 `0.0`（本轮指标与 `baseline_metrics` 完全相等）——也就是说门第一次真跑就站在
自己的基线上，"回归即红"这条能力还没被一次真退化验证过。全份日志里 `unrecognized arguments`
与 `ShellCommandUnresolved` **0 命中**，即死因词没有再生。同一轮 `static-consistency` 也转绿，
检查 14 从此在 CI 上执行。

诚实边界照旧：这四次执行证明的是"命令到了 shell、门按自己的套件跑完且没判红"，**不证明门里的阈值
设置得当**；三道竖门今天第一次有历史数据，此前 47 天没有任何一次运行可以对照。

## 检查 17：Flyway 步骤的旗标与插件钉版（第一百零八批）

`e2e.yml` 两处与 `eval-nightly.yml` 一处 `Run Flyway migrations` 自出生起每次都红，命令只有
`mvn --batch-mode flyway:migrate`，连接信息写在 `SPRING_DATASOURCE_*` 里——flyway-maven-plugin
不读 Spring 的键，于是连续 5 条 run 的 `e2e-full` 都停在
`FlywayException: Unable to connect to the database. Configure the url, user and password!`
（取证见 `docs/CLEANUP_BACKLOG.md:371` 那一条）。同仓 `ci.yml:380-391` 早已写对，所以这不是环境问题。

| 层 | 位置 | 查什么 |
|---|---|---|
| 形状 | `scripts/static-checks.py` 检查 17（`--flyway-cli`，已并入默认全跑档） | 每个 flyway 步骤必须显式带 `-Dflyway.url= / .user= / .password=`；步骤 env 里出现 `SPRING_DATASOURCE_URL/USERNAME/PASSWORD` 判红（空转开关）；`continue-on-error: true` 判红；按文件钉调用数（ci 2 / e2e 2 / eval-nightly 1），**适用面为空本身判红**，所以删步骤、改 goal 都不会把门变绿；pom 必须声明 `flyway-maven-plugin` 且版本写 `${flyway.version}` |
| 语义 | `python-ai/tests/test_flyway_cli_gate.py`（19 例） | PyYAML 作第二个 oracle：断言每个 flyway 步骤的 url 库名 / user / password 与**同一 job 的 `services.mysql.env`** 逐字相等（形状对但指错库照样红）；断言文本解析器读到的脚本与 YAML 解析出的脚本按空白归一后一致、步骤名不为空（解析器瞎了门就是空的）；断言 `flyway-core` 不带 `<version>`——否则 `${flyway.version}` 不再等于运行时版本；六种注入漂移各红一次 |

行为侧判据不由文本门冒充，在活库上量（本机 `mysql:8.0`→8.0.46 容器，库/账号与 workflow 的
service 同凭据）：旧形状复现上面那句异常；新形状 `Successfully applied 87 migrations to schema
hfusionhub, now at version v86`；`flyway_schema_history` 为 `87 行 / success 之和 87 /
最大 installed_rank 87`，schema 落 70 张表；`flyway:info` 绿。钉版那一半的实际效果要说清：
`spring-boot-dependencies:3.5.16` 声明 `<flyway.version>11.7.2</flyway.version>`，与历史日志里
浮动解析到的版本相同 ⇒ **本批没有换掉今天执行的版本**，消除的是"central 哪天发新版就悄悄换插件"。

诚实边界：检查 17 只看 workflow 文本与 pom 的形状，**不证明迁移内容正确**；它也不查
`-Dflyway.locations` 之类的其余配置——库名与凭据同源由上面那层语义判据兜，SQL 本身仍由检查 4/5
那两条迁移链门管。

**补证（第一百一十一批，push `779fd23b` 后取，run 38332373255 / job e2e-full）**：那句"改后的步骤
要等下一个 push 的 runner 才算真跑"已经有了答案——`Run Flyway migrations` 在 runner 上
**success**（同一 run 里三个历史红 job 的对照：38233532705 / 38134153616 / 38025985552 的
`failed_steps` 都是 `["Run Flyway migrations"]`）。同一次 push 的 `CI` run 38332373222 全绿
（含检查 18 所在的静态门），`Plugin Security Pipeline` run 38332373261 五绿一红，红的仍只有
第一百零四批登记为**预期真红**的 `license-check`。
这条绿同时把下一层翻了出来：Flyway 不再挡路后，`Run full E2E suite` 从出生起第一次被执行，
35 失败 / 28 通过 / 10 跳过，报错全是 `net::ERR_CONNECTION_REFUSED :3000` —— 由下面的检查 19 处置。

## 检查 19：e2e 轨的前端服务契约（第一百一十一批）

`e2e.yml` 两个 job 的步骤序列一直是 `npm ci` → `playwright install --with-deps chromium` →
`npx playwright test`，**中间没有任何一步起前端**；而 `playwright.config.ts:31-38` 写的是
`webServer: CI ? undefined : { command: 'npm run dev', port: 3000 }` —— 本地开发靠它起服务器，
CI 档明确不自起。两边各自都"说得通"，合起来的结果是 CI 上 :3000 从来没有进程，浏览器用例整批
`net::ERR_CONNECTION_REFUSED`。这条红在第一百一十一批之前看不见，因为上一步的 Flyway 每次都先红
（10.2 的检查 17 补证有三次 run 的 `failed_steps` 为证）。

| 层 | 位置 | 查什么 |
|---|---|---|
| 形状 | `scripts/static-checks.py` 检查 19（`--e2e-frontend-server`，已并入默认全跑档） | 每个含 `npx playwright test` 的 job 必须：①测试步骤之前有以后台方式起前端的步骤（`npm run dev… &`／`npm run preview… &`）；②它排在 `npm ci` **之后**（否则 node_modules 还没装，vite 起不来）；③起服务与测试之间有一条带 URL 的等待探针，探针端口必须等于 `playwright.config.ts` 里 `baseURL` 的端口（跨文件同源，改一处就孤儿一处），且超时后必须 `exit 1`（否则前端起不来也照样往下跑，红换个报错再来一次）；④适用面按 job 名下界钉住 `{e2e-smoke, e2e-full}`，扫不到任何 playwright job 判红，少一个判"适用面缩小了" |
| 语义 | `python-ai/tests/test_e2e_frontend_server_gate.py`（22 例） | PyYAML 作独立 oracle：只用 YAML 复算"测试步骤前有起前端步骤、且排在 `npm ci` 后、探针在两者之间且带 `exit 1`"；复算探针端口与 `baseURL` 端口同为 3000；有名步骤的顺序与内容与 YAML 逐条相同，无名步骤条数按"uses 步骤数 ＋ 每 job 两条 `- 3306:3306` 端口行"钉住（解析器多吞少吞都会红）；config 那条三元式跨三行必须读得出（`webServer: CI` / `? undefined` / `: {…}` 压平成一条逻辑行再判，与检查 18 的续行教训同一条规则）；七种坏形状各红一次 |

**门自己纠正过一次**：`_playwright_ci_autostarts` 第一版按 `CI \? (\w+) :` 匹配，遇到
`webServer: CI ? { port: 3000 } : {…}`（CI 档自起的是对象字面量）匹配不上，于是"同一端口两个主人"
那支判红永不触发；改成"压平后取 `CI ?` 之后第一个非空 token，等于 `undefined` 才是不自起"，
这条漂移才真的红（测试 `test_multiline_ternary_is_read_as_one_logical_line` 钉住）。

行为侧判据不由文本门冒充，本机量过：`npm run dev` 起 vite 后 `curl -sf http://localhost:3000/`
= **200**（冷启动 `ready in 10354 ms`，日志含 `Re-optimizing dependencies because lockfile has
changed`），`/api/health` 经 `vite.config` 的代理返回 **502**（本机没有 8080，CI 上由
`Start Java backend` 提供），杀掉进程后同一请求 000/refused —— 正是那 35 条红的签名。

诚实边界（写下时）：本检查只看 workflow 与 config 的文本形状，**不证明那 35 条用例在 runner 上会转绿**——
起前端只是它们共同的第一道死因，登录态、seed 数据、mock LLM 这些更高层的失败要等下一次 push 的
e2e run 才分得清；也不证明 `Wait for frontend dev server` 那 60 秒预算够（本机 10.4 秒起来，
runner 上是冷 npm 缓存，未量）。检查 14 继续管这两个新步骤的 YAML 标量形态。

**补证（同批推送 `aaaf045b` 之后取，run 38336201364 / job e2e-full）——上面两条边界都有答案了**：
步骤 15 `Start frontend dev server` 与步骤 16 `Wait for frontend dev server` 都是 **success**
⇒ 60 秒预算在 runner 的冷 npm 缓存下够用；套件从 `35 失败 / 28 通过 / 10 跳过` 变成
**`4 失败 / 59 通过 / 10 跳过`**（合计 73，与 README 的 E2E 口径一致）⇒ 那 31 条确实死在
"没有进程监听 :3000"。同一 push 触发的 `CI` run 38336201365 十一个 job 全绿，其中
`static-consistency` 就是全跑档的 `static-checks.py`，所以检查 19 也在 runner 上真跑过一遍。
（`e2e-smoke` 在这个 run 里是 skipped，按设计——`e2e.yml:10` 写 `if: github.event_name ==
'pull_request'`，push 到 main 只跑 full；检查 19 判的是两个 job 的文本都带这两步，与此不冲突。）

剩下那 4 条**不属于这一层**，已登记为第一百一十三批（原写作第一百一十二批，那个号属于
`eval-runtime` 可达性探针），死因由 artifact 量出（见下面的检查 20）：3 条 demo-data 叠着三层，
本批只解开其中最外的一层（CI 起的后端不是用例假定的那个后端），第 4 条 `tools.spec.ts:11`
是工具列表分页把目标卡片挤到第 3 页，属测试侧问题，**第一百一十五批已按"改用例"处置**
（页数改运行时推导、目标改翻页找）；它的 runner 判据**第一百一十七批拿到**（run `38524739182`
= `61 passed / 2 flaky / 10 skipped`，整份日志里 `tools.spec` 零命中），而那一轮是踩着
`e2e.yml:165` 的 `timeout-minutes: 20` 过的——之前连续三条 run 把 `e2e-full` 杀在
`Install Python dependencies`（一个用例都没执行），`38524739182` 作业总耗时 19m30s、其中装依赖吃到
15m15s。当时把它写成"离上限只剩约 30 秒余量"，**第一百一十八批就地纠正这条口径**：同一台 runner 上
紧接的 run `38530095482`（commit `487e435c`）只花 **13m27s** 就跑完（07:42:35Z→07:56:02Z）
⇒ 装依赖耗时是**波形**而不是常态，高位那轮不能当基线。

**第一百一十九批把这条波形数到三个点、第一百二十批数到四个点、第一百二十一批数到五个点、
第一百二十三批数到八个点、第一百二十四批数到九个点、第一百二十五批数到十个点**，
口径统一＝日志里 `##[group]Run pip install -r requirements.txt`
到下一个步骤 group 的差；套件耗时＝`Run npx playwright test --project=chromium` group 到下一个 group 的差：

| run | commit | 作业总耗时 | 装依赖 | 套件 | 离 20 分钟上限的余量 |
|---|---|---|---|---|---|
| `38524739182` | `0305bc25` | 19m30s（06:51:59Z→07:11:29Z） | **876 s**（06:52:39→07:07:14） | 184 s | ≈30 s |
| `38530095482` | `487e435c` | 13m27s（07:42:35Z→07:56:02Z） | **459 s**（07:43:12→07:50:50） | 223 s（含 6 次 retry） | ≈6m33s |
| `38568478864` | `15e93920` | 11m54s（13:02:13Z→13:14:07Z） | **423 s**（13:02:55→13:09:58） | 163 s | ≈8m06s |
| `38574242376` | `b904efbe` | 12m53s（13:43:50Z→13:56:43Z） | **465 s**（13:44:51→13:52:35） | 148 s | ≈7m07s |
| `38577643030` | `f97fd471` | 13m11s（14:07:01Z→14:20:12Z） | **492 s**（14:07:50→14:16:02） | 163 s | ≈6m49s |
| `38730439786` | `fe057e7b` | 15m59s（11:52:28Z→12:08:27Z） | **655.938 s**（11:53:14.36→12:04:10.29） | 165.07 s | ≈4m01s |
| `38731555698` | `f9449ee9` | 14m57s（12:01:37Z→12:16:34Z） | **606.508 s**（12:02:19.99→12:12:26.50） | 160.97 s | ≈5m03s |
| `38735220260` | `9d6e52a5` | 14m19s（12:30:57Z→12:45:16Z） | **563.546 s**（12:31:48.09→12:41:11.63） | 163.61 s | ≈5m41s |
| `38742412892` | `1a5e0452` | 15m14s（13:24:27Z→13:39:41Z） | **616.407 s**（13:25:13.115→13:35:29.521） | 157.089 s | ≈4m46s |
| `38889773599` | `c26703ef` | 10m31s（10:49:42Z→11:00:13Z） | **338.152 s**（10:50:23.797→10:56:01.949） | 163.740 s | ≈9m29s（569 s） |

同一把尺子量下来，两个旧数的处境不一样，得分开说：
- "装依赖吃到 **15m15s**"**没有错，只是边界不同**：那是 job 起点→装依赖结束（06:51:59→07:07:14＝整 15m15s），
  本表里的 **876 s** 是 pip 步骤自己（06:52:39→07:07:14），差的就是前面那 40 秒 setup。两个数都成立，
  以后引用要带边界。
- "约 **6 min**"对不上任何一种边界：pip-only 是 **459 s＝7m39s**，job 起点→装依赖结束是
  07:42:35→07:50:50＝**8m15s** ⇒ 那条是没量过的估值，本批就地改掉，并按 459 s 记。结论不变：876／459／423／465／492 s
是同一个慢源在五条 run 上的五个振幅（第一百二十批的第四条落在 459～465 s 这一档，即**低档不是只出现一次的巧合**；
第一百二十一批的第五条 **492 s** 仍在同一档内，只是把这档的上沿从 465 s 抬到 492 s），
这条上限**仍未解除**，抖到高位的哪一轮仍然失明（见 `docs/CLEANUP_BACKLOG.md` F 节的镜像单点条目）。
**（第一百二十三批就地纠正这句的现行值：那句"上沿 492 s"已经被推翻——同一把尺子今天量到 655.938／606.508／563.546 s
三条，全都在 492 s 之上，见下面那段。上面五条是历史读数，不改写；被改写的只是"这一档＝423～492 s"这个判断。）**

**第一百二十三批：并发条件第一次可量，而我自己的猜想被这轮数据否掉了。**
起因是仓库两侧 workflow **都没有 `concurrency:` 块**（`grep -n -A4 "^concurrency:" .github/workflows/e2e.yml .github/workflows/ci.yml`
无输出），所以连续三笔 docs-only push 各自触发的那对 run 会叠在一起跑；第一百二十一批写的"下一批若还是 docs-only push，
取读数就只剩振幅价值"在这里要补一句——**并发是新的自变量**，这是第一个能拆它的样本。

我的假设是"两条 `e2e-full` 同时打同一个 pypi 镜像会抬高 pip-only 档"。**读数不支持**：

| 对照 | pip-only | 与另一条 pip 窗口的重叠 |
|---|---|---|
| `38730439786`（`fe057e7b`） | **655.938 s** | 110.3 s＝自身窗口的 **16.8%** |
| `38731555698`（`f9449ee9`） | **606.508 s** | 110.3 s＝自身窗口的 **18.2%** |
| `38735220260`（`9d6e52a5`） | **563.546 s** | **0 s**（pip 窗口间隔＝12:31:48.090 − 12:12:26.503 ≈ **19m22s**）＝**第一百二十四批就地纠正：这个"0 s"只比了 `e2e-full` 对 `e2e-full`，同批 push 的 CI 侧四条安装与它重叠 100%／81%，这条对照根本不存在** |

两点致命：①**最慢的那条（655.9 s）重叠占比最低的一侧也才 17%**，而**完全没有重叠的对照组只比它快 92 s**，
所以"重叠→更慢"在这三条上分不开（n＝3，重叠比 16.8／18.2／0%）；②更要紧的是**对照组 563.5 s 已经站在旧"低档"
（423～492 s）之上**——也就是说今天这三条的抬高**不需要用并发来解释**，把它写成"并发导致的抬高"是过度归因。
本批能钉住的只有这两句：**旧低档 423～492 s 作为"当前默认档"作废**，八个点现在的分布是 876 s 一个高位＋
**563～656 s 连续三条**＋423～492 s 早期四条（**第一百二十四批就地标注：现为九个点＝876×1＋563～656×4＋423～492×4**）；以及"并发抬高振幅"这条**待否/待证的中间态**——要判它，
得再攒到重叠比拉得开（比如一条 0%、一条 80%）的样本，本轮没有这个条件。
**（第一百二十四批就地纠正上面这三段的自变量本身：`并发是新的自变量`、`这是第一个能拆它的样本`、`不需要用并发来解释`
三句都不成立——不是因为并发不抬振幅，而是因为**这个自变量从来没被变过**。每一笔 push 都同时触发 `e2e.yml` 与 `ci.yml`，
而 `ci.yml` 有四个 job 各起一条 pip 安装，所以任何一条 `e2e-full` 的 pip 窗口都被同批 CI 侧的 3～4 条安装**全程重叠**；
"零重叠对照组"是我把观察面只放在 e2e 轨内部造成的错觉，那条对照组实际处在 **100% 重叠**的负载下。
⇒ 本轮能钉的只剩"旧低档 423～492 s 作废"这一句，"并发假设被否"这句**同时作废**（既没被证实也没被否掉，它是**不可测**）；
读数与五行并发表见下面第一百二十四批那段。）**

风险口径按上面作废的那条重算：坏情况仍按 **876 s** 算（本轮最慢 655.938 s 若换成 876 s，那条 job 就是
15m59s（959 s）＋(876−655.938)s＝220.06 s ≈ **1179 s＝19m39s**，余量约 **21 s**），⇒ 候选 B／C 的排序不变，
"落在低档不等于离上限安全"这句照旧成立。
attempt 级本轮三条各摊平 73 行都是 `63 expected / 0 unexpected / 0 flaky / 10 skipped`、`retry>0`＝**0 行**
⇒ 从 `38568478864` 起**连续六轮**不靠 retry；`10 skipped` 那条覆盖面结论本批未变。

**第一百二十四批：`1a5e0452` 那对 run 的读数到手（pip-only 第九个点 616.407 s），而这轮把上一批的自变量本身推翻了——
顺带量到"装依赖的快慢与 pip 缓存无关，只与那几个大 wheel 的吞吐有关"。**

**①本轮读数**（尺子与前八条相同：pip 步骤 group→下一个 group；套件步骤同理）：
E2E run `38742412892`（`1a5e0452`，success）的 `e2e-full` job 窗口 13:24:27Z→13:39:41Z＝**914 s＝15m14 s**，
pip-only **616.407 s**（13:25:13.115→13:35:29.521）、`Install frontend dependencies` **5.209 s**、
套件 **157.089 s**（13:36:57.02→13:39:34.11，与 `stats.duration` 155999.745 ms 一致），
`Running 73 tests using 1 worker` → `63 passed (2.6m) / 10 skipped`；
`stats`＝**63 expected / 0 unexpected / 0 flaky / 10 skipped**，attempt 级 `results` 展开 **73 行**
（`passed` 63／`skipped` 10），**`retry>0` 的行数＝0** ⇒ 从 `38568478864` 起**连续七轮**。
`e2e-smoke` 仍按设计 `skipped`（不是红）。
CI run `38742412916` 同 commit、**十一 job 全绿**（13:24:24Z→13:41:35Z＝17m11 s），`gitleaks` 13:24:28→13:24:37。
`gitleaks` 的轮次这次**逐 job 数过**而不是沿用上一批的说法：第一百一十七批那处高熵字面量修好之后的 CI 序列是
`38530095463`→`38568479058`→`38574242324`→`38577643015`→`38730439984`→`38731555673`→`38735220128`→`38742412916`，
八条 run 的 `gitleaks` job **8/8 `success`** ⇒ 文档里"连续第三轮／第四轮"两句是写作当时的现行值，现行值＝**第八轮**。
九个点现在的分布：**876 s（1 条）＋563～656 s（连续 4 条，含本轮 616.407 s）＋423～492 s（早期 4 条）**。
**（第一百二十五批就地纠正这句的"档位"读法：那三个"档"不是离散档位，本轮 pip-only＝338.152 s 把原"低档"下界 423 s
打穿 ⇒ 十个点是一条 338～876 s 的连续谱，任何"这一档＝X～Y s"的写法都只是样本分箱，不能拿来推"下界"。见下面第一百二十五批那段①②。）**

风险口径仍按 **876 s** 算：本轮 job 914 s 对 1200 s 上限的余量是 **286 s≈4m46 s**，
但若 616.407 s 换成 876 s，那条 job＝914 s＋259.593 s＝**1173.593 s≈19m34 s**，余量约 **26 s**
⇒ 与前两批同形：**落在中间档不等于离上限安全**，候选 B／C 排序不变。

**②并发表（本轮把观察面从"e2e 轨内部"改成"这笔 push 触发的两条 run 全部 pip 步骤"）**：
`e2e-full` 的 pip 窗口 vs 同批 CI 侧各安装窗口的重叠秒数（`gh run view <id> --log` 逐 job 取 group 边界）：

| push（e2e run／CI run） | e2e pip-only | 与 `python`＋`python-container`＋`eval-offline` 的重叠 | 与 `java` 的重叠（**第一百二十五批就地纠正：这一列量的不是安装窗口，见下面那段——只有前三列可用作安装重叠**） | `python-lint`（ruff） |
|---|---|---|---|---|
| `f97fd471`（`38577643030`／`38577643015`） | **491.654 s** | 三条各 **491.7 s＝100%** | 396.8 s＝**80.7%** | 1.9 s，重叠 **0 s** |
| `fe057e7b`（`38730439786`／`38730439984`） | **655.938 s** | 三条各 **655.9 s＝100%** | 532.1 s＝**81.1%** | 1.6 s，重叠 **0 s** |
| `f9449ee9`（`38731555698`／`38731555673`） | **606.508 s** | 三条各 **606.5 s＝100%** | 462.9 s＝**76.3%** | 1.6 s，重叠 **0 s** |
| `9d6e52a5`（`38735220260`／`38735220128`） | **563.546 s** | 三条各 **563.5 s＝100%** | 456.3 s＝**81.0%** | 1.7 s，重叠 **0 s** |
| `1a5e0452`（`38742412892`／`38742412916`） | **616.407 s** | 三条各 **616.4 s＝100%** | 502.6 s＝**81.5%** | 1.7 s，重叠 **0 s** |

三点结论：
- **负载是常量，不是变量。** 五笔 push 的每一条 `e2e-full` pip 窗口都被 3 条 CI 安装全程覆盖、被 `java` 覆盖 76～82%，
  含 e2e 自身合计 **5 条并发安装流**打同一个镜像（`ci.yml:168/196/248` 装 `requirements-dev.txt`，`ci.yml:366` 装
  `requirements.txt -q`；`ci.yml:146` 的 ruff 只 1.6～1.9 s，从不落进窗口）。
  （**第一百二十五批就地收窄这句**：可证的只有 **3 条 CI 安装 ＋ e2e 自身＝4 条并发安装流**；`java` 那一格量的其实是
  一个复合步骤（安装＋起服务＋60 次健康轮询），它的重叠只能给界 **0～210.9 s**、给不出百分比，所以"5 条"与"76～82%"
  不是读数而是把复合步骤误当安装窗口的产物。判"并发不可测"的结论**不变**，变的是它的支撑面：三条 100% 覆盖已经够了。）
  ⇒ 上一批"零重叠对照组"是观察面缺陷（只看 e2e 轨内部），不是样本条件；**并发效应本轮判为不可测**，
  既不能说"被否"也不能说"待证"，要判它必须先把两条轨的负载差出来（加 `concurrency:` 或 `workflow_dispatch` 单轨跑）。
- **同一份负载下振幅照样跨度很大**：`f97fd471` 那轮负载与其余四轮完全相同（100%／80.7%），pip-only 却只有 **491.654 s**，
  比本轮 616.407 s 快 25%。⇒ 振幅**不是**这五路并发带来的，得往别处找（见③④）。
- 顺带一条：`java` 那条安装比另外三条晚起步（本轮 13:27:06 vs 13:24:33），所以它的重叠比不是 100%；
  这个差是 job 起跑顺序，不是设计。

**③pip 缓存不是"快慢"的解释（本轮第一次量到，且只到"无关"这一步）**：
`actions/setup-python@v5` 带 `cache: pip`、`cache-dependency-path: python-ai/requirements.txt`，
两条 run 的日志里都有 `Cache restored successfully` ＋
`Cache restored from key: setup-python-Linux-x64-24.04-Ubuntu-python-3.11.17-pip-bda709e77a3dc99b3a182ad3d8185ce2b8f48051f595d7f223…`
（同一个 key 在 `1a5e0452` 与 `f97fd471` 两轮都命中，也出现在 `python`／`python-container`／`eval-offline` 三个 job 里；
`e2e-full` 还各 restores 了 `setup-java-…-maven-…` 与 `node-cache-…-npm-…` 两个别的缓存）。
但**同一步 pip 日志的计数是**：`python` 三个 job 各 **97 行 `Downloading`／4 行 `Using cached`／0 行 `Building wheel`**，
`e2e-full` 两轮都是 **72 行 `Downloading`／4 行 `Using cached`**。
⇒ 缓存"恢复了"与"每个包重新下载"在这套 workflow 里是**并存**的，所以 `Cache restored` 这句日志**不能当"这轮装得快是因为命中缓存"的证据**，
反过来也不能当"缓存坏了"的证据。
**缓存实际省下的量是量得出的**：两条轨复用的是**同一组四个 wheel**（`faiss_cpu-1.14.3` 18.5 MB、`uvloop-0.23.0` 4.0 MB、
`pypdf-6.19.0` 395 kB、`urllib3-2.8.0` 135 kB＝合计 **23.0 MB**），而同一轮 `e2e-full` 重下 **72 个包／107.4 MB**、
`python` 重下 **97 个包／121.8 MB** ⇒ 缓存覆盖率按体积算只有 **≈18%（e2e）／≈16%（CI）**，
且 **pyarrow 50.1 MB 这一个包就抵得上缓存里全部内容的 2.2 倍**——所以"命中缓存"这件事**结构上不可能**解释档位差。
**诚实边界**：为什么 key 命中却只复用了 4 个包，日志层面判不出来（候选：缓存内容本身只存了这 4 个（早期轮次保存时只有这几个）、
actions 缓存配额驱逐、`cache-dependency-path` 是 `requirements.txt` 而三个 CI job 装 `requirements-dev.txt`
（但这解释不了 e2e 轨——它装的正是 `requirements.txt`，同样只复用这 4 个，所以这条候选**对本轮不成立**）、
保存步骤没写成功（job 日志里没有 `Cache saved` 行，post 步骤可能不进这份日志））。
要钉死得在 runner 上加 `pip cache dir`／`pip cache info`／`pip cache list` 的取证步骤＝**改 workflow，待拍板**。
**（第一百二十五批把这段的候选面砍掉三条，并给出一条新读到的机制**：Post 步骤进得了日志，四个 python job 全部写着
`Cache hit occurred on the primary key setup-python-…-pip-bda709e7…, not saving cache.` ⇒ "保存步骤没写成功"这条候选
**改判为"根本没尝试保存"**；而 `Cache Size: ~146 MB (152908538 B)` 在 `f97fd471`→`c26703ef` **六轮**
（10-14 14:06Z→10-16 10:50Z，六份 CI run 级日志＋两份 e2e job 级日志）里**逐字节相同** ⇒ 这个条目被**冻住**了
（只要 `requirements.txt` 内容不变，Actions 不会覆盖已有 key；同一台 runner 上的 maven `~136 MB (142672703 B)` 与 npm
`~47 MB (49310164 B)` 两条也是同一形态，六轮逐字节相同且 Post 同样 `not saving cache`），所以"缓存内容本身只存了这 4 个"这条候选的准确形态是
**"存了 146 MB 但那份快照与今天这 72 个包几乎不相交"**；`actions 缓存配额驱逐`这条同被排除（若是驱逐，key 不会恒命中、
字节数不会六轮不变）。**（第一百二十六批就地撤回这半句**——它把"当前这个条目六轮不变"当成了"从未发生过驱逐"，是两件不同的事：
10-11 那次保存 restore 的是**前一个 key** `…-pip-cdb57277…`（152584972 B），而这个 key 在今天的仓库缓存列表里**已经不存在**
⇒ 驱逐**确实发生过**，而且总量 10,665,585,548 B＝**9.93 GB**、其中 `index-buildkit-*` 379 条占 **9.34 GB＝94.0%**，
是紧贴着上限的形态 ⇒ 这条候选**回到盘中并升为最可能动因**，见下面第一百二十六批那段②⑤。）**
**"恢复目录不是 pip 查找目录"这条也被日志削掉了**：setup-python 自己就跑过
`/opt/hostedtoolcache/Python/3.11.17/x64/bin/pip cache dir`（10:50:17.579 → 输出 `/home/runner/.cache/pip`，10:50:19.004）
再往里恢复 ⇒ 路径层面对得上。剩下的解释只有"**快照里的 wheel 与今天这 72 个包不是同一批**"，而它需要名单级证据＝候选 D 的问题。
见下面第一百二十五批那段③。**"为什么 key 命中却只复用了 4 个包"本批只推进到"排除三条＋缩到一条"，没有钉死。**
**（第一百二十六批把这条"缩到一条"也否掉了**：名单级证据用只读通道取到了——写手那次 run 自己打印的 99 个包名与本轮 `e2e-full`
的 72 个做集合差是 **70/72＝97.2% 同名**、只有 2 条版本漂移 ⇒ **"不是同一批"不成立**。剩下的问题精确成
"**为什么同名同版本的包在恢复出来的目录里等于没有**"，而那要的是 runner 侧 `pip cache list`／`-vv` 一层，本批仍未取证；
同时本批量到镜像侧**根本没有"过期就得整包重下"这堵墙**（wheel 带 `ETag` 且条件请求答 **304**），
所以"12 h 新鲜度"也不能当解释。见下面第一百二十六批那段③④。）**）


**④那这轮的时间到底花在哪：带宽，落在几个大 wheel 上。**
把 pip 步骤的相邻时间戳做差、只留 ≥20 s 的间隔（一条间隔＝一个包的下载）：

| 样本 | 步骤总时长 | ≥20 s 间隔合计 | 占比 | 其中 pyarrow 50.1 MB |
|---|---|---|---|---|
| `1a5e0452` 的 `e2e-full` | 616.407 s | 501.5 s（6 条） | **81.4%** | 246.2 s @ **229.6 kB/s** |
| `1a5e0452` 的 `python` | 708.759 s | 545.1 s（7 条） | **76.9%** | 249.5 s @ **219.2 kB/s** |
| `9d6e52a5` 的 `python` | 655.467 s | 498.5 s（7 条） | **76.0%** | 229.4 s @ **224.6 kB/s** |
| `f97fd471` 的 `e2e-full`（本轮那类低档） | 491.654 s | 365.1 s（4 条） | **74.3%** | 232.7 s @ **257.2 kB/s** |
| `c26703ef` 的 `e2e-full`（第一百二十五批，新低点） | **338.152 s** | 194.5 s（3 条） | **57.5%** | 118.7 s @ **436.9 kB/s** |
| `c26703ef` 的 `python`（同批） | **406.014 s** | 216.1 s（4 条） | **53.2%** | 118.1 s @ **442.1 kB/s** |

被点名的大包在四份日志里是同一批：50.1 MB（pyarrow）、16.9 MB、11.3 MB、10.3 MB、7.1 MB、5.9 MB、5.2 MB、4.7 MB，
速率全在 **163～273 kB/s** 这个区间。⇒ 装依赖时长的**可解释部分**是"七八个 ≥4.7 MB 的 wheel 以几百 kB/s 下载"，
占步骤的 74～81%；档位差＝同一批包的吞吐差（本轮 163～230 kB/s vs 低档轮 257～273 kB/s），不是包数差、也不是缓存差。
**（两列的尺子不同，第一百二十五批加一句图例以免误读**：`≥20 s 间隔合计`与`时长`用的是**相邻日志行时间戳差**，
`kB/s`那一列后半截是**pip 自己打印的速率行**（`━━ 50.1/50.1 MB 436.9 kB/s 0:01:58`）。两把尺子在同一条包上对得上——
`1a5e0452` 时间戳差 246.2 s、pip 自报 `0:04:06`；本轮 118.7 s、自报 `0:01:58`——但**别拿体积除以时间戳差去复算速率**，
复算值会低 10～15%（`50.1 MB / 246.2 s`＝203 kB/s ≠ 自报的 229.6），因为 pip 的速率分母不含进度条出现前的排队。）**
**（第一百二十五批就地补一句：这个占比本身也随轮次波动——本轮同样 72 个包／107.4 MB，但 ≥20 s 间隔只占 **57.5%**
（194.5 s／**3 条**＝pyarrow 118.7 s @ 436.9、16.9 MB 48.3 s @ 354.8、11.3 MB 27.5 s @ 410.9 kB/s）；
同批 `python` 406.014 s 里 216.1 s（4 条）＝**53.2%** ⇒ **"74～81%"是四份样本的分箱值，不能当固定系数引用**。
本批又把这条尺子架到另外两份往轮日志上：`fe057e7b` 的 `e2e-full`＝531.4/655.938 s＝**81.0%**（6 条）、
`f97fd471` 的 `python`＝394.3/552.982 s＝**71.3%**（5 条）⇒ 六个样本的实际区间是 **71.3～81.4%**，
本轮的 57.5%／53.2% 在区间外——**被点名的间隔条数本身也随轮次变（3～7 条）**，占比不是常数也不是"慢的指纹"。）**
这条对本条目的处置含义是：**候选 B（`--timeout 60 --retries 10`）治不到这种形态**——它治的是"连接超时／重试"，
而这里的每一段都在稳定地慢速传输（没有超时发生）；能治的是候选 C（换 index）和"把大 wheel 移出每轮必装的面"。
候选 C 动的是第九十二批钉住摘要的锁文件，仍**待拍板**。

**第一百二十五批：`c26703ef` 那对 run 的读数到手（pip-only 第十个点 338.152 s，把原"低档"下界 423 s 打穿），
净新增四条：轮次级共同因子第一次有了数、pip 缓存那条从"命中率低"升级为"条目被冻住"、同一台 runner 上缓存通道比 index
通道快约 270 倍的实测、以及上一批并发表的第四列量的根本不是安装窗口。**

**①本轮读数**（尺子与前九条相同：pip 步骤 group→下一个 group；套件步骤同理）：
E2E run `38889773599`（`c26703ef`，success）的 `e2e-full` job 窗口 10:49:42Z→11:00:13Z＝**631 s＝10m31 s**，
pip-only **338.152 s**（10:50:23.797→10:56:01.949）、`Install frontend dependencies`（`npm ci`）**5.281 s**
（10:56:52.057→10:56:57.338）、`npx playwright install` **19.732 s**、
套件 **163.740 s**（10:57:23.540→11:00:07.279，与 `stats.duration` 162804.692 ms 同量级），
`Running 73 tests using 1 worker` → `63 passed (2.7m) / 10 skipped`；`stats`＝**63 expected / 0 unexpected / 0 flaky /
10 skipped**，attempt 级 `results` 展开 **73 行**（`passed` 63／`skipped` 10），**`retry>0` 的行数＝0**（见⑤，链是本轮逐 run 重数过的）。
`e2e-smoke` 仍按设计 `skipped`（不是红）。
CI run `38889773590` 同 commit、**十一 job 全绿**（10:49:42Z→11:00:30Z＝10m48 s），`gitleaks` 10:49:42→10:49:48。
十个点的分布：**876 s（1 条）＋563～656 s（4 条）＋423～492 s（4 条）＋338.152 s（1 条）**
⇒ 这条波形是 **338～876 s 的连续谱**，"档"只是分箱；把任何一箱的边界当"下界"都已被本轮否掉（`f97fd471` 那轮的 491.654 s
当时也被当成过"这一档"）。

**②轮次级共同因子第一次有数**（本轮把同批 CI 侧三条可测安装窗口一起摆出来，同一把尺子）：

| push | e2e `pip-only` | CI `python` | CI `python-container` | CI `eval-offline` | 三条 CI 的极差 | e2e 与 `python` 的相关位置 |
|---|---|---|---|---|---|---|
| `f97fd471` | 491.654 s | 553.0 s | 551.8 s | 612.4 s | 60.6 s＝**10.6%** | 比值 1.125 |
| `fe057e7b` | 655.938 s | 734.3 s | 768.8 s | 738.3 s | 34.6 s＝**4.6%** | 1.119 |
| `f9449ee9` | 606.508 s | 691.1 s | 696.5 s | 695.7 s | 5.4 s＝**0.8%** | 1.139 |
| `9d6e52a5` | 563.546 s | 655.5 s | 651.9 s | 658.1 s | 6.2 s＝**0.9%** | 1.163 |
| `1a5e0452` | 616.407 s | 708.8 s | 713.0 s | 711.4 s | 4.2 s＝**0.6%** | 1.150 |
| `c26703ef` | **338.152 s** | 406.0 s | 386.6 s | 407.8 s | 21.2 s＝**5.3%** | **1.201** |

两件事：
- **同轮之内四条窗口（三台 CI runner＋一台 e2e runner，各自独立 VM）彼此贴合**：CI 三条的极差在 0.60～10.59% 之间，
  六轮里**三轮 ≤0.94%**（`f9449ee9`／`9d6e52a5`／`1a5e0452`）、两轮 4.63／5.31%（`fe057e7b`／本轮）、只有 `f97fd471` 那轮 10.59%；而**跨轮**这三条的均值从 400.2 s 摆到 747.1 s（**347 s**）⇒ 快慢由"**哪一轮**"决定，
  不由"哪台 runner／哪条轨"决定。这是第一百一十九批以来第一次能把"轮次级"这一层单独钉出来。
- **e2e 的 pip-only 与同批 CI `python` 的 pip 窗口在这六轮上的相关系数＝0.997**，比值 **1.119～1.201**
  （CI 装 97 个包／121.8 MB、e2e 装 72 个包／107.4 MB，体积比 1.13 ⇒ 比值就是体积差，不是速度差）。
  ⇒ 上一批"档位差＝吞吐差"的说法本轮升级成**"同一轮里所有安装轨按同一个吞吐整体平移"**，
  这条把候选 B（`--timeout/--retries`）的作用面进一步压小：**它治的是单条流的超时/重试，治不到"整轮一起慢"**。
  能治"整轮"的只有候选 C（换 index）与候选 D 之后才知道的缓存真相。
本轮的工作量再次与前几轮**逐包相同**（`e2e-full`：唯一下载 72 包／**107.4 MB**、`Using cached` **4 包／23.0 MB**；
`python`：97 包／**121.8 MB**、同一组 4 包／23.0 MB），变的只有速度：pyarrow 50.1 MB 本轮 **118.7 s @ 436.9 kB/s**，
上轮同一条 246.2 s @ 229.6 kB/s ⇒ **同工作量、吞吐翻倍、时长减半**，这是"不是包数差、不是缓存差"的最直白一例。

**③pip 缓存：从"命中率低"升级为"条目被冻住"**（本轮第一次读到 Post 步骤，上一批那句"post 步骤可能不进这份日志"是错的）：
四个 python job（`e2e-full`／`python`／`python-container`／`eval-offline`）都打印同一个 key
`setup-python-Linux-x64-24.04-Ubuntu-python-3.11.17-pip-bda709e7…` ＋ 同一个 **`Cache Size: ~146 MB (152908538 B)`**
＋ `Cache restored successfully`，而**每个 job 的 Post 步骤一律是**
`Cache hit occurred on the primary key setup-python-…-pip-bda709e7…, not saving cache.`
⇒ 只要 `cache-dependency-path` 指向的 `python-ai/requirements.txt` 内容不变（最后一次改动是 2026-10-11 `06ea5607`），
**Actions 就不会覆盖这个 key**，那 146 MB 是一份**永不更新的冻结快照**（跨 `f97fd471`→`c26703ef` 六轮字节数逐位相同）。
于是上一批列的候选里"保存步骤没写成功"改判为**"根本没尝试保存"**，而矛盾的形态变成精确的一句：
**恢复进来 146 MB、pip 只认其中 4 个包 23.0 MB（＝快照的 15.8%），其余 107.4/121.8 MB 重新下载**。

③b **恢复本身不是成本项，而且它把两条通道的吞吐差摆到了同一台 runner 上**（本批读到的一条硬数）：
`Cache hit for: setup-python-…`（10:50:19.246）→ `Received 152908538 of 152908538 (100.0%), **87.5 MBs/sec**`（10:50:21.120）
→ `/usr/bin/tar -xf …/cache.tzst`（10:50:21.134）→ `Cache restored successfully`（10:50:21.290）
⇒ 拉＋解 **146 MB 合计 2.04 s**（下载 1.87 s＋解包 0.156 s）。**同一条 job** 上 pip 从 `Looking in indexes:
https://mirrors.aliyun.com/pypi/simple/`（10:50:25.155）拉 107.4 MB 用了 **338.152 s**（≈0.32 MB/s）
⇒ **同一台 runner、同一段流水线，Actions 缓存通道比 index 通道快约 270 倍**。
所以候选 D 要问的**不是**"缓存要不要留"（它只花 2 s），而是"那 123 MB 是什么、为什么 pip 不认"——
**pip 一旦认，等价于把那 123 MB 从慢 270 倍的通道挪到快的那条上**（这条实测不改变候选排序，只是给候选 D 加了一个"值得问"的理由）。

③c **上一批列的两种解释，本批削掉一种**：`pip cache dir` 是 setup-python 自己调的
（`/opt/hostedtoolcache/Python/3.11.17/x64/bin/pip cache dir` 10:50:17.579 → 输出 `/home/runner/.cache/pip` 10:50:19.004），
恢复就解进那个目录 ⇒ **"恢复目录不是 pip 实际查找的目录"在路径层面不成立**；只剩"**快照里的 wheel 与今天这 72 个包不是同一批**"，
而它需要名单级证据。探针（仍是改 workflow、**待拍板**）：安装前 `du -sh /home/runner/.cache/pip`＋`pip cache list`／`info`，
把恢复出的文件名单与本轮 72 个下载包名做集合差。

**④就地纠正上一批并发表的第四列：`java` 那一格量的不是安装窗口。**
`ci.yml:366` 所在的 step 名叫 `Start Python AI service (smoke target)`，它是一块复合脚本
（`pip install -r requirements.txt -q` → `nohup python -m uvicorn app.main:app … &` → `for i in $(seq 1 60)` 的 curl 健康轮询），
`-q` 让 pip **一行日志都不输出**，所以它的安装时长**从日志层面不可测**。本轮该 step 是 10:52:31.082→10:58:28.672＝**357.590 s**，
中间唯一可读的一行是 10:58:28.661 的 `Python AI smoke service healthy (attempt 4)` ⇒ 这 357.590 s 里装着
"安装＋起服务＋至少 4 秒轮询"三件事。于是：
- 上一批那句"被 `java` 覆盖 **76～82%**"要**撤回**——那个百分比是拿复合步骤当分母算出来的；
- 正确的表述是：`java` 的安装起点（10:52:31.082）**落在** e2e 的 pip 窗口（10:50:23.797→10:56:01.949）之内，
  但它与该窗口的重叠只能给界 **0～210.9 s**，给不出读数；
- 结论方向不变：三条可测安装 100% 覆盖已经足够支撑"并发这个自变量没被变过、判为不可测"，
  只是**"合计 5 条并发安装流"要降成"4 条可测＋1 条不可测"**。
- 旁证（**是推断不是读数**）：`java` 装的是与 e2e 同一份 `requirements.txt`，按本轮 e2e 的 338.152 s 推测它也在这个量级。

**⑤两条链本轮都逐 run 重数过，不是沿用上一批的说法**：
- `retry>0` 那条：把 2026-10-14 起 **8 条 push 自触发的 E2E run**（`38568478864`／`38574242376`／`38577643030`／
  `38730439786`／`38731555698`／`38735220260`／`38742412892`／`38889773599`）的 `e2e-results-full` 工件**各下载各摊平**，
  **8/8** 都是 73 行、`retry>0`＝**0 行**、`63/0/0/10`，skip 分布恒为 `plugin.spec.ts` 4／`approval.spec.ts` 2／
  `chat-sse.spec.ts` 2／`write-note.spec.ts` 2 ⇒ 连续**八轮**不靠 retry（上一批写的"七轮"是写作当时的现行值）。
  这八轮的套件时长 **147.452～163.943 s（极差 16.5 s）**，而**同样这八轮**的 pip-only 是
  **338.152～655.938 s（极差 317.8 s＝套件极差的 19 倍）**（高位 876 s 不在这条链里，它是第一百一十六批的
  `38524739182`，那一轮还带着 2 次 flaky）
  ⇒ **抖动全在安装轨，套件轨是稳的**——这条以前只按单轮报过"同量级"，本轮首次有同链跨轮极差。
- `gitleaks` 那条：第一百一十七批修好高熵字面量之后的 CI 序列加上本轮是
  `38530095463`→`38568479058`→`38574242324`→`38577643015`→`38730439984`→`38731555673`→`38735220128`→`38742412916`→`38889773590`，
  九条 run 逐 job 查：**九条的 `gitleaks` job 9/9 `success`，且九条都是十一 job 全绿** ⇒ 现行值＝**第九轮**。

风险口径仍按 **876 s** 算：本轮 job 631 s 对 1200 s 上限的余量是 **569 s≈9m29 s**，
但若 338.152 s 换成 876 s，那条 job＝631 s＋537.848 s＝**1168.848 s≈19m29 s**，余量约 **31 s**
⇒ 与前三批同形：**落在低点更不等于离上限安全**（本轮甚至比"低档"还低 85 s，坏情况余量还是三十秒级），
候选 B／C／D 的排序不变、仍全部**待拍板**。

**本批诚实边界**：
1. 相关系数 0.997 只有 **6 个点**，而且这 6 个点里的四条窗口在时间上彼此重叠 ⇒ 它证到"**存在轮次级共同因子**"这一层，
   **分不清**"镜像源出口节流"与"该时段 runner 池整体拥堵"这两种轮次级解释——但两者都不在候选 B 的作用面上。
2. **338.152 s 是单点** ⇒ "这条波形没有下界"这句话的证据只有这一条；引用时别把它读成"以后都会这么快"，
   坏情况仍按 876 s（约 19m29 s／余量 31 s）算。
3. ④撤回 `java` 那格之后，"每笔 push 并发 5 条安装流"降为"**4 条可测＋1 条不可测**"；`java` 的安装时长
   在这套 workflow 里**结构性不可测**（除非给它单独一步或去掉 `-q`＝改 workflow，待拍板）。
4. "条目被冻住"是日志直读（同一 key＋同一字节数＋`not saving cache`），③c 只把两种解释削到一种（路径层面对得上），
   **冻结快照与今天这 72 个包为什么几乎不相交仍未取证**——剩下那条解释要的是名单级证据，这就是候选 D 要答的具体问题。
   **（第一百二十六批：名单级证据到手，"几乎不相交"被否（70/72 同名），这条边界改写为"**同名同版本为什么等于没命中**仍未取证"；
   同一批也把本条上文"配额驱逐已排除"撤回——前一个 key 已经不在列表里＝驱逐发生过。）**
5. ③b 那句"快约 270 倍"比的是**同一台 runner 到两端的实测**（GitHub 对象存储 87.5 MB/s vs `mirrors.aliyun.com` ≈0.32 MB/s），
   **不能**推广成"换任何通道都快 270 倍"：缓存这条只有**命中**才走得到，而要让那 123 MB 命中就得先付一次上传（本批这六轮的 Post
   全是 `not saving cache`，从没付过，所以上传成本在这套 workflow 里**没有读数**）。它支撑的判断只有一个：
   **慢的是 index 那条通道，不是 runner 的磁盘或网络出口本身**。
   **（第一百二十六批把"没有读数"这半句补上：上传确实付过一次，就在写手那次运行里——
   `tar --posix -cf cache.tzst …`（14:48:51.6727531）→`Cache saved with the key`（14:48:53.0989797）＝**1.426 s**
   （自 `Post job cleanup` 起算 1.578 s），自报 **174.2 MB/s** 上送 152908538 B ⇒ "六轮都没保存"≠"从没保存过"。
   但它同时带来一个新矛盾：**条目只比它 restore 的那份大了 323,566 B（0.21%）**，而那次运行自己下载了 ≈110 MB，
   见下面第一百二十六批那段③b。）**
6. `e2e` 那 **10 条永久 skip**（四条主链路 runner 零覆盖）、`docs/PRODUCTION_OPS.md:50` 仍未勾、
   `chat-sse.spec.ts:24`「CI 上也会红」仍是推断——**三条本批都未变**。
7. ⑤的八轮链仍建立在 docs-only 谱系上、期间没重跑任何代码改动 ⇒ 它钉的是"第一百一十八批那四处监听提前在 runner 上可复现"，
   **不等于套件稳定**。

### 第一百二十六批：候选 D 用**只读通道**跑完一遍（三处撤回＋一个新矛盾，未改 workflow）

上面那段③把候选 D 写成"要在 runner 上加 `pip cache dir/info/list` 取证步＝改 workflow，待拍板"。本批先证明一件事：
**这个候选的大部分问题不用改 workflow 就能答**——`GET /repos/{owner}/{repo}/actions/caches`（分页拉全，本仓 385 条）
给的是**服务端权威数字**：`key`／`size_in_bytes`／`created_at`／`last_accessed_at`，而 `created_at` 精确到毫秒的那条
就是**唯一写手**；再配那份 run 的**分 job 日志**（`/actions/jobs/<id>/logs`，要 `--allow-escape-sequences`），
名单级证据就有了。本机另外量了一次镜像的 HTTP 头（下表）。**全部只读，`.github/workflows/` 一个字没动。**

| 通道 | 读数 |
|---|---|
| 缓存列表（2026-10-16 12:13Z 拉的快照） | **385 条／10,665,585,548 B＝9.93 GB**；pip 家族**只剩 1 条** |
| 唯一条目 | `setup-python-Linux-x64-…-pip-bda709e7…`，`size_in_bytes` **152908538**，`created_at` **2026-10-11T14:48:53.064538Z**，`last_accessed_at` 2026-10-16T12:09:03Z |
| 写手 | CI run **`38145150155`**（`06ea5607`）的 **`eval-offline` job 114486827675** —— 三条 restore 过的 job 里**只有它**打印 `Cache saved with the key`（`python`／`python-container` 只 restore） |
| 上传成本 | `[command]/usr/bin/tar --posix -cf cache.tzst …`（14:48:51.6727531）→ `Sent 152908538 of 152908538 (100.0%), **174.2 MBs/sec**`（14:48:52.9248184）→ `Cache saved with the key`（**14:48:53.0989797**）＝**1.426 s**（自 `Post job cleanup` 51.5210601 起算 1.578 s） |
| 它 restore 的那份 | `Cache restored from key: …-pip-cdb57277…`、`Cache Size: ~146 MB (**152584972 B**)`（三个 job 同一份，13:56:13～14，自报 **143.1 MB/s**） |

**①撤回（第一百二十五批边界 5 的"上传成本没有读数"）**：付过一次，**1.426 s／174.2 MB/s**。上一批说"六轮的 Post 全是
`not saving cache`、从没付过"是把"这六轮没保存"读成"这个条目从没被保存过"——条目就摆在那儿，`created_at` 精确写着谁写的、什么时候。

**②撤回（第一百二十五批那句"`actions 缓存配额驱逐`这条同被排除"）**：它的推理是"若是驱逐，key 不会恒命中、字节数不会六轮不变"，
这句**把两件事混成一件**——"当前条目稳定"不等于"从未驱逐"。证据是 **`cdb57277…` 这个 key 在今天的 385 条里已经不存在**：
它 10-11 还在被三个 job restore（152584972 B），今天整条列表里 pip 家族**只剩 `bda709e7…` 一条** ⇒ 中间**确实删过一条**。
再看体量：**9.93 GB 里 `index-buildkit-*` 占 379 条／9.340 GB＝94.0%**，四条工具缓存（pip 0.142＋maven 0.400＋npm 0.046
＋gitleaks 0.005）合起来 **0.593 GB＝6.0%**；`last_accessed_at == created_at`（写过再没被读过）的有 **294 条／8.67 GB＝87.3%**，
其中 292 条是 buildkit；最老的一条 `created_at` 是 **2026-10-10T05:00:03Z**（六天前的东西已经全没了）。
⇒ 驱逐这条候选**回到盘中并升为最可能动因**；"贴顶"这个说法要留一处边界：GitHub 文档里的仓库级上限数字（10 GB）本仓**未取证**，
我只量到"总量 9.93 GB 且六天前的条目不留"这个形态。

**③撤回（第一百二十五批"剩下的解释只有快照里的 wheel 与今天这 72 个包不是同一批"）**：名单级证据到手，**这条不成立**。
写手那次 run 自己打印的 `Downloading` 去重后 **99 个包名**，与本轮 `c26703ef` 的 `e2e-full` 那 **72 个**做集合差：

- **同名 70 条＝97.2%**（＝明明在名单里、今天仍整包重下）；
- 版本漂移只有 **2 条**：`cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl`、
  `grpcio-1.83.1-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl`（10-11 那次下载的是同包名的别的版本号）；
- 快照侧有而本轮不需要的 **29 条**；
- 本轮那 4 条 `Using cached`（`faiss_cpu-1.14.3`／`uvloop-0.23.0`／`pypdf-6.19.0`／`urllib3-2.8.0`）里，
  **前两条不在 10-11 的 `Downloading` 名单** ⇒ 它们比这次保存更早就在目录里，而它们**偏偏是今天唯二被复用的大件**——
  这条反差本批没解释（见边界 3）。

**口径注意**（别把③读过头）：这里的"快照侧名单"是**写手那次运行的下载名单**，不是归档目录的枚举；归档里到底有什么要 runner 上
`pip cache list` 才数得到。集合差能证伪"名单几乎不相交"，**证不了**"这 70 条的 body 就在恢复出来的目录里"。

**③b 一个新矛盾（本批净新增，未取证）**：条目从它 restore 的 `152584972 B` 长成 `152908538 B`，**只大了 323,566 B＝0.21%**，
而同一次运行打印的 99 条 `Downloading` 里带体积标注的那 11 条合计 **110.6 MB**（pyarrow 50.1 MB 在内）——
**一次下载了上百 MB 的运行，保存出来的条目只长了 0.3 MB**。两种解释都没证据：要么"新下载的 body 没进被归档的那份目录"
（尽管 `pip cache dir` 打印的 `/home/runner/.cache/pip` 与恢复路径对得上，第一百二十五批③c），要么 `size_in_bytes` 记的口径
与"目录内容变化"不同名（tzst 对已压缩的 wheel 几乎不缩，所以 0.3 MB 不像是压缩率造成的）。
⇒ 候选 D 剩下的问题现在**精确成一句**：在 runner 上恢复后打印 `pip cache list` 的**条数**＋`du -sh`，再跑一次 `pip install -vv`
看那 72 条里有没有 `Reusing / Cached response` 行。**这一步之前谁都不许写"缓存没用"或"缓存被 pip 无视"。**

**④镜像侧新鲜度实测（本机→`mirrors.aliyun.com`，2026-10-16 13:05Z 起，`curl -s -o NUL -D -`）**：

| 请求 | 状态 | 关键头 |
|---|---|---|
| `GET /pypi/simple/urllib3/` | 200 | `Cache-Control: max-age=43200`、`Last-Modified: Sun, 11 Oct 2026 12:37:17 GMT`、**无 `ETag`**、`X-Cache: HIT TCP_REFRESH_HIT` |
| 同 URL ＋ `If-Modified-Since: <上面那个 LM>` | **304 Not Modified** | `max-age=43200` |
| 同 URL ＋ `If-None-Match: "any"` | 200（全文 53233 B） | 因为压根没有 `ETag` 可比 |
| `GET …/urllib3-2.8.0-py3-none-any.whl` | 200 | `Content-Length: 135717`、`max-age=43200`、`Last-Modified: Tue, 15 Sep 2026 19:29:34 GMT`、**`ETag: "6aa99c9e-21225"`** |
| 同 wheel ＋ `If-Modified-Since: <它的 LM>` | **304 Not Modified** | — |

⇒ **会话里我曾口头给过的那条机制（"镜像不答 304、所以超过 12 h 必须整包重下、所以恢复出来的 146 MB 结构性不可用"）不成立**，
落文档时按这张表：**index 和 wheel 两条都接受 `If-Modified-Since` 并答 304**，pip 在 12 h 之后**完全可以**靠条件请求复用旧 body。
所以"过期"不能解释③那 70 条整包重下——死因只能在 pip 侧（③b）。**这条是纯撤回，没有新增判断**：它削掉的是"过期"这个候选，
候选 C（换 index）的既有依据（慢在 index 那条通道的吞吐，第一百二十四批④）不受影响。
**边界**：这是**本机落到某个 CDN 边缘节点**的读数，runner 落哪个边缘、边缘回什么 `X-Cache` 未知；pip 用的请求头（`Range`？
带不带 `Accept-Encoding`？）也没量过——所以这张表能证伪"镜像不支持条件请求"，**不能**当"pip 一定会命中"。

**⑤新登记（待拍板）：缓存配额面**。buildkit 层 379 条／9.34 GB 把仓库缓存顶到 9.93 GB，而 87.3% 的字节**写过再没读过**。
②那次驱逐就是这一面的直接后果，后续被驱逐的可能是 `maven`（3 条／0.40 GB）或这条唯一的 pip 条目。
处置候选＝**E：给 buildkit 缓存加保留期／定期清理**（`gh api -X DELETE …/actions/caches/{id}` 是**写操作**，需要单独授权，
本批**没有**执行）。它附带一条**可证伪的预测**：既然③说明这 146 MB 对那 107.4 MB 的下载几乎没帮忙，那么
**pip 条目哪天被驱逐之后，pip-only 时长应当仍落在 338～876 s 这条谱上、不冒新的高档**——
若真冒出显著更高的一档，就说明"缓存没帮忙"这个判断错了，本批③要重开。

**净新增／自我推翻的账**：本批三处撤回全落在**自己上一批的推断**上（①"从没付过上传"、②"驱逐已排除"、③"只剩名单不同批"），
外加一处会话口头机制的落文档纠正（④"镜像不答 304"）；新读数是**写手身份＋上传 1.426 s＋97.2% 名单重合＋385 条／9.93 GB 的配额面＋
镜像条件请求行为**；新矛盾一条（③b 的 +0.21% vs 110 MB）。候选 D 从"待开的取证步"降为"**只差 runner 侧两行打印**"，
候选 B／C 的既有判定不变，**B／C／D／E 仍全部待拍板**。
**风险口径本批未动**：坏情况照旧按 876 s 换掉本轮 338.152 s ＝ 631＋537.848 ≈ **1168.8 s＝19m29 s**、余量约 **31 s**。

**本批诚实边界**：
1. 缓存列表是 **2026-10-16 12:13Z 的一份快照**，`last_accessed_at` 会随每轮 run 变；"pip 家族只剩 1 条"这句只在快照时刻成立。
2. ③的集合差是**下载名单 vs 下载名单**，不是归档内容 vs 需求清单（见③的口径注意）——它只够否掉"名单不相交"这一条。
3. 本轮 4 条 `Using cached` 里两条比写手那次更早（faiss_cpu／uvloop）、两条与那次同批，**为什么恰好这 4 条活着、
   那 70 条同名同版本却不复用，规则没量到**——这就是③b 那两行打印要答的。
4. ④的 HTTP 头来自**本机网络到镜像 CDN 边缘**，不是 runner；pip 的实际请求形态（`Range`/头集合）未量，
   所以这张表**只否掉**"镜像不支持条件请求"，不支撑任何"pip 应该能复用"的正向结论。
5. ②里"仓库级 10 GB 上限"这个**数字**是平台文档口径、本仓未取证；本批量到的只有"总量 9.93 GB＋最老条目只剩六天＋前一个 key 消失"。
6. `e2e` 那 **10 条永久 skip**、`docs/PRODUCTION_OPS.md:50` 未勾、`chat-sse.spec.ts:24` 仍是推断——**三条本批都未动**；
   本批也**没有**任何新的 runner 时长读数（没重跑，只读旧数据），所以十个点的 338～876 s 那条谱**没变长**。

### 第一百二十七批：第二次缓存快照＋`2910f1c6` 自触发那对 run——驱逐机制量到了，但它剪不到工具缓存（一处撤回＋一条新的固定成本）

②那句"驱逐这条候选回到盘中并升为最可能动因"是上一批写的。本批拉了**第二份快照**（`GET /repos/…/actions/caches`，
2026-10-16 **13:54Z**，与 126 那份 **12:13Z** 相隔 1 h 41 m），两份一对，加上 `2910f1c6` 自己触发的那对 run
（CI **`38910654094`**／E2E **`38910654163`**，均 `success`），得到三条净新增：**驱逐是严格 LRU 且与 pip 无关**、
**同一只 wheel 在四台 runner 上耗时几乎相同**、**e2e 轨上有一条 60 秒的固定成本**。全程只读，`.github/workflows/` 未动。

| 通道 | 读数 |
|---|---|
| 快照一 → 快照二 | **385 条／10,665,585,548 B＝9.93 GB** → **397 条／11,131,646,197 B＝10.37 GB**（净 **＋466,060,649 B**、净 **＋12 条**） |
| 这一小时 41 分里删了谁 | **消失 15 条，15/15 是 buildkit 层**（`created_at` 全为 10-13，`last_accessed_at` 距今 **3.00～3.03 天**）；新增 27 条也全是 buildkit（`created_at` 全为 10-16）。**四条工具缓存无一被删** |
| LRU 结构检验 | 被删里**最"新"**的 `last_accessed_at` ＝`2026-10-13T13:52:33.717360Z`；幸存里最"旧"的＝`13:52:34.315094Z`——**相差 0.598 s、无逆序**；"比被删里最新那条还旧却仍幸存"＝**0 条** |
| 谁的时间戳被刷新 | pip `bda709e7…` 12:09:03.300→**13:48:46.104**、maven `d1591b54…` →13:48:43.737、npm `5aa34497…` →13:48:50.420、gitleaks →13:48:08.290（＝本轮那对 run 读的）；另两条 maven 未变 |
| 按新旧累加越 10 GB 的落点 | 从 `last_accessed_at` 最新往旧累加，跨过 10 GB 时落在一条 buildkit（154.1 MB／accessed `2026-10-13T14:19:28Z`）⇒ **四条工具缓存全在切点之内** |
| 写过没读过 | 294 条／87.3% → **305 条／9,779,573,779 B＝87.9%** |

**①撤回（第一百二十六批②"驱逐…升为最可能动因"，只对 pip 这一半）**：驱逐**天天在发生**，但它的对象是 buildkit 层，
而且形态是**严格 LRU**（上表第三行：被删批与幸存批的分界只有 0.6 秒，且 0 条例外）。这对 pip 那条条目是**反向**的——
它每一轮都被四个 job 各读一次，`last_accessed_at` 每轮刷新（12:09→13:48），**在 LRU 下它结构上是最后被剪的那一批**；
126 猜的"下一个被驱逐的可能是 maven 或这条 pip 条目"在本机制下**不成立**。⇒ 于是 126 那个"可证伪预测"（pip 条目被驱逐后
pip-only 应仍落在 338～876 s）**短期内不可用**：等不到它被驱逐。候选 D 剩下的问题不变（还是那两行 runner 侧打印），
但**"缓存条目被配额剪掉"这个解释被摘掉了**——它之所以六轮字节不变，不是没被剪，而是它是最不该被剪的那条。

**②撤回（"贴顶"这个说法）**：本仓已量到 **10.37 GB**，**越过** 126 引的那个 10 GB 文档口径**而条目仍在净增**
（9.93→10.37 GB、385→397 条）⇒ "总量贴到上限就停住"不是这里的形态，形态是**写入时按 LRU 剪旧、总量可以超文档口径**。
候选 E 的表述随之改：它的理由不是"顶到上限会误伤工具缓存"（①已证它误伤不到），而是
**94.3% 的字节属于 buildkit、其中 87.9% 写过再没被读过**＝纯粹的清理收益面。仍是**写操作（`gh api -X DELETE`），要单独授权**，
本批**没有**执行。

**③第十一轮 run 读数（pip-only 第 11 个点，尺子与 124/125 同一把）**：

| 安装窗口（`##[group]Run …` → 下一个 `##[group]`） | 时长 | 带体积标注的下载 | 自报体积和 | ≥20 s 间隔占比 |
|---|---|---|---|---|
| CI `python` | **518.198 s**（13:48:09.99→13:56:48.19） | 97 | 110.6 MB | 5 个／354.8 s＝**68.5%** |
| CI `python-container` | **518.560 s** | 97 | 110.6 MB | 5 个／353.9 s＝**68.2%** |
| CI `eval-offline` | **515.989 s** | 97 | 110.6 MB | 5 个／355.9 s＝**69.0%** |
| E2E `e2e-full` | **440.914 s**（13:48:50.83→13:56:11.74） | 72 | 98.4 MB | 4 个／318.2 s＝**72.2%** |

同轮三条 CI 极差 **0.50%**（连续第四轮 ≤1%）；e2e 那 440.9 s 与三条 CI 窗口**逐条 100.0% 重叠**（第六轮同形）⇒
**并发照旧不可测**；同一条冻结条目 **152,908,538 B** 本轮被四个 job 各自 restore，e2e 一共恢复 **344.9 MB**
（maven 142.7＋pip 152.9＋npm 49.3）却在 440.9 s 里重下 **98.4 MB**——126③b 那个矛盾本轮**没有变软**，它换了一个更尖的形态。

**④包级读数（本批最硬的一条，把 125 的"轮次级共同因子"下沉一层）**：把间隔归给**该行自己那只 wheel**（见下面边界 3 的尺子纠正）
后，同名 wheel 在**四台独立 runner**上的下载时长几乎一样：

| wheel | CI-python | CI-pycont | CI-evaloff | E2E | 极差 |
|---|---|---|---|---|---|
| `pyarrow-25.0.0…` 50.1 MB | 187.0 s | 186.2 s | 187.2 s | 186.0 s | **0.7%** |
| `numpy-2.4.6…` 16.9 MB | 62.3 | 62.2 | 62.3 | 64.2 | 3.1% |
| `pandas-3.0.5…` 11.3 MB | 43.3 | 43.4 | 43.8 | 43.8 | 1.0% |
| `lxml-6.1.1…` 5.2 MB | 17.8 | 17.6 | 17.6 | 18.8 | 6.9% |
| `pydantic_core-2.46.5…` 2.1 MB | 7.4 | 7.4 | 7.4 | 7.8 | 5.8% |

自报吞吐全在 **257～295 kB/s** 这一窄带里。两个后果：
(a) 125 量到的"同轮四条极差 ≤1%"不再是**一轮一个共享系数**，而是**每只大包自己就恒定**——整轮极差是小数点级的；
(b) **"某台 runner 被邻居挤了"这个图景被排除**——若成立，同名 wheel 只会在那一台上变慢，四台同值是反证。
剩下多倍差异的只有 **20 只 ≤5 s 的小包**（如 `isoduration` 2.5→0.5 s、`rpds_py` 4.2→1.7 s），它们的成本在 index 往返而不在体积 ⇒
**候选 B（加超时重试）治不到④这种慢**这条判定不变，且**更硬**了：慢是这台镜像对 MB 级 wheel 的**恒定吞吐**，不是抖动。

**⑤新登记（机制未取证）：e2e 轨上一条 60 秒的固定成本**。把手上 **9 份** `e2e-results-full` 工件（8 轮 runner＋1 轮本机）
按用例摊平，`document-lifecycle.spec.ts :: restore document makes it visible again` 是

```
60.420 / 60.048 / 60.470 / 60.134 / 60.466 / 60.016 / 60.304 / 60.005 / 60.143  s   ← 9/9 全部落在 60.0～60.5
```

极差 **0.77%**，占该轮整条 e2e 墙钟的 **36.6～40.8%**（本轮 60.1 s／148.0 s）。同一文件里用**同一个**
`pollRecycleBinHasDoc`（`helpers.ts:219-236`，默认 180 s／500 ms）的姊妹用例
`delete document moves to recycle bin` 在同样 9 份里是 **12.6～25.7 s**（2 倍振幅）⇒ **这 60 秒不是"等回收站可见"**。
**（这句推论已被第一百二十八批就地收回：它恰恰就是"等回收站可见"，等两次；姊妹条只等一次且相位随机。下同段的"固定成本／常量"措辞。）**
排除项还有两条：`pollDocIndexing` 的 60 s 默认值（`helpers.ts:306`）**不在该用例调用路径**上（只有 `document.spec.ts:50` 传参用到），
Java 侧精确 60 s 的两个定时器（`ApprovalExpiryScheduler.java:24`、`PluginQuotaReservationReaper.java:39`）与文档链路无关，
而删除任务调度器是 **30 s**（`DeletionTaskScheduler.java:28`）。**所以本条只登记读数，不写死因**。
它为什么值得单独记账：这是这一轨上**唯一一条与缓存／镜像／并发都无关**的固定开销——
候选 B／C／D／E 任何一条落地都不会碰它，而它一条就抵得上 125 记的那 31 s 余量的一倍。处置候选：
**A＝先定位**（把该用例拆段计时或落 trace，量出 60 s 落在 restore 前还是清理段，再谈修）；
**B＝挪出主轨**（放进需要显式旗标的用例，主轨只留姊妹那条 12～26 s 的）；
**C＝只登记**（承认它是常量，把它算进 20 分钟上限的分母）。**待拍板，默认 C 之前不碰用例。**
**（第一百二十八批：A 已执行完，落点与死因见该批；B 的前提"它是常量"不成立；新的处置候选在该批末尾另列。）**

**⑥门禁链（本轮）**：CI `38910654094` **十一 job 全绿**、run 13:47:58Z→14:02:40Z＝**14m42s**，`gitleaks` 逐 job 数到**第十轮**；
E2E `38910654163` 的 `e2e-full` success、job 13:48:01Z→14:00:12Z＝**12m11s**、
`63 expected / 0 unexpected / 0 flaky / 10 skipped`，attempt 级摊平 73 行 **`retry>0`＝0 行**（**连续第十轮**），
skip 四条子轨仍是 plugin 4／approval 2／chat-sse 2／write-note 2。

**净新增／自我推翻的账**：撤回两处（126② 的"pip 也会先被驱逐"、以及"贴顶"这个口径），新增**驱逐机制**（严格 LRU＋
工具缓存结构上最后被剪）、**包级恒定吞吐**（把轮次级因子下沉一层并排除邻居假设）、**60 s 固定成本**（9/9、含本机轮）；
pip-only 第十一个点 **440.914 s** 落在 338～876 s 谱内、**谱没变长也没变短**。
（⑤ 的"固定成本"已由第一百二十八批改判为"两腿 × 30 s 调度周期＋自锁相"，两处撤回以该批为准。）
**风险口径不变**：坏情况仍按 876 s 算＝**1168.8 s＝19m29 s／余量约 31 s**；**B／C／D／E 与⑤的 A／B／C 全部待拍板**。

**本批诚实边界**：
1. ①的 LRU 判定是**两次快照之间那 1 h 41 m** 的形态，样本是 15 删／27 增，全在 buildkit 家族内；
   它**只证**"被剪的是最久没被读的、工具缓存因为每轮被读所以排在最后"，**没证**配额数字本身（10 GB 那个数仍是文档口径）。
2. ②改的是候选 E 的**理由**，不是它的优先级；E 仍是写操作、仍需单独授权，本批**未执行任何 DELETE**。
3. **尺子陷阱本批复现过一次并就地纠正**：第一版脚本把两条 `Downloading` 之间的间隔归给了**后一条**那只包，
   于是 pyarrow 被读成 46.7 s、`pydantic_core` 被读成 32.9 s（e2e）；正确归属是**该行自己那只包**，
   末条 `Downloading` 到 `Installing collected packages` 的间隔也归它（pip 先下完全部再装）。④用的是纠正后的尺子，
   与第一百一十八批记的那条"窗口闭合用 `##[endgroup]` 会量出 0.02 s"是同一类错。
4. ④的"同名＝同耗时"是按**文件名**对齐的，`grpcio` 与 `cryptography` 在两侧是**不同版本**（1.67.1 vs 1.83.1、50.0.1 vs 50.0.0），
   已排除在对照表外；四台 runner 是否同一规格未取证，本批只能说"四份独立通道给出同一窄带"。
5. ⑤**没有定位到 60 s 落点**——Playwright JSON 只有用例级 `duration`，没有步骤级时间戳；写完这条别被读成"已知道它为什么是 60 秒"。
   9 份工件里两份是本机轨（`b113_results` 那轮整轨 299 s），它同样 60.4 s ⇒ 这个常量**不是 runner 特有的**。
   **（第一百二十八批把落点定位了：两条删除腿各跨一个 30 s 调度 tick，且被用例自身节奏锁相；"常量"这个措辞在该批被收回。本机轨的 60.4 s 仍成立。）**
6. `e2e` 那 **10 条永久 skip**、`docs/PRODUCTION_OPS.md:50` 未勾、`chat-sse.spec.ts:24` 仍是推断——**三条本批都未动**。

### 第一百二十八批：⑤ 那 60 秒定位完成——不是常量，是两条删除腿各跨一个 30 s 调度 tick，而锁相是它自己造成的

第一百一十七批起这条链路只在 demo-data 上留过证据，⑤是第一百二十七批**新登记**的"机制未取证"，同批又把它写成"一条 60 秒的**固定成本**"。本批执行当时列的
处置 **A＝拆段定位**：在**活栈**上（dev compose 起 mysql8／redis7／minio／etcd／milvus／java／python／worker，
八台全部自报 healthy）用一个**临时、未提交、跑完即删**的探针 spec 逐段计时，再用按秒采样脚本把
"库里那一行何时翻"和"回收站接口何时看得见"分开量。代码、workflow、门禁定义一律没碰。

**读数（全部本批实测）**：

| 通道 | 读数 |
|---|---|
| 静态排除 | `python-ai/app/core/vectorstore/` 四个实现文件按 `sleep\|timeout\|60\|retry` grep **零命中** ⇒ python 侧删除路径里没有等待 |
| 探针单条跑（两轮） | `poll#1` **12.214／12.58 s**、`restore` 0.115／0.016、`get` 0.174／0.083、`delete#2` 0.024／0.018、**`poll#2` 30.401／30.32 s**、`purge` 0.017／0.019、`deleteKB` 0.069／0.017 ⇒ 整条 **45.0／44.4 s** |
| 真实文件顺序跑 | 姊妹条 15.8 s、**restore 60.7 s**、page 那条 3.0 s failed（本批用 `CI=1` 省掉 webServer ⇒ :3000 没人监听，是探针的运行方式不是产品读数） |
| 双腿顺序探针 | T1 `POLL` 10.353 s 收在 **03:58:00.018**；T2 `POLL#1` **29.564 s** 收在 **03:58:30.025**；T2 `POLL#2` **29.928 s** 收在 **03:59:00.123**；T2 `delete#1` 距 T1 poll 结束 **0.795 s**、`delete#2` 距 `POLL#1` 结束 **0.170 s** ⇒ 两腿合计 **59.5 s** |
| 按秒采样（doc 242） | `DELETE` 03:43:06 发出 ⇒ 行**立刻** `status=4`(DELETING)、`deleted=0`、`recycled_at=NULL`；回收站列表在 **03:43:17** 开始含该条；同一秒前后行翻成 `deleted=1 / recycled_at=03:43:25`；回收站请求耗时 **0.218～0.229 s**（5 次）⇒ 不是慢查询。**（那一列的 `t+Ns` 是循环次数不是秒——每轮串行 `docker exec`＋`curl` 约 1.5 s，所以"可见先于翻转"这个顺序既读不出、也不被主张；见下面补证段⑤）** |
| 任务表 | DOCUMENT_DELETE（108／109／111／112）＝ `COMPLETED / step=DOC_NOT_FOUND / step_index=4 / retry_count=0`；DOCUMENT_PURGE（110／113）＝ `COMPLETED / step=COMPLETED / step_index=5`；日志里只有 PURGE 打出"删除任务完成"（03:36:53.976、03:38:54.572），**DELETE 四条一条都没有** |

**死因**：60 s ＝ **2 × 到下一个 30 s tick 的等待**。`DeletionTaskScheduler.java:28` 是
`@Scheduled(fixedDelay = 30_000)`；一条"删除 → 回收站可见"的腿要等这个 tick 去跑
`DeletionServiceImpl.java:381-393`（step 3 `markRecycled`）把 `document.deleted` 翻成 1，而查询侧要求
`d.deleted = 1`（`DocumentMapper.java:69` 的 `countRecycle`、`:78` 的 `selectRecyclePage`）；
`DocumentServiceImpl.java:291-297` 的 `delete()` 只同步写 `status=DELETING`，**不碰 `deleted`**。
腿长＝发出时刻到下一个 tick 的距离 ⇒ 相位随机时是 0～30 s（姊妹条 13 轮 **8.2～30.9 s**、本机单跑 12.2／12.6 s）。
**restore 的两腿都不在随机相位上**：它的每次 poll 恰好在 tick 上返回，而 restore＋get＋delete 只花 0.17～0.80 s，
于是下一次删除仍落在"刚过 tick"的位置 ⇒ 每腿等满一个整周期。**锁相是自维持的**：上一条用例的 poll 结束时刻
就是下一条用例 `delete#1` 的起点前 0.8 s——这也是为什么它在 runner 上 13/13 轮都恰好是 60 秒而不是 0～60 秒的散布。
三条 poll 全收在 **:00／:30** 的格子上，就是这个机制的直接形状。

**两处就地撤回（都写在 127⑤ 原位，不改历史结论的形状只改结论）**：
① "姊妹用例有 2 倍振幅 ⇒ 这 60 秒不是等回收站可见"——**收回**，它正是等回收站可见，等两次；姊妹条只等一次且相位随机，
所以它的带是 0～30 s，restore 的带是 30＋30 s。
② "一条 60 秒**固定成本**／这个**常量**"——**措辞收回**。60 不是常量：同一条用例在没有姊妹条前置的隔离跑法下本机实测 **44～45 s**
（12.2＋30.3）。常量是**周期 30 s**（代码里的 `fixedDelay`），60 是"这条用例结构上要等两次，且两次都被自己的节奏推到整周期"的读数。

**新登记（本批实测出来的缺陷，与 60 秒无关，待拍板）**：DOCUMENT_DELETE 任务的 `step` 标签是错的，且它的完成在日志里**完全不可见**。
链正常跑完 step 0→3 后，`advanceStep`（`DeletionServiceImpl.java:461-466`）把 `step_index` 推到 4、状态推回 `PENDING`，
调度器循环（`DeletionTaskScheduler.java:40-45`）紧接着再进 `executeDocumentDeleteStep`——此时文档已被 step 3 逻辑删除，
`selectById` 返回 null ⇒ 落到 `:356-361` 的 not-found 分支，把 `step` 覆盖成 `DOC_NOT_FOUND`、状态置 COMPLETED，
**而这条分支不调 `completeTask`、不打日志**。PURGE 不受影响是因为它入口用 `selectIncludingDeleted`（`:400`）。
两个后果：(a) `deletion_task.step` 对**所有成功删除的文档**都是假的（本批 4/4 如此）；(b) 运维在日志里看不到文档删除完成，
只能靠查表。处置候选：**甲＝让 index==4 的收尾走 `case 4`（或让 not-found 分支也调 `completeTask` 打日志）**，纯 java 侧，
改后要重跑 Java 全量测试与覆盖率口径；**乙＝只登记**；**丙＝顺手一并处理 `application.yml:124` 的 `python-ai.timeout: 60000`——
本批按 `@Value` 扫过全仓 java 侧，`python-ai.*` 被读的只有 `internal-token／base-url／callback-secret／engine.url／callback-base-url`
五处，`python-ai.timeout` 零消费者 ⇒ 与第一百一十六批那条 `CALLBACK_SECRET` 空转声明同族**。**均待拍板，本批未动任何代码。**
**（第一百二十九批：甲已落地——取的是括号里那半，两条 not-found 分支改调 `completeTask`；乙随之作废；丙仍未动。
读数、选择理由与两条新登记见下面"第一百二十九批"段。）**

**60 秒本身的处置（旧的 A/B/C 已失效，换一批新的）**：**A＝用例侧去掉第二腿**（restore 的清理段不再第二次 delete→poll，
直接 purge 或交给 `apiDeleteKB` 级联）⇒ 省约 30 s，零生产风险；前提待核验——purge 在 `deleted` 尚未翻转时是否幂等
（纸面可行：PURGE step 0 用 `selectIncludingDeleted`，**未实测**）。
**（补证推翻这句的一半：窗口内 purge 是被拒而不是幂等，实测 HTTP 400；见下面"第一百二十八批·补证"段。
A 因此精确成 A1＝只去掉第二次 poll＋purge，保留 `delete#2`＋`apiDeleteKB` fire-and-return。）**
**B＝生产侧把"进回收站"改同步**（`delete()` 事务里直接写 `deleted=1／recycled_at`，状态机只管向量与分块清理）
⇒ 两腿都归零（省 ≈60 s），语义上"删除即可见"更像用户预期，但这是**用户可见的行为变更**，并且让
`DocumentStatus.DELETING` 这个中间态失去存在意义。
**（补证：这条在本仓已有现成先例——`KnowledgeBaseServiceImpl.java:219-220` 的 KB 删除就是在请求内同步 `markRecycled`，
实测 HTTP 200／0.223 s 且调用瞬间 `deleted=1`，不经调度器。所以 B 不是新设计，是"让文档侧向知识库侧看齐"，
代价与先例一起变小；但仍是用户可见行为变更，仍待拍板。）**
**C＝缩 tick 或改事件即时触发** ⇒ 影响所有删除链的延迟，收益不匹配。
**D＝只登记**（现已取证）。**推荐 A1**，但**本批未动任何用例与生产代码**，等拍板。

**账**：风险口径不变——坏情况仍按 pip-only **876 s** 算＝**19m29 s／余量约 31 s**；本批这条与候选 B／C／D／E 无交集，
A 落地最多让 e2e 轨少 30 s（约 0.4%）。**待拍板清单**：候选 B／C／D／E、本批 60 秒的 A／B／C／D、新缺陷的甲／乙／丙。
**（第一百二十九批更新这一格：新缺陷的甲已落地、乙作废、丙仍在；60 秒四条与候选 B／C／D／E 一律未动，另新增两条待拍板＝
"10 条 `@Scheduled` 与 webhook 重试共用 2 线程池"与"`KB_DELETE` 无创建点"。）**

**本批诚实边界**：
1. 本机活栈与 runner 拓扑不同（本机有 Milvus＋worker，runner 两者皆无），但两处的 restore 读数同带
   （本机文件顺序 **60.7 s**；runner 13 轮 60.0～60.5 s）⇒ 结论只依赖"调度器 `fixedDelay=30_000`"这个代码常量，不依赖拓扑。
   **没有**在 runner 上量过分段：runner 上 `trace: 'on-first-retry'` 对绿的用例不产 trace，后台 `&` 步骤的 stdout 也不进 job 日志。
2. tick 相位落在 **:00／:30** 只有 **n=3** 的一次观察；"周期 30 s"另有代码依据，但**一轮工作超过 30 s 时会不会漂移**本批未测。
   **（补证把翻转样本从 3 个加到 5 个，并确认了周期：库内两个 `recycled_at` 是 04:18:31 与 04:19:01＝整 30 s（同一把钟）。
   但绝对相位本批不能定——宿主 Node 钟与 JVM 钟的 skew 未校，详见该补证段④；"一轮工作超过 30 s 会怎样"仍未测。）**
3. 分段计时来自**临时未提交的探针 spec**（逐段复刻两条用例，含 `test.setTimeout(480_000)`），跑完已删除，仓库 `e2e/` 未留插桩。
   第一次探针跑失败是我自己的环境口径错：本机 java 容器的 `ADMIN_PASSWORD` 不是 e2e 那份 `admin123`，
   `ensureAdmin`（`helpers.ts:320-330`）先登录失败、回退去注册就撞 1003——**不是产品缺陷**。凭据值全程未打印，只从容器 env 取进变量。
4. 探针里 `poll#1` 与 `poll#2` 之和（本机单跑 42.6 s）小于两腿的理论上限 60 s，因为第一腿落在随机相位；
   这条差异本身就是锁相假设的**可证伪点**，本批用"文件顺序跑 ⇒ 60.7 s"正面验掉了。
5. "13 轮"是把手上 18 份 `e2e-results*.json` 按 `(姊妹, restore)` 时长对去重得到的（`b125_ch_*` 与
   `b123_art_*`／`b124_art_*`／`b125_art_*` 是同批 run 的重复下载）。127 记的 9 份是当时手上的子集，两组读数不冲突。

### 第一百二十八批·补证：处置 A 的前提实测被否掉一半，顺带量到"文档进回收站"与"知识库进回收站"的 30 秒不对称

仍然只在**本机活栈**取证，代码、workflow、门禁定义一律没碰；探针是 scratch 目录里的临时脚本（不入库、跑完留输出档）。

① **窗口内 purge 不是幂等，是被拒**：`delete#2` 发出后 0.4 s（此时 `status=4／deleted=0`）调 `DELETE /document/{id}/purge` ⇒
**HTTP 400**、`{"code":400,"message":"回收站中不存在该文档"}`、0.228 s，任务表里**没有**新增 `DOCUMENT_PURGE` 行。
死因在 service 入口而不是链：`DocumentServiceImpl.java:357` 要求 `deleted==1`，`DeletionServiceImpl.java:400` 那条
"入口用 `selectIncludingDeleted`"的免疫**根本走不到**。⇒ **上一段 A 里"直接 purge"那一半作废**，
我 128 写的"纸面可行"是把链的性质误安到了入口上——**就地纠正**。A 精确成 **A1＝去掉第二次 poll＋purge，
只保留 `delete#2`＋`apiDeleteKB` fire-and-return**。

② **A1 的测试卫生面成立**：不 poll 也不 purge 之后，那条 `DOCUMENT_DELETE` 任务照旧在下一个 tick 跑完
（`delete#2` 04:18:32.6 发出 → `recycled_at=04:19:01`，`status=0／deleted=1`）；采样里这一行是从
`PENDING/idx=0` **直接**跳到 `COMPLETED/idx=4` 的——一次 tick 内循环把 step 0→3 全推完
（`DeletionTaskScheduler.java:40-45`＋`MAX_STEPS_PER_TASK=10`），所以中间步（向量／分块／索引任务）**没有可观测的停留**，
本补证**不**主张"看到它们逐步发生"。75 s 采样里**没有** `FAILED`、`retry_count` 恒为 0；KB 侧调用瞬间就 `deleted=1`（见③）
⇒ 文档与知识库在列表里都不可见，残留是**回收站里的行**而不是活行，7 天保留期由 `RecycleBinCleanupScheduler` 收。
**代价说白**：A1 让这条用例不再留下"已 purge"的状态，runner 上是每轮新增一行回收站记录（DB 一次性，无影响），
本机 dev 库则会攒——那是本机的事，不是产品的。

③ **新发现的不对称（与 60 秒无关，值得单独记账）**：`DELETE /knowledge-base/{id}` 是**同步**的——
`KnowledgeBaseServiceImpl.java:219-220` 直接在请求里 `markRecycled`，实测 HTTP 200／0.223 s、返回后首条查询即
`deleted=1`，任务表里**没有任何 KB_DELETE 行**（`deletion_task` 按 `target_id IN (doc, kb)` 查，四条全是 DOCUMENT_*）。
同一个"删除"动词，文档侧要等 30 s tick、知识库侧 0.2 s 就进回收站。
⇒ 这条**改写 B 的性质**：B 不再是"新设计"，而是"让文档侧向仓内既有先例看齐"，风险与理由都随之变小；但仍待拍板。

④ **周期与格子的读数**：`delete#1` 04:18:12.922（宿主钟）→ 回收站可见 04:18:31.328（18.4 s）；`delete#2` 04:18:32.617 发出，
库里 `recycled_at=04:19:01`（翻转落在宿主钟 04:19:01.383 的 `del=0` 与 04:19:03.535 的 `del=1` 两次采样之间）。
**同一把钟（库内 `recycled_at`）给出的两个翻转是 04:18:31 与 04:19:01＝相隔整 30 s** ⇒ 周期这条最硬。
但这两个翻转的**秒位是 :31／:01**，而第一百二十八批那三次 poll 收在 **:00.018／:30.025／:00.123**（宿主 Node 钟）——
两个说法不冲突，但**本机没有校过宿主钟与 JVM 钟的 skew**，所以不能说"格子从 :00/:30 平移到了 :31/:01"，
只能说"**周期 30 s 有同钟依据，绝对相位不能由本机定**"。
一个**未实测**的解释摆在这里供后续核：`fixedDelay` 是"上次执行**结束后**再等 30 s"，空闲轮每次多耗 ε（几十毫秒），
半个钟头累积 60 个周期就能漂到秒级——这条要判需要在同一次探针里连数多个 tick，**本补证没做**。
上面边界 2 的"会不会漂移"因此改成"**周期 30 s 已由同钟读数确认，相位漂移机制未取证**"。

⑤ **另一处尺子自我纠正**：第一百二十八批"按秒采样（doc 242）"那一行里"列表 03:43:17 起含该条、行 `recycled_at=03:43:25`"
**顺序读不成**——那个循环每轮串行做 `docker exec mysql`＋`curl` 两次调用，**实测约 1.5 s 一轮**，所以 `t+Ns` 是**循环次数不是秒**，
不能用来判"可见先于翻转"。本补证的探针把时间戳全部改成 `date -u +%T.%3N` 现取，才第一次给出可信的 30.1 s 周期读数。
**这条纠正不推翻死因**（30 s 周期另有代码依据 `DeletionTaskScheduler.java:28`），只否定那一次采样的**次秒级顺序**。

**账**：补证后待拍板清单不变，只是 **A 换成 A1**、B 的性质变了：**候选 B／C／D／E、60 秒的 A1／B／C／D、新缺陷的甲／乙／丙**。
风险口径仍按 pip-only **876 s**＝**19m29 s／余量约 31 s**。**本批与补证都没动任何代码、用例或 workflow，也没有写操作。**

### 第一百二十九批：缺陷"甲"落地——本会话第一条动生产代码的批次（红判据先行，活栈取到"改前根本没有的完成日志"），顺带登记两处新暴露面

**动了什么**：`DeletionServiceImpl.java` 的两处 not-found 分支各 −4/+1 行（`executeKbDeleteStep` `:138-142`、
`executeDocumentDeleteStep` `:352-356` 由"自己写 `status`/`step` 再 `updateById`"改成调 `completeTask`（`:464-470`））＋
`DeletionServiceImplTest` 新增 2 条单测（+102 行）。门禁定义、`.github/workflows/`、`e2e/`、python 侧**一字未碰**；
Python 计数 **2101 不变**，Java 计数 **718→720**。

**红判据先行**：`mvn test -Dtest=DeletionServiceImplTest` 改前 `Tests run: 8, Failures: 2`，
两条失败消息就是缺陷形状（`expected: <COMPLETED> but was: <DOC_NOT_FOUND>`／`<KB_NOT_FOUND>`），改后 **8/8 绿**；
`mvn -q spotless:check` **EXIT=0**；全量 `Tests run: 720, Failures: 0, Errors: 0, Skipped: 1`／BUILD SUCCESS。
**没有**为了让测试过而放宽任何选择器或门——两条新断言写的是"终态应当是 `COMPLETED`"，正是第一百二十八批在库里读到的假标签的反面。

**取的是甲的哪一半，为什么**：甲原文有两半（"让 index==4 的收尾走 `case 4`"或"让 not-found 分支也调 `completeTask` 打日志"）。
读全两条链的形状之后前半在两侧代价都更大：DOCUMENT_DELETE 有 `case 4 -> completeTask`（`:390`）但**正常链到不了**
（step 3 的 `markRecycled` `:377-388` 已把 `deleted` 翻 1，下一圈入口 `selectById`（`:353`）返 null）；
KB_DELETE 连 `case 8` 都没有（`case 7 -> logicalDeleteKnowledgeBase` `:153`／`:345-347`，之后 `default -> throw`）。
而后半是**仓内既有写法**——`executeKbPurgeStep`（`:160-164`）／`executeKbDisableStep`（`:225-229`）／`executeDocumentPurgeStep`（`:395-399`）
的 not-found 分支本来就在调 `completeTask`。⇒ 本批是把两条漏配的分支并进惯例，不新增抽象。
`case 4 -> completeTask`（`:390`）**保留未删**（异常形状"行还在、idx 已到 4"仍可达），本批不主张任何死代码清理。

**活栈读数**（dev 栈＋重建 java 容器；`docker compose build` 第一次 48 ms 打印 "up to date"＝没真构建，`--progress=plain` 重跑量到 68.7 s 真构建）：
`id=147 DOCUMENT_DELETE` 从 `t+1 PENDING/step=-/idx=0` 到 `t+12 COMPLETED/**step=COMPLETED**/idx=4/err=-`
（第一百二十八批同一条形状是 `step=DOC_NOT_FOUND`）；日志新增 **`2026-10-18 04:45:13.372 [webhook-retry] [] INFO c.h.service.impl.DeletionServiceImpl - 删除任务完成: taskId=147, type=DOCUMENT_DELETE, targetId=258`**
＝改前该类型**零条**完成日志 ⇒ 后果 (a) 标签与 (b) 可观测性同时闭合。delete→回收可见 16.4 s 只是 tick 相位落点，**不构成新机制读数**。

**计数门抓到的是我**：改后首跑 `scripts/static-checks.py` EXIT=1，`✗ README.md 测试计数漂移（badge）: java: 文档 718 ≠ 实测 720`
（门在 `check_test_counts()` `scripts/static-checks.py:343`，判据 `:360`）⇒ 同步 `README.md` 四处（`:15` badge、`:37`、`:47`、`:241`）
与 `docs/ROADMAP.md:16` 后 EXIT=0、检查 1–21 逐条 `[ok]`。runner 侧的 `java` job 跑的是同一条命令（`.github/workflows/ci.yml:351`
`mvn --batch-mode test`），所以推送后应数到的判据就是 **720／0 失败**。

**新登记之一（不是门禁缺陷，是运行时暴露面，待拍板）**：完成日志打在线程 **`[webhook-retry]`** 上，而调用来自 `@Scheduled`
（`DeletionTaskScheduler.java:27-29`）。该线程名属于 `WebhookConfig.java:51-57` 的 `ScheduledExecutorService` bean
（`Executors.newScheduledThreadPool(2, …)` `:53`）；全仓该**类型的 bean 只有这一个**（其余五处是组件内 `private final` 字段：
`AgentTaskRecoveryScheduler.java:24`／`AgentTaskWorkerScheduler.java:25`／`PromptTestSetRunWorkerScheduler.java:59`／
`ApprovalEventSseManager.java:43`／`TaskEventSseManager.java:43`），无 `TaskScheduler` bean、无 `spring.task.scheduling.*`
⇒ `@Scheduled` 的兜底调度器就是那 2 条线程，**10 个 `@Scheduled` 方法**（`AgentAlertScheduler:27`／`AgentStatusEventCleanupScheduler:24`／
`ApprovalExpiryScheduler:24`／`DeletionTaskScheduler:28`／`DocumentIndexRecoveryScheduler:20`＋`:34`／`OrphanCleanupScheduler:39`／
`PluginQuotaReservationReaper:39`／`RecycleBinCleanupScheduler:33`／`VectorReconciliationScheduler:28`）与 webhook 重试共用。
叠加 `DeletionTaskScheduler` 一圈内对每个 pending 任务**串行**最多 10 步（`:23`／`:40-41`）、向量步"同步调 Python（最长 120s/次）"（`:111`、注释 `:123`）
⇒ 一个 tick 可把一条线程占住分钟级。**这条给第一百二十八批那把"tick 周期／相位"尺子加了一个未测的干扰项**（若某轮工作超 30 s，
tick 延后不是随机漂移而是被同池任务挤住）。候选：**甲＝显式配 `TaskScheduler`（`spring.task.scheduling.pool.size` 或自建 `ThreadPoolTaskScheduler`）**；
乙＝让该类型 bean 不再唯一（**排除**：Spring 回到默认单线程，10 条调度挤 1 条，比现状差）；丙＝只登记。**本批未动任何配置。**
证据分层：线程名＝实测、bean 唯一＝grep；"Boot 自动配置被 `@ConditionalOnMissingBean`（含 `ScheduledExecutorService`）抑制"是**纸面推断，未在本机核对 Boot 版本源码**。

**新登记之二（纯登记）**：**`KB_DELETE` 没有创建点**——main 侧 `deletionService.createTask(…)` 的全部调用点是
`DocumentServiceImpl.java:295`／`:364`、`KnowledgeBaseServiceImpl.java:170`／`:277`、`RecycleBinCleanupScheduler.java:39`／`:47`，
类型里没有 `KB_DELETE`；该名字只出现在 `DeletionTask.java:22`、`DeletionService.java:15` 的注释与 V3 迁移列注释里
⇒ 本批 KB 半边是**潜伏修复、只有单测覆盖**，活栈上不可能有它的读数（不主张端到端验证过）。删除它属于死代码清理
（`docs/CLEANUP_BACKLOG.md` 现行口径"只登记不删除"），待拍板。

**账与本批边界**：128 的**甲已落地／乙作废／丙（`application.yml:124` `python-ai.timeout: 60000` 零消费者）仍在**；
60 秒的 A1／B／C／D、候选 B／C／D／E、`docs/PRODUCTION_OPS.md:50`、10 条永久 skip、`chat-sse.spec.ts:24` 全部未动。
风险口径不变（坏情况仍按 pip-only **876 s**＝**19m29 s／余量约 31 s**；本批改动不在 e2e 轨上）。
**没重跑 e2e** 的理由是取证面的：`deletion_task.step` 在 main 侧零读取者（写点只剩 `advanceStep` `:457-458` 与 `completeTask` `:466`，
`getStep()` 的读只出现在 `DeletionServiceImplTest` 的 9 条断言里，`mapper/*.xml` 无按 `step` 过滤的 SQL）⇒ 不可能改变用例断言；
而本机跑 e2e 会把明文 `ADMIN_PASSWORD` 写进 `e2e/test-results/**/error-context.md`（gitignore 但不自动清），不制造这个副作用。
覆盖率口径未重测（只跑 `mvn test`，没跑第九十四批含 IT 的 jacoco 尺子）。**runner 侧零读数**：本批未 push。

### 第一百三十批：python job 那条唯一红——用**真用例**在容器里把它打红了，但**死形与 CI 不同形**（一处自我撤回＋一条被代码排除的可能）

**起因（runner 读数，CI run `39099667904`／job `117593162392`，`0b8025eb` 自触发）**：`python` job 十一条里只红一条，
红的是 `tests/test_sandbox_fd_budget.py::TestEndToEndWithLoadedParent::test_execute_in_sandbox_survives_fd_loaded_parent`，
日志原文 `error_code=plugin_timeout error=插件执行超时: 20s`、`duration_ms=20009.35`，套件 `1 failed, 2220 passed, 7 skipped in 110.26s`，
覆盖率 `Required test coverage of 74% reached. Total coverage: 77.09%`（棘轮没过线，红与它无关）。
批次归因先做：`git show --name-only 0b8025eb | grep -c ^python-ai/` = **0** ⇒ 第一百二十九批一字未碰 python 侧，
而它之前该 job 连绿十二轮 ⇒ 这是一次单点复发，不是新代码引入的确定死因。
另有一条尺子：十二份绿轮的 `--durations=20` 里**从没出现**这条用例 ⇒ 它常态用时 <0.24 s，20.009 s 是**挂住**，不是慢。

**先把"死形"这把尺子立起来（读码得到的排除，不是猜）**：`sandbox_runner.py:545-604` 的父侧控制流里，
`plugin_timeout`（`:562-572`）**只有一条路**能产生＝`worker.join(timeout=20)` 之后仍 `worker.is_alive()`；
子进程若已经死了，返回的是 `plugin_process_error`（`:575-580`，`exitcode != 0`）、`plugin_no_response`（`:594`，`poll(1.0)` 无数据）
或 `plugin_comm_error`（`:599-604`，`EOFError`／`JSONDecodeError`）。⇒ **CI 那次的子进程活了满 20 s**。
我先前设想的"子进程死在发 payload 之前，所以父侧只剩超时"**被这段码排除**，本批就地撤回该设想，不再复述。

**容器内把这条断言真打红（同一份测试文件、CI 的文件序，`ghcr.io/xiaodu55/hfusionhub-python:latest`＋dev 依赖）**：

| 跑法 | 结果 | setup 时父进程读数 |
|---|---|---|
| 单跑 `tests/test_sandbox_fd_budget.py` | **11 passed** | VmSize **120,488 kB** |
| `tests/test_milvus_tenant_migration_real.py` 在前、再跑上面那份 | **1 failed / 14 passed**，死形 `plugin_execution_error`／`duration_ms=76.44`／`error=error return without exception set` | VmSize **7,360,404 kB**、threads 17、fds 37 |
| 同上再加 CI 独有的 `--cov=app` | 仍红，`duration_ms=118.2`、**`error=''`（连消息都是空）** | VmSize 7,366,212 kB |

文件序这一条不是挑的：`ci.yml:177` 的命令是 `pytest -q tests`，dev 依赖里没有 pytest-xdist ⇒ 单会话按字母序收集，
`test_milvus_*` 恒在 `test_sandbox_*` 之前。⇒ **同一条断言、真用例、CI 文件序下能确定打红**，
但**死形不同**（76～118 ms 的 `plugin_execution_error` vs CI 的 20,009 ms `plugin_timeout`）
⇒ 我复现到的是这条断言的一个**充分因**，**不等于** CI 那次的死因；coverage 的 `settrace` 被 fork 继承这一条已量过、不是那 20 s。
**CI 那 20 s 的机理本批仍是未取证**。

**单变量实验（把"线程"从因里摘出去，全部在容器、`execute_in_sandbox` 原函数）**：

| 实验 | threads | 父 VmSize (kB) | `memory_mb` | 结果 |
|---|---|---|---|---|
| 全新解释器 | 1 | 18,536 | 256（缺省） | success `79.01 ms` |
| held mmap 抬 VSZ、无 Milvus | 1 | 3,033,192 | 256 | `plugin_execution_error` `64.69 ms` |
| held mmap 抬到 7.5 GB | 1 | 7,555,176 | 256 | `plugin_execution_error` `19.81 ms` |
| 真 MilvusLite 客户端（泄漏，grpc 线程活着） | 4 | 5,543,608 | **8192** | **success `40.92 ms`** |
| CI 文件序的那条用例 | 17 | 7,360,404 | 256（用例缺省） | 红 |

⇒ 决定性变量只有一个：**`RLIMIT_AS` 在 fork 之后设成 `memory_mb`（`sandbox_runner.py:126`，缺省 256＝`:43`）对上了子进程继承的 VSZ**。
grpc 线程既非必要（threads=1 无 Milvus 照样死）也非充分（threads=4／17 在放开 `RLIMIT_AS` 后正常成功）。
fork 本身也不是那 20 s：`Process.start()` 的墙钟在 VSZ 7,555,176 kB 下量到 **0.001 s**。

**就地撤回两条我自己的口径**：① 第一百三十批中途把这条红写成"MilvusLite 泄漏 grpc 线程 × fork 不安全"——
对上表所复现的那个死形而言线程已被排除，标题与结论一起改；② "绿轮日志里没有那行 glog"当证据——
绿轮日志里 `"Captured stderr"` 区块数＝**0**（pytest 只在失败时打印），观察面根本看不见它，
与第一百二十三批那个"零重叠对照组"是同一类错觉（判据面只放在自己看得见的轨道里）。
边界写清楚：`fork_posix.cc:71 Other threads are currently calling into gRPC, skipping fork() handlers` 在 CI 红轮和我的红跑里**都**出现，
它是否构成 CI 那 20 s **挂起**的机理，本批**没测**、不作主张。

**生产暴露面（登记为缺陷丁，含 reachability 的实测边界）**：
`runner_mode` 的缺省是 subprocess 且写了两处——`sandbox_runner.py:50`（`SubprocessConfig`）与 `sandbox.py:66`（`RunnerConfig.mode`）；
`registry.py:76` 只在 manifest **写了** `runner` 时才覆盖，省略即落缺省。
两份随镜像发布的新建 manifest 都显式 `container`：`plugins/bid_docx/hfusion_plugin.json:23-26`、`plugins/bid_quote/hfusion_plugin.json:23-26`，
Java 种子同源：`V73__bid_plugin_builtins.sql:31`／`:68` ⇒ **今天上架的插件不走 fork 档**，本批不主张"生产正在坏"。
但安装入口 `api/plugin_admin.py:102` 读的是 wheel 自带 manifest，而仓内**没有**任何"生产必须 container"的门
（`require_container|PLUGIN_RUNNER_MODE|force.*container` 在 `python-ai/app` 零命中）⇒ 省略 `runner.mode` 的第三方 wheel 就落到 fork＋`RLIMIT_AS`。
活服务侧量到的可用底数：`docker exec hfusionhub-python` 的 pid 1（`python -m app.main`）`VmSize=2,978,184 kB`（≈2.84 GB）
⇒ 在这个进程里 fork 出的子进程，256 MB 额度下**任何新映射即失败**。
证据分层：2.84 GB＝活进程实测；"插件因此失败"＝**同形状的全新解释器**里测的（VSZ 2,914,744 kB、fds 6、插件 `import numpy` → `[Errno 12] Cannot allocate memory`），
**没有**在活栈上注入插件调用（那要往活栈写插件文件），故不主张端到端。

**观测面缺口（缺陷戊，读了码也跑了码）**：子进程把 `traceback` 放进 payload（`sandbox_runner.py:426`），
父侧只取 `success`/`data`/`error`/`error_code`（`:586-595`）⇒ 栈在 CI 与生产里都被丢；
上面那张表里 `--cov` 那行 `error=''` 是同缺口的另一面（子进程连异常消息都没了，父侧再丢栈 ⇒ 只剩"超时"两个字）。
核查方式＝同一份 `_subprocess_worker` 直接起 `Process` 收全 payload，`keys` 含 `traceback` 而 `execute_in_sandbox` 的返回对象里没有该字段。

**测试隔离（缺陷己）**：`tests/test_milvus_tenant_migration_real.py:26-49` 的 fixture 只 monkeypatch 路径＋`factory.reset_vector_store()`，
不释放 MilvusLite 客户端／本地服务器；`release_all|release_server` 在 `python-ai/app` 与 `python-ai/tests` **零调用点**（grep 过），
只有 milvus-lite 自己的 `server_manager.py:101`／`:108` 在解释器退出时才跑 ⇒ 会话内一次 `ensure_collection()` 就把 VSZ 抬到 5.5 GB、threads 抬到 4。
这条不是生产缺陷（生产路径的 store 常驻是有意的），是**用例之间互相污染**，而它正是上表第二行的触发器。

**处置（三组选项，全部待拍板，本批未动任何代码）**：
- 测试面 **A1**＝给那条 e2e 用例显式 `memory_mb=8192`（本文件 `:50-52` 早已为观测用例写过同一理由，`_OBSERVE_CONFIG_KWARGS`），
  fd 断言与覆盖率棘轮都不动；代价＝把缺陷丁在这条用例上**永久掩盖**。**A2**＝修 fixture 的释放（把会话 VSZ 拉回），
  去掉的是触发器而不是阈值。**A3**＝只登记，CI 继续偶发（13 轮 1 次）。
- 生产面 **B1**＝`RLIMIT_AS` 改成"继承量＋预算"，与第九十七／九十九批对 `RLIMIT_NOFILE` 的修法同形（仓内先例 `_apply_fd_budget` `:91-104`）。
  **B2**＝把 subprocess 档从生产摘掉（缺省改 container＋安装期强制），是安全姿态变化。**B3**＝fork 换成新解释器（`posix_spawn`／`subprocess`）
  让继承面归零，改动最大。**B4**＝只登记。
- CI 那 20 s 的取证 **C1**＝在 `ci.yml` 的 python 步骤里加一条一次性诊断（打印 pytest 父进程 VSZ／threads，不放宽任何门）；
  **C2**＝等自然复发；**C3**＝不做。
  **推荐 A2＋B1**：A1 单独做等于把刚抓到的生产缺陷按下去，C 档与 A／B 相互独立。

**账与本批边界**：docs-only——`.github/workflows/`、`e2e/`、`python-ai/app`、`python-ai/tests` 一字未碰，Python 计数 **2101 不变**，
runner 侧零新增读数（本批未 push）；风险口径不变（坏情况仍按 pip-only **876 s**＝**19m29 s／余量约 31 s**）。
既有待拍板清单全部未动：128 的 60 秒 A1／B／C／D、129 的调度器共池与 `KB_DELETE`、候选 B／C／D／E、`docs/PRODUCTION_OPS.md:50`、
10 条永久 skip、`chat-sse.spec.ts:24`。取证用的容器 `b130fd` 与其可写层已随本批结束删除，仓库外脚本未进仓。

## 检查 20：e2e 轨的后端特性开关契约（第一百一十三批）

第一百一十一批把前端进程补上之后，`Run full E2E suite` 从 `35 失败 / 28 通过` 变成
**`4 失败 / 59 通过 / 10 跳过`**（run 38343229817 的 `e2e-results-full` 工件，合计 73 与 README
口径一致）。三条 demo-data 的报错是同一条：`page.waitForResponse: Timeout 10000ms exceeded`
（`demo-data.spec.ts:23`、`:40`、`:72`），第 4 条是 `getByText('搜索知识库')` 找不到元素。

解包 `playwright-traces` 里三条 demo-data 的 retry1 `trace.zip` → `0-trace.network`，请求**确实发出去
了，而且回来了**，每条留下同一个响应体：

```
200 http://localhost:3000/api/demo/import
{"code":403,"message":"演示数据功能已关闭（DEMO_ENDPOINTS_ENABLED=false），如需使用请在环境配置中开启",…}
```

三条的 traceId 分别是 `d36804ec03644249b011b204d5d97713` / `ac1ca5cb04b74d84b64e47721f767fce` /
`57e397cc38ac42c6adee633a75fafd49`。根因是键没声明：`application.yml:177` 写
`endpoints-enabled: ${DEMO_ENDPOINTS_ENABLED:false}`，`DemoController.java:39` 按
`@Value("${app.demo.endpoints-enabled:false}")` 读，`:44` 在未开启时 `R.fail(403, …)`。
**HTTP 状态仍是 200**，所以步骤不红、探针不红、`Wait for Java backend` 绿，死的只有用例读到的语义。
dev 侧一直是开的（`docker/docker-compose.yml:272` 与 `docker/.env:24`），只有 `e2e.yml` 的两个 java
env 块（`:84-105`、`:236-257`）没带这个键——**"配置写了、容器里没有实体"（检查 18）的同族**，
只是这一族是"开关默认关、CI 没显式开"。

**但开关不是这三条当时的死因，只是最外那一层。** 同一份 retry1 trace 的时间轴（`_monotonicTime`
与 `test.trace` 的 `startTime` 同尺度）量到的是：`/api/demo/import` 起于 `114340`、历时 `121 ms`
⇒ 响应约在 `114461` 落地；而 `click()` 那条 pw:api 到 `114770.8` 才返回，`waitForResponse`
（`__waitInfo__`）在 `114773.2` 才注册——**waiter 比响应晚 312 ms**，于是 10 秒空等。用例写的是
`await importButton.click()` 之后再 `waitForResponse`，这个顺序在"端点被关、后端 16 ms 短路返回"
的条件下必红。这样的位置在本文件里是**四处**（原写"同族三处"是漏数，第一百一十八批就地纠正）：
三处 `POST /api/demo/import`（改前 `:20`→`:23`、`:39`→`:40`、`:70`→`:71`）加一处
`POST /api/demo/clear`（改前 `:81`→`:85`）——第三处当时从未执行到，所以只被数成三条红。
三层从上到下是：
①CI 没开 `DEMO_ENDPOINTS_ENABLED`（第一百一十三批处置，且是 16 ms 短路让竞态显形的那一层）；
②spec 把 waiter 装在 click 之后（**第一百一十八批按"改用例"处置**，见下面"②的处置"一节）；
③`li:has-text("知识库文档")` 这一条期望本身陈旧（**第一百一十四批·补证整条撤销**，理由见下）。

| 层 | 位置 | 查什么 |
|---|---|---|
| 形状 | `scripts/static-checks.py` 检查 20（`--e2e-backend-feature-flags`，已并入默认全跑档） | 每个既 `spring-boot:run` 起 java 后端、又 `npx playwright test` 跑用例的 job，其**job 级 env ∪ 起后端步骤 env** 必须显式声明 `DEMO_ENDPOINTS_ENABLED: "true"`；四种坏形状各红一次：键缺失、值不是 `true`（`"false"`／`1`／空串都不算）、被注释掉的行冒充声明、键放在别的步骤里而不在起后端那条链上；适用面为空（没人起后端或没人跑 playwright）与缩小（少一个 job）都判红，不能靠删步骤让门变绿 |
| 语义 | `python-ai/tests/test_e2e_backend_feature_flag_gate.py`（18 例） | PyYAML 作独立 oracle：只用 YAML 复算"每个 playwright job 的 env 并集里有这个键且值为 `true`"；一条跨文件同源判定——workflow 钉的值必须等于 dev compose `:272` 钉的值，防止"门跟着 CI 一起变松"；键位置的两条（job 级 vs 步骤级都算，放错 job 不算）与注释那支各红一次；fixture 每个 job 都带 `steps: []`，与 `_workflow_steps` 的既有噪声规则同源 |

**门自己纠正过一次**：`_e2e_backend_flag_offenders` 的"适用面缩小"分支第一版写成
`E2E_TEST_JOBS - set()`（恒等于全集），于是任何裁剪都判绿；改成先收集本轮真扫到的 job 名集合、
再拿它跟下界作差，`test_shrunken_applicability_is_red` 才真的红。

诚实边界（写下时）：①本检查只覆盖**e2e 轨**，`deploy/docker-compose.prod.yml:187` 的
`${DEMO_ENDPOINTS_ENABLED:-false}` 按设计保持默认关（`/clear` 有数据破坏性，
`application.yml:175` 的注释写着这条），所以门不能推广成"所有拓扑都得 true"；②键值只钉
`DEMO_ENDPOINTS_ENABLED` 一条——它是这 4 条红里被工件证实的那一条，其余特性开关没有证据就不上门，
否则就成了把 CI 变严而没有红用例支撑的猜测；③**门绿不等于用例绿**：本批只除了最外的一层，
内两层后来的读数（第一百一十四批·补证与补证二；③的依据是 run `38349608765`／`38384435241`，
②的依据是 run `38388749034`）是——
**③"陈旧 label"整条撤销**（用例走 `/api/demo/import`，`DemoImportServiceImpl.java:143` 发的就是
「知识库文档」；含 `:29` 的那条在两条 run 上都通过，`:78` 从未执行到），
**②"waiter 注册顺序是死因"改判竞态**（第三条 run 里那两条 demo 用例转绿／flaky，
`retry` 会把竞态掩盖成"这轮没红"；第四条 run `38524739182` 给的是同一形状——`demo-data.spec.ts:40`
与 `:71` 各以 `page.waitForResponse: Timeout 10000ms exceeded` 红一次、attempt 2 通过，
判为 **2 flaky** 而非 failed，所以开关解开之后这 3 条到底几条转绿，
只能按 attempt 级 `results[].status` 比 ≥3 条 run 来判，单看一轮 `stats` 不够。
**"竞态"这条口径又在第一百一十八批被推翻**：第五条 run `38530095482`（commit `487e435c`）读 attempt
级是 `61 expected / 2 unexpected / 10 skipped / 0 flaky`，那两条 demo 用例是 **3/3 attempt 全红**
（`should show demo data in various pages after import`、`should clear demo data with confirmation`），
同文件的 `:14` 冷态首导同形却通过——所以它不是抖动，是**结构性漏听**，本批已按"改用例"处置（下节）。第 4 条 `tools.spec.ts:11` 与本检查无关：工具列表按 `pageSize=6` 分页而注册表有
30 项，`getByText('搜索知识库')` 的目标在第 3 页——**第一百一十五批已处置**（用户拍板 A＝改用例：
页数由页面自报条数推导、工具改成翻页找，本地活栈改前同形红／改后 2 passed），runner 侧那一格
由第一百一十七批的 run `38524739182` 补上（`tools.spec` 在整份日志里零命中，即两条用例都在
`61 passed` 内），不再是空档。

### ②的处置：四处监听提到点击之前（第一百一十八批）

改的是 `hfusionhub-frontend/e2e/demo-data.spec.ts` 一处文件、四个位置，形状全部改成
"先创建 promise → 再 `click()` → 最后 `await`"，与本仓已有的正确写法同源
（`theme-preference.spec.ts:38-43` 的注释就写着"先挂响应监听再 reload，避免错过事件"）：

| 位置（改后行号） | 监听的请求 | 点击 |
|---|---|---|
| `:22-24` | `POST /api/demo/import`（`:14` 冷态首导） | `:25` |
| `:40-42` | `POST /api/demo/import`（`:37` 导入后各页可见） | `:43` |
| `:72-74` | `POST /api/demo/import`（`:69` 清除用例的前置导入） | `:75` |
| `:85-89` | `POST /api/demo/clear` | `:90` |

**为什么"漏听"而不是"网络慢"**：请求是在 `await click()` 内部就发出的。runner 侧
（run `38530095482` 的 retry1 trace，第一百一十七批量）响应完成时刻比 waiter 注册时刻**早**
51.9 ms（`:36`）与 80.0 ms（`:67`）；本地活栈同形代码量到的是**晚** 184.5～8688 ms（四组读数：
+184.5 / +289.9 / +594 / +8688 ms，取决于那天服务端播种有多慢）。也就是余量的符号由宿主速度决定，
用例本身不提供任何顺序保证——`retry` 只会把"这次够慢所以绿"掩盖成"这轮没红"。
把监听挪到点击前之后，注册先于派发，不再依赖耗时。
**这条红本地复现不出来**：活栈上改前代码跑出的是"监听漏听"零次（三次跑里要么全绿、要么红在
另一条断言上，见下），所以改前红判据只有 runner 侧那一条，本批的本地取证只能证明"改后不退化"。

**改后绿判据（本地）**：活栈（dev compose 的 java＋python＋mysql＋redis＋milvus 全 healthy，
前端换成当前源码的 `npm run dev`）上 `npx playwright test e2e/demo-data.spec.ts` =
**3 passed (25.7s)**；全量 = **62 passed / 1 failed / 10 skipped（3.1m）**。那 1 条失败与本批无关，
是 `document.spec.ts:36`「document indexing completes with mock LLM」，库里 `document.error_message`
原文＝`向量嵌入失败: Embedding生成失败: 无法生成向量嵌入：Ollama 服务不可用`（doc id 236），
本机没起 Ollama；115 批记的"本地全量 63/2/8"里它就是那两条红之一。skip 从 8 涨到 10 也不是代码变化：
`write-note.spec.ts:14/:36` 按 `PYTHON_AI_INTERNAL_TOKEN` 是否注入决定跳过，本轮 shell 没带这个变量。
**runner 侧那一格由第一百一十九批补证闭合**：这笔改动推上去（commit `15e93920`）的 E2E run
`38568478864` 的 `e2e-full`＝**success**（13:02:13Z→13:14:07Z＝11m54s），`stats`＝
**63 passed / 0 unexpected / 0 flaky / 10 skipped**（合计 73，与前四轮同基数）。按 attempt 级
`results[].status` 读，`demo-data.spec.ts` 三条**全部单次通过、没有一条走过 retry**：
`should import demo data successfully` 2231 ms、`should show demo data in various pages after import`
（②那条）6626 ms、`should clear demo data with confirmation` 4466 ms。对账：上一轮（`38524739182`）是
`61 passed + 2 flaky + 10 skipped`，本轮 `63 + 0 + 10` ⇒ 转成稳定通过的那两条正是②。
`tools.spec.ts` 两条同样单次通过（2252 ms／1159 ms）⇒ 第一百一十五批与第一百一十七批的判据在这一轮再确认一次。
这条"绿不靠 retry"是可以数出来的：`E2E Tests` 最近 25 条 run（2026-10-10→2026-10-14）里
`success` 只有两条——`38524739182` 与本轮 `38568478864`，前者靠 **2 条 flaky**（Playwright 把 flaky
记为通过、退出码 0，红被 `retry` 兜住），后者 `0 unexpected / 0 flaky`；其余 23 条要么 `failure`
（按定义至少有一条 unexpected）要么被 20 分钟上限 `cancelled`（拿不到 `stats`）
⇒ 这是这个套件第一条不需要 retry 兜住的绿。
CI 侧同一笔 push 的 run `38568479058` 十一 job 全绿（13:02:10Z→13:16:32Z＝14m22s）。

**第一百二十批：第一百一十九批自己触发的那对 run 读数到手**，并且把上一句的"两条"改写成现行值＝**三条**。
`b904efbe` 这笔 docs-only push 触发的 E2E run `38574242376` 的 `e2e-full`＝**success**
（13:43:50Z→13:56:43Z＝12m53s），`Running 73 tests using 1 worker` → **63 passed (2.5m) / 10 skipped**，
`stats`＝**63 expected / 0 unexpected / 0 flaky / 10 skipped**；解包 `e2e-results-full` 按 attempt 级数，
`results` 展开共 **73 行**，`passed` 63／`skipped` 10，**`retry>0` 的行数＝0**（不是"红被兜住"，是从头就没红过）。
本轮的单次通过耗时：`demo-data.spec.ts` 三条 1830／6065／4066 ms（②那条 6065 ms），
`tools.spec.ts` 两条 1940／943 ms。⇒ 上一段那条"只有两条 success"是**写作当时的现行值**，现在数到三条
（`38524739182`、`38568478864`、`38574242376`；**第一百二十一批就地标注：这句又推了一次，`38577643030` 是第四条，见下面那段**），
而后两条**连续**都是 `0 unexpected / 0 flaky / 0 retry`
⇒ "绿不靠 retry"从一次性的孤例变成**可复现的状态**，这是第一百一十八批那处改动（四处监听提前）真正拿到的 runner 侧判据。
CI 侧同一笔 push 的 run `38574242324` **十一 job 全绿**（13:43:47Z→13:57:29Z＝13m42s）；
其中 `gitleaks` 是第一百一十七批那处高熵字面量修好后**连续第三轮**过（`38530095463`→`38568479058`→本轮）。
（**第一百二十四批就地标注：这句到本轮是连续第八轮**，见下面第一百二十四批那段，run 序列已列全。
**第一百二十五批：现行值＝第九轮**——`38889773590` 的 `gitleaks` job 逐 job 读到 `success`，序列与九条 run 的
job 级读数见上面第一百二十五批那段⑤，九条 CI 都是十一 job 全绿。）

**第一百二十一批：连续第三轮同一判据成立，但这一轮新增的不是"绿"而是"绿的次数"**。
`f97fd471`（第一百二十批本体）这笔 docs-only push 触发的 E2E run `38577643030` 的 `e2e-full`＝**success**
（14:07:01Z→14:20:12Z＝13m11s），`stats`＝**63 expected / 0 unexpected / 0 flaky / 10 skipped**；
attempt 级 `results` 展开仍是 **73 行**（`passed` 63／`skipped` 10），**`retry>0` 的行数＝0**。
单次通过耗时：`demo-data.spec.ts` 三条 2145／6573／4424 ms、`tools.spec.ts` 两条 2178／1117 ms
——与上一轮（1830／6065／4066、1940／943）在同一个量级，②那条两次都在 6 s 档，
说明"监听提前"之后那条路径走的是同一条链路，没有换死因。
⇒ `38568478864`／`38574242376`／`38577643030` **连续三轮**都是 `0 unexpected / 0 flaky / 0 retry`，
"绿不靠 retry"已经不是"可复现的状态"而是**这个套件当前默认的形态**（前提是那四处监听改动还在）。
（**第一百二十三批就地标注：这句数到六轮**——`38730439786`／`38731555698`／`38735220260` 三条各摊平 73 行仍是
`retry>0`＝0 行；谱系条件没变，仍是同一条 docs-only 线，见上面波形表那段。**第一百二十四批：`38742412892` 又加一轮，
现行值＝连续七轮**。**第一百二十五批：现行值＝连续八轮**——这条链本轮不是沿用说法，而是把
  2026-10-14 起八条 push 自触发的 E2E run 的 `e2e-results-full` **逐个下载、逐个摊平**数出来的（8/8 都是 73 行、
  `retry>0`＝0 行、`63/0/0/10`、skip 分布同为 plugin 4／approval 2／chat-sse 2／write-note 2），见上面⑤那段。）
CI 侧同一笔 push 的 run `38577643015` **十一 job 全绿**（14:06:58Z→14:19:52Z＝12m54s），
`gitleaks` 从"连续第三轮"数到**第四轮**（**第一百二十四批就地标注：按八个 CI run 的 job 级读数，现行值是第八轮**；**第一百二十五批：九个 CI run 数到第九轮**）；`e2e-smoke` 仍按设计为 `skipped`（不是红）。
这一轮对文档的唯一净新增就是上面那句"连续三轮"＋装依赖的第五档振幅（492 s，见上面的波形表）；
（**第一百二十三批就地标注：这句的"唯一"已经不唯一**，那批取的是并发条件下三笔 docs-only push 的三条读数，
净新增是"旧低档 423～492 s 作废"＋"并发会抬高振幅这条猜想被否"。）
覆盖面那条结论**没有变**：仍是 63 绿＋10 永久 skip，`docs/PRODUCTION_OPS.md:50` 仍未勾。

**但"63 passed"不等于"73 条都跑过"——那 10 条 skip 在 CI 里是永久的**（第一百一十九批数出来的，
文档此前只写总数、从没写过这 10 条是什么）：

| 条数 | 文件与行 | 跳过判据 | runner 上是否可能被打开 |
|---|---|---|---|
| 2 | `chat-sse.spec.ts:26`／`:71` | `HFUSIONHUB_RUN_SSE_LIVE == 'true'`（`:22`） | 否——没有任何 workflow 设过这个变量 |
| 2 | `approval.spec.ts:263`／`:271` | 行内读 `HFUSIONHUB_RUN_APPROVAL_LIVE` | 否 |
| 4 | `plugin.spec.ts:37`／`:99`／`:133`／`:143` | `HFUSIONHUB_RUN_PLUGIN_LIVE == 'true'`（`:9`） | 否 |
| 2 | `write-note.spec.ts:14`／`:36` | `PYTHON_AI_INTERNAL_TOKEN` 是否注入 | 否 |

`grep -rn "HFUSIONHUB_RUN_SSE_LIVE\|HFUSIONHUB_RUN_APPROVAL_LIVE" .github/workflows/` 命中数 **0**。
后果要说白：**流式对话（SSE）、插件安装/卸载、审批活链路、python 内部回调这四条路径在 runner 上
没有一条 e2e 覆盖**，`e2e-full` 全绿证明的是另外 63 条。本地活栈同理——本批那三轮也是 10 skipped。

**顺带发现一处说法冲突，未取证、没动代码**：`chat-sse.spec.ts:12-24` 的文件头把这 2 条 skip 归因给
"后端 bug：`sseTaskExecutor` 用 JDK 21 虚拟线程、不继承 Sa-Token 的 `ThreadLocal` ⇒ `NotLoginException`"，
并称"待后端修复（例如给执行器加 Sa-Token 上下文传递）后即可恢复"。而现行
`ThreadPoolConfig.java:34-45` 是**平台线程池**（`ThreadPoolTaskExecutor`＋`CallerRunsPolicy`），
它自己的注释（`:25-33`）写的恰恰是"不能用虚拟线程执行器……虚拟线程不继承父线程的普通 ThreadLocal，
Sa-Token/租户上下文会丢失（表现为流式对话 NotLoginException）"——也就是说**用例头注释描述的那个执行器
形态已经不是现在代码里的形态**。登记完当场就把它跑了（判据＝活栈上带 `HFUSIONHUB_RUN_SSE_LIVE=true`
跑 `e2e/chat-sse.spec.ts`，19.5 s，读数见下）。

来源也钉住（`git show` 读历史，不改代码）：写这段头注释的那笔提交就是 `1ce30072`（2026-08-17，
提交信息带"SSE 修复"），而**同一笔提交里** `ThreadPoolConfig.java:24-37`（该提交版本）的
`sseTaskExecutor` 已经是 `ThreadPoolTaskExecutor`＋`CallerRunsPolicy`、注释也已经是"不能用虚拟线程执行器"
⇒ 头注释从写下那天起描述的就是修复**之前**的执行器形态。现行
`application.yml:15-17` 的 `spring.threads.virtual.enabled: ${SPRING_THREADS_VIRTUAL_ENABLED:true}`
作用在 Tomcat 请求线程与 Spring 的 `applicationTaskExecutor`，不是这个 bean
⇒ "虚拟线程＝`sseTaskExecutor`"这句在现行代码里找不到对应物。

**实测读数（本地活栈，旗标 `HFUSIONHUB_RUN_SSE_LIVE=true`；这个文件里是 3 条用例，其中 2 条挂旗标）**：

| 用例 | 走法 | 结果 |
|---|---|---|
| `:24` send message and receive SSE response | 浏览器内 `page.evaluate` 里 `fetch('http://localhost:8080/api/conversation/message/stream')`（`:31` 写死绝对 URL） | **失败** `page.evaluate: TypeError: Failed to fetch`（栈指向 `:31`） |
| `:70` SSE response contains [DONE] marker | `javaApi.post`（node 侧请求，不经浏览器） | **通过** |
| `:93` chat detail page renders | 页面渲染 | **通过** |

⇒ 头注释那句"SSE 流在首个空事件后即被终止、**没有 `[DONE]`**"在当前活栈上被直接否掉：`:70` 断的正是
`toContain('[DONE]')`，它过了。`:24` 的红与 Sa-Token／虚拟线程无关，死因是**同源策略**——

```
curl -X OPTIONS http://localhost:8080/api/conversation/message/stream \
  -H 'Origin: http://localhost:3000' \
  -H 'Access-Control-Request-Headers: content-type,satoken,accept'
→ HTTP/1.1 403
  X-Trace-ID: 0d934f7eebbb49a8ad4d78651771410d
  Vary: Origin / Access-Control-Request-Method / Access-Control-Request-Headers
  （没有 Access-Control-Allow-Origin）
```

三个 `Vary` 是 Spring `CorsFilter` 留下的，说明拒绝发生在 CORS 过滤器而不是登录拦截器。而 CORS 不放行是
**按设计**：`CorsConfig.java:31` 的 `app.cors.allowed-origins` 默认空、`:39` 的
`app.cors.allow-any-origin` 默认 `false` ⇒ 走 `:92-93`"注册空配置、仅放行同源"这条分支。
compose 侧只有 `deploy/docker-compose.prod.yml:185` 透传 `APP_CORS_ALLOWED_ORIGINS`（值取
`${CORS_ALLOWED_ORIGINS:-}`，不配就是空），dev 的 `docker/docker-compose.yml` 两个键都没设；
键的口径记录在 `docs/ENVIRONMENT.md:75` 与 `docs/PRODUCTION_OPS.md:20`（含"禁止 `*`"与
"开发/内网穿透需显式开 `APP_CORS_ALLOW_ANY_ORIGIN=true`"）。应用本身不受影响，
前端一律走 vite 同源代理（`vite.config.ts:44-47` 把 `/api` 转到 `http://localhost:8080`）。

所以这条红的性质是**用例侧写死跨源绝对 URL，撞上一条正确的安全默认值**，与第一百一十一批的"`:3000` 契约"、
第一百一十三批的"后端特性开关"同族，是它的第三个数据点。本批一行代码没改、旗标也没进 workflow，
A／B／C 见 `docs/CLEANUP_BACKLOG.md` F 节。

**顺带量到一条产品缺陷（未处置，登记在 `docs/CLEANUP_BACKLOG.md` F 节）**：`page.goto` 之后那条
`演示知识库` 标题断言（改前 `:48`、改后 `:50`）在本地**3/3 全红**，且**改前改后同形**——
所以它跟监听顺序无关，死因在缓存：`DemoImportServiceImpl.java:316` 用
`knowledgeBaseMapper.insert(kb)` 直插，绕开了 `KnowledgeBaseServiceImpl.create():113` 的
`bumpVersionAfterCommit`，于是 B3 热点读缓存的版本键不动，`/api/knowledge-base/my` 继续命中旧页
（`KnowledgeBaseServiceImpl.java:340-346` 命中即返回缓存），最长 TTL 300 s 内查不到刚导入的库。
取证：导入 200 返回 `knowledgeBaseId=127／演示知识库／新增 12 项`（10:35:56.569），
同用户 3 秒后的 `GET /api/knowledge-base/my?page=1&pageSize=9` 仍是 8 条且无该库，而 MySQL 里
id 127 `deleted=0, recycled_at IS NULL, status=0, user_id=1`；Redis 里
`kb_list:ver:tenant:t1:user:1 = 6` 且 `kb_list:{4,5,6}:tenant:t1:user:1:p1:s9` 三份旧页并存；
在同一份改后代码上**只 `DEL` 那个版本键**（代码一行不再动），同一条用例 11.1 s 转过 ⇒ 判死成立。
清除路径不犯这个错（`DemoImportServiceImpl.java:199` 走 service 的 `delete`，会 bump）⇒ 播种与清除不对称。
这也给第一百一十五批留的"本地那 2 条 e2e 红＝拓扑差未取证"补上了机制：CI 每轮是新 Redis，
长寿命活栈才会撞上这条 TTL 窗口。

## 检查 21：弱默认值扫描器必须拦得住自家示例文件（第一百一十六批）

起因是 `docs/PRODUCTION_OPS.md:16` 那句「`--check` 可扫描弱默认值」。本轮把它按到实测上：
真机跑 `bash scripts/rotate-secrets.sh --check` 读 `docker/.env` 报 `[ok]`、退出码 0，
逐键比对 `docker/.env.example` 的 13 个键**没有一个等于示例占位值** ⇒ 本地这份确实轮换过，
那句在本地成立；但把 `docker/.env.example` **原样复制**成 `.env` 再喂同一个真脚本，
10 个占位键（8 个 `changeme-*` ＋ `minioadmin` ＋ `sk-replace-with-your-own-key`）只点名 1 个
（`minioadmin`），**退出码还是 0**。根因是脚本里那份 `WEAK_PATTERNS` 写的是 `change-me`
（带连字符），而自家示例用的是 `changeme`——扫描器与它要保护的那份样例不同源。
最常见的失效模式（照抄仓库里公开的示例上线）一路放行，所以"扫描器说绿"当不了"默认值换过"。

| 层 | 位置 | 查什么 |
|---|---|---|
| 形状 | `scripts/static-checks.py` 检查 21（`--weak-default-scan`，已并入默认全跑档） | 真起 bash 跑 `rotate-secrets.sh --check`，用 `ROTATE_SECRETS_ENV_FILE` 喂两份输入：**负控**喂 `docker/.env.example`，必须退出码非 0 **且**逐个点名到示例里所有占位键；**正控**喂"与示例同键集、值全换成强随机形态＋补上 `MODEL_CREDENTIAL_ENCRYPTION_KEY`"的临时文件，必须退出码 0 且不点任何名。另有四条自反规则：脚本或示例文件不存在红、`PLACEHOLDER_KEYS_LOWER_BOUND=10` 适用面缩小红（示例一旦不含占位符，负控就空转）、本机找不到 bash **不许默认绿** |
| 语义 | `python-ai/tests/test_weak_default_scan_gate.py`（18 例） | 判据是**行为**，不把脚本里那份模式抄到 python 侧（抄过来只会把 bug 复述一遍，故有一条 `test_scanner_source_is_not_the_oracle` 直接断言 `WEAK_PATTERNS` 那行里不许出现 `changeme`）；负控/正控各起真 bash；七条红路径各钉一次（恒 0、漏点名、一律红、示例失去占位符、脚本缺失、示例缺失、没有 bash）；`_scan_named_keys` 只认脚本自己写的那个 `[!] KEY` 形状（现 `rotate-secrets.sh:59`），形状一改就判 0/10 红而不是跟着猜 |

**为什么正控也要跑**：只写负控的话，把扫描器改成"一律红"同样能让门变绿，而那种门在真上线时
会把自己 `.env` 的弱值埋进噪音里。正控的输入是从示例文件**同键集**派生的（有一条判定专门
比两个键集），否则"绿"可能只是因为少了几行要被扫的键。

**正控自己被判红了一次（第一百一十七批）**：本地 static-checks 全跑的 检查 21 是绿的，
推送后 CI 的 `gitleaks` 却把这条门带进来的东西点了名——`_strong_env_file_fixture()` 里写死的
`MODEL_CREDENTIAL_ENCRYPTION_KEY=<32 位大小写字母数字>` 字面量命中 `generic-api-key`
（entropy 5.0，fingerprint 指到 `scripts/static-checks.py:2677`，run `38524739099` 的 `gitleaks` job 判失败）。
那是一串**假值**，但形状与真凭据无异，而"仓库里有没有看着像密钥的字面量"正是 gitleaks 的判据——
所以这不是误报，是门抓到了自家新写的东西。处置＝值改运行时生成（`secrets.token_urlsafe(24)`，
两条键值行都不再留字面量）：扫描器对这条键的要求只是"非空"（`rotate-secrets.sh:66` 是
`grep -q '^MODEL_CREDENTIAL_ENCRYPTION_KEY=.'`），门的门也只断言键在键集里
（`test_weak_default_scan_gate.py:264`），故 18 例与检查 21 的语义不变。**没有**用
`.gitleaks.toml` 白名单把这条 fingerprint 消掉——那等于把刚抓到真问题的门改成噪音。
本地取证用与 CI 同一版本（gitleaks 8.24.3）：改前同参复现出同一条命中且退出码 2，
改后 `--no-git` 逐行全文扫与 `--log-opts=-1` 复扫都是 `no leaks found`／退出码 0。
副作用要记下：正控的值现在每轮随机，门因此不再是逐字节可复现的输入，换来的是仓库里少了一条
可被当成凭据的形状。

诚实边界（写下时）：①本检查只保证**扫描器能拦住照抄示例**，不保证任何环境的 `.env` 真的换过——
`docker/.env` 不在版本库里，门够不着它；②覆盖面只有 `docker/.env.example` 一个文件，
`deploy/.env.example` 与 `python-ai/.env.example` 里的占位值至今没有门扫（已登记
`docs/CLEANUP_BACKLOG.md` F 节，**待拍板**）；③`CALLBACK_SECRET` 的方向口径本轮一并纠正为
"Java 单向分发"，但 compose 注给 python-ai／worker 的那三行是空转声明，删与留都是行为决策，同条待拍板；
④抓到这处红的 `gitleaks` 在 runner 侧，本地那套门够不着它——`ci.yml` 的 lint job `working-directory: python-ai`
（`:135-148`，`ruff check .` 因此只覆盖 `python-ai/`），仓库根没有 ruff 配置文件，
`scripts/*.py` 从不在 CI 的 lint 作用域内（本轮量：以 `python-ai/.venv` 里钉的 ruff 0.16.3 手工扫
`scripts/static-checks.py` 得 **18 条**，HEAD 与工作区同为 18 条 ⇒ 本批没新增，但也没人管它）。
检查 21 的"门的门"仍只由 `static-checks.py` ＋ 18 例 pytest 两处钉，密钥形态这一半靠 gitleaks 兜。

## 检查 18：容器轨的运行期契约（第一百零九批）

第一百零九批第一次把 `docker/docker-compose.yml` 整栈跑起来（9 服务，含 mysql/redis/milvus/
minio/etcd），量到四处同一形状的断链：**配置写了、容器里没有对应实体或语义指错**。四处都不会让
任何一步变红——容器起得来、探针绿、API 正常，死的是队列、握手、出站地址或状态可读性。

| 规则 | 坏形状（本批实测） | 判据 |
|---|---|---|
| ① | worker 的 command 是 `python -m arq arq_worker.WorkerSettings`，而 `deploy/Dockerfile.python` 只 `COPY app/ app/` | 容器内 `ModuleNotFoundError`，`RestartCount` 14 次崩溃循环，`arq:queue` 那条 job 滞留 83.69s 无人消费，而 python-ai 的 API 日志照写 "dispatched via arq" |
| ② | dev compose 的 redis7 起 `--requirepass`，java-backend 只给 `SPRING_DATA_REDIS_HOST` | 登录 500 `RedisConnectionFailureException`（traceId `40bb29cf73464ff28f01caa37cbb40b8`）；prod compose 同一段一直是成对的（`deploy/docker-compose.prod.yml:176`），所以只在整栈上暴露 |
| ③ | `python-ai.base-url` / `python-ai.engine.url` 是 yml 裸字面量，三档拓扑只设 `AI_SERVICE_URL` | java 调 python 的解析请求打到自己身上：`POST /api/document/204/parse` → 400 I/O error on `http://localhost:9000/api/parse`（traceId `9dae81714a9a41a1812c0cb3155fca89`） |
| ④ | worker 继承镜像里给 uvicorn 写的 `HEALTHCHECK`（`curl -f http://localhost:9000/health`） | 容器 running、心跳键在写，状态永久 `unhealthy`（`probe_http=000`、`curl exit=7`）——真信号（进程退出）被这片假红盖住 |

| 层 | 位置 | 查什么 |
|---|---|---|
| 形状 | `scripts/static-checks.py` 检查 18（`--container-runtime-contract`，已并入默认全跑档） | ①每条 `python -m arq` 命令的入口模块必须落在其 build 上下文那份 Dockerfile 的 `COPY` 派生顶层模块集合里，且源文件真在上下文里；②凡拓扑以 `--requirepass` 起 redis，声明 `SPRING_DATA_REDIS_HOST` 的工作负载必须同时声明 `SPRING_DATA_REDIS_PASSWORD` 或 `REDIS_PASSWORD`；③java 侧以 `:9000` 为缺省值的 `@Value` 属性必须在 application.yml 里全部由**同一个**环境变量喂，且 dev/prod/helm 三档都声明它；④跑 worker 的服务必须显式 `healthcheck.disable` 或换成不打那个端口的探针。四条都按拓扑钉数量（worker 1 / redis 客户端 2 / 出站点 10），**适用面为空本身判红** |
| 语义 | `python-ai/tests/test_container_runtime_contract_gate.py`（39 例） | 真仓库四条都绿、已并入默认全跑档、每种历史坏形状注入时各红一次；三条"形状对但指向别处"的语义面单独钉：密码键插值的必须是 redis 自己用的那个变量、`COPY` 的目的地必须是 WORKDIR、worker 自定义探针仍打 `:9000` 照样红；解析器反空转用 PyYAML 作 oracle（command 令牌、application.yml 的点号路径两条），helm 的 redis 至今无 `--requirepass` 这件事也写成断言——哪天上了密码，规则②必须被拓宽而不是被默许 |

建门过程中门自己纠了一处：`_image_probe_port` 第一版按物理行匹配 URL，而真仓库那行 `HEALTHCHECK`
是带 `\` 续行的（`deploy/Dockerfile.python:52`），端口恒为 `None` ⇒ "自定义探针仍打服务端口"
那一支永远不触发。现在先拼逻辑行再匹配，规则④的报告也因此能写出具体的 `:9000`。

诚实边界：检查 18 查的是**文本与拓扑之间的一致性**，不证明链路在跑——①③④的"修好了"来自
活栈复测（见 `docs/PRODUCTION_OPS.md` 10.2.1 的 W3–W6），②的绿同样在活栈上量到登录 200。
它也不查"嵌入服务可达吗"这类外部依赖：第一百零九批 W7 里文档 204 终态是 `FAILED`，死因是容器内
`OLLAMA_BASE_URL` 不可达，那条链路本身已经通到回调写库。

## 相关文件

- `.github/workflows/ci.yml` — push/PR 主 CI（含 `eval-offline` 门禁 job）
- `.github/workflows/eval-nightly.yml` — 运行时 Nightly 评测
- `python-ai/scripts/eval_offline.py`、`python-ai/scripts/eval_runtime.py` — 双轨评测入口
- `python-ai/scripts/eval_baseline.py` — 共享报告 / 门禁 / 基线逻辑（2026-08-29 由 `app/core/rag/` `git mv` 而来，见 `docs/CLEANUP_BACKLOG.md:34`）
- `python-ai/evaluation/README.md` — 评测系统设计、用例、双轨与基线流程
- `scripts/ci/check_container_skips.sh` — 容器专项 skip 计数门禁（0/1/2 退出码契约）
- `scripts/ci/vuln_report_gate.py` — pip-audit 报告的判定门（0 无漏洞 / 1 有 / 2 读不出形态）
- `scripts/ci/sbom_lock_coverage_gate.py` — SBOM 与依赖锁的一致性判定门（第一百一十四批：
  0 覆盖齐且版本一致 / 1 缺失或版本不符 / 2 读不出被描述的对象，空组件表归 2 不再只打印 `WARNING`；
  适用面按 `sys_platform` marker 算，`--sys-platform` 只为门的门而存在）
  ——runner 侧已实测（补证 run 38384621875，job 115253222329）：`Generate SBOM` success，日志打印
  `SBOM covers all 76 applicable locked packages (77 components; …)`，产物组件 35→77。
  两条口径要记住：组件**个数不是判据**（下界判定，runner 77 / 容器 78，集合差只有 `wheel`），
  且这条 workflow 的 push 触发带路径过滤（只列 `python-ai/plugins/**`、`requirements*.in`、
  `app/core/plugin/**`），**改 workflow 或 `scripts/ci/` 本身的批次不会自动跑出它的证据**，
  补证得 `workflow_dispatch` 手跑。
- `python-ai/tests/test_plugin_security_gates.py` — `plugin-security.yml` 三个 job 的判据：
  旗标与当版本旗标表同源、钉版与 `requirements-dev.txt` 同源、两条 helper 的退出码契约
  （第一百零四批 15 例 ＋ 第一百一十四批 17 例），含"不许静音"那条
- `python-ai/tests/test_ci_workflow_gates.py` — 上述 compose/skip 两条非评测门禁的判据（含真执行 workflow 步骤体）
- `python-ai/tests/test_workflow_run_scalars.py` — 检查 14 的判据：四道门的 argv 形状、`--flag` 与 argparse 的契约、历史折叠形态真会红
- `python-ai/tests/test_python_clock_caliber_gate.py` — 检查 15（python 钟面口径）的判据：真仓库绿、已并入默认全跑档、每种漂移（裸读法 / `TZ` 缺失 / 非 UTC / helm 死键 / 工作负载标记改名）都红；工作负载集合另用 PyYAML 写一个 oracle
- `python-ai/tests/test_tool_clock_caliber.py` — 内置时间工具的钟面行为判据（显式 UTC 口径 + 进程时区免疫，免疫那例在 POSIX 容器里执行、Windows 上跳过）
- `python-ai/tests/test_db_lock_lifetime_gate.py` — 检查 16（审计库共享 SQLite 连接）的判据：真仓库绿、已并入默认全跑档、锁外取连接 / 锁外关连接 / 整组改名 / 适用面为空 / 语法坏掉这五种形态都红，同行 `with` 写法不误伤；行为侧的确定性红在 `test_plugin_audit.py::TestDbConnectionLifetime`。反空阈值现为 `>= 12`（9 个 `_get_db()` 调用点 ＋ `_reset_db` 里 3 处 `_db_conn` 读写），构成变化时按账改阈值、不改规则
- `python-ai/tests/test_plugin_audit.py::TestFlushVerdictReadsCurrentRow` — 审计 flush 的超限判定必须读**行的当前状态**的判据：events 把在途 flush 卡在"快照 → 回写"之间，运维回灌后不得被旧快照翻回 dead-letter（第一百零七批）
- `python-ai/tests/test_flyway_cli_gate.py` — 检查 17（Flyway 旗标与插件钉版）的判据：真仓库绿、已并入默认全跑档、六种漂移（只给 Spring 键 / 残留空转 env / `continue-on-error` / 删步骤 / 改 goal / pom 未钉或钉数字）各红一次，旗标值与 job 的 mysql service 凭据同源，解析器自身不与 YAML 分歧（第一百零八批）
- `python-ai/tests/conftest.py::_stop_audit_flusher` + `test_plugin_audit.py::TestAuditFlusherIsolation` — 测试隔离门禁：autouse fixture 换库前后各停一次 `audit-flusher`（join 不掉直接 `pytest.fail`），配一条反空判定先证明 `record_audit` 真起了 daemon，否则"开局无残留线程"会凭空绿（第一百零七批）
- `python-ai/tests/test_container_runtime_contract_gate.py` — 检查 18（容器轨运行期契约）的判据：四条规则各种历史坏形状各红一次、三种"形状对但指向别处"的语义面单独钉、按拓扑的数量反空转、command 与 application.yml 两处解析器各有一个 PyYAML oracle（第一百零九批）
- `python-ai/tests/test_e2e_backend_feature_flag_gate.py` — 检查 20（e2e 轨后端特性开关契约）的判据：真仓库绿、已并入默认全跑档、四种坏形状（键缺失 / 值不是 `true` / 注释冒充 / 键不在起后端那条链上）各红一次、适用面为空与缩小都红，并有一条"workflow 钉值 == dev compose 钉值"的跨文件同源判定（第一百一十三批）
- `python-ai/tests/test_e2e_frontend_server_gate.py` — 检查 19（e2e 轨前端服务契约）的判据：真仓库绿、已并入默认全跑档、七种坏形状（没起前端 / 探针端口与 baseURL 不同源 / 探针无 `exit 1` / 起前端排在 `npm ci` 前 / 缺探针 / config 在 CI 档也自起=双主人 / 删测试步骤或改命令名）各红一次，适用面下界按 job 名钉住；有名步骤与无名步骤条数都由 PyYAML 复算（第一百一十一批）
- `python-ai/tests/test_weak_default_scan_gate.py` — 检查 21（弱默认值扫描器覆盖契约）的判据：真仓库绿、已并入默认全跑档、负控与正控各起一次真 bash、七条红路径（恒 0 退出码 / 漏点名 / 一律红 / 示例失去占位符 / 脚本缺失 / 示例缺失 / 没有 bash 时不许默认绿）各红一次；有一条判定反向钉"python 侧不许把脚本里那份 `WEAK_PATTERNS` 抄成 oracle"（第一百一十六批）
- `python-ai/tests/test_eval_suite_eol_binding.py` — 冻结摘要与行尾无关的判据（钉值、两种检出形态、篡改仍红、emit 写 LF）
- `.git-blame-ignore-revs` + `CONTRIBUTING.md`「Java code style (spotless)」— 全仓重排那一笔如何不污染 `git blame`
