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

剩下那 4 条**不属于这一层**，已登记为第一百一十二批，死因先记在这里：
`demo-data.spec.ts:29/78` 等 `li:has-text("知识库文档")`，而 `SetupChecklist.vue:251` 渲染的是
`{{ section.label }}`、`BidDemoImportServiceImpl.java:149-152` 发的 label 是「招标文件知识库／
企业资质库／历史标书库／示例投标项目」——"知识库文档"这串字只剩在 `DemoController.java:62` 的
Swagger 描述里，属测试侧陈旧期望；同族的另一种死法是 `waitForResponse('/api/demo/import' && 200)`
超时（`SetupChecklist.vue:109` 的 `if (!userStore.isAdmin) return` 在管理员标志未就位时**根本不发请求**，
同一条用法的两种死法在不同 retry 里都出现过，**主因待 artifact 确认**）；
`tools.spec.ts:11` 的 `getByText('搜索知识库')` 之前两条静态文案断言（`:9`/`:10`）都通过，只有
数据驱动的能力卡片没渲染——卡片来自工具注册表（`Tools.vue:124` 按 registry 行取
`abilityCatalog[tool.name]`），注册表为空就没有卡片。**这是假设，还没有复现。**

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
- `python-ai/tests/test_ci_workflow_gates.py` — 上述 compose/skip 两条非评测门禁的判据（含真执行 workflow 步骤体）
- `python-ai/tests/test_workflow_run_scalars.py` — 检查 14 的判据：四道门的 argv 形状、`--flag` 与 argparse 的契约、历史折叠形态真会红
- `python-ai/tests/test_python_clock_caliber_gate.py` — 检查 15（python 钟面口径）的判据：真仓库绿、已并入默认全跑档、每种漂移（裸读法 / `TZ` 缺失 / 非 UTC / helm 死键 / 工作负载标记改名）都红；工作负载集合另用 PyYAML 写一个 oracle
- `python-ai/tests/test_tool_clock_caliber.py` — 内置时间工具的钟面行为判据（显式 UTC 口径 + 进程时区免疫，免疫那例在 POSIX 容器里执行、Windows 上跳过）
- `python-ai/tests/test_db_lock_lifetime_gate.py` — 检查 16（审计库共享 SQLite 连接）的判据：真仓库绿、已并入默认全跑档、锁外取连接 / 锁外关连接 / 整组改名 / 适用面为空 / 语法坏掉这五种形态都红，同行 `with` 写法不误伤；行为侧的确定性红在 `test_plugin_audit.py::TestDbConnectionLifetime`。反空阈值现为 `>= 12`（9 个 `_get_db()` 调用点 ＋ `_reset_db` 里 3 处 `_db_conn` 读写），构成变化时按账改阈值、不改规则
- `python-ai/tests/test_plugin_audit.py::TestFlushVerdictReadsCurrentRow` — 审计 flush 的超限判定必须读**行的当前状态**的判据：events 把在途 flush 卡在"快照 → 回写"之间，运维回灌后不得被旧快照翻回 dead-letter（第一百零七批）
- `python-ai/tests/test_flyway_cli_gate.py` — 检查 17（Flyway 旗标与插件钉版）的判据：真仓库绿、已并入默认全跑档、六种漂移（只给 Spring 键 / 残留空转 env / `continue-on-error` / 删步骤 / 改 goal / pom 未钉或钉数字）各红一次，旗标值与 job 的 mysql service 凭据同源，解析器自身不与 YAML 分歧（第一百零八批）
- `python-ai/tests/conftest.py::_stop_audit_flusher` + `test_plugin_audit.py::TestAuditFlusherIsolation` — 测试隔离门禁：autouse fixture 换库前后各停一次 `audit-flusher`（join 不掉直接 `pytest.fail`），配一条反空判定先证明 `record_audit` 真起了 daemon，否则"开局无残留线程"会凭空绿（第一百零七批）
- `python-ai/tests/test_container_runtime_contract_gate.py` — 检查 18（容器轨运行期契约）的判据：四条规则各种历史坏形状各红一次、三种"形状对但指向别处"的语义面单独钉、按拓扑的数量反空转、command 与 application.yml 两处解析器各有一个 PyYAML oracle（第一百零九批）
- `python-ai/tests/test_e2e_frontend_server_gate.py` — 检查 19（e2e 轨前端服务契约）的判据：真仓库绿、已并入默认全跑档、七种坏形状（没起前端 / 探针端口与 baseURL 不同源 / 探针无 `exit 1` / 起前端排在 `npm ci` 前 / 缺探针 / config 在 CI 档也自起=双主人 / 删测试步骤或改命令名）各红一次，适用面下界按 job 名钉住；有名步骤与无名步骤条数都由 PyYAML 复算（第一百一十一批）
- `python-ai/tests/test_eval_suite_eol_binding.py` — 冻结摘要与行尾无关的判据（钉值、两种检出形态、篡改仍红、emit 写 LF）
- `.git-blame-ignore-revs` + `CONTRIBUTING.md`「Java code style (spotless)」— 全仓重排那一笔如何不污染 `git blame`
