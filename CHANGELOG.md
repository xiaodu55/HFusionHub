# Changelog

All notable changes to HFusionHub are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

> 版本脉络：`[1.0.0]`（2026-08-30，平台完整能力首次固化）→
> `[1.1.0]`（2026-09-09，评测双轨门禁 + 主体级 ACL + 招投标垂直化 +
> 大数据扩展包 + R16/R17 优化与 44 批自审修复）。批次粒度变更记录
> 保留于各版本小节内。

## [Unreleased]
### 第一百一十七批（2026-10-14：第一百一十六批推送后 CI 的 `gitleaks` 把自家正控 fixture 里那串假密钥点了名——同版本同参数本地复现，值改运行时生成，同一条 push 的另一只鞋（E2E 首次擦线跑进 20 分钟上限）也一并落账）

**结论**：`0305bc25`（第一百一十六批）触发的两条 run 一正一红，红是这批自己带进来的。
- CI `38524739099`：**10 绿 1 红**，唯一红的是 `gitleaks`（job `115722314260`，步骤 `Scan for secrets (gitleaks)`，命令 `gitleaks detect --redact -v --exit-code=2 ... --log-opts=-1`）。命中 `generic-api-key`、entropy 5.000000、fingerprint `0305bc25…:scripts/static-checks.py:generic-api-key:2677` ⇒ 被点名的是这批新写的 `_strong_env_file_fixture()` 里那行 `MODEL_CREDENTIAL_ENCRYPTION_KEY=<32 位大小写字母数字>`。
- E2E `38524739182`：**success**，`e2e-full` 06:51:59Z→07:11:29Z＝**19m30 s**，用例读数 `61 passed / 2 flaky / 10 skipped`（73 条，与前三轮同基数）⇒ 第一百一十五批缺的 runner 判据到手：整份日志 `tools.spec` 命中数 **0**，`tools.spec.ts:11` 那格不再是空档。

**红判据（先写先量）**：本机没有 gitleaks、Docker 引擎未起，于是取 CI 的**同一版本** 8.24.3（`gitleaks_8.24.3_windows_x64.zip`）在真仓上按 CI 的参数复跑，`--log-opts=-1` 给出同一条 finding、同 fingerprint，退出码 **2** —— 复现成立才动手。假值不是免责理由：形状与真凭据无异，而"仓库里有没有看着像密钥的字面量"正是这条门的判据，所以这是门抓到了自家新写的东西，不是误报。

**改了什么**：`scripts/static-checks.py`
- 新增 `import secrets`（与既有 stdlib 同段字母序）。
- `_strong_env_file_fixture()`：两行值都改成运行时 `secrets.token_urlsafe(24)`，源码里不再出现高熵字面量；docstring 记下为什么不能写死（写死＝往仓库提交一条能被当成凭据的形状）。
- 语义不变的依据：扫描器对这条键只要求非空（`scripts/rotate-secrets.sh:66` 是 `grep -q '^MODEL_CREDENTIAL_ENCRYPTION_KEY=.'`），门的门只断言键在键集里（`python-ai/tests/test_weak_default_scan_gate.py:264`），都不比字面值。
- **没有**加 `.gitleaks.toml` 白名单去消这条 fingerprint——那等于把刚抓到真问题的门改成噪音。

**验证**：
- 复扫：改后同一文件放进隔离临时 git 仓，`--no-git` 逐行全文扫与 `--log-opts=-1` 各一次，双双 `no leaks found`／退出码 **0**。
- 门：`static-checks.py --weak-default-scan` EXIT=0（负控 10 个占位键全点名且退出码非 0、正控为绿）；全跑档 EXIT=0（检查 1–21）。
- 门的门：`tests/test_weak_default_scan_gate.py` **18 passed**。
- ruff（`python-ai/.venv` 里钉的 0.16.3）：HEAD 版与工作区版**同为 18 条**，本批零新增。
- 计数：Python 侧无新增用例，README 口径不变（2101）。

**就地纠正的旧口径**（语义漂移，不另立缺陷号）：`docs/CI_GATES.md` 两处"runner 判据还空着／原因是 `timeout-minutes: 20`"改判为已到手（并写明 19m30 s 是擦线），②竞态补第四个数据点（`demo-data.spec.ts:40` 与 `:71` 各红一次、attempt 2 通过 ⇒ 2 flaky，`retry` 仍会掩盖竞态）；`docs/CLEANUP_BACKLOG.md` 的镜像单点条目把"证据通道断了"改写成"擦线"，候选 B／C 仍待拍板。

**诚实边界**：①`e2e-full` 这轮过是**余量约 30 秒**的过——装依赖吃到 07:07:14（≈15m15 s），同一条慢源波形再抖一档就回到七条 `cancelled` 的形态，所以别把"115 的 runner 判据到手"读成"上限问题解决了"；②`②的两条 demo 用例`本轮仍只有 flaky 级读数，attempt 级 `results[].status` 的判读纪律不变；③正控的值现在每轮随机 ⇒ 门的门不再逐字节可复现，换来的是仓库少一条可被当成凭据的形状；④`scripts/*.py` 从不在 CI 的 lint 作用域内（`ci.yml:135-148` 的 `working-directory: python-ai`），这处红只有 runner 侧的 gitleaks 抓得到，本地那两套门都够不着——已登记 F 节 A／B／C 三档**待拍板**。

### 第一百一十六批（2026-10-14：把「`--check` 可扫描弱默认值」这句话按到实测上——量出它拦不住自家示例文件（10 个占位键只点名 1 个、退出码还是 0），修扫描器并把门钉上去，顺带清掉上线清单里两处指向不存在的键的口径）

#### 结论（先给判定性质）

- 本批**只加门、只修那个门要保护的脚本**，不放宽任何既有判据：`scripts/rotate-secrets.sh` 的 `--check`
  从"恒返回 0 的提示器"改成"发现即退出码 1 的扫描器"，新增 **检查 21**（`--weak-default-scan`，已并入默认全跑档）
  用**负控**钉住它——把 `docker/.env.example` 原样喂进去必须被拦住。
- 起因是上线评审里被追问的一条：`docs/PRODUCTION_OPS.md:16` 写着「`--check` 可扫描弱默认值」。
  这句话**在本地成立、在最常见的失效模式下不成立**，两半都量了：
  ①真机跑 `bash scripts/rotate-secrets.sh --check`（读工作区里的 `docker/.env`）报 `[ok] 未发现弱默认值`、退出码 0，
  逐键比对已入库的 `docker/.env.example`（13 个键）**没有一个等于示例占位值** ⇒ 本地这份确实轮换过；
  ②把 `docker/.env.example` **原样复制**成 `.env` 喂同一个真脚本 ⇒ 10 个占位键
  （8 个 `changeme-*` ＋ `minioadmin` ＋ `sk-replace-with-your-own-key`）只点名 1 个（`minioadmin`），
  **退出码还是 0**。照抄仓库里公开的示例上线这条最常见的路径，扫描器一路放行。
- 根因不在判据松，在**扫描器与它要保护的那份样例不同源**：`WEAK_PATTERNS` 里写的是 `change-me`（带连字符），
  而自家示例用的是 `changeme`；`sk-replace-with-your-own-key` 不在任何模式里。缺键那一支（`MODEL_CREDENTIAL_ENCRYPTION_KEY`
  未配置）当时也只打印、不参与退出码。

#### 红判据（改前实测，两轮读数的差别本身也登记）

- 第一版判据落地前测到的是「没点名 …（10/10）」——这个数是**假红**：那时脚本还没实现
  `ROTATE_SECRETS_ENV_FILE`，负控实际扫的是本机真实 `docker/.env`，等于拿 A 文件判 B 文件。
  先把覆盖路径（plumbing）落地，再重测的**诚实红**是两条：`退出码 0：照抄示例默认值不判红`
  ＋`没点名 …（9/10）`（只点名 `minioadmin`）。
- 教训写成一句话：**负控的输入必须是负控自己那份文件**，否则红判据在测本机环境而不是测判据。

#### 改了什么

- `scripts/rotate-secrets.sh`：①`ENV_FILE` 改成 `${ROTATE_SECRETS_ENV_FILE:-$ROOT/docker/.env}`（门靠它喂样例文件）；
  ②弱判据拆成两张表——`WEAK_PATTERNS`（值**开头**就是众所周知的弱口令，保守，避免误伤含 `admin`/`test` 的强随机值）
  与新增的 `PLACEHOLDER_PATTERNS`（值里出现占位符腔：`changeme`／`change-me`／`replace-with`／`your-own`／`sk-replace`／
  `placeholder`／`xxxxxx`），两张表任一命中即点名；③缺 `MODEL_CREDENTIAL_ENCRYPTION_KEY` 那支现在也置 `found=1`；
  ④`check_env` 以 `return $found` 收尾，`--check` 分支据此 `exit 1` 并把处置指引打到 stderr。
  键名解析顺手兜住 `export KEY=` 与两侧空白（`key="${key#export }"` ＋ `tr -d '[:space:]'`）。
- `scripts/static-checks.py` 新增检查 21：真起 bash 跑两遍——
  **负控**喂 `docker/.env.example`，要求退出码非 0 **且**每个占位键都被 `[!] KEY` 点名（漏一个红，红文案直接给
  「没点名 …（N/M）」）；**正控**喂"与示例同键集、值全换成强随机形态、补上加密键"的临时文件，要求退出码 0 且不点任何名
  （防"一律红"把门变成噪音）。另有四条自反：脚本或示例不存在红、`PLACEHOLDER_KEYS_LOWER_BOUND = 10` 适用面缩小红、
  本机找不到 bash **不许默认绿**。占位形态写在 python 侧当独立 oracle，不抄脚本那份模式。
- 文档就地纠正四处语义漂移（不另立缺陷号）：
  `docs/PRODUCTION_OPS.md:16` 把那句改成带退出码与被钉住事实的完整口径；`:18` 的 `PLUGIN_RUNNER_SECRET_KEY`
  是全仓零命中的键名，换成现行的 `PLUGIN_RUNNER_TOKEN` 并给出两侧读取点（Java `application.yml:159` ↔
  Python `app/core/plugin/container_runner.py:29`）；`:21` 的「Sa-Token JWT 密钥 `SA_TOKEN_JWT_SECRET_KEY`」
  是**虚构项**（`application.yml:89-96` 的 sa-token 段只有 `token-name/timeout/active-timeout/is-concurrent/
  token-style: uuid/is-log`，没有签名密钥可配；`JwtUtils.java` 只是 `StpInterface` 的权限提供者、不读任何密钥），
  标作废并说明"照此项去配只会造出一个没人读的空转键"；覆盖密钥清单里 `CALLBACK_SECRET` 那行（现 `scripts/rotate-secrets.sh:15`）原写
  「`CALLBACK_SECRET` Python → Java 回调 HMAC（两侧一致）」——方向反了且"两侧各配一份"不成立，改成单向分发口径。
- `docs/CI_GATES.md` 新增「检查 21」章节与门清单行；同时纠正该文件里两处**已被后续 run 推翻的 stale 口径**
  （`tools.spec.ts:11` 从"尚未处置"改成"第一百一十五批已按改用例处置、runner 判据被 `timeout-minutes: 20` 挡住"；
  检查 20 诚实边界里"②waiter 注册顺序与③陈旧 label 都还在"改成③整条撤销、②改判竞态的实测读数）。
- `docs/CLEANUP_BACKLOG.md` F 节新登记两点**待拍板**（本轮只取证不处置）：①扫描覆盖面只有 `docker/.env` 一个文件，
  `deploy/.env.example:13`（`replace-with-long-random-token-2`）与 `python-ai/.env.example` 的占位值至今没有门扫；
  ②`CALLBACK_SECRET` 只有 Java 读（`application.yml:128` → `VectorizationServiceImpl.java:725-750` 写进请求体），
  Python 全程只回显那把钥匙去签名（`vectorization.py:245`、`:810-820`），`grep -rn "environ.*CALLBACK_SECRET" python-ai/app`
  零命中 ⇒ `docker/docker-compose.yml:318/400`、`deploy/docker-compose.prod.yml:236` 与 `python-ai/.env.example:42`
  是空转声明（与第一百零九批 `UPLOAD_DIR` 同形），删或留都是行为决策。

#### 验证

- 负控：`rotate-secrets.sh --check` 以 `docker/.env.example` 为输入 ⇒ **退出码 1，10 个占位键全部被点名**；
  正控（等键集强随机值）⇒ 退出码 0、零点名；本机真 `docker/.env` ⇒ 仍 `[ok] 未发现弱默认值`、退出码 0（**没有误伤**）。
- `python scripts/static-checks.py --weak-default-scan` 退出码 0；全跑档 `python scripts/static-checks.py` 退出码 0（检查 1–21 全绿）。
- 门的门 `python-ai/tests/test_weak_default_scan_gate.py`：**18 passed**。首跑 1 红是**判据写错、不是产品错**：
  我在测试里造了 `[!]KEY`（`[!]` 与键名之间无空格）这种脚本从不产出的形状去要求解析器认它。脚本自己写死的是
  `echo "  [!] $key ..."`（现 `:59`），解析器就该只绑这个形状；真改成别的形态时宁可判「没点名 …（0/10）」大声红，
  不猜形状。测试数据改回脚本实际产出的形态（保留 tab 缩进那一支），并把这条边界写进注释。
- 计数同步：Python 2083 → **2101**（＋18 条门测试），README 四处同源（`:15` badge / `:37` / `:47` / `:241`）；
  Java 718、前端 117 未动，`--test-counts` 复核绿。

#### 诚实边界

- 检查 21 只保证**扫描器拦得住照抄示例**，不保证任何环境的 `.env` 真换过——`docker/.env` 不在版本库里，门够不着它；
  所以上线清单那条仍是 `- [ ]`（勾它要的是运维动作，不是门绿）。
- `PRODUCTION_OPS.md` §0 至今 **34 项未勾**（本批把那条虚构项标 `[x]` 作废，读数从 0/35 变 1/35，性质仍是流程债：
  没有任何机器判据读这 35 项）。把它做成门要先回答"勾选项由谁核"，本批不做代理指标。
- 扫描器改的是**判据覆盖面**，值面仍取决于两份模式表；`PLACEHOLDER_MARKERS`（python 侧 oracle）与
  `WEAK_PATTERNS|PLACEHOLDER_PATTERNS`（bash 侧）今天是两套字面量，将来加形态要两边各改一次才会绿——
  这是刻意的（抄同源就只是把 bug 复述一遍），但也是维护成本，登记在此。
- 本批不动 `--index-url` 那笔镜像单点（F 节候选 B/C 待拍板），因此**第一百一十五批的 runner 判据仍没拿到**：
  本批 push 之后若 `e2e-full` 再被 `timeout-minutes: 20` 取消，就还是同一道上限，不是用例。

### 第一百一十五批·补证（2026-10-13：runner 判据还是没拿到，但这次量清了它卡在哪——`e2e.yml:165` 的 `timeout-minutes: 20` 把整条 e2e 轨杀在装依赖那一步，而依赖源是被锁文件钉住的那一个镜像；顺带把"cancelled 归因不可判定"这条陈旧口径就地纠正）

#### 结论（先给判定性质）

- 本批**不改代码、不改配置、不放宽任何门**，做两件事：①把"旧 run 里的 `cancelled` 归因不可判定"这条已被测量
  推翻的口径就地纠正；②把第一百一十五批的 runner 判据状态与它的真实阻碍如实登记。
- 被纠正的原话有两处：`docs/CLEANUP_BACKLOG.md`（Flyway 那一条里写"**取消来源不能从日志判定**：`e2e.yml` 里没有
  `concurrency` 键，日志里也没有 timeout 声明"）和本文件第一百零八批的诚实边界（"旧 run 里的 `cancelled` 归因口径
  不变（`e2e.yml` 无 `concurrency`、日志无 timeout 声明，既不算过也不算被挤掉）"）。前半句到现在仍成立——
  `grep -rnE "^[[:space:]]*concurrency:" .github/workflows/` 与 `grep -rn "cancel-in-progress" .github/workflows/` 均退出码 1，
  所以"被新 run 挤掉"确实不成立（唯一的 `concurrency` 字样在 `eval-nightly.yml:142`，那是发给评测 harness 的 JSON 请求体字段，
  不是 workflow 级键）；
  **后半句错**：timeout 是声明在 workflow 里而不是打印在日志里，`e2e.yml:165` 给 `e2e-full` 设了
  `timeout-minutes: 20`（`:13` 给 `e2e-smoke` 设 15）。
- 量出来的归因（七条 `cancelled` 的 `e2e-full`：`38135767903`／`38137950016`／`38140336693`／`38145150097`／
  `38226782059`／`38395206533`／`38399840606`）：每条从 job 起算 **20m05 s–20m19 s** 就断，且 **7/7 停在同一步
  `Install Python dependencies`**（`e2e.yml:211-213`）。对照组关掉另一种解释：`ci.yml` 通篇不设 `timeout-minutes`，
  同一天被同一个源拖到 **44 分钟**的 CI run `38395206325` 就没有被取消 ⇒ 取消的判据是那道声明，不是并发，也不是人手。
  更贴的一组对照就在同一 commit 上：`9a5b27da` 的 CI `38399840634` 被同一慢源拖到 **36m32 s** 仍十一个 job 全绿，
  它的 E2E `38399840606` 却在 **20m19 s** 被取消——两边差别只有那道 `timeout-minutes: 20`。
  连带纠正：这七条**从没走到 `flyway:migrate`**，不属于 `docs/CLEANUP_BACKLOG.md` 那条里数出来的"连续 5 条死在
  同一 Flyway 步骤"家族（那 5 条是真正 `failure` 且步骤名对得上的）。
- 第一百一十五批的 runner 判据（CI 拓扑 30 条 ⇒ 推导式页数＝5 页、`tools.spec.ts` 在 runner 上绿）**仍未取得**：
  该批自己的 E2E run `38399840606` 于 12:46:57→13:07:16 被超时取消，日志里连一个用例名都没出现。
  同时没拿到的是 `demo-data` 竞态的第 4 个数据点；而它上一轮的归因写法（"本批 push 把 `38395206533` 挤掉了"，
  只存在于会话与记忆、没进过仓库文档）也是同一条陈旧口径的复发——那条 run 同样是 20m19 s 超时，本轮按测量改判。

#### 处置

- 两处就地纠正（`docs/CLEANUP_BACKLOG.md` 的 Flyway 条目、本文件第一百零八批那行），原话保留在纠正句里，不另立缺陷号。
- 新开一条"已取证未修"登记（`docs/CLEANUP_BACKLOG.md` F 节末）：**`--index-url` 钉在锁文件里 ⇒ 一个外部镜像的
  限流同时卡死 CI 与 e2e 两条轨**。钉点是 `python-ai/requirements.txt:12` 与 `python-ai/requirements-dev.txt:12-13`
  （pip 会执行 requirements 文件里的选项行），于是 `ci.yml:168/196/248/366`、`e2e.yml:61/213`、
  `eval-nightly.yml:76/168`、`plugin-security.yml:24/136/165` 八处安装全走 `mirrors.aliyun.com`；仓库里没有
  `--timeout`／`--retries`／`--extra-index-url`／`PIP_DEFAULT_TIMEOUT` 任何一处配置（grep 为空），韧性只剩 pip 默认的
  15 s 读超时 × 5 次重试。候选 B（八处加 `--timeout 60 --retries 10`，不动源也不动版本）与 C（换/加 index，动的却是
  被第九十二批冻结摘要钉住的锁）**都待拍板，本批一个都没执行**。
- 判据不足所以不动手：同一镜像在当天 10:35（run `38384435241`）和 11:13（run `38388749034`）两轮里让 e2e 全套
  73 条 **12m09 s** 走完——它不是恒久不可用，"持续限流还是这半小时抖动"本轮没量到。

#### 验证（取法全是 runner 侧读数，不照 YAML 猜）

- 窗口：`gh run view <id> --json jobs --jq '.jobs[]|select(.name=="e2e-full")|{conclusion,startedAt,completedAt}'`；
  停靠步骤：`gh api repos/xiaodu55/HFusionHub1/actions/runs/<id>/jobs` 取 step 级 `conclusion`
  （七条全部只有 `Install Python dependencies` 是 `cancelled`，其余为 `success`／`skipped`）。
- 镜像那两条红的原文：`gh run view 38395206325 --log-failed`——两个 job 各自唯一失败步骤都在
  `pypdf-6.19.0-py3-none-any.whl` 上 `Read timed out. (read timeout=15)` ×5 后 `error: connection-timeout` 退出 1；
  同段量到 numpy 16.9 MB＝68.0 kB/s（9m21 s）、pyarrow 50.1 MB＝95.7 kB/s（8m41 s）。
  同一 run 里不读锁的六个 job（`python-lint` 13 s／`docker-compose-validate` 10 s／`static-consistency` 11 s／
  `gitleaks` 12 s／`helm` 14 s／`frontend` 33 s）全绿。
- 本批是 docs-only：`scripts/static-checks.py` 全跑档 EXIT=0，测试计数不变（Python 2083，四处同源）。

#### 诚实边界

- 同 commit 的 CI run `38399840634` 已经收口，结论是 **success、十一个 job 全绿**，但整轮 **36m32 s**
  （12:46:56→13:23:28，取 `java` 的完成时刻）——对照同一天源正常时的两条：`38388749193` 里
  `python` 9m15 s／`eval-offline` 7m34 s／`java` 12m33 s，`38384435276` 里 `java` 11m42 s。这一次这四个 job
  是 33m26 s／32m07 s／28m58 s／36m32 s，**慢 4–5 倍但一个都没红**。⇒ 这构成同 commit 的自然对照：
  `ci.yml` 不设上限 ⇒ 慢到 36 分钟也跑得完；`e2e.yml:165` 设 20 分钟 ⇒ 同一条源、同一个源因，直接被取消。
  判据因此不是"源坏了"，而是**同一慢源在两个 job 上有两种结局，差别只在那道 `timeout-minutes`**。
- 归因到 `timeout-minutes: 20` 是"窗口＋停靠步骤＋对照组"三点一致，GitHub 没有在下载的日志里写
  "exceeded the configured job timeout"那句声明（只有 `##[error]The operation was canceled.`），所以"超时"与
  "恰好在第 20 分钟人手取消"这两个解释之间，本批靠的是七次都落在 20m05 s–20m19 s 这一条分布，不是那条字样。
- 第一百一十五批那处改动的正确性证据仍只有本地活栈（32 条／6 页）那一轮；CI 拓扑那一轮要等 e2e 轨能装完依赖。

#### 下一批（待拍板，按建议顺序）

- 先让 e2e 轨拿到一次 runner 结论：等镜像恢复后 `gh run rerun`，或按候选 B 给八处安装加超时重试（后者是 CI 基础设施改动，要点头）。
- 第一百一十三批·续（只剩 ②：`demo-data.spec.ts:23`/`:40`/`:71` 的 waiter 先注册再点）；第一百一十批 judge-cache；第一百零五批 license 策略。

### 第一百一十五批（2026-10-13：`tools.spec.ts` 那条 3/3 全红的红既不在开关也不在竞态——注册表按「status＋名称字母序」排、20 条演示业务工具把 `search_knowledge_base` 推到第 15 位，于是把写死的页数换成从页面自报条数推导、工具改成翻页找）

#### 结论（先给判定性质）
- 这条是**确定性陈旧判据**，不是竞态：`tools.spec.ts:11` 等"第 1 页能看到搜索知识库"、`:13` 写死
  `第 1 / 2 页`，两行都建立在"公开能力面 10 条"这个已经不存在的事实上。
- 第一百一十三批登记时写"未量"的两个数本轮量到了（取法是 python venv 里直接调
  `create_full_registry` ＋ `app/api/tools.py:42` 的 `_build_tool_entry` ＋ `:92-93` 那段 sort，
  同一函数同一排序键，不是照 YAML 猜）：
  ① 端点**不按注册顺序出**——`app/api/tools.py:92-93` 按 `(status 档, name 字母序)` 排，
  status 由 `agent_version` 推（`app/api/tools.py:30-34`：`1.0`→active、`1.1`→beta、`0.0`→experimental）；
  ② CI 拓扑（`e2e.yml` 那组 env）注册表 **30 条**，其中 20 条 B3 沙箱演示业务工具在
  `demo_business_tools.py:137` 写 `agent_version="1.0"` ⇒ 与三条 V1 知识库工具同属 active 档、
  按字母序插在前面 ⇒ `search_knowledge_base` 落**第 15 位**；
  ③ `Tools.vue:62` 是 `pageSize = 6` 的客户端分页 ⇒ 第 1 页渲染
  `add_device／apply_annual_leave／apply_sick_leave／cancel_auto_renew／create_incident／export_finance_report`，
  目标在**第 3 / 5 页**；
  ④ 活栈（第一百零九批那套 dev 栈）页面 aria 快照自报「全部能力 **32**／知识库 4／日常工具 27／
  联网能力 1／需要确认 2」＋`第 1 / 6 页` ⇒ **条数与页数本来就随拓扑变**（CI 30→5 页、dev 栈 32→6 页），
  任何写死的页数都是陈旧的。
- 两行当年为什么自洽也有反证：摘掉那 20 条 ⇒ 10 条 ⇒ 恰好 2 页、且第 1 页含 `search_knowledge_base`。

#### 处置（用户拍板 A＝改用例，不动产品可见面）
- 页数改成运行时推导：`totalCount` 读页面「全部能力 N」，`cardsPerPage` 数 `#ability-list article`
  首屏实际渲染的卡片数（就是每页条数），断言 `第 1 / ceil(totalCount / cardsPerPage) 页`。
- `搜索知识库` 改成**翻页找到它**（翻页上限＝推导出的页数；只在按钮未禁用时点，所以最后一次点击
  必然落在存在的页上），不再假设它在第 1 页。
- 原 `:20` 起那段（点「知识库」tab ⇒ `数学计算` 不出现 ⇒ 点卡片看示例问法／复制／技术详情）原样保留，
  分组语义仍是判据；演示业务工具继续算公开能力面的一部分（B 方案"让端点不列沙箱工具"没采纳）。
- 对照组登记进文档：`agent-operations.spec.ts:62` 的 `第 1 / 2 页` **不动**——那页走 `mockAgentApis(page)`，
  条数由 mock 定。写死在 mock 面是对的，写死在活注册表面才是这一条的红因。

#### 验证
- **改前取证**（活栈 `:3000`，`npx playwright test e2e/tools.spec.ts`）：`- waiting for
  getByText('搜索知识库', { exact: true }).first()` ⇒ `:11` 在活栈上以与 CI 同一条报错红，
  快照里读到的就是上面 ④ 那组数。
- 改后同一条命令：**2 passed（4.1 s）**。
- 全量 e2e 套件（本地活栈，73 条）：**63 通过 / 2 失败 / 8 跳过**（2.9 m）。那 2 条不是本批改的文件，
  且 CI 上是绿的：`document.spec.ts:52` 的索引状态收到 `FAILED`（期望 `COMPLETED`）、
  `write-note.spec.ts:60` 的回读 `content` 是 `undefined` ⇒ 判为本地 dev 栈拓扑与 CI 的差异，
  **未取证**，不当成本批的回归。
- `scripts/static-checks.py` 全跑档 EXIT=0（检查 19/20 同批在跑，本批没动 workflow）。
- python 侧测试计数不变（本批没碰 python／java）：README 与 `docs/ROADMAP.md:16` 仍是 2083；
  `docs/ROADMAP.md:16` 那行 e2e 口径从"59/4/10 ＋ 余两层未处置"改成本批的真实状态。

#### 诚实边界
- **runner 侧还没验**：本批改的正是 `e2e/tools.spec.ts`，CI 拓扑（30 条／5 页）要等下一次 push 的
  e2e run 才算实测；本轮的绿只到"本地 dev 栈拓扑（32 条／6 页）"。
- **e2e 的 TS 类型没有任何门**：`e2e/` 不在任何 tsconfig 的 `include`（`tsconfig.app.json:19` 只收
  `src/**`），`npm run lint` 只跑 `src`，CI 的 `npm run build`（`vue-tsc -b`）同样不覆盖 ⇒
  本批"过"的含义是 Playwright 真执行过这个文件，不是类型检查过。
- **没有新增静态门禁**：想把"用例不得写死注册表页数"机器化，就得先判"这个 spec 读的是活注册表还是
  mock"，那是代理指标（会造出假门），改按书面人工检查登记在 `docs/CLEANUP_BACKLOG.md`。
- 推导式页数在"总条数 ≤ 每页条数"时会去断言一个不渲染的分页标签（`Tools.vue:505` 的 `v-if totalPages > 1`）；
  三条 V1 工具＋20 条演示工具是无条件注册的，当前拓扑下不成立，所以没为它加分支。
- 还剩待拍板的只有 ②：`demo-data.spec.ts:23`/`:40`/`:71` 的 waiter 在 `click()` **之后**注册，
  是会被 retry 掩盖的竞态。本批没动那三处。

#### 下一批（待拍板，按建议顺序）
- 第一百一十三批·续（只剩 ②）：waiter 先注册再点（`Promise.all` 或把 waiter 提到 `click()` 前），纯测试卫生。
- 第一百一十批：judge-cache 驱逐；第一百零五批：license 策略（均需人拍板）。

### 第一百一十四批（2026-10-13：SBOM 那 35 个组件不是产品的依赖面——`sbom-generation` 从没装过 `requirements.txt`，空组件表还只打印 `WARNING`；先按锁安装再把组件面判定搬进 helper）

#### 结论（先给判定性质）

- 这一条**不是门红，是门绿而产物没有价值**：`sbom-generation` 在 run 38332373261 上是 success，
  步骤打印 `SBOM contains 35 components` 后退出 0，但那 35 个组件＝`cyclonedx-bom 7.3.1` 的闭包
  ＋ `pip`——产品依赖面一个都没进去。`cyclonedx-py environment` 读的是"当前解释器已装的包"，
  而这个 job 全程没装过产品依赖。
- 与检查 18（第一百零九批）同族：**配置写了、容器里没有实体**在这里是**产物生成了、产物里没有
  被描述的对象**。第一百零四批 CI 补证时登记为第四条未处置错位，本批处置；改的是产物描述的对象，
  不是把门放宽。
- 更糟的是它没有会红的地方：组件表为空时旧步骤只 `print('WARNING: SBOM has no components')`，
  退出码仍是 0。

#### 修复与判据

- 判据来自 runner 的产物本体（`gh run download -R xiaodu55/HFusionHub1 38332373261 -n sbom`），
  不是读 workflow 猜的：组件 **35**；`python-ai/requirements.txt` 顶层 pin **78**，ubuntu 侧按
  `sys_platform` marker 适用的是 **76**。把那份**改前的真产物**喂给改后的门 ⇒
  **42 缺失 ＋ 9 版本不符 / 76 适用 pin，退出 1**——缺失含 fastapi / uvicorn / httpx / numpy /
  pandas / pymilvus / pypdf，版本不符含 lxml / packaging / rpds-py / setuptools / tzdata / fqdn /
  idna / jsonpointer / pyparsing（后者是工具自己现拉的最新版本，不是锁钉的那一版）。
- 修复两半同做：
  ① `Generate SBOM` 步骤补 `pip install -r requirements.txt`。形状沿用**同一条流水线**里
  `license-check` 的 `Check licenses`——同一条 run 的日志 `:345` 实测它在同一个 ubuntu runner 上
  90 秒装完这 76 个包（`pywin32` / `win32-setctime` 按 marker 跳过），所以不是纸面推演。
  ② 组件面判定从内联 `python -c` 搬进 `scripts/ci/sbom_lock_coverage_gate.py`，退出码契约与
  `vuln_report_gate.py` 同源：**0** 覆盖齐且版本一致 / **1** 至少一个缺失或版本不符（逐个打印）/
  **2** 读不出被描述的对象（打不开、非 JSON、`components` 缺失**或为空**、锁里出现认不出的行形、
  同一个包钉两个版本、适用面为空）。空组件表从此是 2，不再是打印一句 `WARNING` 后绿。
- 适用面**算出来**而不是写死名单：锁里三条带 marker（`pywin32`、`win32-setctime` 是 win32-only，
  `uvloop` 是非 win32）。如果按 78 个 pin 一律要求出现在 SBOM 里，ubuntu runner 上就是一条
  **天生红**的门——这与第八十八批给锁补 `sys_platform` marker 是同一条因果。
  `--sys-platform` 只为门的门存在：不传就按当前宿主算，同一份 fixture 会在 Windows 开发和
  ubuntu CI 上得出不同结论，那正是要防的漂移。
- 名字的比对按 PEP 503 规范化（`Boolean.Py` / `typing_extensions` / `charset_normalizer` 与
  `boolean-py` / `typing-extensions` / `charset-normalizer` 同源），extras（`uvicorn[standard]`）
  只取分发名——这两条各有一例钉住，因为锁里两种写法都有。

#### 门自纠

- **口径纠正**：登记时写的是"44 个产品包在产物里根本不存在"，那是 **78 个 pin** 的口径；
  ubuntu 侧适用的口径是 **42**。两个数都对，但门报的是后者，文档与测试 docstring 一律改成
  "78 pin / 76 适用 / 42 缺失"三层写清，免得下一个人拿 44 去对门的输出。
- **门的判据一度想数组件个数**（"组件数与锁的 pin 数一致"）。实测否掉了：装完锁的环境里
  `pip` 这类不在锁上的包必然出现，改后容器实测是 **76 适用 pin / 78 组件**。判"个数相等"会把
  一条正确产物判红，于是门改成**下界判定**：锁的适用 pin 必须全在且版本一致，多出来的不判。
- **不用被测代码的输出构造输入**：`test_the_real_lock_is_covered_on_the_ci_platform` 的 fixture
  由测试侧的独立 oracle（列 0 正则＋marker 字面判断）从真锁现造，再与 helper 的解析对照；
  helper 若把 `--hash=` 续行或 `# via` 行当成 pin，这条会红而不是空转。
- 两条反空转前置照抄第一百零四批的纪律：`assert SBOM_GATE.is_file()`（否则 `python <不存在的脚本>`
  自己就退出 2，所有"必须退出 2"的用例会空过），以及 oracle 解析数 `> 50` 的下界。

#### 验证

- 改后的步骤形状在 `python:3.11-slim` 容器里按同序真跑：`pip install cyclonedx-bom==7.3.1` →
  `pip install -r requirements.txt` → `cyclonedx-py environment` → 门。门打印
  `SBOM covers all 76 applicable locked packages (78 components; extras describe the tool itself
  and are not judged)` 退出 **0**，抽查 fastapi / uvicorn / httpx / numpy / pypdf / pymilvus /
  lxml / packaging 全部在产物里。**同一份改前产物在这条门口判 1**（就是上面那 42＋9）——宿主上跑 helper
  显式 `--sys-platform linux` 复现一次，`python:3.11-slim` 容器里同参数再跑一次，两轮都数到
  **42 缺失＋9 版本不符 / 76 适用 pin**、退出 1，所以这个数不跟宿主漂。
- venv 全量 pytest 两轮 parity：**2234 passed / 18 skipped**（121.87 s 与 119.24 s 两轮同数）。
- `static-checks.py` 全模式 EXIT=0（含计数同步那条：Java 718 · Python 2083 · 前端 117）；
  `python-ai` 钉版 ruff（0.16.3）与 `scripts/ci/`＋本批判据文件 ruff 均 All checks passed。
- 门的门：`tests/test_plugin_security_gates.py` 32 例全绿（本批新增 17 例＝helper 语义 12 ＋
  步骤形状/真锁覆盖 5）；红→绿是分两步量的——先只写判据跑出 17 failed / 15 passed，再补 helper
  与 workflow。
- 计数：`def test_` 实测 2066→**2083**（本批 17 例），README 四处同源、`--test-counts` 绿，
  `docs/ROADMAP.md:16` 血统行追一行；`docs/CLEANUP_BACKLOG.md` 那条改成 `[x]` 并写处置；
  `docs/CI_GATES.md` 相关文件补 helper 与判据文件两条锚点。

#### 诚实边界

- 门是**下界**判定：产品依赖面必须全在且版本与锁一致，产物里多出 `pip` 这类不在锁上的组件不判红。
  所以它保证的是"CI 这一次生成的 SBOM 描述锁"，不保证部署镜像里装的就是锁——后者是第八十八批
  的锁与检查 18 那条线。
- `environment` 子命令的性质没变：它读实装状态，所以门的前提是"步骤确实按锁装过"。本批把它
  钉成文本契约（`pip install -r requirements.txt` 必须出现在 `cyclonedx-py environment` **之前**）＋
  语义契约（装完必须真覆盖），但没有把它换成 `cyclonedx-py requirements` 那条"直接从文件生成"的
  路线——**7.3.1 的那个子命令的旗标表没在本机核过**（仓内 venv 没装 cyclonedx-bom），第一百零四批
  的教训就是"没核过的旗标会把门写死"，所以宁可沿用同流水线已实测的形状。
- 改后的步骤当时**还没在 runner 上跑过**（本批登记原话）：容器实测只覆盖"python 3.11 ＋ linux ＋
  同一份锁"这一层，runner 的镜像与网络（`--index-url` 走 aliyun 镜像）当时没在同一台机器上验证过。
  **这条已闭合，但闭合方式本身是个新坑**：`plugin-security.yml` 的 push 触发带路径过滤（只列
  `python-ai/plugins/**`、`python-ai/requirements*.in`、`python-ai/app/core/plugin/**`），而本批改的
  正是 workflow 与 `scripts/ci/` 本身 ⇒ 本批那笔 push **不会**触发 `sbom-generation`，补证只能
  `workflow_dispatch` 手跑（run 38384621875 / job 115253222329）。该 run 的 `Generate SBOM`
  **success**，日志第 442 行打印
  `SBOM covers all 76 applicable locked packages (77 components; extras describe the tool itself and are not judged)`；
  产物本体下载后独立复算 ⇒ 组件 35 → **77**，76 适用 pin **缺失 0／版本不符 0**，锁外组件
  **只有 `pip`**；同 run 其余 job（`hash-verify`／`signature-verify`／`plugin-runner-build`／
  `vulnerability-scan`）绿，`license-check` 仍是第一百零四批那条预期红、原文一字未变。
- 不静音那条老规矩继续覆盖 `sbom-generation`：不删步骤、不加 `continue-on-error`、执行步骤上
  不出现 `if: always()`（`test_the_three_jobs_are_not_silenced`）。
- `license-check` 仍是第一百零四批登记的那条**预期真红**（SPDX 复合表达式），本批一个字没动它；
  第一百一十三批的②④两层（waiter 注册顺序 / tools 分页）仍未处置——**③"陈旧 label"已撤销**
  （判定取错了 service，详见第一百一十三批诚实边界③的原地纠正）。
- 本批补证那笔 docs-only push（`39be2f27`）自己带出的 run，把②的定性也改了：`CI` run 38388749193
  **11 个 job 全绿**（`gitleaks / static-consistency / eval-offline / frontend / python-lint / java /
  python-container / helm / python / docker-compose-validate / docker-build`），`E2E` run 38388749034
  的 `e2e-full` 由 60/3/0/10 变成 **61 通过 / 1 失败 / 1 flaky / 10 跳过**（213.3 s）——真红只剩
  `tools.spec.ts:11`（三条 run × 3/3 次尝试全红），`:71` 首次即过、`:40` 首败后 retry 通过，
  retry1 的 trace 里 `/api/demo/import` 花 **49.422 ms**（HTTP 200）。⇒ 本批补证把②写成
  "这 2 条的**确定死因**"、并据此宣布 113 原句"被 runner 否掉"，**这两步都判重了**：②是竞态
  （由 retry 掩盖的 flaky by construction），113 的"会转绿、但那是时序运气不是修好"成立。
  已按语义漂移就地改进第一百一十三批诚实边界②与末段，不另立缺陷号。

#### 下一批（待拍板，按建议顺序）

- 取本批 push 后 `Plugin Security Pipeline` 的 runner 结果做第一百一十四批补证——**已完成**，
  见上面诚实边界那条（`workflow_dispatch` run 38384621875，`Generate SBOM` success、产物 77 组件）。
  原写法"并把产物组件数与 78 对上"**作废**：门是下界判定，**组件个数不是判据**——runner 侧
  77 = 76 适用 pin ＋ `pip`，容器侧 78 = 这 77 ＋ `wheel`，两边集合差只有 `wheel` 一个元素；
  把 78 当期望等于把"装锁的机器上还多装了些什么"误当判据。
  顺带已补第一百一十三批那条 E2E run 的 `e2e-results-full`：`CI` run 38349608746 **success**
  含 `static-consistency`＝检查 20 在 runner 上跑过；`E2E` run 38349608765 与第一百一十四批
  push 的 run 38384435241 都是 `e2e-full` **failure**（60 / 3 / 10）、`e2e-smoke` skipped
  （按 `e2e.yml:10` 只在 PR 上跑的设计）。
- 第一百一十五批候选仍是两条：`license-check` 的许可证策略收敛（第一百零五批，**需人拍板**——
  LGPLv2+ 那条要么判红要么换包，不能给清单加名字放行 copyleft）、judge-cache 驱逐（第一百一十批）。
- SBOM 的**消费者**仍缺：产物只是 upload-artifact，没有任何门禁读它。要不要把它接进
  `vulnerability-scan`（对同一份锁审计、对同一份产物报告）属下一步决策。

### 第一百一十三批（2026-10-13：e2e 那 4 条红用 trace 拆开——报错写的是"等不到响应"，trace 里响应 16 ms 就回来了、还带着 200 里的信封 403；补上 CI 缺的那个特性开关并新增检查 20）

#### 结论（先给判定性质）
- 输入仍是 runner 事实：第一百一十一批补证＋撞号纠正那两笔（`5a55b042`、`418596c4`）push 后，
  `CI` run 38343229838 十一个 job **全绿**，`E2E` run 38343229817 只有 `Run full E2E suite` 红，
  计数与上一批补证一致（**59 通过 / 4 失败 / 10 跳过**）⇒ 检查 19 那两步在 runner 上成立，
  剩下的 4 条是更里面一层的东西。
- 本批只除了这 4 条**最外那一层**：CI 起的后端不是用例假定的那个后端
  （`DEMO_ENDPOINTS_ENABLED` 没声明）。剩下两层（spec 里 waiter 注册顺序、陈旧的 section label 期望）
  和 tools 那条分页**没有被本批处置**，判据与取证都写进文档了。

#### 修复与判据
- 取证链（`e2e-results-full/e2e-results.json` ＋ `playwright-traces`，三条 demo-data 的 retry1
  `trace.zip` 解出 `0-trace.network`）：报错都是 `page.waitForResponse: Timeout 10000ms exceeded`
  （`demo-data.spec.ts:23`/`:40`/`:72`），但 trace 显示 `/api/demo/import` **确实发出并回来了**，
  HTTP 200、响应体 `{"code":403,"message":"演示数据功能已关闭（DEMO_ENDPOINTS_ENABLED=false）…"}`
  （traceId `d36804ec03644249b011b204d5d97713`／`ac1ca5cb04b74d84b64e47721f767fce`／
  `57e397cc38ac42c6adee633a75fafd49`）。同一条 trace 的时间轴还量到请求 `114340` 起、历时 121 ms
  （≈`114461` 落地），而 `waitForResponse` 在 `114773.2` 才注册 ⇒ waiter 比响应晚 312 ms。
  **这两件事叠在一起**：开关关着让后端 16 ms 短路返回，把 spec 里"先点再注册 waiter"的竞态显形。
- 根因锚点：`application.yml:177` 的 `endpoints-enabled: ${DEMO_ENDPOINTS_ENABLED:false}`、
  `DemoController.java:39` 的 `@Value("${app.demo.endpoints-enabled:false}")`、`:44` 的
  `R.fail(403, …)`。dev 侧一直是开的（`docker/docker-compose.yml:272`、`docker/.env:24`），
  只有 `e2e.yml` 两个 java env 块（`:84-105`、`:236-257`）没带这个键——与检查 18 的
  "配置写了、容器里没有实体"同族，只是这一族是"开关默认关、CI 没显式开"。
  因为死在信封里，**步骤不红、探针不红、`Wait for Java backend` 绿**，退出码这一层永远看不见它。
- 处置：`e2e.yml` 两处补 `DEMO_ENDPOINTS_ENABLED: "true"`（与 dev compose 同源，带两行 WHY 注释）。
- 门禁：新增**检查 20**（`scripts/static-checks.py --e2e-backend-feature-flags`，已并入默认全跑档）——
  每个既 `spring-boot:run` 起 java 后端、又 `npx playwright test` 跑用例的 job，其 job 级 env ∪
  起后端步骤 env 必须显式声明 `DEMO_ENDPOINTS_ENABLED: "true"`；四种坏形状各红一次（缺键／值不是
  `true`／注释行冒充／键放错步骤），适用面为空与缩小都判红。
  `python-ai/tests/test_e2e_backend_feature_flag_gate.py`（18 例）是这条门的门：真仓库绿、
  接线进全跑档、PyYAML 独立 oracle 只用 YAML 复算 env 并集、外加一条跨文件同源判定
  （workflow 钉的值必须等于 dev compose `:272` 钉的值——防"门跟着 CI 一起变松"）。

#### 门自纠
- `_e2e_backend_flag_offenders` 的"适用面缩小"分支第一版写成 `E2E_TEST_JOBS - set()`（恒等于全集），
  于是裁掉 job 也判绿；改成先收集本轮真扫到的 job 名集合、再与下界作差，
  `test_shrunken_applicability_is_red` 才真的红。
- 门的红态是**先量后改**：检查 20 落地时真仓库先报 2 条 offender
  （`job 'e2e-smoke'，起后端在 :84` / `job 'e2e-full'，起后端在 :235`），补键之后转绿；
  收尾时再把两行键删回去复跑，`RED_RETEST_EXIT=1` 且两条 offender 再现，确认门咬的是这个键
  而不是别的形状。

#### 验证
- `python-ai` venv 全量 pytest 两轮 parity：**2217 passed / 18 skipped**（196.6 s 与 202.5 s 两轮同数）。
- `static-checks.py` 全模式 EXIT=0；检查 20 单独跑 `[ok]`；检查 19 与新门的门测试同跑 40 例全绿；
  venv 钉版 ruff 干净。
- 计数：`def test_` 实测 2048→**2066**（本批 18 例），README 四处同源、`--test-counts` 绿，
  `docs/ROADMAP.md:16` 同步；文档面新增 `docs/CI_GATES.md` 的检查 20 一节，
  `docs/CLEANUP_BACKLOG.md` 那条 4 红改成 `[x]`＋拆出三条未处置子项。

#### 诚实边界
- **门绿不等于用例绿**。这 4 条红里的三层只除了最外一层：
  ②`demo-data.spec.ts:23`/`:40`/`:71`（同族三处）都是 `await click()` **之后**才注册
  `waitForResponse`。登记时推断"开了关后导入会真做播种、耗时大概率越过注册点 ⇒ 红会转绿，但那是
  时序运气不是修好"。第一百一十四批的补证一度把这句判成"已被 runner 否掉"（run 38384435241 的
  trace 里 `/api/demo/import` 只花 38.342 ms 与 31.011 ms，`:40`/`:71` 各 3/3 次尝试全红）——
  **那个否定本身又被第三条 run 否掉**：run 38388749034（`39be2f27` 那笔 docs-only push，e2e 代码
  逐字节相同）是 **61 通过 / 1 失败 / 1 flaky / 10 跳过**，`:71` 首次就过、`:40` 首败后 retry 通过，
  retry1 的 trace 里同一个请求花 **49.422 ms**、HTTP 200，与 38.3／31.0 ms 同一量级。
  ⇒ 正确定性是**竞态（由 retry 掩盖的 flaky by construction）**：响应与注册点都在几十毫秒量级、
  谁先到不稳定，所以"会转绿、但那不是修好"成立；要改的仍是顺序——先注册再点（`Promise.all`
  或把 waiter 提到 `click()` 前）。未拍板，没动 `.spec.ts`。
  ③原登记"`:29`/`:78` 等的 `li:has-text("知识库文档")` 本身陈旧"——**这条判定取错了 service，已撤销**：
  用例点的是 `DemoController.java:63` 的 `/api/demo/import`，section label 由
  `DemoImportServiceImpl.java:143` 发 `"知识库文档"`（`:195/:200/:203` 同名字符串），招投标那条
  `/import-bid` 才是 `BidDemoImportServiceImpl.java:149-152` 的四个 label；
  `SetupChecklist.vue` 唯一的 `<li>` 在 `:251`（`v-for="section in lastSections"`），
  `:224` 的"（知识库文档、回答方案…）"在 `<div><span>` 引导文案里、不是列表项。
  runner 侧同样不支持原判：含 `:29` 的用例在 38349608765／38384435241 两条 run 上都是绿的，
  `:78` 从未执行到（同用例死在 `:71`）；
  ④`tools.spec.ts:11` 与开关无关（`Tools.vue:62` 是 `pageSize = 6` 的客户端分页，
  `:20` 才点分类 tab），而 **CI 注册表里工具条数与 `search_knowledge_base` 的排序位置未量**。
- 检查 20 只覆盖 e2e 轨：`deploy/docker-compose.prod.yml:187` 按设计保持
  `${DEMO_ENDPOINTS_ENABLED:-false}`（`/clear` 有数据破坏性），门不推广成"所有拓扑都得 true"；
  键也只钉这一条——它是被工件证实的那一条，其余特性开关没证据就不上门。
- ②④要怎么改属产品/测试侧决策，**没有拍板就没动任何 `.spec.ts`**；本批的"绿"只到
  "CI 起的后端与用例假定的后端是同一个"为止。**"那 3 条是否转绿"现在有三条 run 的数**：本批自己的
  push（run 38349608765）把 4 失败降到 **3 失败**（60 通过 / 10 跳过），闭掉的正是
  `should import demo data successfully`，**没有新增红**；第一百一十四批的 push（run 38384435241）
  是同一组三条、`flaky 0`（237.3 s，三条各 3/3 次尝试全红）；第一百一十四批补证的 push
  （run 38388749034，e2e 代码未变）只剩 `tools.spec.ts:11` 一条真红，另两条 demo 变绿、其中 `:40`
  记为 flaky。⇒ **唯一确定复现的是 ④**，② 是竞态；③不是"转绿"而是**原本就绿**，按语义漂移
  就地纠正，不另立缺陷号。

#### 下一批（待拍板，按建议顺序）
- 第一百一十三批·续：spec 侧两条（waiter 先注册再点、tools 分页）需要用户拍板改法；
  改前先把"CI 注册表里工具条数与排序位置"量出来。**原列的"陈旧 label 判哪一侧对"已撤销**
  （label 与期望一致，见上面诚实边界③），待拍板的从三条减到两条。
- 第一百一十四批：SBOM 的组件面改成 python-ai 产品依赖（含空组件表判定），见 `docs/CLEANUP_BACKLOG.md:265`。
- 第一百一十批：judge-cache 驱逐；第一百零五批：license 策略（需人拍板）。

### 第一百一十一批（2026-10-13：推送把三条 run 换成 runner 事实——Flyway 第一次真跑就绿，于是 e2e 翻到下一层"测试步骤写了、:3000 上的进程没有"，补两步并新增检查 19）

#### 结论（先给判定性质）
- 本批的输入不是本机测量，而是第一百零六～一百零九批那笔 push（commit `779fd23b`）带出的三条
  runner run：`CI` 38332373222 全绿；`Plugin Security` 38332373261 五绿一红，唯一红是第一百零四批
  已知、要等第一百零五批拍许可证策略的 `license-check`；`E2E` 38332373255 的
  `Run Flyway migrations` **第一次在 runner 上绿**——第一百零八批的 `-Dflyway.*` 修法由此从
  "本机判据"升到"runner 实测"。
- Flyway 绿既是好消息也是坏消息：它下面那一步 `Run full E2E suite` 从出生起第一次被执行，
  一跑就是 **35 失败 / 28 通过 / 10 跳过**，35 条报错是同一条
  `net::ERR_CONNECTION_REFUSED at http://localhost:3000/…`。这不是回归——前三次 e2e run
  （38233532705 / 38134153616 / 38025985552）都死在 `Run Flyway migrations`、测试步骤是 `skipped`，
  所以那 35 条一直是被上一层挡着的既有缺陷。
- 死因是两处各自"合理"的配置合谋：e2e.yml 两个 job 的步骤序列都是
  `npm ci` → `playwright install` → `npx playwright test`，中间没有任何一步起前端；而
  `hfusionhub-frontend/playwright.config.ts:31-38` 在 `CI` 为真时把 `webServer` 置成 `undefined`
  （那是本地开发用来自动起 `npm run dev` 的）。两边合起来 = CI 里没有进程监听 :3000。同 job 的
  `Wait for Java backend` / `Wait for Python AI` 两条轮询都是绿的，缺的正是前端那一条——与第一百零八批
  "配置写了、容器里没有实体"同族。
- 修法由用户拍板为**方案 A：在 workflow 里加显式两步**，而不是把 config 的 CI 分支改成自起
  `webServer`：显式步骤与同 job 另两条轮询同形、门禁读得到、失败时说的是"前端没起"而不是
  "playwright 内部超时"。

#### 修复与判据
- `.github/workflows/e2e.yml`（两个 job 各补两步，同形落地）：`Start frontend dev server`
  （`npm run dev &`，复用 job 已有的 `defaults.run.working-directory: hfusionhub-frontend`）＋
  `Wait for frontend dev server`（`curl -sf http://localhost:3000/` 轮询 30 次 ×2s，命中即
  `exit 0`，超时打印一行后 `exit 1`）。后台进程跨步骤存活是这轨的既有形态
  （`python -m app.main &`、`mvn spring-boot:run &`），本批没有引入新机制。
- `scripts/static-checks.py` 新增**检查 19**（`--e2e-frontend-server`，并入默认全跑档），按 job 名
  下界（`e2e-smoke` / `e2e-full`）逐个判四条规则：① 测试步骤之前必须有后台起前端
  （`npm run dev|preview … &`）；② 起前端必须晚于 `npm ci`，否则 `node_modules` 还不存在；
  ③ 起服务与测试之间必须有带 URL 的等待探针；④ 探针端口必须与 `playwright.config.ts` 的
  `baseURL` 端口同源，且探针要真能失败（缺 `exit 1` 的红判据不算红）。另加一支"双主人"判定：
  config 在 CI 档也自起 `webServer` ＋ workflow 又显式起 ⇒ 同一端口两个主人（`EADDRINUSE`），判红。
  适用面为空、适用面缩小了各自判红，删步骤或改命令名都不能让门变绿。
- `python-ai/tests/test_e2e_frontend_server_gate.py`（22 例）：真仓库绿 ＋ 七种坏形状各红一次 ＋
  一条 PyYAML 独立 oracle（有名步骤顺序逐条比对；起服务、顺序、探针、`exit 1`、端口两处同源
  只用 YAML 复算，防文本解析器与 YAML 分歧）。
- 行为侧不由文本门冒充：本机 `npm run dev` 起 vite 后 `curl -sf http://localhost:3000/` 返回
  **200**（冷启动 ready in 10354 ms，日志含 "Re-optimizing dependencies"），`/api/health` 经代理返回
  **502**（本机没有 8080，CI 上有），杀掉进程后同一请求返回 **000/refused**——探针的三种结果
  在真机上各量过一次。

#### 门自纠
- `_playwright_ci_autostarts` 第一版是 `webServer: CI \? (\w+) :`，读不出"CI 分支是对象字面量"
  （`{ port: 3000, … }`），于是"双主人"那支永远不会触发；`test_double_owner_is_red` 与
  `test_multiline_ternary_is_read_as_one_logical_line` 两条先红把它暴露出来。改成先把三行三元式
  压平成一条逻辑行、再取 `webServer:` 后第一个非空 token，判据是"该 token ≠ `undefined`"——
  与检查 18 的 `HEALTHCHECK \` 续行是同一条教训：**跨物理行的构造必须先压平再匹配**。
- `test_text_parser_agrees_with_yaml_on_step_order` 红过一次：文本解析器把 `services.*.ports` 下的
  `- 3306:3306` / `- 6379:6379` 认成了无名步骤（每 job 多 2 条）。没有去改共享解析器（它服务十几条门，
  改它的爆炸半径大于本批），改成"有名步骤逐条比对 ＋ 无名条数按 uses 步骤数与端口行数钉死"，
  噪声来源写进 docstring。

#### 验证
- 检查 19 先红（两条 offender，两个 job 各缺起前端与探针）→ 修 e2e.yml →
  `--e2e-frontend-server` 与 `--container-runtime-contract` 均 EXIT=0。
- `python-ai/tests/test_e2e_frontend_server_gate.py`：**22 passed**。
- Python 全量两轮 parity（`python-ai/.venv/Scripts/python.exe -m pytest -q tests`）：
  **2199 passed / 18 skipped，两轮 exit 0**（第一百零九批口径 2177 ＋ 本批 22 例）。
  中间一次误用宿主全局解释器（`D:\python3.11.9`，embeddable 发行版）跑出 3 红
  （`test_eval_retention.py::test_env_override_is_honoured` ＋ `test_milvus_tenant_migration_real.py` 两条），
  换回 venv 解释器即全绿——**这条红读的是本机安装形态，不是套件回归**，已在
  `env-network-and-tooling-quirks` 记忆里钉过，本批再确认一次。
- `static-checks.py` 全模式 EXIT=0；python-ai venv 钉版 ruff 干净；README 测试计数四处 2026→2048
  （本批新增 22 个 `def test_`）。

#### 诚实边界
- 本批只证明"**第一道死因已除**"，不证明那 35 条用例会转绿。登录态、seed 数据、mock LLM 这些
  更高层的失败要等下一次 push 的 e2e run 才分得清——检查 19 判的是"有没有进程监听 :3000"，
  不判"页面能不能用"。**这条边界在同批推送后就闭合了**（run 38336201364，commit `aaaf045b`）：
  `4 失败 / 59 通过 / 10 跳过`，31 条确实是死在 :3000 没人监听；剩下 4 条不在这层
  （`demo-data.spec.ts` 三条等 `li:has-text("知识库文档")`，而 `BidDemoImportServiceImpl.java:149-152`
  发的 label 是「招标文件知识库／企业资质库／历史标书库／示例投标项目」＝测试侧陈旧期望；
  `tools.spec.ts:11` 只有数据驱动的能力卡片没渲染），登记为第一百一十三批（原写作第一百一十二批，
  与 `eval-runtime` 可达性探针那条已占用的编号撞车，就地改号）。
- 60 秒探针预算没在 CI 上量过：本机 vite 冷启动 10354 ms，runner 首屏还要现编译依赖。若首跑仍超时，
  应当把预算调大，而不是把探针删掉。**也量了**：那两步（`Start frontend dev server` /
  `Wait for frontend dev server`）在同一 run 里都是 success，预算够用。
- 同一 push 的 `CI` run 38336201365 十一个 job 全绿，其中 `static-consistency` 就是全跑档的
  `static-checks.py` ⇒ 检查 19 第一次在 runner 上跑过。`e2e-smoke` 在该 run 里是 skipped，
  按 `e2e.yml:10` 的 `if: github.event_name == 'pull_request'` 设计如此，不是新缺陷。
- `docs/CI_GATES.md` 检查 17 那句"改后的步骤要等下一个 push 的 runner 才算真跑"已就地改写——本批
  它被证伪了（Flyway 那一步已经真跑并绿）。保留一条错误边界句属于只代理式断言。
- 补证段自己引入过一次**批次编号冲突**：4 条 e2e 红最初登记为第一百一十二批，而那个号在
  `docs/CLEANUP_BACKLOG.md` 与上面几处"遗留清单"里已经属于 `eval-runtime` 可达性探针。登记新对象前
  没先核号，只做了"下一号"的推断。四处引用已改为第一百一十三批并在原句里写明改号原因；编号没有
  门禁管，这类撞号只能靠"先 grep 再登记"挡。
- 顺着同一处核号往下看，还查出一段**更早的、本批造成的**撞号：`sbom-generation` 组件面那条在
  `docs/CLEANUP_BACKLOG.md:265` 与上面三处"下一批"清单里写作第一百一十一批，而 111 已被本批占用
  （它先前从第一百一十批抬到一百一十一批时也没先核号）。四处已改为第一百一十四批并逐处留了原号。

### 第一百零九批（2026-10-12：整栈第一次真跑——把"能写/能读"从镜像级抬到活栈级，量出四处"配置写了、容器里没有对应实体"的断链，并新增检查 18 把它们钉成四条规则）

#### 结论（先给判定性质）
- 本批的对象不是某条 CI 红，而是**一件从没做过的事**：`docker/docker-compose.yml` 9 服务整栈
  （java / python-ai / python-ai-worker / frontend ＋ mysql8 / redis7 / milvus / etcd / minio）
  第一次在本机起来、每台自报健康。`docs/PRODUCTION_OPS.md` 10.2 在那之前写着"上面这两条
  `docker compose exec` 本身仍未跑——它们要 fullstack 档整栈起来，本机没有跑过一次整栈"，
  跨服务互见只做到镜像层（第八十九批的 C1–C4）。
- 整栈一跑就量出四处断链，共同形状是**容器起得来、健康检查不红、API 正常，死的是别处**：
  D1 worker 的 `python -m arq arq_worker.WorkerSettings` 在镜像里没有那个模块（只 COPY 了 `app/`）
  ⇒ `ModuleNotFoundError` 崩溃循环 `RestartCount=14`，队列里那条 job 滞留 83.69s 无人消费，而
  API 日志照写 "dispatched via arq"；D2 dev compose 的 redis 起 `--requirepass` 而 java-backend
  只给 host ⇒ 登录 500 `RedisConnectionFailureException`（traceId `40bb29cf73464ff28f01caa37cbb40b8`），
  prod compose 同一段一直是成对的，所以这条只在整栈上暴露；D3 `application.yml` 的
  `python-ai.base-url` / `python-ai.engine.url` 是裸字面量而三档拓扑只设 `AI_SERVICE_URL`
  ⇒ java 的解析请求打到自己身上（`POST /api/document/204/parse` 400，traceId
  `9dae81714a9a41a1812c0cb3155fca89`）；D4 worker 继承镜像里给 uvicorn 写的 HTTP 探针
  ⇒ `Up (unhealthy)` 而 `probe_http=000`、`curl exit=7`，假红盖住了真要看的崩溃循环。
- 四处都是**把配置对齐到真实存在的实体**，没有一处靠放宽判据或删服务收口；四条方案逐条由用户
  拍板（D1 镜像补 `COPY`、D2 compose 补成对键、D3 两个键并入同一个环境变量、D4 显式关探针）。

#### 修复与判据
- `deploy/Dockerfile.python`：`COPY app/ app/` 之后补 `COPY arq_worker.py .`——入口模块在仓库根
  的顶层，compose 的命令、`arq_worker.py` 的 docstring、`app/core/tasks/queue.py` 与
  `app/utils/config.py` 的注释用的都是同一条命令，只有 `/app` 下真有这个文件才成立。
- `docker/docker-compose.yml`：java-backend 补 `SPRING_DATA_REDIS_HOST` ＋
  `SPRING_DATA_REDIS_PASSWORD: ${REDIS_PASSWORD:-}`（与 prod 同形）；python-ai-worker 补
  `healthcheck.disable: true`，存活信号改看 redis db2 的 `arq:queue:health-check`。
- `java-backend/src/main/resources/application.yml`：`python-ai.base-url` 与
  `python-ai.engine.url` 改成 `${AI_SERVICE_URL:http://localhost:9000}`——键名保留，来源收成
  只有一个；宿主缺省值留在冒号之后，本地起栈照旧可用。
- 新增 `scripts/static-checks.py` 检查 18（`--container-runtime-contract`，已并入默认全跑档），
  四条规则：①每条 `python -m arq` 的入口模块必须落在其 build 上下文那份 Dockerfile 的 `COPY`
  派生顶层模块集合里、且源文件真在上下文里；②凡拓扑以 `--requirepass` 起 redis，声明了
  `SPRING_DATA_REDIS_HOST` 的工作负载必须同时声明 `SPRING_DATA_REDIS_PASSWORD` 或 `REDIS_PASSWORD`；
  ③java 侧以 `:9000` 为缺省值的 `@Value` 属性必须在 yml 里全部由**同一个**环境变量喂，且
  dev/prod/helm 三档都声明它；④跑 worker 的服务必须显式 disable 或换成不打那个端口的探针。
  四条各按拓扑钉数量（worker 1 / redis 客户端 2 / 出站点 10），**适用面为空本身判红**。
- 门的门：`python-ai/tests/test_container_runtime_contract_gate.py`（39 例）。除了"每种历史坏形状
  注入时各红一次"，还钉三条"形状对但指向别处"的语义面（密码键插值的必须是 redis 自己用的那个
  变量、`COPY` 的目的地必须是 WORKDIR、worker 自定义探针仍打 `:9000` 照样红），以及两个
  PyYAML oracle（command 令牌、application.yml 的点号路径），helm 的 redis 至今无 `--requirepass`
  也写成断言——日后上密码时必须拓宽规则而不是被门默许。
- 建门过程中门自己纠了一处：`_image_probe_port` 第一版按物理行匹配 URL，而真仓库那行 HEALTHCHECK
  带 `\` 续行（`deploy/Dockerfile.python:52`），端口恒为 `None` ⇒ "自定义探针仍打服务端口"那一支
  永不触发。改成先拼逻辑行再匹配。

#### 验证
- 活栈（`docs/PRODUCTION_OPS.md` 10.2.1 的 W1–W7）：§10.2 那两条 `exec` 逐字跑通；上传
  `title=b109-java-upload` → `document.id=204`，`file_path=/app/uploads/documents/
  cfc1458c-850b-4524-b3f4-39ac80844a4b.txt`，宿主 / java / python / python-worker / 独立挂卷容器
  **五处 sha256 全等于** `879595640d62f69aa4e289c609a86d7537bf32135c3c120d1cc87181dc617bd0`；
  登录 `code=200`（token 36 字符，会话确实落进 requirepass 的 redis7）；`parse` **HTTP=200**
  且 java 日志写明 `调用Python引擎: http://python-ai:9000/api/parse`（改前是同一条请求 400 打
  `localhost:9000`）；worker `0.50s → 4ed30ccc…:process_document({'document_id': '204', …})`、
  `arq:queue` zcard=0；`docker inspect` → `health=<none> restarts=0`。
- 套件：`python-ai` 全量两轮一致 **2177 passed / 18 skipped**；`static-checks.py` 全模式 exit 0
  （新增 39 例后 README 的 Python 计数 1987→2026，四处同步）。
- `ruff check` 对本批新文件干净；顺带量到 `scripts/static-checks.py` 里一条 HEAD 上就存在的
  F541（`:995` 那行 `f"[ok] 依赖锁可安装面："`，改前在 `:974`），CI 的 ruff 范围是 `python-ai/`
  而非 `scripts/`，本批没动它。

#### 诚实边界
- 端到端只到"按外部依赖失败"这一格：worker 消费后嵌入调用
  `OLLAMA_BASE_URL=http://host.docker.internal:11434` 报 `Network is unreachable`，文档 204 终态
  `status=3 / chunk_count=0`；但回调真的回到了 java 并写了库（`文档状态已更新: 204 -> FAILED`）。
  ⇒ 缺的是一个可达的嵌入端点，不是配置，这条留在 10.3 未收口第一位。
- 三处 compose / Dockerfile / yml 改动只在**本机活栈**上验过；CI 跑的是 prod compose 与 helm，
  dev compose 这条轨在 runner 上没有等价执行。D3 的生效前提是重建 java 镜像（yml 打进 jar），
  本批复测就是这么做的，但它说明规则③本质是文本一致性检查，不证明部署面真的换过镜像。
- 一处活栈事实差点被误读：手工往卷上放的探针文件被 java 的 `OrphanCleanupScheduler` 清掉了
  （日志 `已清理孤儿文件: b109-shared.txt` 等 5 条）。这不是缺陷，但任何"往卷上写文件做验证"都
  必须把这个回收器算进去。

#### 下一批
- 第一百一十批：judge-cache 驱逐。第一百零五批（license 策略）仍等人拍板。
### 第一百零八批（2026-10-12：Flyway 那一步在 CI 里红了一路——把连接信息搬到插件真读的名字上，顺带把插件版本钉成运行时的那个引用）

#### 结论（先给判定性质）
- 对象是第一百零四批登记、当时判为"跨面缺陷、处置要连 pom 一起"的那条红：
  `e2e.yml` 两处与 `eval-nightly.yml` 一处的 `Run Flyway migrations` **从诞生起每次 execution 都失败**，
  连续 5 条 run 的 `e2e-full` 停在同一句
  `FlywayException: Unable to connect to the database. Configure the url, user and password!`
  （本批再次从 run 38233532705 的日志第 620 行取到同一句）。
- 机理不是"MySQL 起不来"：同仓 `ci.yml:380-391` 早已写成
  `-Dflyway.url/user/password`，它在 runner 上是绿的。flyway-maven-plugin 只认
  `-Dflyway.*`、`flyway.conf`、`FLYWAY_*`，**不认 `SPRING_DATASOURCE_*`**，仓库里也没有
  `flyway.conf`（全仓 find 为零）⇒ 那三个 Spring 键是空转的开关，插件拿到空配置。
- 第二半是**版本不同源**：`java-backend/pom.xml` 当时没有声明 `flyway-maven-plugin`，
  `mvn flyway:migrate` 走 Maven 前缀从 central 浮动解析（日志里解析到 11.7.2，
  外加两条 `Could not transfer metadata … 401` 噪声），于是"命令行插件版本"与运行时
  `flyway-core` 的关系靠运气。
- 两处都是把**判据/配置对齐到真实读取方**，没有任何放宽：没有删步骤、没有加
  `continue-on-error`、没有把红的那一步改成软失败。

#### 修复与判据
- 三处站点统一成 `ci.yml` 的参照形态（块标量 + 三个 `-Dflyway.*`，库/账号取该 job 的
  `services.mysql.env`＝`hfusionhub / e2e / e2e-pass`），并删掉步骤里空转的
  `SPRING_DATASOURCE_*` 三键——`Start Java backend` 那一步**保留**它们（那边读 Spring 的是应用，不是插件）。
  改后锚点 `e2e.yml:76-83`、`e2e.yml:215-222`、`eval-nightly.yml:90-97`。
- `java-backend/pom.xml:211-219` 声明 `flyway-maven-plugin`，版本写 **`${flyway.version}`** 而不是数字：
  `flyway-core` 依赖不带 `<version>`、由父 BOM 的同一个属性管理，写引用就是**结构同源**，
  写 `11.7.2` 则是把同源复制成两处会各自漂移的常量。`spring-boot-dependencies:3.5.16` 里
  `<flyway.version>11.7.2</flyway.version>` ⇒ 本批**没有**改变今天实际执行的版本，消除的是未来的悄悄换版。
- 新增 `scripts/static-checks.py` **检查 17**（`--flyway-cli`，已并入默认全跑档：旗标声明 `:1866`／全跑档条件 `:1876`／默认置真 `:1883`／分派 `:1917`）：
  缺任一 `-Dflyway.*`、flyway 步骤 env 里出现 `SPRING_DATASOURCE_URL/USERNAME/PASSWORD`、
  步骤带 `continue-on-error: true`、按文件的调用数与 `FLYWAY_STEP_EXPECTATIONS`（ci 2 / e2e 2 / eval-nightly 1）不符
  ⇒ 红；**适用面为空（一处 flyway 调用都找不到）本身判红**，所以"把红的那一步删掉/改 goal"这条路被堵住。
- 门的门 `python-ai/tests/test_flyway_cli_gate.py`（19 例）：真仓库绿、默认全跑档接线在、
  六种注入漂移各红一次（只给 Spring 键／正确旗标＋残留空转 env／`continue-on-error`／删一处步骤／
  三处一起改 goal／pom 未钉·钉数字·缺 `<version>`·pom 缺失）；
  旗标值按 PyYAML 与**同一 job 的 `services.mysql.env`** 逐字比对（形状对但指错库照样红）；
  解析器反空转两例——文本解析出的脚本与 YAML 解析出的脚本按空白归一必须一致、步骤名不得为空。
- 写这条门时先被自己踩到两个坑，都留在了代码与 docstring 里：
  ① 步骤块若按"下一个 `- xxx:`"切，会一路吃进 job 级 `defaults:` 里那个**空的 `run:`**，
  真脚本被空值盖掉 ⇒ 改成按缩进切块（`_step_block`）；
  ② `- name:` 那行的键在列表符**后面**（6 空格 + `- `），只按纯缩进匹配会把步骤名读成空、
  违规报告指不出是哪一步 ⇒ `_step_key` 同时接受 `key_col` 列与 `- ` 前缀两种形态。

#### 验证
- 红判据先行：改前 `--flyway-cli` 报 7 条违规（三站点 × 两条规则 ＋ pom），`ci.yml` 未被牵连；
  改后 `[ok] 扫描 5 个 workflow / 5 处 flyway 调用`。
- **活库行为判据**（本机 `mysql:8.0` 容器＝MySQL 8.0.46，库 `hfusionhub`、用户 `e2e/e2e-pass`，
  与 workflow 的 service 同凭据）：① 旧形状（只有 `SPRING_DATASOURCE_*`）复现 CI 日志那句异常
  （`b108_head_form.log:41`）；② 新形状 `Successfully applied 87 migrations to schema hfusionhub,
  now at version v86`（`b108_fixed_form.log:106`）；③ `flyway:info` 绿；
  ④ 库内侧 `COUNT(*)=87 / SUM(success=1)=87 / MAX(installed_rank)=87`，schema 落 70 张表
  （迁移文件 87 个＝V1–V86 加一个 `V10_1`）。
- 钉版真的解析得到：`mvn -o flyway:info` 报出的 goal 坐标是 `org.flywaydb:flyway-maven-plugin:11.7.2:info`
  （离线只缺两个 jackson jar，说明 `${flyway.version}` 已展开、旗标已生效）。
- `test_flyway_cli_gate.py` ＋ `test_workflow_run_scalars.py` ＝ **34 passed**；
  `scripts/static-checks.py` 全模式退出 0（检查 14/15/16 同轮绿）；新测试文件 ruff 干净；
  `mvn -o -B validate` 退出 0（pom 加了 `<plugin>` 之后模型仍能建起来），spotless 只管 Java 源码、不碰 pom。
- 全套件连跑两轮一致：**2138 passed, 18 skipped**（205.93 s / 210.90 s，日志 `b108_pytest_run1/2.log`）。
  与第一百零七批那轮的 `2083 passed, 12 skipped` 差额按文件对得平：本批新增 19 条
  （`test_flyway_cli_gate.py`），其余 42 条来自 `tests/test_plugin_container.py`——那一轮的命令显式带了
  `--ignore=tests/test_plugin_container.py`（本批这轮没带；该文件单独 `--collect-only` 恰为 42 条，
  且第一百零七批那份日志里文件名 0 命中）。于是 2083 ＋ 19 ＋ (42−6) ＝ 2138、12 ＋ 6 ＝ 18，两侧闭合。
  那 6 条以 `Docker daemon not available` 跳过，而同一时刻 `docker` CLI 与容器都在跑——
  python 侧 `docker.from_env()` 的探测与 CLI 不同源，属环境事实，本批没有改动容器轨任何一条判据。
- 计数：新增 19 个 `def test_` ⇒ README Python 1968 → **1987**（badge、第 37/47/241 行四处）。

#### 诚实边界
- 检查 17 只回答"旗标到没到命令行""插件钉没钉""步骤还在不在"，**不证明迁移内容正确，也不证明
  改后的那一步在 runner 上会过**——后者只能在下一个 push 的 `e2e-full` 日志里看，本批没有跑 e2e 全栈。
- 它也不查 `-Dflyway.locations` 等其余配置；库名/凭据同源由语义层兜，SQL 本身仍归检查 4/5。
- 活库测的是"空库→迁移全绿"，没有业务行；`hfusionhub` 那份数据随容器一并删除。
- `scripts/static-checks.py:974` 那条 ruff `f-string without placeholders` 是**第八十八批留下的既有行**，
  不在本批 diff 里，按"不顺手清理无关行"留着（`ci.yml` 的 ruff 只跑 `python-ai/`，所以它从未让 CI 红）。
- 旧 run 里的 `cancelled` 归因口径**已由第一百一十五批·补证就地纠正**（原写作"口径不变"）：`e2e.yml` 确实没有 `concurrency` 键，但 timeout 声明写在 workflow 里——`e2e.yml:165` 给 `e2e-full` 设了 `timeout-minutes: 20`，7 条 `cancelled` 每条从 job 起算跑 20m05 s–20m19 s 就断，且 7/7 停在同一步 `Install Python dependencies`（逐条窗口与取法见 `docs/CLEANUP_BACKLOG.md`）。

#### 下一批
第一百零九批：全栈 compose 真跑一次（fullstack 档 + mysql/redis），把"能写/能读"从镜像级升到活栈级，
顺带验 `UPLOAD_DIR` 那个空转键与 `docker compose exec` 那对命令。

### 第一百零七批（2026-10-12：审计 flush 的超限判定从"读快照"抬到"读当前行"——运维的 dead-letter 回灌不再被一条在途 flush 吞掉；顺带把 autouse fixture 的后台 flusher 停掉，修的是测试隔离）

#### 结论（先给判定性质）
- 对象是第一百零六批**第四次全套件**踩到的那条红（`TestRetryDeadLetters::test_second_retry_is_idempotent`，
  `assert 1 == 0`）。当时已按同一套确定性编排对 HEAD 与第一百零六批改后**各跑一遍、两边都红**，
  判定为独立缺陷、没有折进第一百零六批，也没有放宽那条断言——本批就是它的处置。
- 缺陷在生产语义上是实的：`_do_flush` 把"取快照 → 锁外做出站 I/O → 按快照里的 `retry_count` 判超限 → 落 dead-letter"
  分成四步，`_db_lock` 只保证每条语句原子，**从来不覆盖"快照 → 回写"这段距离**。于是运维点一次
  `retry_dead_letters()`（`SET dead_letter = 0, retry_count = 0`）之后，一条在途的后台 flush
  会拿着回灌前的 `retry_count` 把判定重新落下去 ⇒ **这次点击等于没生效**，行又翻回 dead-letter 且计数被加回。
- 套件偶发红是**同一个机理的测试面**：autouse fixture 只换库、不停 daemon，上一条用例留下的
  `audit-flusher` 会写进当下这条用例的临时库。一次 drain 只该打一行"超过最大重试次数"，
  而那份日志里同一 id 打了**两次**（42.107 / 42.113）——第二次来自另一条线程。
- 两处都是**改判据读的东西**，不是改判据的宽严：没有任何断言被放宽、没有加 skip／重跑／提高阈值。

#### 修复与判据
- 实现侧删掉 `_mark_dead_letter`（改前 `audit.py:225`）与 `_increment_retry`，合成
  **`_register_failed_attempt(entry_id) -> bool`（现 `:249`）**：读 `retry_count`、自增、
  落 `dead_letter = 1` 三步共用**同一次** `with _db_lock:`，返回值即"这一行是否被**本次调用**标成 dead-letter"。
  比较的仍是"自增之前读到的计数"，与旧判定 `entry.retry_count >= _MAX_RETRIES` **同形**，
  只是把读的对象从出站快照换成了行的当前状态；`_MAX_RETRIES` 走 Python 侧比较而非 SQL 常量拼接，
  所以测试对它的 patch 照旧生效。`_do_flush`（现 `:312`）不再自己判超限，只按返回值决定要不要打 warning（`:339`）。
- 行为判据 `python-ai/tests/test_plugin_audit.py::TestFlushVerdictReadsCurrentRow`：把取证脚本的确定性编排
  搬进套件——在途线程的 `_post_to_java_backend` 被 patch 成"发出 `snapshot` 事件后卡在 `release`"，
  主线程在这道窗口里跑完一轮 `_do_flush()` ＋ `retry_dead_letters()`，再放行在途线程并 join。
  改前红（`first=1 second=1`，`get_sync_status()["dead_letter"] == 1`）⇒ 改后绿（`first=1 second=0`，`dead_letter == 0`）。
- 隔离侧 `python-ai/tests/conftest.py`：新增 `_stop_audit_flusher()`
  （置 `_flush_stop`、摘走 `_flush_thread` 句柄、join 30s；join 不掉就 `pytest.fail` 并写明死因是
  "它会把这次 flush 写进下一条用例的临时审计库"，同时提示先查真实出站 POST 的 30s/10s 超时），
  autouse fixture 在 `_reset_db()` **之前和之后**各调一次——换库前先停线程，只换库不停线程等于
  让上一条用例留下的线程写当下这条的库。
- 反空判定 `TestAuditFlusherIsolation::test_record_audit_really_starts_the_daemon`：先证明
  `record_audit` 确实留下一个活着的 `audit-flusher`，否则"下一条用例开局没有残留线程"那条会凭空绿。

#### 验证
- 红判据改前：**2 failed, 1 passed, 51 deselected**——两条红分别是
  "在途 flush 按旧快照把刚回灌的行又标回了 dead-letter" 与 "上一条用例留下的后台 flusher 还活着（`['audit-flusher']`）"。
- `tests/test_plugin_audit.py` 51 → **54 passed**；
  `test_db_lock_lifetime_gate.py + test_plugin_audit.py + test_plugin_security.py` 合跑 **84 passed**。
- 检查 16 的反空阈值按**构成变化**从 `>= 13` 改成 `>= 12`：12 ＝ 9 个 `_get_db()` 调用点 ＋ `_reset_db` 里
  3 处 `_db_conn` 读写；第一百零六批量到 13 是因为那时 `_mark_dead_letter` 里还有第 10 个调用点，
  本批把它折进 `_register_failed_attempt` 就少一个。**是构成变了，不是规则匹配不上**，
  这笔账写进了 `tests/test_db_lock_lifetime_gate.py` 的 docstring 与 `docs/CLEANUP_BACKLOG.md`。
- `scripts/static-checks.py` 全模式退出 0，检查 16 那行现为"扫描 1 个碰共享连接的模块、**12 处**引用，
  全部在 `with _db_lock:` 体内"；ruff 干净。
- 全套件连跑两次绿：`2083 passed, 12 skipped`（日志 `b107_pytest_run1.log`、`b107_pytest_run2.log`）。
  第一百零六批是"三次绿 ＋ 一次红（红的那条与本批无关）"，本批之后第四次那种红不再出现。
- README 的 python 用例数按检查 3 同步 1965 → **1968**（四处站点，字节级替换保持 LF）。

#### 诚实边界
- 本批修的是**判定读当前行**，不是"给回灌加锁"。`retry_dead_letters()` 与 flush 之间仍无跨语句事务隔离：
  若运维回灌发生在在途 flush **取快照之前**、而该行的出站又失败，那条行会被正常地再计一次数——
  那是预算语义，不是本批的缺陷。本批关掉的是"判定用**已过期的**计数推翻**已生效的**回灌"。
- `_register_failed_attempt` 的读＋自增＋落标记在同一次持锁里，因此**不需要** `RLock`，
  第一百零六批"锁外取引用"的约定一分没退；检查 16 对新函数同样核对通过。
- 停 flusher 的 fixture 只在测试面生效，生产侧 `flush_on_shutdown`（现 `:584`）"预算到点仍带着
  在跑线程返回"那条观察**没有**随本批处置，仍登记在 `docs/CLEANUP_BACKLOG.md`，
  优先级低于第一百一十一／一百一十二批。
- 全套件历史 1-in-4 的偶发红，本批按机理关掉了一个来源（快照判定 × 跨用例 daemon）；
  连跑两次的绿是"这两个来源不再出现"的证据，不是"再也不会红"的证明。

#### 下一批（按红面与上线阻塞度排序）
1. **第一百零八批**：Flyway 迁移步骤四处统一到 `-Dflyway.*`（`e2e.yml:82`、`e2e.yml:221`、`eval-nightly.yml:96`
   三处只给 `SPRING_DATASOURCE_*`，`ci.yml:382-383` 已是写对的那一份）＋ 在 `java-backend/pom.xml`
   显式声明并钉住 `flyway-maven-plugin`。判据要证明迁移**确实发生**（表结构落到 e2e/eval 库），
   不得靠删步骤或 `continue-on-error` 变绿。
2. **第一百零九批**：全栈 compose 真跑一次，把"能写／能读"从镜像级升到活栈级。
3. **第一百一十批**：judge-cache 驱逐。
4. **第一百一十四批**：SBOM 组件面（原写作第一百一十一批；111 已被本批的 e2e 前端服务契约占用）。**第一百一十二批**：eval-runtime 可达性探针（那条 run 38224268851 的第二条红）。
5. **第一百零五批仍搁置**：license-check 的 SPDX 复合表达式与 copyleft 口径要**人拍板**，
   不能由改代码的一方顺手往允许清单里加名字。
### 第一百零六批（2026-10-12：审计库那个跨线程共享的 SQLite 连接——取用与关闭都收进 `_db_lock` 体内，并新增检查 16 把"锁外取引用"这种形态钉死）

#### 结论（先给判定性质）
- 对象是第一百零三批登记、第一百零四批补证时拿到崩溃栈的那条：本地跑全套件会**偶发**解释器级崩溃
  （`PYTEST_EXIT=139`，一次 `Windows fatal exception: access violation`、更早容器里一次
  `Fatal Python error: Segmentation fault`）。CI 的 `python` job 在同一把锁上一直是绿的
  ⇒ 这是"本地跑法才有概率命中"的窗口，不是环境问题，也不因为不常发生就当噪声。
- **判据不建立在"多跑几次看运气"上**：行为侧两条确定性红（其中一条改前是稳定红，不是概率红），
  形态侧新增 `scripts/static-checks.py` 检查 16。崩溃本身本批没有复现，也**不声称**复现过——
  关掉的是它赖以发生的形态。
- 推荐方案的一半被否掉了：第一百零三批当时写的是"`_reset_db` 全程持 `_db_lock`"，**单做这一半
  仍留窗口**，因为漏的是"引用在锁外取"。`_increment_retry`/`_cleanup_synced` 这些函数的形状是
  `db = _get_db()` 然后 `with _db_lock:` —— 锁排开了"execute 撞 execute"，排不开
  "锁外握住的对象 vs `close()`"。所以处置必须两半同做。

#### 修复与判据
- 行为侧 `python-ai/tests/test_plugin_audit.py::TestDbConnectionLifetime`（2 例，先跑红再改）：
  - `test_reset_db_waits_for_the_db_lock`——主线程外起一个线程占住 `_db_lock`，再起线程调
    `_reset_db(str(tmp_path / "relocated"))`，断言 0.3s 内**还没跑完**。改前红：
    `AssertionError: _reset_db 不持 _db_lock：锁还被占着它就把连接关了`。
  - `test_concurrent_first_use_builds_exactly_one_connection`——8 个线程并发首次写审计行，
    数 `_init_db()` 被调用几次。改前**稳定红：8 个连接**（每个都真的 `makedirs`＋`connect`＋
    建表＋commit，只有最后一个进 `_db_conn`，其余成为没人关的句柄）。
    **就地纠正**：这条最初写进判据时标的是"防回潮、改前靠运气不是稳定红"，实测把它证伪了——
    检查-然后-换绑的窗口在懒建连接这种慢路径上是**每次必中**，注释已按实测改写。
    诚实说清代价面：这 8 个连接都写同一个文件且各自 commit，所以**不丢审计行**；
    损失的是 fd 与"谁以为自己拥有这个库"的确定性。
- 形态侧新增 **检查 16 `--db-lock-lifetime`**（已并入默认全跑档，CI 的 `python scripts/static-checks.py`
  无参调用即覆盖）：用 `ast` 算出每个 `with _db_lock:` 体的行号区间，要求
  R1 所有 `_get_db()` 调用（含 `mod._get_db()`）、R2 除 `_get_db` 本体以外所有 `_db_conn` 读写
  都落在区间内。改前对 HEAD 的 `audit.py` 量到 **13 处违规 / 核对到 13 处引用**
  （10 处 `db = _get_db()` 在锁外 ＋ `_reset_db` 里 3 处连接读写），改后 **0 处 / 仍是 13 处**——
  两侧引用数相等，绿不是因为少扫。
- 判据本身也要有判据：新增 `python-ai/tests/test_db_lock_lifetime_gate.py`（12 例）钉住
  真仓库绿、接线进默认全跑档、锁外取连接红、锁外关连接红、整组改名**不会**静默变绿
  （适用面按"有没有碰这三个名字"算，一个都没碰到就判红）、语法坏掉的模块报"无法核对"而不是跳过、
  以及 `with _db_lock: db = _get_db()` 这种同行写法不误伤。
- 实现（`python-ai/app/core/plugin/audit.py`）：`_reset_db` 的 close＋换绑整段进 `with _db_lock:`
  （现 `:171`），10 处取连接全部挪进锁体内（`_persist_to_sqlite:200`、`_cleanup_synced:276`、
  `_queue_counts:536` 等），`_get_db` 的 docstring 把前置条件写明——"调用方必须已经持有 `_db_lock`"
  （`:158-166`），门禁测试钉这句话不消失。
- **锁没有换成 `RLock`**：约定是"调用方持锁后再取连接"，`_get_db` 本体不取锁，因此不产生重入需求。
  这条不是想当然——用 `ast` 扫过全部锁体，锁内再调用本模块其它 DB 函数的情况为 0
  （只有 `json.dumps`、`time.time()`、sqlite 自己的 `execute/commit/fetch*`），换成 `Lock`
  也不会自锁死。

#### 验证
- **套件连跑三次**（同一命令、venv 解释器口径）：改生产码后两次
  `2068 passed, 12 skipped`（220.74s / 239.89s，scratch `b106_pytest_run1/2.log`），
  加进门禁测试文件后第三次 `2080 passed, 12 skipped`（234.77s，`b106_pytest_run3.log`），
  三次退出码全 0，日志里 `access violation` 与 `Segmentation fault` **0 命中**。
  对账：第一百零四批基线 `2065` ＋ 补证那一笔加的 1 例（dev-lock 一致性）＋ 本批行为判据 2 例 ＝ 2068，
  ＋ 检查 16 的门禁测试 12 例 ＝ 2080，逐位对得上。
- `python-ai/tests/test_plugin_audit.py` 单跑 `51 passed`（49 → 51）。
- **第四次全套件不是绿的**（这次把完整日志留在文件里，因为上一轮 `| tail -6` 只捞到 teardown 噪声、
  汇总行被挤掉）：`1 failed, 2079 passed, 12 skipped`，退出码 1，红的是
  `tests/test_plugin_audit.py::TestRetryDeadLetters::test_second_retry_is_idempotent`
  （`assert retry_dead_letters() == 0` 实测 1，scratch `b106_pytest_run4.log`）。
  **本批不把它算进"三次绿"，也不把它当 flaky 放过**：它是一条独立的、改前就在的竞争，
  取证见下面"诚实边界"最后一条。
- `scripts/static-checks.py` 全跑档退出码 0，检查 16 的 `[ok]` 句是
  `审计连接生命周期：扫描 1 个碰共享连接的模块、13 处引用，全部在 with _db_lock: 体内`。
- `ruff check` 对 `audit.py`、两个测试文件全通过。
- 计数同步：README 四处 Python 计数 1951 → **1965**（＋14 ＝ 2 例行为判据 ＋ 12 例门禁测试，
  检查 3 用的是静态 `def test_` 定义数，与 pytest 展开数在本批恰好相等，因为 14 例都没参数化）。

#### 诚实边界
- **崩溃没有被复现过第三次**，本批证明的是形态消失：锁外取不到引用 ⇒ 那个 use-after-close 的
  对象来源被切断。若还有别的线程以别的方式握住同一个连接对象（例如有测试直接
  `audit_mod._db_conn` 传给线程），检查 16 抓不到——它只覆盖 `_get_db()` 与 `_db_conn` 这两个名字，
  且只扫 `python-ai/app/`，**不扫 `tests/`**（测试自己起线程构造竞争正是行为判据本身，不该被门禁判红）。
- `flush_on_shutdown`（`:573`）预算到点仍**带着仍在跑的 daemon 线程返回**（`:603` 把
  `final.is_alive()` 写成 `timed_out` 就算交差）。改后那个线程只会阻塞在 `_db_lock` 上，
  不会再拿着已关闭的连接 ⇒ 崩溃窗口没了；但"退出函数返回时仍有出站未确认"这个事实**保留**，
  已作为未处置观察登记在 `docs/CLEANUP_BACKLOG.md` 那条关闭记录里，没有混进本批的"已修"。
- 三次绿是必要不是充分：本地命中窗口本来就是概率事件，第一百零三批那轮是"同一命令第一次 0、
  第二次 139"。所以本批的判定分量全压在两条确定性判据＋一条形态门上。
- 行为面有一处**有意的**代价：`_init_db()`（建目录＋建表）现在在锁内跑，进程首次并发写审计时
  会串行等一次建表。换来的正是那条 8 连接红。
- `ruff format --check` 对 `audit.py` 与 `test_plugin_audit.py` 报 `2 files would be reformatted`——
  这一条**不是本批引入**：同一命令对 `git show HEAD` 落盘的同两个文件跑，结果一样是 2 files；
  CI 只跑 `ruff check .`（`ci.yml:148`），没有格式化门。本批没有顺手重排它们，免得把"改动可审"变成噪声。
- 本批跳过第一百零五批是**决策不是遗漏**：那条要定的是许可证策略（SPDX 复合表达式怎么判、
  LGPLv2+ 这类 copyleft 成不成分），属于需要人拍板的口径，不能由改代码的一方顺手往允许清单里加名字。
- 第四次那一条红的**归因不靠推测，靠同一套编排对两个版本各跑一遍**：`_do_flush` 是
  "锁外取快照（`_get_unsynced_entries`）→ 出站 I/O → 按**快照里的** `entry.retry_count` 判超限 →
  `_mark_dead_letter`"，判定读的是快照不是行的当前状态。后台那条每 30s 到点的 `audit-flusher` daemon
  （`record_audit` 经 `_ensure_flush_thread`（改前 `audit.py:480`，现 `:432`）起的，`tests/conftest.py:122-128`
  的隔离 fixture（改前只换库、**不停线程**；第一百零七批已改成换库前后各停一次 `audit-flusher`））只要在运维 `retry_dead_letters()` 之前取到快照、在之后落
  `_mark_dead_letter`，刚回灌的行就被翻回 dead-letter（运维这次点击等于没生效）。
  套件里那次红的现场证据对得上：一次 drain 的三轮 `_do_flush` 只会越预算一次、只打一行
  "超过最大重试次数"，而失败用例的 captured stdout 里**同一 id 打了两次**（42.107 与 42.113），
  随后两次回灌各打一行（42.123 与 42.133）⇒ 第二条标记来自另一条线程。
  确定性编排（events 把"取快照"与"落标记"卡在回灌两侧）在 HEAD 与工作区**各跑一遍，两边都红**
  （`first=1 second=1`；同脚本的单线程对照组 `first=1 second=0`，scratch `repro_stale_snapshot_requeue.py`）
  ⇒ 与本批的连接生命周期修复无关，没有把它折进本批"已修"，也没有把那条断言放宽。
  对象登记在 `docs/CLEANUP_BACKLOG.md`，处置为**第一百零七批**（已处置，见本文件第一百零七批条目：
  判定抬到当前行 ＋ fixture 换库前后停掉 `audit-flusher`）；原先排在 107 的 Flyway 及其后的队列
  整体顺延一位，相关的前向锚点已就地纠正（见下一批小节）。

#### 下一批
1. **第一百零七批**（本批直接下游，判据已就绪）：`_do_flush` 的超限判定改成读**行的当前状态**
   （在同一个 `_db_lock` 里 `retry_count = retry_count + 1` 后再按当前值落 dead-letter），
   配那条确定性编排红；顺带处置"隔离 fixture 不停后台 flusher"这一半测试串台。
2. **第一百零八批**：Flyway 迁移步骤四处统一到 `-Dflyway.*`（原第一百零七批）。
3. **第一百零九批**：全栈 compose 活栈真跑一次。**第一百一十批**：judge-cache 驱逐。
   另有 dev 锁审计门、`UPLOAD_DIR` 残留键、错误信封 code 统一、Java 侧状态码统一四条待排。
4. **第一百一十四批**：SBOM 组件面对象（原写作第一百一十一批，该号已被 e2e 前端服务契约占用）；**第一百一十二批**：`eval-runtime` 可达性前置探针。
   第一百零五批（许可证策略）仍需人拍板，不由本批改。

### 第一百零四批（2026-10-12：`plugin-security.yml` 三个"从诞生起就没绿过"的 job——修的是旗标与解析形态，门的强度一分没降）

#### 结论（先给判定性质）
- 对象是第一百零三批登记的那三条：`vulnerability-scan`、`sbom-generation`、`license-check`。
  三条与锁无关（锁修干净前后红的是同样这三条），机理同族——**写门的人用的 CLI 与数据形态，
  和 runner 实际装上去的版本不同源**，而那三个 `pip install <tool>` 全都没钉版。
- 处置形态＝钉版 + 换成当版本真实存在的旗标 + 把内联解析搬进可测试的 helper。
  **不删 job、不加 `continue-on-error`、不放宽任何过滤**；helper 里连 severity 过滤都不存在，
  并且专门有一条用例钉住"low 也判红"，防止未来有人借"改旗标"之名把门改宽。
- **结果不是三条全绿**：`license-check` 的旗标修好之后暴露出一条真实的清单语义红
  （`--allow-only` 整串精确匹配不认 SPDX 复合表达式）。本批做的是把**假红**变成**真红**，
  不是把红改成绿；真红那条已登记为第一百零五批对象。

#### 修复与判据
- `vulnerability-scan`：`pip install pip-audit==2.10.1`（runner 实测版本，报告顶层是
  `{"dependencies": […]}`），判定步骤从 20 行内联 `python -c` 换成
  `python scripts/ci/vuln_report_gate.py /tmp/vuln-report.json`。helper 的退出码契约写进文件头：
  **0** ＝ 读得出且零漏洞；**1** ＝ 至少一条（不过滤 severity）；
  **2** ＝ 报告打不开 / 形态不认识 / 依赖数为 0——把"读不出"当 0 就是一条永远绿的空转门。
- `sbom-generation`：`pip install cyclonedx-bom==7.5.0` +
  `cyclonedx-py environment -o ../sbom-python.json --output-format JSON`（旧写法 `--format json`
  在该子命令的旗标表里不存在 ⇒ `unrecognized arguments: --format`）。
- `license-check`：`pip install pip-licenses==5.5.5` + `--format=plain`
  （该版本 `--help` 实测可选值：`plain / plain-vertical / markdown / rst / confluence / html /
  json / json-license-finder / csv`，**没有** `table`）。`--allow-only` 清单一个字没动。
- 判据落在 `python-ai/tests/test_plugin_security_gates.py`（14 例：9 例跑 helper 的退出码契约，
  5 例核 workflow 的旗标、钉版与"没有被静音"）。文件头把四条 runner 事实逐条写明来源。
- 一处**测试自身**的缺陷就地纠正：`test_the_three_jobs_are_not_silenced` 最初对所有步骤一律禁止
  `if: always()`，于是把 `Upload vulnerability report` 也判成静音。那条 `always()` 的语义是
  "门已经判红之后仍把报告留档"，不改变门的结论。钉法改成：执行步骤不得有条件跳过，
  `actions/upload-artifact*` 例外；`continue-on-error` 仍然全面禁止。
- 加了 `workflow_dispatch`：不动任何门禁，只是让这条安全流水线在不改路径文件时也能按需复跑。
  不加它就没有 runner 证据可取——本批的 diff（workflow、`scripts/ci/`、`tests/`、文档）
  恰好不落在 `push.paths` 的三个过滤里。

#### 测量与证据
- **红先行**：新判据第一次跑＝`10 failed, 4 passed`。而那 4 条"通过"是**空转**——
  `python <不存在的脚本>` 自己就退出 2，正好等于 helper 的"读不出形态"码，所以所有
  "必须退出 2"的用例在 helper 缺席时也会绿。补上 `assert GATE.is_file()` 之后
  `14 passed` 才有意义；这条前置断言留在 helper 调用函数里，不在用例里。
- **helper 对真实产物判过**：把 runner 日志里那份 pip-audit 报告原文（76 个 dependency 条目、
  `{"dependencies": […], "fixes": []}` 形态）落盘后直接执行
  `python scripts/ci/vuln_report_gate.py b104_real_report.json` ⇒
  `No known vulnerabilities found (76 packages audited)`、退出码 0。同一份报告在旧内联脚本下是
  `AttributeError: 'str' object has no attribute 'get'`（run 38145150133 第 284 行）。
- **容器内实测新命令**（`python:3.11-slim`，scratch `b104_gates.log`）：
  `PINS_EXIT=0`（7.5.0 与 5.5.5 都可装——这句是当时的可安装性实测，`Install CycloneDX`
  现在钉的是 `requirements-dev.txt` 里的 **7.3.1**，见下面「就地自我纠正」）、
  `CDX_EXIT=0`（`--output-format JSON` 成立）、
  `LIC_JSON_EXIT=0`、`LIC_TABLE_EXIT=1` ＝
  `license Apache-2.0 OR BSD-2-Clause not in allow-only licenses was found for package packaging:26.3`。
  同一次 `REQ_EXIT=2` 是宿主网络把 aliyun 镜像读到 `ReadTimeoutError`，**不是**锁的问题；
  主锁 `python-ai/requirements.txt:809` 钉的 `packaging==26.2` 的 PyPI 元数据
  `license_expression` 是同一串，所以 CI 那套完整锁环境同样会撞上这条真红。
- **套件**：`.venv/Scripts/python.exe -m pytest -q tests --ignore=tests/test_plugin_container.py`
  ＝ `2065 passed, 12 skipped`，退出码 0。与第一百零三批基线 `2051 / 12` 的差值**正好**是本批
  新增的 14 例，skip 面没动。
- **一次差点误判成回归**：同一命令换成 bare `python` 跑，得到 `3 failed / 2098 passed / 18 skipped`
  （全量口径 2119 ＝ CI 口径 2063 ＋ 容器轨 42 ＋ 本批 14，逐位对得上）。逐条查到底：
  `D:\python3.11.9` 目录里有 `python311._pth` ⇒ `sys.flags.safe_path=True` ⇒
  在 `python-ai/` 里 `python -c "import app"` 也 `ModuleNotFoundError: No module named 'app'`，
  于是 `tests/test_eval_retention.py::test_env_override_is_honoured`（起子进程探针）必红，
  `tests/test_milvus_tenant_migration_real.py` 两条报 `AttributeError: function_score`。
  换回 venv 解释器三条全部复位——**这是宿主解释器的安装形态，不是套件回归**；
  本机跑这套件的口径因此钉死为"必须用 `python-ai/.venv/Scripts/python.exe`"。
- `scripts/static-checks.py` 全跑档退出码 0、15 项全 `[ok]`。检查 3 的 python 计数是
  **静态 `def test_` 定义数**，与 CI 的"参数化展开后用例数"是两条口径，本批 1936 → **1950**
  （＋14），README 四处同步；Java 718 与前端 117/73 没动。
- **补证之后的重测**（钉版改 7.3.1 ＋ 新增一条"钉版必须等于锁"的判据，静态计数 1950 → **1951**，
  README 四处同步；`static-checks.py` 再次全 `[ok]`、退出码 0）：
  `tests/test_plugin_security_gates.py` 单档 ＝ `15 passed`；
  全量口径（`pytest -q tests`，**含**容器轨，与上面 CI 的 `--ignore` 口径不同源，不可混读）
  ＝ `2102 passed, 18 skipped`、退出码 0。CI 侧的数字仍只用 run 38226782026 的
  `2070 passed / 7 skipped`（＝ commit `488fa32d`，不含这第 15 条判据）。

#### 诚实边界
- 改了的 workflow 只有"旗标、钉版、触发方式"三类内容，三条门的**判定强度没有下降**：
  helper 不过滤 severity、读不出形态判 2 不判 0、空依赖清单判红；`--allow-only` 清单与
  第二步那份字面清单都没动（两份清单不同源这件事本身是缺陷，登记在第一百零五批）。
- `sbom-generation` 里那段"components 为空只打印 `WARNING`"的内联脚本本批没动——
  它不是一条门（空 SBOM 照样绿）。这是门的语义弱点，与许可证策略一并处置，不在本批偷加新红。
- **本批没有"改后 runner 已绿"的说法**。plugin-security 的 CI 证据要推送之后手工触发才有
  （`push.paths` 不含本批改动的文件），在那之前关于这三条门只有两个来源：runner 历史日志
  （改前为什么红）＋ 容器实测（新命令在 Linux 上装得上、跑得起、判定是什么）。
  ⇒ 该说法的时效已由下面的「CI 补证」小节解除：两条门在 runner 上确实转绿，第三条按预期红。
- 顺带取证的 Flyway 那条红本批**只登记未处置**：`e2e.yml:82`、`e2e.yml:221`、`eval-nightly.yml:96` 三处
  的 `Run Flyway migrations` 只给 `SPRING_DATASOURCE_*`，而 flyway-maven-plugin 只认
  `-Dflyway.url/user/password`；`e2e-full` 在 2026-10-10～10-12 连续 5 次死在同一步，nightly 的
  `eval-harness` 也死在同一步。**同仓里已经有一份写对的**——`ci.yml:382-383` 用的正是
  `-Dflyway.url=… -Dflyway.user=… -Dflyway.password=…` 且为绿，所以这不是"MySQL 起不来"，
  是复制粘贴漂移（四处站点、`java-backend/pom.xml` 里插件未声明也未钉版）。
  更早 2026-09-22、09-29 两次 `failure` 的失败步骤不在 step 列表里，没有归到"同一步红"。
  登记为第一百零七批对象。**（第一百零六批就地纠正这条前向锚点：第一百零六批第四次全套件查出的
  审计 flush 判定竞争已插入为第一百零七批，本条 Flyway 顺延为第一百零八批，其后队列整体 +1。）**

#### CI 补证（run 38226827011 ＝ commit `488fa32d`，手工触发 Plugin Security）
- `vulnerability-scan` ＝ **success**（这个 job 历史上从没绿过）。job 114736287138 的日志原文顺序：
  `No known vulnerabilities found`（pip-audit 自身，第 249 行）→ 执行行
  `python scripts/ci/vuln_report_gate.py /tmp/vuln-report.json`（第 252 行）→ helper 自己打印
  `No known vulnerabilities found (76 packages audited)`（第 263 行）。最后那一行是**门真的读过报告**
  的证据：旧的内联脚本在同样干净的报告上会 `AttributeError: 'str' object has no attribute 'get'`，
  所以这不是"没有可审的东西所以绿"。
- `sbom-generation` ＝ **success**，`SBOM contains 35 components`（第 273 行）——组件表非空，
  那条只打印 `WARNING` 的分支没被走到。
- `license-check` ＝ **failure**，红在 `Run Check licenses`：
  `license BSD License not in allow-only licenses was found for package webcolors:25.10.0`
  （job 114736287980 第 349 行）⇒ 本批"结果不是三条全绿"的预判兑现。这是**策略语义红**，
  不是旗标红：允许清单一个字没改，也没有加 `continue-on-error`。处置＝第一百零五批。
  **整个 run 的 `conclusion` ＝ failure**，红的来源只有这一条——不要把"run 红"读成"两条门又红了"。
- 同一 commit 的 `CI` run 38226782026 ＝ **11 个 job 全 success**（`python / java / python-container /
  docker-build / docker-compose-validate / helm / frontend / static-consistency / python-lint /
  gitleaks / eval-offline`）。其中 `python` job（114736131160）给的是
  `2070 passed, 7 skipped, 1 warning in 78.17s` ＋ `Required test coverage of 74% reached.
  Total coverage: 77.11%`——这是第一百零四批 14 条新判据进 CI 之后的展开数口径。
- `E2E` run 38226782059 ＝ **cancelled**：死在 `Run pip install -r requirements.txt`
  （08:58:10 开始，09:17:32 `##[error]The operation was canceled.`，停了 19 分 22 秒），
  **没有走到 Flyway 那一步**。取消来源无法从日志判定——`e2e.yml` 没有 `concurrency` 键，日志里
  也没有 timeout 声明，所以本批只把它登记成"证据未取到 ＋ 镜像装在阿里云镜像上停摆"，
  第一百零八批（原写作第一百零七批，第一百零六批就地纠正编号）的 Flyway 判据仍然只用 run 38221938525 那一族历史日志。

#### 就地自我纠正（同一批内，改的是本批自己留下的两个来源错误）
- **钉版的来源钉错了**：`Install CycloneDX` 一度钉成 `cyclonedx-bom==7.5.0`——那是"未钉版当时
  解析到的版本"，而 `python-ai/requirements-dev.txt:452` 早就钉着 **7.3.1**，eval-nightly 从锁装的
  也是 7.3.1（run 38224268851 第 384 行 `Successfully installed … cyclonedx-bom-7.3.1 …`）。
  钉成 7.5.0 等于让同一个仓里并存两个 cyclonedx-bom，"同一个工具"这句话就不再成立。
  实测两版的旗标表一致（7.3.1 的 `environment --help`：`--of, --output-format`
  `{choices: JSON, XML}`、`-o`），并用仓库 venv 真生成过 `specVersion 1.6 / 126 components`
  的 SBOM（scratch `b104_sbom_731.json`）⇒ 工作流改钉 7.3.1，并新增一条
  `test_pins_that_the_dev_lock_already_carries_agree_with_it` 把"版本号从哪来"钉住
  （自带"没有任何钉版能与锁对照 ⇒ 空转"的反空转断言）。
  **效力边界**：CI 那一步是用 7.5.0 跑绿的（run 38226827011），改成 7.3.1 之后这一步还没在 runner
  上重跑，所以"7.3.1 也绿"只有本地实测这一层，不写成 runner 结论。
- **`SBOM contains 35 components` 这句话的对象不是产品**：那个 job 从不 `pip install -r requirements.txt`，
  所以它生成的是 **runner 自带 python 环境**的 SBOM（35 个组件），而漏洞门读的是
  `requirements.txt`（76 个包）。同一个 workflow 里两条产物描述的不是同一个对象——本批只发现并登记，
  不动它（登记为第一百一十四批；第一百零六批、第一百一十一批两次就地纠正编号——111 那个号最终被本批
  的 e2e 前端服务契约占用；同时那条"空组件表只打印 WARNING"的弱点一并处置）。
- 顺带取到第一百零五批的实料：对着仓库 venv 生成的 126 组件里许可证串有 14 种形态，含分类器原文
  `License :: OSI Approved :: Apache Software License`、`PSF-2.0`、`Python-2.0`、`MIT-0`、`MIT-CMU`，
  以及 **`License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)`**
  ——允许清单里只有 LGPLv3，没有 LGPLv2+。策略判定必须逐成分处理这些形态，不能靠往字面清单尾部
  追加字符串。
- **第一百零六批的处置方向被崩溃栈改写了**（本批只改写登记，未动生产代码）：改完补证重跑套件时，
  67% 处 `Windows fatal exception: access violation`、`PYTEST_EXIT=139`，dump 的 **Current thread**
  逐帧点名 `app/core/plugin/audit.py:596 _run`（线程名 `audit-shutdown-flush`）→ `:337 _do_flush`
  → `:273 _cleanup_synced`，同一 dump 里主线程在 pytest 的 fixture teardown。
  这**推翻了第一百零三批对根因的描述**：不是"线程没拿锁就 execute"，而是"**连接引用在锁外取**"——
  `_increment_retry:256-257`、`_cleanup_synced:271-272`、`_persist_to_sqlite:194-195` 都是先
  `db = _get_db()` 再 `with _db_lock:`，而 `_get_db()` 本体（`:158-162`）不持锁。
  ⇒ 原来推荐的 A 方案（`_reset_db` 全程持锁）**单独做仍然留窗口**：线程握住旧对象、等锁释放、
  再对已 `close()` 的对象 execute。处置必须两半同做（close＋换绑持锁 ＋ 取引用也在锁内），
  并且还发现一条不需要低概率就能打开窗口的路径：`flush_on_shutdown`（`:573`）在预算用尽时
  **带着仍在跑的线程返回**（`:603` `result["timed_out"] = final.is_alive()`）。
  本批与此的因果关系也说清楚：改动只有 workflow YAML 与一份纯静态判据文件，**没碰 `app/`**，
  所以这不是本批引入的回归，是本批把第一百零六批从"推断"抬成"有栈可查"。

#### 下一批（按红面与崩溃代价排序）

> 编号更正（第一百零六批）：第一百零六批第四次全套件查出的"审计 flush 按快照判定"竞争插入为
> **第一百零七批**，下面 3～7 项整体 +1（Flyway 107→108、全栈 compose 108→109、judge-cache 109→110、
> SBOM 110→111、eval-runtime 111→112）。
1. **第一百零五批**：`license-check` 的许可证策略收敛——一份可测试的策略来源、按 SPDX 表达式
   逐成分判定（任一成分不在允许集合即红），两步同源；不得靠追加复合表达式字符串把门改绿。
2. **第一百零六批**：`_reset_db()` 全程持 `_db_lock`（消除与 flush 线程的段错误窗口），
   配一条确定性红判据。
3. **第一百零八批**：Flyway 迁移步骤四处统一到 `-Dflyway.*`（`e2e.yml:82/221`、`eval-nightly.yml:96`，
   参照 `ci.yml:382` 的现行正确形态），并在 pom 里声明＋钉住 `flyway-maven-plugin`，
   判据要证明迁移确实发生而不是步骤跑绿。
4. **第一百零九批**：全栈 compose 活栈真跑一次（把"能写/能读"从镜像级升到活栈级）。
5. **第一百一十批**：judge-cache 驱逐。另有 dev 锁审计门、`UPLOAD_DIR` 残留键、
   错误信封 code 统一、Java 侧状态码统一四条待排。
6. **第一百一十四批**（原写作第一百一十一批，该号已被 e2e 前端服务契约占用）：`sbom-generation` 的组件面改成 python-ai 自己的依赖（现在那 35 个组件是
   runner 环境，漏洞门审的 76 个包一个都没进 SBOM），并把"组件表为空只打印 `WARNING`"改成判定。
7. **第一百一十二批**：`eval-runtime` 的可达性前置探针（nightly 现在把"隧道不可达"报成
   "错误率退化"：220 例每个 ≈0.1 秒 ERR、`error_rate=1.000 exceeds maximum 0.020`）。

### 第一百零三批（2026-10-11：两条依赖审计门从红转绿——pip-audit 的 29 条与 npm audit 的 15 条，收口靠的是把锁钉到修复版本，不是放宽门）

#### 结论（先给判定性质）
- `ci.yml` 里剩下的两条红是本批对象：`python-lint` 的 pip-audit
  `Found 29 known vulnerabilities in 5 packages`，`frontend` 的
  `npm audit --audit-level=high` ⇒ `15 vulnerabilities (7 moderate, 8 high)`。
  第一百零二批推送后的 run 38140336727 逐步骤核对过：同一条流水线里 `helm`、
  `static-consistency`、`docker-compose-validate`、`gitleaks` 全绿，红的只有这两步。
- **写这条之前"main 上只剩这两条红"的说法不成立**，那是只看了 `ci.yml` 的结论。
  另一条工作流 `plugin-security.yml`（push 到 `python-ai/requirements*.in` 就会触发）
  在 run 38134153670 里红了 3 个 job：`vulnerability-scan`（与本批同源，主锁修好后即绿）、
  `sbom-generation`（`cyclonedx-py environment … --format json` ⇒
  `error: unrecognized arguments: --format`，cyclonedx-bom 已不收这个旗标；
  **就地纠正**：这句当时写的是 `7.3.1`，那是没核 runner 版本就落的数字——第一百零四批
  在容器内按 runner 实际版本实测为 `cyclonedx-bom 7.5.0`，runner 日志（run 38145150133）同口径）、
  `license-check`（`pip-licenses -f table` ⇒ `invalid choice: 'table'`，可选值是
  `plain/markdown/json/…`）。后两条是 CLI 旗标与已安装版本对不上，与本批的锁升级无关，
  已登记为待处置项（见 `docs/CLEANUP_BACKLOG.md` F 段）。
- 门的形态**一个字都没动**：本批改的文件只有三样 python 清单（`requirements.txt` /
  `requirements-dev.txt` / `requirements.in`）、两样 npm 清单（`package.json` /
  `package-lock.json`）和 `src/api/request.ts`，`.github/workflows/` 整个目录不在 diff 里。
  既没改 `--audit-level`，没加 `--ignore-vuln`，也没调任何阈值——被改的只有锁与需求下限。
- 修复走的是"钉版本"而不是"加门禁"：主锁 4 条直接依赖 + 1 条传递依赖升级到 pip-audit
  给出的最早修复版本，npm 侧用不带 `--force` 的 `npm audit fix`（`changed 39 packages`）。

#### 修复与判据
- **python 主锁**（`python-ai/requirements.txt`）：`pypdf 6.16.2→6.19.0`、
  `python-dotenv 1.0.1→1.2.2`、`requests 2.31.0→2.33.0`、`starlette 0.52.1→1.3.1`、
  `urllib3 2.7.0→2.8.0`。前四条是 `.in` 里的直接依赖，`urllib3` 只由 `requests` 带进来——
  **不**把它写成直接依赖，否则 `.in` 与锁尾的 `# via` 就不同源了（那是第八十八批那条
  "裸 pin 追加到哈希锁尾部"缺陷的另一种形态）。
- **`requirements.in` 的下限改成漏洞下限**：`python-dotenv>=1.2.2`、`pypdf>=6.19.0`、
  `requests>=2.33.0`、`starlette>=1.3.1,<2.0`。理由写进文件注释——只钉锁不改 `.in`，
  下一次 `pip-compile` 会照着旧下限重新解析回带 PYSEC 的版本，同一批 CVE 静默复活。
  `starlette` 原来的 `>=0.46,<1.0` 上界是 fastapi 未适配 1.x 时加的；实测 PyPI 元数据里
  fastapi 0.141.1 只写 `starlette>=0.46.0`（无上界），故换成主版本守卫。
- **dev 锁的幽灵条目**（第一百零三批取证的那条独立缺陷）：`requirements-dev.txt` 里
  `pypdf2==3.0.1` 挂着 `# via -r requirements.in`，而 `requirements.in` 从未声明过 pypdf2，
  生产码也没有任何 `PyPDF2` 导入（`pdf_parser.py:23`、`multimodal_evidence.py:291` 都是
  `from pypdf import PdfReader`）。原地换成 `pypdf==6.19.0` 并与主锁同哈希。
- **npm 侧**：`package-lock.json` 经 `npm audit fix` 后 0 漏洞；`package.json` 里 5 个
  带公告的直接依赖把范围下界抬到修复版本（`axios ^1.18.1→^1.20.0`、
  `dompurify ^3.4.12→^3.4.16`、`vue ^3.5.39→^3.5.43`、`vue-i18n ^10.0.7→^10.0.8`、
  `vitest ^4.1.10→^4.1.11`），与 python 侧同一条纪律——钉锁之外还要钉下限。
  其余（`brace-expansion`/`postcss`/`js-yaml`/`nanoid`/`glob`/`source-map-js`）是工具链的
  传递依赖，由 audit fix 去重后自然升上去，`package.json` 里没有对应条目可抬。
- **axios 1.20 的类型断点**（升级唯一的真实破坏面）：1.20 起实例方法返回
  `Promise<AxiosResponseResult<T,R,D,P>>`，`R` 默认是 `unique symbol` 的
  `AxiosResponseDefault`；响应拦截器把 `AxiosResponse` 拆成业务体之后，5 个封装函数
  各自报 `TS2322`。修法是在**实例边界**上重述一次类型（`src/api/request.ts` 的
  `UnwrappedClient`），而不是在 5 个封装和所有调用点各 cast 一次。
  试过引 axios 内部符号 `rawAxiosResponseDefault`，两条路都堵：它是 `type` 形态，
  `isolatedModules` 下报 `TS1484`，而 `noUnusedLocals` 又不允许留着不用。

#### 诚实边界
- 主锁的绿**没有**关掉第三处同源红——这句本批写错过，就地纠正。`plugin-security.yml:72-108` 的
  `vulnerability-scan` job 有两处叠着的缺陷，前一处一直把后一处挡在后面：
  ① `pip-audit -r requirements.txt --desc --output … --format json` 自己在发现漏洞时退出 1
  （run 38134153670 停在这里：`Found 29 known vulnerabilities in 5 packages`）；
  ② 锁修好后第①步转绿（run 38145150133 该步打印 `No known vulnerabilities found`），
  下一步的解析脚本却按"顶层是 list"去读 pip-audit 的 JSON，而它现在写的是
  `{"dependencies": […], …}`——`for item in data` 迭代到的是字符串键，
  `AttributeError: 'str' object has no attribute 'get'`，job 仍红。
  ⇒ 这个 job 从来没有绿过的能力：改锁前死在第①步，锁修好后死在第②步。
  本批没给它加过滤、没改脚本，登记为第一百零四批对象。原先"主锁的绿同时关掉第三处同源红"
  是从读 workflow 得出的纸面结论，与"CI runner 日志才是判据"这条纪律冲突。
- 门覆盖的是 `requirements.txt` 一条锁：`pip-audit -r requirements.txt --disable-pip`
  （`ci.yml:149-152`），`requirements-dev.txt` **没有任何审计门**。本批把 dev 锁里与主锁
  共享的 4 条对齐了，但 dev 锁仍留着 `pytest 8.3.5 → PYSEC-2026-1845（修复 9.0.3）`：
  把它转绿需要 pytest 主版本升级 + `pytest-asyncio 0.25.3`/`pytest-cov` 的兼容链和 2087 例
  重跑，本批没做，因此**没有**顺手给 dev 锁加一条红门（那是计划外的新红）。已登记为待处置项。
- OSV 返回的行会重复：dev 锁那条在表里出现两行（`PYSEC-2026-1845` ×2，别名去重前的形态），
  数"漏洞条数"时不能直接按行数算。
- `starlette 0.52.1→1.3.1` 是**跨主版本**升级，本批的把握来自同一解释器上的前后对照重跑
  （见验证：覆盖 starlette 后套件逐项数字与基线**完全相同**），不是来自读 changelog；
  这条把握的口径限制要说清：对照跑的是本机 venv 的 `pytest 9.1.1`，而 dev 锁钉的是
  `pytest 8.3.5`——两者不是同一个测试运行器版本。CI 已给出结论（见 CI 补证）：
  runner 上按新 dev 锁装环境跑 = `2056 passed / 7 skipped`，覆盖率 77.09%。
- 行尾：`.gitattributes` 没绑 `.txt`（第九十二批只绑了 `.jsonl`），锁的工作副本因而跟
  `core.autocrlf` 走。本批按字节核对过：入库侧两把锁都是纯 LF（`CRLF 0`），
  差异只在检出副本，`pip` 与 `pip-audit` 对此不敏感。这是既有形态，不是本批引入的。
- 哈希锁手工编辑的可核验判据（本批用的）：哈希行两把锁分别 1534 / 1854 条、畸形 0 条、
  条目数主锁 75 条 `name==ver` + 3 条带 extras（`uvicorn[standard]`、`jsonschema[format-nongpl]`、
  `cyclonedx-python-lib[validation]`）＝ **78**，dev 锁 98 + 5 ＝ **103**；无重复包名、
  每个条目块都以 `# via` 收尾、无重复 `# via` 行。这两个总数与门禁 11 自己数出来的
  "78 个 pin / 103 个 pin，每个 pin 都带哈希"是两条独立来源，本批两边都对上。
  第一版脚本漏检过一处重复的 `# via -r requirements.in`（哈希行以 4 空格开头，而它按
  `--hash=` 起首比对块尾），靠"无重复 `# via` 行"这条判据抓出来。

#### CI 补证（run 38145150155 ＝ commit `06ea5607`，推送后第一次）
- **CI 整条流水线第一次全绿：11 个 job 全部 success**
  （`gitleaks, static-consistency, docker-compose-validate, helm, python-lint, python, python-container,
  eval-offline, frontend, java, docker-build`）。这条"第一次"是按逐 run 核对说的，不是外推：
  run 38137949997（第一百零一批）红的只有 `python-lint` + `frontend`，
  run 38140336727（第一百零二批）红的也只有这两条，本 run 两者转绿后整条流水线没有别的红。
  更早批次（第九十～九十九）的红另有 owner，见各批条目，本批没有把它们算进来。
- `python-lint`：审计那步在 runner 上打印 `No known vulnerabilities found`
  （scratch `ci_b103_python.log` 对应的 python-lint job 日志第 252 行）。
- `frontend`：`found 0 vulnerabilities` 出现两次（安装后与 `npm run audit` 门本身），
  `Test Files 16 passed (16)`。
- `python`：`2056 passed, 7 skipped, 1 warning in 78.40 s`，`TOTAL 19164 4391 77%`，
  `Required test coverage of 74% reached. Total coverage: 77.09%`。
  收集总数与本机对齐：CI 2056+7 = **2063** ＝ 本机 2051+12 = 2063——同一批用例，
  差的是 5 例在 Linux 上真跑而在 Windows 上 skip（不是新增或丢失）。
  这条同时是**新 dev 锁可安装**的 runner 级证据：`pip install -r requirements-dev.txt`
  在 `--require-hashes` 自动生效下成功，第八十八批那类"手工编辑把锁改坏"的缺陷没有复发。
- `plugin-security.yml`（run 38145150133）仍是 3 红：`license-check`
  （`pip-licenses 5.5.5`：`invalid choice: 'table'`）、`sbom-generation`
  （`cyclonedx-bom 7.5.0`：`unrecognized arguments: --format`）、`vulnerability-scan`
  （见诚实边界②：解析脚本按 list 读 dict）。三条都是 CLI/库漂移，与锁无关，
  且都**没有**能力通过；`signature-verify`、`hash-verify`、`plugin-runner-build` 绿。
  第一百零四批的对象就是这三条，处置纪律不变：修旗标与解析形态，不删 job、不加 `continue-on-error`。
- 第一百零一批的 CI 补证同时补齐：run 38137949997 的 `java` job
  `Tests run: 718, Failures: 0, Errors: 0, Skipped: 1`、`BUILD SUCCESS`（scratch
  `ci_b101_java.log`）——SSE 终止闸门在 runner 上成立。
  第一百零二批 run 38140336727 当时 `python=success / python-lint=failure / frontend=failure`，
  即那批自己的钟面判据在 runner 上是绿的，红的只有本批修掉的这两条审计门。

#### 验证
- 改前取证（容器内，CI 同款命令）：`Found 29 known vulnerabilities in 5 packages`
  ＝ CI run 38135767897 `python-lint` 的表逐行相同（scratch `b103_pip_audit_before.log`）。
- 改后（同一容器、同一命令）：主锁 `No known vulnerabilities found`（`MAIN_EXIT=0`）；
  dev 锁 `Found 2 known vulnerabilities in 1 package`（仅 pytest，见诚实边界；
  scratch `b103_pip_audit_after_final.log`）。
- `npm run audit`（`--audit-level=high` + 指定 registry，与 CI 同）：`found 0 vulnerabilities`
  ——`package.json` 抬下限、`package-lock.json` 同步之后复测仍为 0。
- `npm run build` 退出码 0；`npm run test` **16 个文件 / 117 例全绿**（与升级前同数）；
  `npm run lint` 0 error（55 条既有 warning，退出码 0）。
- `scripts/static-checks.py` 全跑档退出码 0、15 项全 [ok]（scratch `b103_static_final.log`）。
  其中门禁 11 独立复核两把锁的 pin↔哈希配对：主锁 78 pin / 78 条带哈希、
  dev 锁 103 pin / 103 条带哈希，Windows-only 两条 marker 仍在——手工编辑没有把锁改坏。
  检查 3 读到 Java 718 · Python 1936 · 前端单测 117，本批没有增删用例，计数棘轮无需同步。
- python（跨主版本那条的实测）：同一 venv、同一命令跑两遍。
  基线 `pytest -q tests --ignore=tests/test_plugin_container.py` = **2051 passed / 12 skipped in 200.43 s**，
  退出码 0；然后把本批五把升级（`starlette 1.3.1`、`pypdf 6.19.0`、`requests 2.33.0`、`urllib3 2.8.0`、
  `python-dotenv 1.2.2`）用 `pip install --no-deps --target` 放到 `PYTHONPATH` 最前重跑 =
  **2051 passed / 12 skipped in 237.46 s**，退出码同为 0——逐项数字与基线**完全相同**。
  覆盖确实生效是核过的，不是假定：`starlette.__version__` 报 1.3.1、`starlette.__file__` 指向覆盖目录。
  （scratch `b103_pytest_baseline.log` / `b103_pytest_overlay.log`）
- 与第一百零二批的 2087/18 的逐位关系：那条口径是**含容器轨**的全量 `pytest -q`，本批两遍都按 CI 的
  `--ignore` 排除它。对得上：`--collect-only tests/test_plugin_container.py` = **42 例**，
  2051+12 = 2063，2063+42 = 2105 = 2087+18；容器轨自己贡献 36 passed / 6 skipped。
- 整套在**新 dev 锁**下的 Linux 重跑：`python:3.11-slim` + 挂载仓库，`pip install -q -r requirements-dev.txt`
  打印 `INSTALL_EXIT=0`（哈希锁在新版本下照样全量可装），容器内随后确认
  `starlette 1.3.1 pypdf 6.19.0 requests 2.33.0 urllib3 2.8.0`。
  第一次 `pytest -q tests --ignore=tests/test_plugin_container.py` 的 docker run 退出码为 0
  （汇总行没留在日志里——重定向把 `-q` 的进度与汇总吞在 teardown 噪声之前，只能证退出码）；
  同一镜像、同一缓存卷、同一命令的第二次在 62% 处 **`Fatal Python error: Segmentation fault`**，
  `PYTEST_EXIT=139`（scratch `b103_container2_pytest.log` 第 23-28 行是崩溃线程栈）。
  这条 segfault 与本批的锁升级无关（见下面的登记），而 CI 的 `python` job 在同一把锁上给的是
  `2056 passed / 7 skipped`——所以锁与套件这两件事都判绿，容器那次崩溃单独追。


#### 本批测量中发现的缺陷（登记，语义一字未动）
- **`_reset_db()` 关闭 SQLite 连接时不持 `_db_lock`，与后台 flush 线程竞争，代价是解释器段错误。**
  崩溃栈：`app/core/plugin/audit.py:258 _increment_retry ← :326 _do_flush ← :596 _run`，
  即 `:600` 起的 `audit-shutdown-flush` 线程（`_flush_worker`／`audit-flusher`，`:425` 建，daemon）
  走的是同一段 `_do_flush`。连接以 `check_same_thread=False` 建立（`:128`），
  所有写路径都在 `with _db_lock:` 里；但 `_reset_db`（`:165-190`）先 `_db_conn.close()` 再换
  `_DB_DIR/_DB_PATH`，**整段不持锁**。关闭一个正被另一线程 `execute` 的连接是 CPython 层的未定义行为，
  于是表现为随机 segfault。
- 触发面今天是测试面：全仓 `_reset_db` 的调用方只有 `tests/conftest.py:126,128`（每条用例前后各一次）
  与 `tests/test_plugin_audit.py:727,731`，`app/` 下**没有调用方**——所以生产不受影响，
  但它是一颗已被实测踩到的地雷：任何把"重定向审计库"接进运维路径的改动都会走进同一个窗口。
- 这条也是"看起来像 CI/容器基础抖动"的红背后的自有缺陷：第一次跑绿、第二次崩，差别只在 flusher
  线程有没有正好落在 close 的窗口里。以复现率描述它比以"偶发"打发它更有用（第一百零一批同一形态：
  本地 0/8 而 CI 5 例）。
- 处置选项（下一批由用户拍，推荐 A）：
  **A.** `_reset_db` 全程持 `_db_lock` 再 close+换路径（3 行，不改任何生产语义）。
  红判据可**确定性**写，不需要复现 segfault：测试里先持有 `_db_lock`，起线程调 `_reset_db`，
  `join(timeout)` 断言它尚未完成，释放锁后断言完成——这把"关连接必须与写串行"这条不变量钉住。
  **B.** A + 把该不变量写成注释并加静态门（扫描"`_db_conn.close()` 出现在 `with _db_lock` 之外"）。
  **C.** flusher 可停：`_reset_db` 先置 stop event、等线程退出再 close（测试隔离最干净，改动面最大）。


### 第一百零二批（2026-10-11：python 侧的钟面并入同一 UTC 口径——内置时间工具此前给模型的是裸本地墙钟，而三档拓扑里 python 工作负载的 `TZ` 声明为 0 处）

#### 结论（先给判定性质）
- 这是第九十六批自己在 `docs/PRODUCTION_OPS.md` §13.3 登记过的**未收口面**，不是新发现的抖动：
  java 写侧三张钟面钉死后，仓库里剩下的另一套钟是 python 进程的墙钟。`datetime.now()` 的零参写法
  取进程时区，容器里就是宿主/节点时区；实测 `docker/`、`deploy/`、`helm/` 三档 shipped 拓扑里
  python 工作负载的 `TZ` 声明 **0 处**，而 `python-ai/app` 里唯一那处裸读法正落在内置
  `get_current_time` 工具上（`time_tool.py:21`）。
- 后果不是精度而是**口径静默**：那个工具把"现在几点"直接交给模型，返回值里没有任何口径标签，
  同一句提问在 +08 节点与 UTC 节点上差 8 小时，调用方无从分辨。容器内取证
  （`hfusionhub/python88:rc`，`time.tzset()` 把进程时区翻到 `Asia/Shanghai`）：
  修前输出 `2026-10-11 20:14:58`，同一瞬间 UTC 是 `2026-10-11 12:14:58`。
- 与第九十五/九十六批同族：那两批钉的是"前端渲染"和"java 写侧 + 判定 SQL"，本批钉最后一套钟。

#### 修复与判据（红判据先行，两面都收）
- **代码面**：`time_tool.py` 改 `datetime.now(UTC)`，并给返回值加 `caliber: "UTC"` 与 `iso8601`
  （带 `+00:00` 偏移）——口径写在数据里，而不是只写在部署里。
- **部署面**：`TZ: "UTC"` 补进 dev compose 的 `python-ai` / `python-ai-worker` / `plugin-runner`、
  prod compose 的 `python-ai` / `plugin-runner`，helm 走 values 键
  （`pythonAi.tz` / `pluginRunner.tz`）→ `templates/python.yaml` / `templates/plugin-runner.yaml`
  引用，与 java 侧 `javaToolOptions` 同一个形状，避免"键写了没人消费"的死配置。
- **判据**：`python-ai/tests/test_tool_clock_caliber.py`（3 例）——输出声明口径且数值等于本次调用的
  UTC 瞬时、进程时区免疫、`app/` 无裸读法。免疫那例先自证翻转真的发生（`naive != UTC`），
  否则那句免疫断言是空转的；它依赖 `time.tzset()`，Windows 上跳过，执行处是 CI 的 `python` job。
- **门禁**：`scripts/static-checks.py` 新增检查 15（`--python-clock-caliber`，已并入默认全跑档）。
  代码面用 `ast` 扫零参 `now()` / `utcnow()` / `today()` / `localtime()` / 少 tz 的 `fromtimestamp()`；
  部署面按**镜像标记**（不是服务名）认出三档拓扑里的 python 工作负载，逐个核对 `TZ` 归一化为 UTC，
  并核对 helm 模板真的引用了 values 里的 `tz` 键。
- 为什么是 `ast` 而不是正则：`time_tool.py` 的 docstring 就在解释"此前用的是 `datetime.now()`"，
  按原文扫的门禁会在自己的说明文字上判红——那种红只会教人删注释。判据文件那例用 `tokenize`
  涂白注释与字符串，与门禁的 `ast` 分面（两个 oracle 同时看错同一形状的概率才低）。
- **门禁自身的判据**：`python-ai/tests/test_python_clock_caliber_gate.py`（17 例）钉"真仓库绿 +
  已并入默认全跑档 + 每种漂移都红"，包括两种"门禁消失"形态：工作负载镜像标记改名（认不出任何
  工作负载必须自己报红，而不是静默通过）与拓扑文件缺失。
- **红判据在真树上取过证**：把门禁常量指向本批改前的 HEAD 快照（`git archive HEAD` 的
  `python-ai/app` + 两份 compose + helm values/模板），12 面齐红（scratch `b102_gate_red2.log`）——
  1 处裸读法 `time_tool.py:21`、5 个工作负载缺 `TZ`、helm 6 面（两模板各缺 `- name: TZ`、
  缺 `.Values.*.tz` 引用、values 缺键）。改后同一门禁绿：
  `7 个 python 工作负载声明 TZ=UTC，app/ 扫描 183 个 .py 文件无裸本地墙钟读法`。

#### 成本
- `time_tool.py` 的返回体多两个键（`caliber` / `iso8601`），是**新增字段**不是改名，旧调用方按
  `datetime`/`date`/`time`/`weekday` 读的值语义变了：从"容器时区墙钟"变成"UTC 墙钟"。在 `TZ`
  从未声明的现行容器里镜像默认时区就是 UTC，所以对现存部署是一次**读数不变、口径显式化**的改动；
  一旦有人曾给容器加过 `TZ=Asia/Shanghai`，那套环境的工具输出会平移 −8 小时——那正是本批要消除的
  不确定性，`docs/PRODUCTION_OPS.md` §13.1 那段"曾用非常规时区起过容器的环境要核一次存量"的
  提醒同样适用于此。
- 检查 15 会拦住"在 `app/` 里写裸 `datetime.now()`"的改动，包括测试夹具之外的任何新代码；
  需要本地时间显示的场景应显式 `.astimezone()` 而不是靠进程时区。

#### 诚实边界
- 检查 15 的代码面只覆盖 `python-ai/app`（我们自己的应用码）。跑在 plugin-runner 沙箱里的**插件代码**
  管不了——那正是给那个工作负载钉 `TZ=UTC` 的理由，而不是相反。零参 `now()` 按方法名匹配、不看
  接收者类型，别的类恰好有 `now()` 会误报（`app/` 目前没有）。
- 部署面证明"三档拓扑声明了同一口径、且模板真的读了 values 键"，不证明 Pod 起来后容器里 `TZ`
  真的生效。本批能给的最强的证据是**渲染产物**而非文本：helm 3.16.2（与 CI `helm` job 同版本，
  本机无 helm 客户端，用 `alpine/helm:3.16.2` 容器跑）`helm lint` → `0 chart(s) failed`，
  `helm template` → 746 行清单里 `hfusionhub-python` 与 `hfusionhub-plugin-runner` 各有一条
  `- name: TZ / value: "UTC"`，`<no value>` 计数 0；compose 两档用 `docker compose config`
  解析后同样核对（dev 需 `--profile fullstack`，否则 `python-ai` / `python-ai-worker` 根本不在
  渲染结果里——这也是"文本绿而渲染态没核对"会漏掉的那一类）。
- 但"容器里 `TZ` 环境变量真的把 python 的墙钟挪动了"这件事本批只在**测试容器**里证明过
  （`tzset` 免疫用例），没有在 shipped 镜像起出的活容器里证明过；三档拓扑的活栈实测仍是遗留项。
- 待补证：推送后 CI 的 `python` job（免疫那例在 Linux runner 上第一次由 CI 执行）与 `helm` job。

#### 就地纠正（文档声称与行为对不上）
- `docs/PROJECT_TOUR.md:327` 写"静态一致性门禁（十三项…）"，而第九十七批起就已经是十四项——
  那批加了检查 14 却没动这句枚举。本批补成"十五项"并把两项（workflow run 标量形态 / python 钟面口径）
  一起列进枚举。人工核对方式：`grep -c "parser.add_argument" scripts/static-checks.py` = 15，
  与头 docstring 里"检查 1..15"的枚举逐条对得上。
- 本批原先把核对方式写成 `grep -c "^# ── 检查"` = 15，**那是错的**：实测量出该模式只匹配 13 处，
  缺的是检查 5（`--h2-schema-drift`）与检查 6（`--readme-claims`）——这两节从未用过 `# ── 检查`
  分节横幅。用横幅数当门禁总数，等于把"漏写一条横幅"读成"门禁少一项"，而它既不是充分也不是
  必要证据。旗标数才与 `main()` 的调度一一对应，故此处改为按旗标核对（第一百零三批就地纠正）。

#### 验证
- 新增两文件本地：`19 passed, 1 skipped`（skip 的那例是 `tzset` 缺失，Windows 无进程时区翻转能力）；
  在 `hfusionhub/python88:rc` 里同一批：**20 passed**（免疫用例在 Linux 上真执行）。
- `python-ai` 全量 `pytest -q`（venv，python 3.11）：**2087 passed / 18 skipped**，退出码 0
  （scratch `b102_py_green_container.log` / `.b102_full_suite.log`）＝第一百批留存的 2068 passed /
  17 skipped ＋ 本批 20 例（19 通过 + 1 因平台跳过），既有用例一条状态没变。
- `scripts/static-checks.py` 全绿，退出码 0（含新检查 15 与计数同步 Python 1916 → **1936**：
  README ×4、README_EN ×1、ROADMAP ×1、CLEANUP_BACKLOG ×1 共 7 处）。
- `ruff check`（venv 钉版，`python-ai` 工作目录）：`tests/ app/ scripts/` All checks passed
  （新文件初稿有 4 条 `UP017`，`--fix` 后为 `datetime.UTC` 别名形态）。
- CI 侧对本批改前的 main（第一百批 run 38135767897）读到的其余两条红已定位，均为依赖审计门：
  `python-lint` 的 pip-audit `Found 29 known vulnerabilities in 5 packages`
  （pypdf 6.16.2 / python-dotenv 1.0.1 / requests 2.31.0 / starlette 0.52.1 / urllib3 2.7.0），
  `frontend` 的 `npm audit --audit-level=high` ⇒ `15 vulnerabilities (7 moderate, 8 high)`，
  且 npm 侧逐条都写着 `fix available via npm audit fix`。同一 run 的 `java`、`python`、
  `python-container`、`docker-build`、`helm`、`static-consistency`、`docker-compose-validate`、
  `eval-offline`、`gitleaks` 全部 success ⇒ 第一百批那条"容器轨 6 条 ERROR"的补证到位。
  审计两条是下一批（第一百零三批）的范围，不在本批动阈值。

### 第一百零一批（2026-10-11：SSE 终止事件收敛为一道闸门——`[DONE]` 此前由哨兵与 `onComplete` 各发一次，"线上不重复"只靠"complete 之后再 send 会抛异常被吞掉"）

#### 结论（先给判定性质）
- 这是 CI 抓出的**真竞态**，不是环境抖动。main 上 `java` job 唯一那条红来自 run 38134153636
  （第九十九批的 `3dba7e3d`，**零 Java 改动**下从第九十六/九十七批的 success 翻成 failure）：
  `ConversationStreamingPersistenceTest.asyncContentResetClearsAccumulatedContentAndForwardsResetEvent:334
  content_reset should be forwarded: content×2 + reset + [DONE] ==> expected: <4> but was: <5>`，
  `Tests run: 717, Failures: 1`。
- 根因由代码结构给出：`StreamSession` 的 `[DONE]` + `complete()` 有 **5 个出口**（哨兵 `handleDone`、
  取消信号、`onError` 取消分支、`onError` 错误分支、`onComplete` 兜底）。Python 正常收尾时哨兵与
  `onComplete` **必然都走到**，第二发 `send` 依赖 `SseEmitter.complete()` 之后再 `send` 抛异常、
  被 `catch (Exception ignored)` 吞掉才没到线上——不变量挂在 emitter 的实现细节上，任何包装
  （装饰器、按次计数的测试替身）都不再抛，重复就显形，于是同一份断言读数取决于流线程与主线程谁先到。
- **本地复现率 0/8**：`-Dtest=<类>#<该方法>` 连跑 8 次全绿（scratch `b100_java_loop_1..8.log`，
  每次 `Tests run: 1, Failures: 0`）⇒ 只能偶发，符合竞态形态；CI 那一次读到了 5。

#### 修复与判据
- **红判据先行**：新增 `doneSentinelAndStreamCompleteEmitExactlyOneTerminalEvent`
  （`ConversationStreamingPersistenceTest:353`）——**同步 Flux**（不带 `subscribeOn`），订阅在测试线程
  上跑完，计数没有竞态；记录型 emitter 把 `builder.build()` 的 `DataWithMediaType` 分段拼回一条再断言
  "content + 恰好一个 `[DONE]`"、`complete()` 恰好一次。改前实测红：
  `rendered payloads=[data:{content=可信回答}, data:[DONE], data:[DONE]] ==> expected: <2> but was: <3>`
  （`b101_red4.log`）。
- 判据自己也红过两轮才可用：第一版直接 `String.valueOf(builder.build())`，拿到的只有
  `ResponseBodyEmitter$DataWithMediaType@…` 地址，`[DONE]` 计数取到 **0**（`b101_red.log` /
  `b101_red2.log`）——不是"没有重复"，是渲染取不到载荷。记下来防后来人把这两种形态混淆。
- **实现**：`ConversationServiceImpl:1028` 加 `terminalEmitted`（`AtomicBoolean`），`:1151`
  `emitTerminal()` 为唯一终止出口（`compareAndSet` 先到先得，后来的直接返回，发送失败只记 debug），
  5 处终止点全部改为调用它：`:1165`（哨兵）、`:1189`（取消信号）、`:1207`（`onError` 取消分支）、
  `:1223`（`onError` 错误分支）、`:1258`（`onComplete` 兜底）。
- **未采纳**：把既有断言从 `== 4` 放宽成 `>= 4`。那等于把这条 CI 红换成一个恒真的判据，信号消失。
  也**没有**删掉 `onComplete` 兜底——"Python 没发 `[DONE]` 就结束流"仍要靠它收尾，两者只是收敛到同一道闸门。
- 同类出口扫过一遍，缺陷面确认只有这 5 处：`OpenApiServiceImpl:194` 只在 `doOnComplete` 发一次
  （`[DONE]` chunk 被跳过）、`AgentTaskQueueServiceImpl:361` 用自有 `terminalReceived` 闸门、
  `ConversationServiceImpl:545`（幂等重放）是单一出口且没有第二条终止路径。
- **这条不变量的守夜人是行为判据本身**，没有另加"源文件里 `[DONE]` 出现几次"的静态计数门禁：
  任何人再写一处绕过 `emitTerminal()` 的裸 `send`，同步流用例的 payload 计数会立刻回到 3。

#### 成本（修复带出的真实行为改变）
- `onError` 非取消分支：`emitTerminal()` 自己吞掉发送失败，所以**错误消息落库不再被"send 抛异常"跳过**。
  此前客户端已断开时会跳到 `catch → completeWithError`，那条 `status=error` 的助手消息不会写库；
  现在会写。这是行为变更，不是等价重构。

#### 诚实边界
- 闸门只管**终止事件**。哨兵之后如果 Python 还推分片，content 分支照样会往已 `complete()` 的
  emitter 上 `send`，仍靠 Spring 抛异常 + `onChunk` 的 `catch` 打 warn——本批没动它，也没法用同一道
  闸门管（它不是"终止"语义）。
- "竞态消失"的运行时证据只能由 CI 给：本地 8/8 绿 + 单例红→绿说明的是**机制**（第二发根本不再发生），
  不等于 runner 上已观察到的 5 从此不再出现。本批推上去后 `java` job 的 `Tests run: 718 / 0 fail`
  才是补证，登记在 `docs/CLEANUP_BACKLOG.md` F 节。

#### 验证
- 单例红→绿：改前 1 failure（3 发 / 两个 `[DONE]`），改后 `Tests run: 1, Failures: 0`（`b101_green1.log`）。
- 全量：`mvn --batch-mode test` ⇒ **Tests run: 718, Failures: 0, Errors: 0, Skipped: 1**，
  jacoco `check` 通过、BUILD SUCCESS（`b101_java_full.log`）。既有那条 `== 4` 断言未改，
  在新结构下变成确定性的（助手行落库发生在终止发之后，计数只可能停在 4）。
- `spotless:check` 由红（2 文件违规）转 `spotless:apply` 绿，apply 只动本次这 2 个文件。
- 计数同步：Java 717 → **718**（README ×4、README_EN ×1、ROADMAP ×1 并把实测口径归到本批、
  CLEANUP_BACKLOG ×1）。这一项**有**静态门禁：`scripts/static-checks.py` 的检查 3 数 Java 侧
  `@Test` 注解（和 Python 的 `def test_`、前端的 `it/test` 一起）与文档比对，计数没跟上就是它先红——
  本批跑通即为 718（静态 `@Test` 口径与 surefire 的 run 数在本批恰好相等：新增 1 个 `@Test`，
  run 数 717→718）。

### 第一百批（2026-10-11：容器轨的 owner 定为 `python-container`，`python` job 不再跑它；镜像守卫把"daemon 问不到"与"没带标签镜像"分成两句话）

#### 结论（先给判定性质）
- 本批处置 `docs/CLEANUP_BACKLOG.md` F 节第二条。三条候选里**没有采纳 skip**（那会把"容器轨没跑"
  重新变成无信号），也没有"只靠红着提醒"：owner 收进 workflow 的结构里，守卫继续 fail-not-skip，
  但必须说清它到底在抱怨哪一件事。
- **前提不是推断，是 CI 日志原文**：第九十七批 run 38115360383 的 `python` job 是
  `5 failed, 2047 passed, 7 skipped, 6 errors`，6 条 ERROR 逐条都是 `TestRunnerIntegration::*`，
  文本全是 `Integration tests require a tagged local Python base image`，落点
  `tests/test_plugin_container.py:761`（守卫那句 `pytest.fail`）；同一个 run 里 `python-container`
  是 **success**（预拉镜像、跑该文件、接 skip 门禁）。⇒ "同一个文件被两个 job 以不同期待执行"
  坐实，且第九十七批把这条登记成「`python-container` job 的 6 条 ERROR」**归属写错了**，
  本批就地纠正（见下方"就地纠正"）。
- 同 run 那 5 条 `failed` 是第九十九批的 fd 链，与本批无关；两条红是两条缺陷，不是一条。

#### 修复与判据（判据先红，再动 workflow 与守卫）
- 判据先行：`python-ai/tests/test_ci_workflow_gates.py:254` 起新增 9 例（`:292`
  `TestContainerLaneOwnership` 4 例 + `:359` `TestContainerImageGuardDiagnostics` 5 例，
  后者用注入的 fake client 真执行守卫本体）。对 HEAD 的 workflow 与守卫是
  **4 failed / 5 passed**（`scratch-b99/b100_red_judgement.log`），红的正是归属两例、
  daemon 误报一例、候选顺序一例——即本批要修的那四个面。改后同一文件 **28 passed**。
- 改动一（归属）：`.github/workflows/ci.yml:177` 的 `python` job pytest 命令加
  `--ignore=tests/test_plugin_container.py`，注释点名 owner 是 `python-container`；owner 侧
  一字未动（`:200` 预拉、`:215` 跑文件并接 `check_container_skips.sh`）。判据钉的不只是"加了
  `--ignore`"，还有**排除面**：`pytest -q tests` 的套件面、`--cov=app`、`--cov-fail-under` 必须
  原样留着，且 `--ignore` 恰好出现一次（防止把"排除一个文件"悄悄长成"缩小套件"）。
- 改动二（可诊断性）：`python-ai/tests/test_plugin_container.py:726` `_resolve_local_python_image`
  改为**先** `client.images.list()`——它失败就是 daemon 不可达，单独报（带异常类型与
  "先确认引擎在跑/DOCKER_HOST/socket 权限"），不再和"可达但无镜像"共用一句话；候选表按顺序命中，
  表里没有再兜底任意带标签的 `python:*`，无标签镜像不会被静默拿去 `FROM`。预拉的标签由判据
  `guard_candidate_tags()` 从守卫源码自己解析出来比对，标签名不再有第二份抄本。

#### 成本（先声明判据，再量）
- 排除文件会把该文件 36 例非 Docker 测试从 `python` job 的覆盖率口径里拿走，而棘轮是
  `--cov-fail-under=74`——**改前先声明**："文件级 `--ignore` 只在 TOTAL 损失 < 0.5 个百分点时采用，
  否则改成只摘 `TestRunnerIntegration`"。实测（本地全量，两次）：
  含该文件 `2068 passed / 17 skipped`，`TOTAL 19163 stmts / 4281 miss` = 77.66%；
  加 `--ignore` 后 `2032 passed / 11 skipped`，`TOTAL 19163 / 4350` = 77.30%
  ⇒ **损失 0.36 个百分点**（69 条语句，集中在 `app/core/plugin/container_runner.py`：79% → 33%）。
  判据满足，故保留文件级排除；棘轮余量从 ~3.7pp 降到 ~3.3pp，未动阈值。
- 那 6 例 Docker 集成测试本地是 skip（venv 里 docker 不可用）、CI 里是 ERROR，两边都对它零覆盖，
  该文件对 TOTAL 的贡献全部来自另外 36 例非 Docker 测试 ⇒ 本地量到的 0.36pp 就是 CI 侧的成本，不是它的下界。

#### 诚实边界
- CI 侧**尚未取证**：run 38134153636 跑的是第九十九批的码，`python` job 里那 6 条 ERROR 必然还在。
  本批的判定证据是推送后新 run 的 `python` job 日志——期望形态：`6 errors` 消失、
  只剩第九十九批那 5 条是否也消失（那是 fd 修复的判定），以及 TOTAL 仍 ≥ 74。
- 守卫的 daemon 分支在本地不可执行（无 docker ⇒ 整类 skip），5 例判据是把 fake client 注进
  **守卫本体**真跑，不是文本核对；真 daemon 故障那条文本仍只在 CI/人工环境里才会第一次出现。
- `--ignore` 只解决"谁执行这个文件"，不解决"这个文件在 CI 里到底跑绿没有"——后者由 owner job 的
  skip 门禁继续盯着，第九十批那套语义未变。

#### 验证
- `python -m pytest tests/test_ci_workflow_gates.py` ⇒ 28 passed；
  `tests/test_plugin_container.py` ⇒ 36 passed / 6 skipped（与改前同形态，守卫重写未动非 Docker 面）；
- 全量两次见"成本"段；`scripts/static-checks.py` 全绿（含计数同步 Python 1907 → **1916**，
  README ×4 / README_EN / ROADMAP / CLEANUP_BACKLOG 共 7 处）；`ruff check` 两文件通过。

### 第九十九批（2026-10-11：插件子进程的 fd 上限从"绝对数"改成"继承数 + 预算"——CI 那 5 条 `Errno 24` 在容器里按 HEAD 代码原样复现，再原样消失）

#### 结论（先给判定性质）
- 本批是 `docs/CLEANUP_BACKLOG.md` F 节第一条的处置，方案由用户选定：**A**（设限前先数已打开的 fd，
  上限钉成"继承数 + 预算"，只动 soft、hard 留给运行期）。B（让子进程不继承）与 C（只在测试里抬
  `max_open_files`）未采纳，C 的形态本就是该清单反对的"把红压掉而缺陷留在生产码"。
- **先做成 CI 级复现，而不是只写判据**：在 `hfusionhub/python88:rc` 里用一个 session-start 灌 fd 的
  一次性插件（`scratch-b99/b99_fdload_plugin.py`，把 pytest 父进程抬到 200 个 fd）复现 CI 的主机形态，
  跑的却是 **HEAD 的生产码 + HEAD 的两份既有测试**（`test_plugin_sandbox_runner.py` +
  `test_plugin_security.py`，29 例）⇒ `5 failed, 24 passed`，且这 5 条与 CI `python` job 里那 5 条
  **同名**：`test_fs_default_baseline_reads_own_plugin_dir`、
  `test_fs_default_baseline_denies_paths_outside_baseline`、
  `test_network_default_deny_blocks_connect_in_subprocess`、
  `TestNetworkSandbox::test_network_access_to_allowed_domain`、`TestResourceLimits::test_timeout_enforcement`。
  这条把第九十七批的推断（"CI 那 5 条红等价于 pytest 父进程当时握着 ≥64 个 fd"）从推理变成可复算。
- 判据层的红同样先取到手：新文件对 HEAD 代码是 **6 failed / 2 passed**（当时 8 例，容器内），
  红的正是这条缺陷的三个面——hard 被钉成预算、子进程抬不回 soft、soft 不含继承数。

#### 修复与判据
- `python-ai/app/core/plugin/sandbox_runner.py`（+42/−4，净 +38 行）：新增 `:72` `_FD_SCAN_CAP`、
  `:75` `_count_open_fds()`（Linux 走 `/proc/self/fd`，其余按 `fstat` 扫到 4096）、
  `:91` `_apply_fd_budget()`；`:132-141` 的 fd 分支由 `setrlimit((max_open_files, max_open_files))`
  改为调用它。三条口径写进函数与 docstring：**soft = 设限时已打开的 fd 数 + 预算**；
  **只按继承 hard 夹、不按继承 soft 夹**（按 soft 夹的话，继承 soft 比预算小就又退回 0 额度）；
  **hard 保持继承值**（fork 之后设限，若把 hard 也钉死，非 root 的子进程连抬回去的余地都没有）。
  `target == soft` 时不调 `setrlimit`，避免每次执行都做一次无谓系统调用。`:45` 的字段含义随之改注为
  "新增 fd 的预算，非绝对上限"（它是 manifest 可声明项，`manifest.py:40` / `registry.py:73` 走的是同一条路）。
- `python-ai/tests/test_sandbox_fd_budget.py`（11 例，6 个类）：`TestHardLimitStaysInherited`（hard
  仍是继承值、子进程可把 soft 抬回继承 hard）、`TestSoftIsInheritedPlusBudget`（soft 含继承数；预算是
  真上限而非绝对数；继承 soft 荒谬地大时仍会被下调）、`TestEndToEndWithLoadedParent`（父进程灌 200 fd
  后 `execute_in_sandbox` 仍能跑通插件 import——即 CI 的失败点）、`TestBudgetNeverCrossesInheritedHard`
  （`hard_floor = 当时 fd + 8` 且断言 `继承数 + 预算 > hard_floor`，让"夹"这一步真被执行到）、
  `TestCountOpenFds`、`TestNoResourceModuleFailsLoudly`。计数全部由 fork 出的子进程现场回报
  （`soft/hard_before`、`inherited`、新增可用 fd、能否抬回），不是父进程猜的。
- 三处机制细节被钉成断言而非注释：① `os.listdir("/proc/self/fd")` 会数到自己那个目录 fd，
  所以 `/proc` 通道恒比 `fstat` 扫描多 1 ⇒ **声明预算实际是"预算 + 1 富余"**
  （`test_scan_fallback_is_exactly_one_below_proc` 钉差值恰为 1，上限也按 `BUDGET + 1` 算）；
  ② 探测"额度用尽"必须**握着** fd 再计数（open-then-close 的循环永远碰不到上限，第一版因此把整轮
  跑成 191 秒超时）；③ 观测用例必须抬 `memory_mb`，因为 fork 出的 pytest 子进程 VSZ 远超 256MB，
  否则 `RLIMIT_AS` 先把子进程杀掉，红的是环境不是判据。

#### 诚实边界
- **CI 上这条修复的真执行尚未取到**（本批未推送）。已有的是容器内 HEAD/修复两版对跑的差异，
  与第九十七批那条纪律一致：判定标准只能是 runner 日志，容器复算只是必要条件。
- 本机永远验证不到主体：Windows 无 `resource` 模块，11 例里 **9 例按设计跳过**，只剩
  `/proc` 计数与"无 resource 只 warning"两类跨平台例（本地 `2 passed, 9 skipped`）。
  判据的真身在容器/CI，**不能拿本地的绿当作这条链被验证过**。
- 未定位"pytest 父进程为什么握着那么多 fd"：本批消除的是"上限不看继承面"这个缺陷本身，
  CI 里那份 fd 账本的来源没查，也不需要查（修好后它不再决定成败）。
- A 方案的代价要说清：soft 现在随父进程 fd 数水涨船高，所以 `max_open_files` **不再是子进程可用 fd
  的绝对资源上限**，只是"新增预算"。B 方案（`spawn` / `close_pipe_fds` / exec 干净进程）才能把父子
  两类账本彻底分开，改动面更大，本批未做。
- 同形状的 `python-ai/app/core/plugin/sandbox.py:229`（`_apply_posix`）**仍未动**——`apply_resource_limits`
  全仓无真实调用点（`:262` 那段是 docstring 示例），生产不可达，收它要另立批次决定是否删。

#### 待确认（用户决定，本批未替用户拍）
- `python-container` job 那 6 条 ERROR（镜像缺失守卫）：skip / CI 预构建镜像 / 保留红着提醒——
  已在 `docs/CLEANUP_BACKLOG.md` F 节第二条登记，本批未动。

#### 验证
- 红→绿：容器（`hfusionhub/python88:rc`，CI 同版本 `pytest==8.3.5` + `pytest-asyncio==0.25.3`，
  `/app` 以 `:ro` 挂载 ⇒ 生产码运行时不可写）灌 200 fd 的 session 里，HEAD 生产码 + 两份既有测试
  `5 failed, 24 passed`（`scratch-b99/b99_ci_replay_pre.log`）；换修复后代码，两份既有测试 + 新判据
  共 40 例 **40 passed**（`b99_post_final_fdload.log`）；同一 40 例在不灌 fd 的裸 session 里也
  **40 passed**（`b99_post_final_bare.log` ⇒ 新判据不是靠灌 fd 才绿的）。
- 本地（venv，python 3.11）新文件 `2 passed, 9 skipped`；`python-ai` 全量 `pytest -q`
  **2059 passed / 17 skipped**，退出码 0（第九十七批留存产物记的是 2057/8，差值恰为本批 +2 passed
  /+9 skipped ⇒ 无回归）。
- `ruff check`（venv，0.16.3）对 `tests/test_sandbox_fd_budget.py` 与
  `app/core/plugin/sandbox_runner.py` 通过；全量 `static-checks.py` 仅剩计数漂移一条，随本批把
  Python 计数 1896→1907 同步（README 4 处 + README_EN + `docs/CLEANUP_BACKLOG.md:4` +
  `docs/ROADMAP.md:16`）后转绿。
- `docs/CLEANUP_BACKLOG.md` F 节第一条划掉（`[x]`）并写出处置、锚点与代价；同节内因
  `sandbox_runner.py` 净 +38 行而漂移的锚点就地改到现行行号（fd 设限点 `:99`→"`:132-141` 调 `_apply_fd_budget`"、
  `:530/:538/:572`→`:568/:577/:611`、`:80`→`:116`），改后逐条 `sed` 复核落点。
- **顺带纠正一条本仓自己的旧声称**：第九十七批"验证"里那句"全量 `pytest -q` **2293 passed / 11 skipped**"
  与留存的该批产物对不上——`scratch-b97/b97_pytest_full.log` 记录的是 **2057 passed / 8 skipped**
  （无 deselected），本批全量 2059/17 恰为 2057+2 / 8+9。2293 在当前测试面（静态 `def test_` 1907、
  参数化后采集 2076）上不可能出现，来源无法复算，故就地改为产物记录的 2057/8 并注明口径出处。
  手工核对记录：本批全量运行退出码 0，产物在 `scratch-b99/b99_local_full.log`。

### 第九十七批（2026-10-11：招投标三道评测竖门自出生起从未在 CI 跑过——死因是 YAML 把 `run:` 的续行折叠成了空格；顺带在容器里把 `Errno 24` 那条链的量测完，"父进程漏 fd"的假设被否掉）

#### 结论（先给判定性质）
- 推送 `ad92367e` 后那轮 CI（run 38099630611）7 绿 4 红。红的是 `eval-offline`、`python`、
  `frontend`（npm audit）、`python-lint`（pip-audit）。本批处理前两条，且第一条**与评测指标无关**：
  `eval-offline` 的三步失败全是 argparse 的 `unrecognized arguments`，退出码 2。
- 死因在 YAML 不在评测：`run: python scripts/eval_offline.py \` + 缩进续行是**一个 plain 多行标量**，
  折叠规则把换行换成一个空格，`\` 原地留下，shell 收到的不是续行而是"被转义的空格"，argv 里就是
  `' --cases'`。按 `git log` 定位出生：bid 门 `aabd3df6`（2026-08-25）、施工/IT 门 `f684d6bb` 同批引入，
  **形态从第一天就是错的** ⇒ 三道竖门 47 天里没有阻断过一次合并。
- 这条缺陷的形态值得单独记：它不产生"红"这种信号，只产生"门在但从不生效"。所以本批的门禁一半查形状、
  一半查**存在性**（`--cases` 的 needle、用例文件在位、入口脚本在位），后者对应的是"门禁消失比门禁变红更安静"。

#### 取证（先把推断做成可复算的）
- argv 层复现：把 ci.yml 用 PyYAML 解析成 shell 实际收到的脚本，先吃掉 `\`+换行、再按 POSIX 切词，
  历史写法产出 `['python', 'scripts/eval_offline.py', ' --cases', …]`，与 CI 日志里那句两倍空格的
  `unrecognized arguments` 对齐；范围核查扫全仓 5 个 workflow / 81 个 `run` 步骤，命中 3 个（全在 ci.yml）。
- **排掉"评测退化了"**：三套件在本地按正确引法各跑一遍，退出码 0 且 `gate_failures: []`。
- 主门（通用套件）此前依赖 `eval_offline.py:46,53` 的默认值取用例，ci.yml 里不出现 `--cases` 字样，
  于是检查 14 第一版误报"不再调用离线套件 suite"。处理是**把主门显式写出
  `--cases evaluation/suite/cases.jsonl`**（与默认值逐字相同、行为中性），而不是把门禁放宽成数调用次数。

#### 修复与判据
- `.github/workflows/ci.yml`：三个竖门改 `run: |`，bid 那一步留了成因注释；主门改显式 `--cases`。
- `scripts/static-checks.py` **检查 14**（`--workflow-run-scalars`，已并入默认全跑档）：行内值以 `\`
  收尾、或存在"比 `run:` 键更缩进、又不是 key/列表项"的折行 ⇒ 红；再钉四道门的存在性。
- `python-ai/tests/test_workflow_run_scalars.py`（15 例）：真仓库绿、接线（全跑档 `args.workflow_run_scalars`
  出现 ≥2 次）、四门 argv 里 `--cases` 是独立 token 且无空格污染、**每个 `--flag` 都必须在 argparse 里声明过**
  （形状对了仍可能拼错选项名，那同样是退出码 2）、`--cases` 相对路径必须命中 job 声明的
  `working-directory: python-ai`、历史折叠形态真会产生 `' --cases'`（红判据不是纸面推断）；
  漂移注入 6 例：行内反斜杠、plain 折行、门整步消失、用例文件缺失、入口脚本缺失、ci.yml 缺失。
- 判据故意用 PyYAML 而生产码只用标准库——两个 oracle 不同源，检查 14 背错折叠规则时语义判据能发现。
- 文档纠正：`docs/CI_GATES.md` 第 3 行"每个 push/PR 都跑离线评测门禁"与 `README.md:49` 的
  "CI push 阻断门禁"此前只对主套件成立；新增第 5 节记录本批，并把"四处自伤"改成五处（正文里那句
  "三条判据"在第九十四批就已经落后，一并纠正）、`相关文件` 里那条"上述两条判据"的旧措辞同样改对。
- 诚实边界：检查 14 不保证门里的断言会过，`run:` 内 shell 逻辑对不对仍归"把步骤体落盘真跑"那类判据；
  本批提交时 CI 上那四次真实执行**还没取到**，写的核对记录只到本地 argv 与本地套件（本地 argv 只是
  必要条件，判定标准只能是 runner 日志）。推送后的补证见下面"验证"末段。

#### B 链取证：`Errno 24` 不是漏 fd（容器内实测，未动生产码）
- CI `python` job 那 5 条红是同一条链：都是 `[Errno 24] Too many open files: '<插件目录>/__init__.py'`，
  `error_code=plugin_execution_error` ⇒ 异常在**子进程** `_subprocess_worker` 的 Step 3 import。
  另 6 条 ERROR 是 `test_plugin_container.py` 的"无标签镜像就 `pytest.fail`"守卫，与本链无关。
- `hfusionhub/python88:rc` 里量：裸 `python` 父进程 fd=4；一次成功调用的子进程看到 9 个 fd、
  `RLIMIT_NOFILE=(64, 64)`；三条分支各跑 15/8/8 次，父进程 fd **before=after=after_gc=4，净增 0**
  ⇒ `sandbox_runner.py:530`/`:538` 绕过 `finally`（`:572`）是代码事实，但 CPython 按引用计数在栈帧
  展开时关连接，**"父进程漏 fd"这个怀疑作废**。
- 决定性对照：父进程灌到 64/70/80/100/150/200 六档全部红且都栽在子进程第一个 import；父进程固定 150 时
  `max_open_files` 64 红、128 红、**256 绿** ⇒ 限制变量是"上限 vs fork 时已继承的 fd 数"（`:99` 在 fork
  之后设限，hard 也被钉死，子进程再也抬不回去）。故 CI 那 5 条红等价于"pytest 父进程当时 ≥64 fd"。
- 本机看不见的机制：Windows 无 `resource` 模块，`:80` 的 `ImportError` 分支把三项限制全跳过 ⇒ 本机恒绿。
- 同形状的 `sandbox.py:229` 经核查**生产不可达**（`apply_resource_limits` 的"调用方"只有 `:262` 的
  docstring 示例）。三条出路（抬到"继承数+预算"且只动 soft／让子进程不继承／只改测试）登记在
  `docs/CLEANUP_BACKLOG.md` 新增的 F 节，属行为决策，本批不动。

#### 待确认（用户决定，本批未替用户拍）
- `test_plugin_container.py` 那 6 条 ERROR：改 skip（CI 绿但"容器轨没跑"重新变成无信号）、CI 预构建镜像
  （绿且真跑，代价是时间与网络依赖）、还是保留 `pytest.fail`（红着提醒）。

#### 验证
- 红→绿：修改前 `python scripts/static-checks.py --workflow-run-scalars` 退出码 1，点名
  ci.yml:252 / :266 / :279；修改后同一命令 `[ok] … 扫描 5 个文件 / 81 个 run 步骤 … 四个离线评测门 … 用例文件在位`。
- 新判据文件 15 例全绿；`python-ai` 全量 `pytest -q`（venv，python 3.11）**2057 passed / 8 skipped**
  （第九十九批就地纠正：此处原写 2293/11，与该批留存产物 `scratch-b97/b97_pytest_full.log` 对不上，
  2293 在当前测试面上不可能出现，详见第九十九批"验证"末段），退出码 0；
  `ruff check python-ai/tests/test_workflow_run_scalars.py`（venv，0.16.3）通过
  —— `scripts/static-checks.py` 不在 lint 面内（CI 的 `ruff check .` 工作目录是 `python-ai`）。
- 全量 static-checks 仅剩计数漂移一条，随本批把 Python 计数 1881→1896 同步后转绿
  （README 4 处 + README_EN + `docs/CLEANUP_BACKLOG.md:4` + `docs/ROADMAP.md:16`）。
- **补证（推送 `d3d31f36` 后取，run 38115360383 / job 114399072071）**：`eval-offline` 在本批修法
  上线后的第一轮即 success，四道门各有一次带时间戳的 `##[group]Run python scripts/eval_offline.py`
  （`05:47:11.2899680Z` 主门单行、`:12.9625378Z` bid、`:13.9317179Z` 施工、`:14.8539778Z` IT 三条
  块标量续行被 runner 逐条回显）；四份报告的 `suite_sha256` 互不相同
  （`15b0ea64…` / `135114f4…` / `6d8a045b…` / `f23c8bf0…`），bid 门 `case_count: 27`，主门
  `citation_recall 0.8942`、`citation_f1 0.7409` 在 0.85 / 0.70 下限之上，三条竖门的四项
  `*_recall / *_accuracy` 聚合 `1.0`，四份都停在 `"gate_failures": []` 且 `diffs` 逐项 `0.0`；
  整份日志 `unrecognized arguments` / `ShellCommandUnresolved` 0 命中。`static-consistency` 同轮转绿
  ⇒ 检查 14 在 CI 上执行。同一轮仍红的是 `python`（fd 上限那条链）、`frontend`（npm audit）、
  `python-lint`（pip-audit），与本批的修法无关。`docs/CI_GATES.md` 第 5 节的手工核对记录已按这份
  日志就地改写，本批的"尚未取到"因此结清。

### 第九十六批（2026-10-10：写侧三张钟面钉成同一个 UTC，判定 SQL 换成会话免疫的 `UTC_TIMESTAMP()`——红判据第一次栽在"MyBatis 一级缓存让二次读根本没问库"）

#### 结论（先给判定性质）
- 第九十五批把读取侧定完，本批做第八十四批定下的 B+ 方案 1–6 项（生产时区口径）。取数先
  推翻一条现成声称：ADR-008:89 那句"`TZ` / `-Duser.timezone` / MySQL `default-time-zone`
  目前在**任何部署面上都没有声明**"在第九十五批的提交上确实成立
  （`git grep -n -e user.timezone -e default-time-zone HEAD -- docker/ deploy/ java-backend/src`
  = **0 处**），但同一句里没写的是**已经存在的钟面自己就不一致**：`serverTimezone` 5 处里
  4 处 `Asia/Shanghai`（`docker/docker-compose.yml:253`、`deploy/docker-compose.prod.yml:172`、
  `application.yml:24`、`application.yml.example:13`）、只有 `templates/java.yaml:48` 写 `UTC`。
  也就是说"没声明"的真实形态是"声明了三套、其中两套互相矛盾"。
- 缺陷的落点不是"偏了 8 小时"，而是**同一行的判定随连接翻转**：`DATETIME` 存不带时区的字面
  墙钟，写入用 JVM 默认钟（`LocalDateTime.now()`）、谓词里的 `NOW()` 用**会话**钟，两处都没被
  钉住。翻不翻得动是可算的：一行 `expires_at` 落在 `(UTC 此刻, UTC 此刻+8h)` 这个窗口里时，
  会话为 `+00:00` 判"未过期"、会话为 `+08:00` 判"过期"，而行内容是同一个字节。
- 红判据（`WriteClockCaliberTest`，真库，第九十五批的树）：**4 run / 3 failed**
  （`b96_it_red_head.log`），三条会话免疫断言各自红在 `assertTrue/assertFalse` 的对照行上；
  第四条（缓存探针）本就是绿的，因为它钉的机制与钟无关。红阶段那条清扫用例叫
  `expirySweepDoesNotDependOnWhichClockTheNowCameFrom`——它断言的是"JVM 传进来的 now"与"库钟"
  两个来源会给出不同集合，修复把这个入参删掉之后，用例退成"清扫不随会话时区翻转"并改名，
  这是**结构上不再可能有双钟**的证据，不是把断言放宽。
- **本批第一次红判据拿到的是假绿**，且成因值得单独记：`@Transactional` 的 Spring 测试让整条
  用例共用一个 SqlSession，MyBatis 一级缓存以 `{语句+参数}` 为键活在里面，于是"切了
  `SET time_zone` 再读一次"同参数时**根本不去问库**，返回第一次的结果集——两条会话免疫用例
  在缺陷存在时都是绿的。发现方式是临时诊断（同会话插一行新的、看它可不可见），现已钉成
  第四条用例 `identicalStatementAndParamsAreServedFromTheMyBatisFirstLevelCache`；其余用例
  要么换参数读（`selectExpiredRecycled(100)` / `(101)`、两个 user_id），要么（无参的清扫）
  显式 `sqlSession.clearCache()` 后用"刚插入的行必须可见"自证这次读真的问了库。

#### 改动（判定侧改写法 + 部署侧钉钟面，两侧都必须有）
- **判定 SQL 10 处**全部从 `NOW()` 改成 `UTC_TIMESTAMP()`（8 处比较 + 2 处写入；第九十五批
  的"下一批"指针写的是"6 处判定 SQL"，那是当时按 mapper XML 数的，实测口径见本条）：
  `AgentApprovalMapper.xml:56`（待办列表）、`:74`（过期清扫）、`DocumentMapper.java:80`、
  `KnowledgeBaseMapper.java:53`、`PromptTemplateMapper.java:63`（三处回收站过期）、
  `PluginMapper.xml:88`（熔断到点）、`NotificationController.java:44/:68`（公告过期），
  写入侧 `PluginMapper.xml:145`（`DATE_ADD(UTC_TIMESTAMP(), INTERVAL …)` 冷却）与
  `NotificationController.java:84`。
- **合掉审批双钟**：`AgentApprovalMapper.selectExpiredPending(@Param String now)` → 无参，
  `AgentTaskServiceImpl.java:729` 不再传 JVM 的 `LocalDateTime.now()`（`nowStr` 只留给
  `decided_at`），`AgentApprovalRaceGuardTest.java:297/:316` 的 stub 随之改。
- **三张钟面钉成 UTC**：JVM `-Duser.timezone=UTC` 走 `JAVA_TOOL_OPTIONS`
  （`docker/docker-compose.yml:268`、`deploy/docker-compose.prod.yml:198`、
  `values.yaml:72` → `templates/java.yaml:70`）；MySQL `--default-time-zone=+00:00`
  （compose `command` 两处 + `values.yaml:36` → `templates/mysql.yaml:34` 的 `args`）；
  JDBC `serverTimezone=UTC`（4 处 `Asia/Shanghai` 收口 + `application.yml.example:13`、
  `application-test.yml`、`application-it.yml`）。选 `JAVA_TOOL_OPTIONS` 而不是 `JAVA_OPTS`
  是因为后者**不是通道**：`deploy/Dockerfile.java:26` 的 ENTRYPOINT 是 exec 形式，没有任何
  shell 展开 `$JAVA_OPTS`（实测 `Picked up JAVA_TOOL_OPTIONS` 出现在 maven JVM 与 surefire
  fork 两处，前者是 JVM 自己读的）。`JAVA_OPTS` 那三处按用户选定方案**本批不动**、另立缺陷
  登记（删掉还是改入口是行为决策，会真的改变堆上限）。
- `spring.jackson.time-zone` 一并改 UTC，但**注明它是空转的**：`date-format` 只作用于
  `java.util.Date`，而 `src/main/java` 普查不到一处 `Date`/`Instant`/`OffsetDateTime`/
  `ZonedDateTime` 字段，出站全是 `LocalDateTime`。改它是为了让配置里不留一张指向别处的钟面，
  而不是因为它有效果。
- **检查 13（`--write-clock-caliber`，已并入默认全跑档）**：10 张钟面必须都归一到 UTC、
  helm 模板必须**真的引用**那两个 values 键（第八十三批"模板读了一个不存在的键"的反向形态：
  键存在但没人读，同样是死配置）、三张判定列不得再和 `NOW()` 同处一个比较式；注释行不计入
  声明（第八十四批规则）但行号保留，所以报告能指到真行。

#### 验证（红→绿，逐条实测）
- 判据类：`WriteClockCaliberTest` 红 **4 run / 3 failed** → 绿 **4 passed**（外部真库
  `HFH_IT_JDBC_URL=…127.0.0.1:3308…serverTimezone=UTC`，`b96_it_green1.log`）。宿主时区实测
  `+08:00`（maven 日志 `Finished at 2026-10-10T21:45:40+08:00`），判据仍绿 ⇒ 断言与宿主钟无关。
- Java 全量：`mvn -B -o spotless:check test -Djacoco.skip=true` **BUILD SUCCESS，
  Tests run: 717, Failures: 0, Errors: 0, Skipped: 1**（`b96_mvn_full.log`；第九十五批口径
  713 ＋ 本批 4 例，唯一 skip 是 `PythonEngineSmokeTest`，由 `CI_SMOKE_PYTHON_URL` 门控，
  与第九十四批同数）。
- Python 全量：**2042 passed / 8 skipped**（`b96_pytest_full.log`）＝第九十二批 2025 ＋
  第九十五批 6 ＋ 本批 11（`tests/test_write_clock_caliber.py`）。
- 门禁：`static-checks.py` 全跑档除计数棘轮本批待同步外其余 [ok]，检查 13 绿
  （`[ok] 写侧时钟三源同源（10 张钟面全部 = UTC），判定列不读会话钟：扫描 472 个 mapper XML
  与 src/main/java 文件`）；红侧用**真实文件**注入三种漂移各判红一次并跑完还原
  （JVM→`Asia/Shanghai`、`mysql.defaultTimeZone`→`+08:00`、模板删掉 `.Values.mysql.defaultTimeZone`
  引用）。接线测试按第八十三批那次哑火的破坏方式实测过它自己会红
  （要求 `args.write_clock_caliber` 在 parse 之后、首个 dispatch 之前出现 ≥2 次）。
- helm：`lint` 0 failed；`template`（secrets/pluginRunner 用 RENDER-CHECK 占位）退出 0、
  24 个对象、0 个 `<no value>`；与第九十五批树的渲染产物逐行 diff **恰好 +5 行**
  （java 两行 `JAVA_TOOL_OPTIONS`、mysql 三行含 `args`），无其它改动。对照产物按
  `git archive HEAD` 解到仓库外生成，不碰工作副本。
- `ruff check` 干净；行尾纪律：三处被门禁注入过的文件工作副本一度被 Python 的
  `read_text`/`write_text` 往返改成 CRLF，已按第九十二批口径改回 LF
  （`git ls-files --eol` 现 `w/lf`，`git diff --stat` 只剩内容改动）。

#### 上限（不假装做过）
- 检查 13 只读文本：证明"声明存在且同源"，不证明 mysqld 真以该参数起过、也不证明三档拓扑
  中任何一档起过容器。IT 的 JDBC URL 一律被 `@DynamicPropertySource` 覆盖，生产那条 URL 上
  的 `serverTimezone` **没有任何一次真实连接**走过。
- 存量数据"本来就是 UTC 字面量"是**三条已核事实的推论**（镜像未声明 `TZ`、字段全为
  `LocalDateTime` 故驱动不做偏移换算、会话取 server 默认），不是对某个真库做过的普查；
  `docs/PRODUCTION_OPS.md` §13.1 给了逐表核对的 SQL 与判读口径。
- 本批没有把 JVM 默认钟 == 库钟写成断言——那等于要求每台开发机系统时区都是 UTC，正是第九十
  四批刚从 `application-it.yml` 撤掉的那类宿主假设。

#### 三条只登记不修
- `JAVA_OPTS` 死开关（3 处声明 / 0 处消费）：见 `docs/CLEANUP_BACKLOG.md` B 节，并顺带纠正
  `docs/OPTIMIZATION_PLAN.md:220` 把它当成生效堆上限的那句。
- python 侧仍在口径之外：`python-ai/app/core/tools/time_tool.py:21` 的 `datetime.now()` 取
  容器时区，而 4 个 python 工作负载都没有声明 `TZ`；同一容器里另有 `datetime.now(UTC)` 的写法。
- `NotificationController.java:118` 把管理员输入的过期时刻按 naive 本地墙钟与
  `LocalDateTime.now()` 比：钉住 JVM=UTC 之后它的语义变成"管理员按 UTC 填"，而前端
  `admin/Notices.vue:81` 发的是带浏览器偏移的 ISO 串——谁负责换算没有定，属行为决策。

#### 下一批（按可核验性排序，取数成本从低到高）
1. **把 python 侧接进同一口径**：`app/core/tools/time_tool.py:21` 的 `datetime.now()` 与
   4 个 python 工作负载未声明的 `TZ` 是同一条缺陷的两半，且检查 13 的钟面表已把 java 侧收口，
   python 侧只需同一手法（compose/helm 各加一张钟面 + 门禁把它纳进 `expected` 集）。
2. **整栈 compose 端到端跑一次**：本批 10 张钟面全部只有文本层与渲染层证据，§13.3 那句
   "三档拓扑没起过任何一个容器"从第八十四批一路带到现在，是该收口的时候。
3. 判定列的写入侧收口：`AgentTaskServiceImpl.java:669` 的 `setExpiresAt(LocalDateTime.now()
   .plusMinutes(5))` 仍由 JVM 写，虽然 JVM 已钉 UTC，但"审批 5 分钟"这类时长更适合由
   `DATE_ADD(UTC_TIMESTAMP(), INTERVAL 5 MINUTE)` 产生，使写入也会话免疫。
4. CI-green 轨遗留：`Errno 24` fd 泄漏、pre-pull/tag 不匹配、`test_timeout_enforcement`、
   `pip-audit`、spotless `ratchetFrom` B′、`-Djacoco.skip=true` 的显式配方。



### 第九十五批（2026-10-10：显示时区按 A 方案落定——同一瞬间在前端曾有三套互相矛盾的解释，现在只剩一套）

#### 结论（先给判定性质）
- 第八十四批把"生产时区钉在哪"留成待办，本批先做**读取侧**（用户选定 A 方案：只修显示，
  API 与库里的值一字不动）。取数得到的判定是：缺陷不在"偏移算错了一次"，而在**同一个瞬间
  有三种互相矛盾的解释并存**，且三者各自能自圆其说：
  ① `hfusionhub-frontend/src/utils/date.ts:3` 注释断言"后端已存储北京时间（UTC+8）"，
     并把无偏移串按**本地墙钟**构造 `Date`；
  ② 8 个页面绕过它，直接 `value.replace('T',' ').slice(0,16)`，即把服务端字面量当显示值；
  ③ `src/pages/chat/Detail.vue:311` 手工 `getTimezoneOffset()+480`，把浏览器墙钟硬算成北京墙钟。
- 线上形状实测（同一瞬间 `2026-10-10T11:58:12Z` 的四种写法）：java 的 Jackson+`LocalDateTime`
  发**无偏移** ISO，python 分别发 `+00:00` / `Z` / 无偏移，另有数组形式 `[y,m,d,h,min,s]`。
  推论：任何"统一 +8"的整把偏移都是错的（对已带偏移的值会二次位移）。成立的口径只有三条——
  **无偏移按 UTC 解释、带偏移按偏移解释、渲染交给浏览器本地时区**，纯日期（`LocalDate`、
  日历日）按当地零点处理、不参与位移。
- 本批第一次红判据撞出的不是产品缺陷而是**我自己写的测试夹具**：`withTz` 用
  `delete process.env.TZ` 复原，实测 `ZONE_INSIDE=America/New_York → ZONE_AFTER=America/New_York`
  而 `envTZ=undefined`——node 在首次构造 Date/Intl 时缓存本地时区，删环境变量**不会**回到宿主时区，
  而是停在最后一次显式设置的值。后果是 HEAD 那次红跑里 `formatRelativeTime` 的两例是假绿/假红
  （泄漏的纽约时区让 11:58:12 落在未来 ⇒ 一律返回"刚刚"）。改为"把宿主时区名写回去"并补一条
  夹具自检，才让红判据可信。

#### 改动（唯一入口 + 14 处调用点 + 门禁 12，三处都必须有）
- `hfusionhub-frontend/src/utils/date.ts`：删掉那句假前提，`parseServerTime` 改成三条口径
  （`NAIVE_RE` 无偏移 ⇒ `Date.UTC(...)`，`DATE_ONLY_RE` ⇒ 当地零点，数组 ⇒ UTC，其余交给
  `new Date(text)` 并拒 Invalid）；`formatDateTime` **保持原斜杠模板**（显示格式不变，本批只改
  "显示的是哪个瞬间"），新增 `formatDateOnly`，`formatRelativeTime` 改用 `Date.now()-getTime()`
  的瞬时差。四个格式化函数统一接受 `string | number[] | null | undefined`，不可解析原样返回。
- 14 个页面/组件收口到该入口：`WebhookSettings.vue:44`、`admin/Users.vue:38`、`agent/Index.vue:188`、
  `approval/Index.vue:112-116`（`isExpiredRow` 的倒计时与显示同入口，去掉 Safari 手解注释）、
  `memory/Index.vue:136`、`rag/Index.vue:350`、`builder/TestSet.vue:1014`、`admin/Notices.vue:118`、
  `builder/Apps.vue:390`、`builder/Plugins.vue:886`、`builder/Tools.vue:266`、`settings/Index.vue`、
  `profile/Index.vue`（两处 `new Date(value)` 手解）、`chat/Detail.vue:309`（删 +480 硬算，
  本地回显改发带偏移的 `toISOString()`）。
- 防回潮：`scripts/static-checks.py` 新增**检查 12** `--frontend-time-entry`（并入默认全跑档），
  在 `src/pages|components|api` 下禁 `replace('T'…)` 与 `getTimezoneOffset()` 两种字面写法，
  目录缺失判红而非静默通过，`__tests__` 跳过以免误伤夹具。
- 测试：新增 `src/utils/__tests__/date.spec.ts` 16 例（解析契约 9 / 渲染 4 / 相对量 2 / 夹具自检 1）；
  新增 `python-ai/tests/test_frontend_time_entry.py` 6 例（真实仓库为绿、默认全跑档接线、
  两种字面写法注入为红、夹具不误伤、根缺失不静默）。
- 文档：`docs/adr/ADR-008-it-mysql-testcontainers.md` 新增「显示面口径的落定（第九十五批）」，
  把三套 theory、四种线上写法、三条规则和"写侧仍未钉"的上限一起落在时钟口径唯一的归属处；
  `docs/PROJECT_TOUR.md:327` 的门禁清单原写"十一项"却只列了 10 项（检查 10/11 加进去时漏改），
  一并订正为十二项并补齐条目；`docs/CLEANUP_BACKLOG.md:4` 的"删除前先确认基线
  （Java 572 · Python 1258 · 前端 49）"是一份早已不存在的号码，按门禁口径改成当前实测值。

#### 验证（红→绿逐条，含门禁自己的红）
- 红判据：把 HEAD 的 `date.ts` 放回原位（并补 `formatDateOnly` 等价 shim，使失败落在解析口径
  而不是"导入不存在"），`vitest run src/utils/__tests__/date.spec.ts` = **14 failed | 2 passed (16)**，
  日志 `hfusionhub-scratch/b95_vitest_red_head3.log`。仍绿的 2 例要如实写出：
  `自带 +08:00 偏移的串按偏移读` 在 HEAD 上是**假绿**（HEAD 忽略偏移、把 19:58:12 当本地墙钟，
  宿主恰好是 UTC+8 才对得上），另一例是本批新增的夹具自检，它检查的是夹具而非实现。
- 门禁红→绿：对 HEAD 的 `hfusionhub-frontend/src` 跑同一函数报出 **9 处违规**（8 个文件的
  `replace('T',' ')` + `Detail.vue` 的 `getTimezoneOffset()`）；对当前工作副本
  `[ok] … 扫描 115 个文件，未见 …`。注入式红另测 4 例（`tmp_path` 假 src）。
- 接线测试先红过一次：检查 12 第一次实现时只加了 `add_argument` 和默认全跑档赋值、**漏了
  `main()` 里的 dispatch**，`test_time_gate_is_in_the_default_all_mode` 直接判红
  （`assert 'check_frontend_time_entry()' in main_body`），补上后 6 passed——这正是第八十三批
  那次哑火的形态被它自己设计的判据抓到。
- 全量：前端 `vitest run` **117 passed / 16 files**；`vue-tsc -b --force` 退出 0（本批一度报
  `approval/Index.vue:117 TS18048 'expires' is possibly 'undefined'`，改成 `?.getTime() ?? NaN` 后清；
  `date.spec.ts` 里的 `process` 因 `tsconfig.app.json` 的 `types` 只有 `vite/client` 报 4 条 TS2591，
  用一处局部类型声明解决，**没有**为此拖进 `@types/node`）；`eslint src` 0 error，
  唯一落在改动文件里的 warning 是 `pages/rag/Index.vue:279` 的 `any`，在改动行（37、350）之外，属存量；
  `python scripts/static-checks.py` 全跑通过。
- 计数同步：Python 1864→**1870**、前端单测 101→**117**（Java 713 不变），改 README 徽章 + `:37/:47/:241`、
  README_EN 徽章、`docs/ROADMAP.md:16` 共 6 处；`--test-counts` 由红转绿，门禁计数与 vitest 执行数同口径
  （参数化用例已展开成独立 `it()`，否则 `it.each` 不计入门禁）。
- 行尾：`git ls-files --eol` 核到 `src/utils/date.ts` 工作副本是 CRLF 而同批其余文件是 LF
  （`i/lf` 一致，故提交侧无 blob 变化），已按第九十二批的教训统一成 LF；两个新文件均为 LF。

#### 可见变化与上限（不假装做过）
- 用户可见的格式变化（本批只改"显示的是哪个瞬间"，下述格式差异是走统一入口的副产物，逐条实测/核对过）：
  原先 8 个页面用字符串切出来的 `2026-10-10 11:58`，现在是 `utils/date.ts` 的斜杠模板
  `2026/10/10 19:58`（与该入口在个人中心、通知页上的既有口径一致，切片长度仍是页面自己 `.slice(0, 16)`）；
  记忆页改用 `toLocaleDateString('zh-CN', 2-digit)`，本机 node 24 / ICU 76 实测输出 `2026-10-10`
  与旧切法同形，但**分隔符从此由宿主 ICU 决定**而不是由字符串切法决定（zh-CN 的 `-` 是较近 CLDR 的行为，
  旧 ICU 的浏览器可能给 `2026/10/10`——本批没有在真实浏览器里逐个实测，只在本机 node/jsdom 上测）。
  时刻类显示的格式（`2026/10/10 19:58:12`）一字未动；但**显示的数值**在非 UTC 宿主上会与改动前相差一个本地偏移——那正是本批要修的错。
- 检查 12 是纯文本门禁：只认两种字面写法，不证明其余页面解析正确，不覆盖 `new Date(serverStr)`
  这种依赖引擎口径的写法，也不覆盖第三方日期库；契约正确性由 `date.spec.ts` 负责，写侧的钟由下一批负责。
- 三条只登记不修：`admin/AuditLogs.vue:46` 的导出文件名前缀 `new Date().toISOString().slice(0,10)`
  取的是 UTC 日而非本地日（>16:00 本地会写成"明天"，属 cosmetic 出站串，不在本批口径内）；
  `admin/Notices.vue:81` 的出站仍是 `new Date(form.value.expiresAt).toISOString()`（写侧，带偏移是对的，
  但它把 naive 输入按本地解释，与后端"无偏移按 UTC"的口径不同向）；`date.ts` 的数组分支此前是死代码，
  现在由一条用例覆盖，但它是否真会出现在响应里仍未取到证据。纯日期分支（`DATE_ONLY_RE`）也一样取不到现行调用方——java 侧唯一的 `LocalDate` 字段是 `DailyCostDTO.statDate:18`，而成本页把 `api/cost.ts:13` 的 `statDate` 当字面量直接展示（`pages/cost/Index.vue:205` 等），不经这个入口；`utils/date.ts:9` 的注释因此改成只陈述契约，不再点名调用方（原写作 bid deadline，它是 `BidProject.java:51` 的 `String`，前端只当表格文本显示，同样不构成证据）。
- 下一批（口径方案 B+ 的 1-6 项，已在第八十四批定下）：把 `-Duser.timezone`、MySQL
  `--default-time-zone`、`serverTimezone` 钉成三处同源的一个 UTC 口径，6 处判定 SQL 改
  `UTC_TIMESTAMP()`，审批过期去掉双钟，并配红先行的真库 IT（在 `SET time_zone='+08:00'` 下断言过期判定）。

### 第九十四批（2026-10-10：覆盖率棘轮第一次有了"含 IT"的数，取数过程撞出一个自 ADR-008 起就埋着的宿主假设）

#### 结论（先给判定性质）
- 本批要回答的问题只有一个：`jacoco:check` 那两条下限（LINE 0.46 / BRANCH 0.34，`pom.xml:269-298`）
  到底钉在哪个口径上。用 `AbstractItMySQLTest` 自带的外部库通道（`HFH_IT_JDBC_URL`，不为修 Testcontainers
  的 Windows 管道探测）把 54 例 docker 门控 IT 真跑起来，两个口径第一次同时有数：
  **含 IT = LINE 6622/13798 = 0.4799 / BRANCH 2161/6071 = 0.3560，两条下限都过**（余量 +275 行、+97 分支）；
  **IT 整类跳过 = 0.4017 / 0.3116，两条都不过** ⇒ 无 MySQL 的 `mvn test` 在 `jacoco:check` 处 BUILD FAILURE
  （第九十三批实测过两次，`b93_mvn_test_head.log:1567`、`b93_mvn_test.log:1710`）。
  于是 `pom.xml:279` 那句"CI 含 IT 会更高"从声称变成实测（+7.8 pp）；同一句里"本机口径：IT 类无 Docker
  跳过"被实测成低于自己的下限，而 `pom.xml:278` 声称 2026-09-08 正是在这一口径上测到 46.15%——今天同一口径
  只能测到 40.17%，那句按历史脉络保留、不再当现行依据（改注释而不删，是为了留下"下限曾钉在一个复现不出的数上"）。
- 取数撞出的是一条**活的缺陷**，不是环境噪声：`application-it.yml` 为"对齐 JVM"写了
  `connection-init-sql: SET time_zone='+08:00'`，其前提（跑测试的机器 JVM 在 +8）写在 ADR-008 第 3 条里，
  是**开发机**的事实而非仓库的事实。CI 的 ubuntu runner 与 maven 容器里 JVM 都是 UTC，于是会话与 JVM
  不是对齐而是相差 8 小时，库的 `NOW()` 比 Java 侧快 8 小时 ⇒ `DocumentMapperRecycleTest` 里
  `recycle_expires_at = now + 1h` 的"未过期"行被判成过期，`expected: <1> but was: <2>`。
  这条从未见过光的原因与第九十三批同一条链：`spotless:check` 恒红，java job 走不到第 2 步。
  机制是可算的，不是推测：`SELECT @@session.time_zone, NOW(), UTC_TIMESTAMP()` 在 +08:00 会话下给出
  `+08 / 18:55 / 10:55`，同一容器同一时刻 JVM 侧 `date` 是 10:55 UTC。

#### 改动（配置撤偏移 + 判据两侧余量对称，两处都必须有）
- `application-it.yml:11-14`：删掉 `hikari.connection-init-sql` 那一行及其注释，代之以说明"会话不额外偏移、
  这里曾写过什么、为什么它把 now+1h 判成过期"的注释。撤掉后 it 会话取 MySQL 的 SYSTEM（容器里 = UTC），
  与 compose / helm / prod 三处的实际拓扑一致（普查：`TZ` 环境变量在 `docker/docker-compose.yml`、
  `deploy/*.yml`、`Dockerfile.java` 里**一处都没有**，`serverTimezone=Asia/Shanghai` 只是 Connector/J 的
  会话参数，移动不了 `NOW()`）。
- `DocumentMapperRecycleTest.java:95` `:105`：未过期侧余量 `plusHours(1)` → `plusDays(1)`，与过期侧对称，
  并在方法头写下为什么两侧都要 ≥1 天（宿主偏移上限 ±14 小时）。这不是迁就缺陷——第四个实测组合
  （JVM 在 `America/New_York`，比库慢 5 小时）在只撤偏移、不改余量时**又红了**，同一条断言、同一句消息；
  改余量后同一组合绿。mapper 语义一个字没动。
- 顺带清掉 7 处声称"跑在 H2 上"的注释（`ConversationStreamingPersistenceTest`、
  `ConversationStreamingUsageTest`、`PromptTemplateVersionIntegrationTest`、`PromptTestSetIntegrationTest`×2、
  `UsageLedgerServiceImplTest`×2）与 `DocumentMapperRecycleTest` 类头那句 "against H2"——这些类自
  `2063a548`（2026-09-05）起就跑真实 MySQL。**这批 stale 标签正是那 54 例被跳过却无人察觉的原因之一**：
  读注释的人以为它们不需要外部服务。`CostWebhookGateIntegrationTest.java:47` 那句讲"H2 时代"的
  是历史归因，保留。
- `docs/adr/ADR-008-it-mysql-testcontainers.md`：第 3 条就地改写为"当年用 +08:00 对齐、第九十四批撤掉"，
  并按该 ADR 自己的补记体例新增「时区口径的二次修正」一节（含四种组合的因果）。
- `java-backend/pom.xml` 棘轮注释：补上两个口径的实测数与"本机要跑绿必须给测试库"。
- `CONTRIBUTING.md`「Running Tests」：`mvn test` 之后说明两条下限是按含 IT 口径钉的、外部库的三个环境变量、
  以及无库时 0.40/0.31 会红是**有意的**（绿就意味着集成套真跑过）。
- `docs/CI_GATES.md`：「CI 自己的三处自伤」→ 四处（第九十批、第九十三批、第九十四批），新增第 4 节
  放口径表、四组合表和 append 那条否证。

#### 验证（判据先红 → 逐组合取数，共 7 次容器运行）
- 红：JVM UTC × 会话 +08:00 ⇒ `Tests run: 713, Failures: 1`（`b94_mvn_test_with_it.log`；因 surefire 先失败，
  `jacoco:report/check` 那一次根本没执行——顺带说明"棘轮从未在 CI 跑过"在第九十三批之后仍然成立，
  直到本批把它修到能跑）。
- 绿：撤偏移后 JVM UTC ⇒ 713 / 0 fail / 1 skip + `All coverage checks have been met` + BUILD SUCCESS（06:37 min）；
  JVM +08（`TZ=Asia/Shanghai`，日志时间戳 19:1x 对 UTC 11:1x，证明确实生效）⇒ 同样 713/0/1 skip 且 checks met；
  JVM −05 改余量后 ⇒ 单类绿；最终组合（UTC + 不偏移 + 1 天余量）全量复跑 713 / 0 / 1 skip + checks met。
- 唯一剩下的 skip 是 `PythonEngineSmokeTest`（`@EnabledIfEnvironmentVariable(CI_SMOKE_PYTHON_URL)`，
  本批未起 Python 服务，CI 里由第 4 步负责）。之前"52 skipped"这个口径本身也低估了：
  `TenantInterceptorIsolationTest` 走 `@BeforeAll` assume 中止，surefire 记的是 `Tests run: 0`
  （`b93_mvn_test_head.log:1421`），所以真实池子是 54 例——52 计入 skipped + 2 计成 0。
- 否证一条第九十三批登记的怀疑：`ci.yml:365-368` 的 `mvn test -Dtest=PythonEngineSmokeTest` **不是**潜在红。
  jacoco `prepare-agent` 默认 `append=true`，单独跑 8 例的类仍报 `All coverage checks have been met`；
  加 `-Djacoco.append=false` 重跑同一条命令 ⇒ `ratio is 0.00` + 两条 `Rule violated`。
  机制证实，结论翻转——那条怀疑是错的，写进文档时按"已被取数否掉"处理。
- 格式化不回退：改完 7 个 Java 文件后 `mvn -B -o spotless:check` exit 0（第九十三批那一步的红不能由本批复发）。
- XML 合法性：`pom.xml` 注释改动后用 ElementTree 解析通过（注释体内无 `--`）。

#### 遗留（只登记不修）
- **生产的时区口径没有任何一处钉住**：`recycle_expires_at` 由 JVM 时钟写（`recycledAt.plusDays(7)`，
  `KnowledgeBaseServiceImpl.java:220` / `PromptTemplateServiceImpl.java:166` / `DeletionServiceImpl.java:383`），
  读侧却是库的 `NOW()`（三个 mapper 各一条 `<= NOW()`）。今天两侧都默认 UTC 所以自洽，
  而每个 JDBC URL 都写着 `serverTimezone=Asia/Shanghai`——若有人据此给 java 容器加 `TZ=Asia/Shanghai`
  而不动 MySQL，7 天的回收窗口会静默偏 8 小时。修法要么两侧同时钉，要么把比较改成
  `UTC_TIMESTAMP()`；属部署面/生产语义变更，需要先定方向。
- `append=true` 使棘轮是"按 target 目录累积"的度量：本机反复 `mvn test -Dtest=Foo` 会一直拿着上一次全量运行的
  数据过关。CI 每次全新 workspace 所以数值是真的，代价是冒烟那一步的 check 不增加信息；
  要收紧就是给冒烟步显式 `-Djacoco.skip=true`。
- `docs/ROADMAP.md:16` 的 Java 用例数：本批实测 CI 口径 713（无 IT 时 711），文档仍写 703。


### 第九十三批（2026-10-10：java job 自 2026-08-17 起恒红的第一步修绿了，代价是同一次运行把第二步的真实状态暴露出来）

#### 结论（先给判定性质）
- `java` job 的第一关 `mvn --batch-mode spotless:check` 是**格式化欠账**，不是产品缺陷：插件在
  `a27f6c40`（2026-08-16）进 `pom.xml`，CI 那一步在 `1ce30072`（2026-08-17）进 workflow，此后
  128 / 532 个文件从未合格过。第九十批只把它测到"能生成补丁、补丁能编译打包"，本批把它修成绿。
- "这只是格式化"这句话必须由判据支撑，因为配置里除 `palantirJavaFormat 2.39.0` 还有
  **`removeUnusedImports`**，后者不是空白操作。两级逐文件比较（口径见 `docs/CI_GATES.md` 第 3 节）：
  ① 丢掉所有 `import` 行、再删掉全部空白后与 HEAD 逐字节比——**128/128 代码体完全相同**，没有任何一条
  语句被改写；② 比较 import 语句**集合**——107 个文件只是重排/分组，21 个文件删掉 32 条未引用 import，
  **新增 0 条、通配符 0 处**。
- 残余风险单独查了：`removeUnusedImports` 只认代码用法，所以逐条查"被删 import 是否仍在 Javadoc 散文里
  有指代"——32 条里唯一命中是 `VectorizationServiceImpl.java` 那行"**故意不加** `@Transactional`"的说明，
  讲的正是它的缺席；且 `pom.xml` 里没有 `maven-javadoc-plugin`，没有可被打破的 javadoc 构建。
- 判权：`mvn -B spotless:check test` 重排后**越过 check 进入编译**，`Tests run: 711, Failures: 0,
  Errors: 0, Skipped: 52`，与 HEAD 上同一条命令的结果逐字相同；JaCoCo 第三方对照见验证段。
- **同一次运行把下一处红挖出来，且它不是本批造成的**：`jacoco:check` 绑在 `test` 阶段
  （`java-backend/pom.xml:269-298`），实测 LINE 0.40 / BRANCH 0.31，下限 0.46 / 0.34。HEAD 上同样红
  （0.4017 / 0.3116），所以与格式化无关。更深一层：这两道下限设于 2026-08-31 与 2026-09-08（第三十九批），
  而那时 java job 已经在第一步死掉、`mvn test` 在 CI 里根本不会执行——**这道棘轮从未在被守护的环境里
  被评估过**。`pom.xml:276-280` 的"CI 含 IT 会更高"是有依据的推测，但本地这 711 例里 52 例是
  docker 门控的 IT、全部跳过，没有任何一次运行验过。

#### 改动（三处，重排单独一笔）
- `java-backend/`：128 个文件由 `mvn -B spotless:apply` 重排，**+1383/−1264**，无手写改动。
- 新增 `.git-blame-ignore-revs`（第二笔，记第一笔的 sha）+ `CONTRIBUTING.md`「Java code style
  (spotless)」：`apply` 命令、"改动面只有空白与 import" 的口径、以及每人 clone 一次的
  `git config blame.ignoreRevsFile .git-blame-ignore-revs`。**这条配置不写进仓库脚本**——改 git config
  是用户侧动作，CI 也不需要它。
- `docs/CI_GATES.md`：把「CI 自己的两处自伤」改为「三处」（计数口径跟着事实走），新增第 3 节记上面的
  判据、对照表与 jacoco 那条未收口。
- **不新增门禁**：`spotless:check` 本身就是门禁且已在 CI 里跑（只是恒红）。再加一层"用正则数违规文件"
  的文本判据是第九十一批 `vue-tsc` 那条口径的同一形态——工具链已拥有契约时，判据去执行它，不复制它的结论。
  本批的判据就是命令本身：改前 exit 1，改后在同一次运行里通过 check 进入编译。

#### 验证（取数全部实测，非转述）
- 红侧：`mvn -B -o spotless:check` 在 HEAD **exit 1**，日志原文 `Violations also present in 125 other
  files`（按截断日志字面读会数错——第九十批已纠正过一次，这里复现同一个坑）。
- 绿侧：`mvn -B spotless:check test`（重排后）`Tests run: 711, Failures: 0, Errors: 0, Skipped: 52`，
  与 HEAD 对照运行逐字相同；两次都在 `maven:3.9-eclipse-temurin-17` + 同一个 `.m2` 卷里跑。
- JaCoCo 计数器对照：LINE `5529/13765=0.4017` → `5528/13798=0.4006`（总数 +33 是语句摊到更多行，
  覆盖 −1），BRANCH 与 INSTRUCTION **总数不变**。顺带得到一条口径：INSTRUCTION 覆盖 −102 / METHOD −3
  格式化解释不了，只能来自两次执行的路径差异 ⇒ **这道棘轮不承载 0.1 个百分点的精度**。
- 行尾类缺陷在此不适用：`git ls-files --eol` 532 个 java 文件在 apply 前后都是 `i/lf w/lf`。
- 可复现性三条：现采补丁与第九十批留档的 `b90_spotless.patch` 除 index 行外逐字节相同；
  `git apply -R` 退回 HEAD 跑完对照再 `git apply` 回来，diff 与补丁文件逐字节相同（+1383/−1264/128 全部复现）。
- Python 侧未受影响且实测：全量 `pytest -q tests` **2025 passed / 8 skipped**（与第九十二批同数），
  因为多条门禁与测试是**按文本读 java 源码**的（`内部契约锚点：5 处` 等）；`static-checks.py` 全跑档
  exit 0，Java 徽章仍 713（本批没有增删测试）。
- 为什么这一批是**两笔提交**而不是一笔：`.git-blame-ignore-revs` 的内容是重排那一笔的 sha，
  sha 只能在提交后得知。第一笔纯格式化（这样 `git blame` 才有意义、也才好回退），第二笔是文档与忽略表。

#### 遗留（只登记不修）
1. **jacoco 棘轮与 CI 的错位**（本批新发现，需要选路）：要么给本地补上 docker 让 52 例 IT 真跑，
   量出"CI 口径"的覆盖率再决定下限；要么把补测当成一批正经工作（第三十九批的传统就是"补测后上调"）；
   下调下限不在选项里——那正是假门禁。**在选路之前，即使推了本批，`java` job 也只是从第一步红变成
   第二步红，不会变绿。**
2. 其余 404 个 java 文件本来就合格，但 `pom.xml` 没配 `ratchet`/`ratchetFrom`，所以"新代码没格式化"
   与"旧代码没格式化"在同一个门禁里不可区分——第九十批列过的 B′ 选项仍未决（要看 CI 的 checkout 深度）。
3. spotless 未接本地 pre-commit / `static-checks.py`，格式化仍只由 CI 挡（刻意如此：避免第二套口径）。
4. 32 条未引用 import 里 6 条集中在第七十四/七十五批改过的控制器（`EvalHarnessInternalController` 等），
   是"重构后没跑 apply"的习惯残留；本批不逐条追问出处，因为判据已覆盖到"删的都是未被代码引用的"。


### 第九十二批（2026-10-10：冻结摘要钉的是"这台机器的换行"，于是四个完整性门禁在 CI 恒红、在本地恒绿）

#### 结论（先给判定性质）
- 这条红**不是用例被改过**。取数是决定性的：`evaluation/suite/cases.jsonl` 的 **git blob 是 79,321 字节、0 个 CR**，
  本地工作副本是 **79,541 字节、220 个 CR**（220 行，每行一个）。manifest 与六份基线钉的是
  `b02b9dd3…`＝**CRLF 字节的**摘要，CI 里 `python -c …verify_suite_integrity` 读到的是 blob 原文（Linux runner
  默认 `core.autocrlf=false`）＝`15b0ea64…`。所以第九十批记录那条"实际 vs 钉住"时，两边都是对的——
  **同一次 CI 用 LF 算，本地用 CRLF 算**，这条门禁测的是检出平台的换行风格，不是"篡改没有"。
- 机制链完整：套件当年在 Windows 上由 `build_suite.py` 生成，`path.write_text(...)` 默认 `newline=None`
  会把 `\n` 翻译成本地换行 ⇒ Windows 产出 CRLF；`git add` 又按 `core.autocrlf` 把它归一回 LF 存进 blob；
  而 `.gitattributes` 里**没有 `*.jsonl` 规则**（只有 `.py/.json/.md/…`），于是检出侧由开发者决定。
  四个套件全部如此（`suite_bid` 11,542/27 CR、`suite_bid_it` 10,521/24、`suite_bid_construction` 10,480/24）。
- 判据先红：**21 failed + 2 errors**（钉值层 10 例、检出对称层 4 例、emit 层 4 例、规则同源层 3 例），
  实现＋再钉后 **25 passed**。其中 `test_verify_still_rejects_real_tampering` 从一开始就是绿的，
  它是邻居保护：规范化行尾**不等于**放弃篡改检测。

#### 改动（三层，缺一层就还有一个平台读到另一个哈希）
- `python-ai/scripts/eval_baseline.py`：新增 `suite_content_digest(data: bytes)`（CRLF→LF 后取 SHA-256，
  docstring 写明为什么），`verify_suite_integrity` 改用它，文档串从"byte-identical"改成"identical (modulo line endings)"。
- `python-ai/scripts/eval_retrieval_live.py:58`：`compute_cases_sha` 走同一 helper（顺带删掉该文件里已无用的
  `import hashlib`）。这条重要：纯检索直测自己写基线摘要，它若还按裸字节算，就和 CI 用的规则分叉。
- 四份 `build_suite.py` 的 `emit_cases(..., newline="\n")`：生成侧不再按平台翻译换行。
- `.gitattributes`：`*.jsonl text eol=lf` ＋ 注释说明这条为什么存在。
- **再绑定（不改内容）**：重跑四份 `build_suite.py` ⇒ `cases_sha256` 变为
  `15b0ea64… / 135114f4… / f23c8bf0… / 6d8a045b…`；四份离线基线按 CI 原样参数 `--update-baseline` 重钉。
  `retrieval_baseline.json` 与 `runtime_baseline.json` 只换绑定字段（本机没有 live 服务，指标**仍是
  2026-09-09 真机跑批的值**——用例内容未变，这是再绑定不是重测），old→new 逐条记在 `docs/CI_GATES.md`。

#### 验证
- **重建后的四份 `cases.jsonl` 与 `HEAD` 的 blob 逐字节相同**（`blob==wt` 四例 True），`git add` 之后
  暂存区对这四个文件**零变更** —— 这是"内容没动、只动绑定"的硬证据，不是靠人说。
- 离线基线的 diff 每份恰好 2 行（`suite_sha256` ＋ `generated_at`），**指标一位没改** ⇒ 离线轨确定性复现。
- CI 的步骤原样跑：四个 `Verify frozen suite integrity` 全打印 OK；四个离线门禁（含 `--fail-on-regression`
  与 bid 的 4 个 0.9 阈值）退出码全 0；`eval_bid_workflow.py` 退出 0。
- 判据：`tests/test_eval_suite_eol_binding.py` 25 例（11 个 `def test_`），其中 6/8 两组在 Windows 上红、
  在 Linux 上绿——**这正是它们要钉住的东西**：一条判据不该随检出平台变颜色。
- 全量回归：**2025 passed, 8 skipped**（= 第九十批的 2000 ＋ 本批 25 例），`tests/test_eval_baseline.py`
  等既有评测测试 94 例一起绿；`scripts/static-checks.py` 全跑档通过，计数 1853→**1864** 已同步
  README 徽章＋3 处正文、README_EN 徽章、`docs/ROADMAP.md:16`；`ruff check` 干净。
- 顺带结掉一处**文档声称漂移**（按"就地纠正＋写进手册记录"处理，不另立缺陷号）：
  `docs/CI_GATES.md:12` 与 `:156` 把共享模块写成 `python-ai/app/core/rag/eval_baseline.py`，而它在
  2026-08-29 已 `git mv` 到 `python-ai/scripts/eval_baseline.py`（`docs/CLEANUP_BACKLOG.md:34` 记着这次移动）。
  两处已改回真实路径并留下出处；`python-ai/evaluation/README.md` 的冻结段落补上"摘要按内容算"的精确说法，
  否则读者会以为纯行尾改动也会被捕获。

#### 遗留（只登记不修）
- **Nightly 的 runtime 基线首次会落空**：cache 键是 `runtime-baseline-<cases 哈希>-<run_id>`，前缀哈希换了 ⇒
  下一次定时跑 restore 不到旧基线，报告会是"无基线可对比"（门禁仍按绝对阈值走）。要恢复对比必须在真机上
  跑通一次并勾选 `update_baseline` 重冻结——本机没有 live 服务，这一条只能等 push 后在 runner 上结。
- `kb_manifest.json` **没有任何摘要钉扎**（grep 无 sha256）：知识库文档被改动不会触发完整性门禁，只有用例改动会。
  是否要给 KB 也上一道冻结，取决于"文档改动是否需要显式再冻结仪式"，本批不决定。
- 新 `.gitattributes` 规则**不会自动改写既有工作副本**（smudge 只在检出时生效）。本机已由 `build_suite` 重写成 LF，
  其他机器要 `git checkout -- <file>` 或重克隆才一致——这也是把摘要做成行尾无关的第二个理由。
- CI 与本地的其余平台分歧本批一条没碰：`Errno 24` fd 泄漏、`TestRunnerIntegration` 的预拉取 tag 口径、
  `test_timeout_enforcement` 的错误类别、`pip-audit` 29 漏洞无策略、java spotless 的 128 文件（仍等选路）。


### 第九十一批（2026-10-10：frontend 重新能 build —— 12 个死导入，加一个把 `apps` 漏掉的分组联合类型）

#### 结论（先给判定性质）
- 这一批**不新增门禁**。`npm run build`（= `vue-tsc -b && vite build`）本来就是 CI `frontend` job 的既有步骤，
  两类错误它都自己抓出来了：TS6133（未使用的图标导入）和 TS2322（`group: 'apps'` 赋不进
  `'use' | 'personal' | 'build' | 'admin'`）。所以本批的判据就是"红变绿"，不需要另立断言——
  给编译器已经守着的契约再加一道文本门禁，属于重复门禁。
- 但第二条的**修法**要先辨方向：报错看起来像"5 个 `apps` 项写错了"，实际是联合类型漏了一个值。
  三处取数后才定性——`menuGroups`（`MainLayout.vue:147-152`）渲染的 key 恰是 `use/apps/build/admin`，
  27 个菜单项的 `group:` 分布是 use 7 / apps 5 / build 8 / admin 7，`personal` **一次都没被用**。
  也就是说改联合类型（补齐 `apps`、删掉 `personal`）让类型与渲染集合相等；反过来改那 5 项会让它们
  **落到一个没有分组标题可渲染的 key 上**——`menuGroups` 只 filter 这四个值，第五个值的项会静默消失。
  隐身比报错难发现得多，所以方向不能反。

#### 改动
- `hfusionhub-frontend/src/pages/dashboard/Index.vue`：删 12 个只出现在 import 行的图标
  （Cpu/Wrench/Fingerprint/User/StickyNote/DollarSign/Cable/Rocket/GitBranch/Megaphone/Package/CreditCard），
  逐个核过全文件出现次数恰为 1，即删的不是"模板里还在用"的东西。
- `hfusionhub-frontend/src/components/layout/MainLayout.vue:90-91`：`group` 联合类型
  `'personal'` → `'apps'`，并加一行契约注释（"必须与 menuGroups 渲染的 key 同集合：多一个值 = 该项没有分组标题可渲染，直接隐身"）——
  这句是 WHY，不是复述类型。

#### 验证
- `vue-tsc -b` 退出 0；`npm run build` 退出 0（`✓ built in 30.09s`）；`npm run test` **101 passed（15 文件）**，
  与改动前同数，说明删导入没有碰到任何被测试引用的东西。
- 三集合核对（手工，写在这里而不是加门禁）：TS 联合 4 个值 == `menuGroups` 渲染 4 个 key == 菜单项实际用到 4 个值。
- 本批不动 Python/Java 面，计数不变：全量 pytest 见第九十批那条（2000 passed / 8 skipped）。

#### 遗留（只登记不修）
- `nav.groups.ops` 与 `nav.groups.personal` 在 `src/locales/zh-CN.ts:11-12` 和 `en-US.ts:11-12` 都还在，
  但没有任何分组渲染它们——**孤儿文案 key**。没有任何门禁会抓它（未使用的 i18n key 不是类型错误），
  也不造成行为问题，故只登记。要不要顺手删，取决于"是否预留将来加 ops 分组"，这个判断归用户。

### 第九十批（2026-10-10：CI 的 P0 容器门禁在"跑干净"时必然红，compose 校验缺 4 个变量 —— 两处都是 CI 自己的错）

#### 结论（先给判定性质）
- 本批修的两条都不是产品缺陷，是**门禁脚本自己写错**：一条在"套件一条 skip 都没有"这个理想形态下必然判红，
  一条在校验第一个文件时就死在半路。两者都只影响 CI 是否能给出结论，不影响运行时行为。
- 死因不是猜的，是**把 workflow 里那段 shell 原样抽出来在本地真执行**得到的（`python-ai/tests/test_ci_workflow_gates.py`
  的 `TestContainerGateStepExecution`，用 `python` 桩喂五种形态）。这一步之前不存在，也正是它把第二条缺陷挖出来的：
  我先"看着对"地写了 `pytest_status=${PIPESTATUS[0]}` + `gate_status=${PIPESTATUS[2]}` 两行分开取，
  实测 `PIPESTATUS` 会被**任何**后续命令重置（第一条赋值自己就把它清了），于是 `gate_status` 取空、
  `[ "$gate_status" -ne 0 ]` 报 "integer expression expected"，**有 6 个 skip 也判绿**。
  只查文本的断言永远看不见这条——它语法合法、语义正确、跑起来哑火。
- `pipefail` 那条同理：`skipped=$(… | grep -oE '[0-9]+ skipped' | …)` 在零命中时 grep 返回 1，pipefail 让赋值失败，
  `set -e` 打死步骤。语义正好反了。改成独立 helper 不是为了复用，是为了**能被执行**（workflow 里的一段字符串没法真跑）。

#### 改动
- `scripts/ci/check_container_skips.sh`（新）：stdin 接 pytest 输出，只统计**汇总行**（`-rs` 的逐条原因行里也含
  "1 skipped"，按行全查会重复计数）。退出码契约 0=有汇总行且 0 skip / 1=有 skip（把条数打出来）/ 2=读不到汇总行
  （采集阶段就崩不能当成"0 skipped"放过去）。消息一律 ASCII——本批实测踩过一次：含破折号时宿主 GBK 解码失败，
  `proc.stdout` 静默变成 `None`，退出码正确而判据其实什么都没读到。
- `.github/workflows/ci.yml`：容器门禁步骤改成 `set +e` + `tee /dev/stdout` + helper，并用
  `statuses=("${PIPESTATUS[@]}")` 一次性取整组状态再下标，先报 pytest 自己的退出码、再报门禁的。
  dev compose 校验步骤补 4 个变量（`PYTHON_AI_INTERNAL_TOKEN`/`CALLBACK_SECRET`/`ADMIN_PASSWORD`/`PLUGIN_RUNNER_TOKEN`，
  全沿用既有 `ci-test-*` 良性形态，无真实密钥）；monitoring 步骤补 `MYSQL_ROOT_PASSWORD`
  （`GRAFANA_ADMIN_PASSWORD` 自带 default，按"只补缺的"原则不动）。
- `python-ai/tests/test_ci_workflow_gates.py`（新，11 个 `def test_` / 19 例）：`TestComposeValidateEnvPairing`
  从 compose 文件本身正则取 `${VAR:?}` 需求集，逐步骤核对"需求⊆供给"和"供给⊆需求"两个方向——**不重抄变量名**，
  否则第四份手抄又会漂。`TestContainerSkipGate` 真执行 helper。`TestContainerGateStepExecution` 真执行步骤体。
- `docs/CI_GATES.md`：新增「非评测门禁：CI 自己的两处自伤」，含逐文件需求-供给对照表、本地复现 CI 条件的配方
  （`--env-file /tmp/empty.env`，因为本地按项目目录自动加载 `.env` 会把这条红掩掉）、0/1/2 契约、PIPESTATUS 那段
  实测经过，以及规则"**凡是 CI 步骤里带 shell 逻辑的，都要有一段把它真跑一次的判据**"。

#### 验证
- 红→绿：helper 的 6 例先对旧的内联语义全红；步骤执行 5 形态（干净跑→0、有 skip→1、pytest 失败→沿用它的码、
  读不到汇总行→2、pytest 崩且无汇总行→3）在改成数组取 PIPESTATUS 前，"有 skip"那条实测判绿。
- 漂移注入 5 次各自判红（删 helper 调用、去掉 `| bash`、把数组取法改回分开取、dev 步骤少喂一个变量、
  供给一个 compose 不认的变量），跑完用改前原文写回并核 sha256。
- 本地真命令复现：`docker compose -f docker/docker-compose.yml --env-file /tmp/empty.env config -q`
  改前 exit 1（`required variable ADMIN_PASSWORD is missing a value`），改后 exit 0；monitoring 同法复现与结清。
- 全量回归：**2000 passed, 8 skipped in 495.15s**（= 第八十九批的 1981 ＋ 本批 19 例，无一条既有测试受影响）；
  `scripts/static-checks.py` 全跑档通过，计数按用例数 1842→**1853**，已同步 README 徽章＋3 处正文、README_EN 徽章、
  `docs/ROADMAP.md:16`。
- `core.fileMode=false`，helper 的可执行位不会进 git；CI 用 `bash "$GITHUB_WORKSPACE/scripts/..."` 调用，
  与仓内其余 `.sh`（如 `scripts/backup-mysql.sh`，同样 100644）一致，故不加 `--chmod=+x`。

#### 遗留（只登记不修）
- **java `spotless:check` 不是"一个文件"**：CI 日志被截断时只显式列出一个，原文写着 "Violations also present in
  127 other files"。本地在 `maven:3.9-eclipse-temurin-17` 里实测：`spotless:check` 报 **128 / 532 个 java 文件**不合格，
  `spotless:apply` 对这 128 个是 **+1383/−1264** 行。补丁已生成并留档，且证明格式化后仍能编译打包
  （`docker build` 复用缓存的 `dependency:go-offline` 层 → 镜像 `hfusionhub/java90:fmt`，jar 89,704,424 字节）。
  **这不是清理而是全仓改写的决策**（可加 `.git-blame-ignore-revs`，本仓目前没有；或改 `ratchetFrom` 只查变更文件，
  但那要 CI 的 checkout 深度，本机验证不了），故未动，等用户选路。
- CI 平台与本地的其余分歧仍只登记：`python` job 的 6 个 `TestRunnerIntegration`（预拉取的 tag 与测试的检测口径不一致）、
  `test_plugin_security.py` 里的 `[Errno 24] Too many open files`、`test_timeout_enforcement` 的错误类别、
  冻结套件 `cases_sha256` 实际 `15b0ea64…` 与基线钉的 `b02b9dd3…` 不一致（需重建 manifest）、
  `pip-audit` 29 个漏洞/5 个包无忽略策略。本批只把"CI 自己写错"的两条清掉，没有碰这些。
- 判据的可移植边界写清楚：`TestContainerGateStepExecution` 喂的是桩输出的 pytest 文本，证的是**那段 shell 的判定逻辑**，
  不是 GitHub runner 上的真实容器套件；真实形态只能等下一次 push 后看 runner。2026-09-22 那批旧失败日志已不可下载，
  那些 run 的具体死因未经核验，不写成结论。

### 第八十九批（2026-10-10：java 镜像第一次真实构建就通了，"java 写、python 读"补齐成双向哈希 —— 顺带发现 10001 从来不是一个字段）

#### 结论（先给判定性质）
- 这一批**不动生产代码与配置**，只结第八十四～八十八批一直挂在"未收口"上的两笔账：
  `deploy/Dockerfile.java` **自引入至今第一次真实构建**（未改一行、一次通过），以及
  第八十五批那条"同路径互见"契约唯一没证的半条——**java 写、python 读**。两者都在真 docker 上做到，
  并且判据不是"`touch` 成功"这种弱断言：同一块命名卷、写与读分属两个镜像，**读回的 sha256 与写入侧逐条相同**，
  再让 java 容器读回 python 落的文件（C4），最后用 python 的**生产入口** `POST /api/parse`
  去认 java 写的那个绝对路径（C3）——它不再回 10001，而两个负例（卷外真实文件、卷内不存在的文件）
  仍回 10001，证明放行的是"同一个文件"而不是把围栏放宽了
- 构建侧一个此前只有文档口径的事实拿到了数：Alpine 的 `addgroup -S -g 10001 && adduser -S -u 10001 -G …`
  与 `mkdir -p /app/uploads` 在真实基镜像上 **DONE 0.3s** 通过（第八十四批写"首次构建即验收"，本批即那次验收）。
  运行身份实测 `uid=10001 gid=10001`，空命名卷挂上后 `/app/uploads` 属主即 10001（印证"属主来自镜像内容"），
  而 `documents` 这一级**不在卷里**，由 java 侧 `mkdir -p` 建出——正是第八十四批补这条 mkdir 的理由
- 实测顺手否掉一句自家文档的措辞：`code 10001` 在线上**不是响应字段**。`validators.py` 抛的是
  `HTTPException(400, detail={"code":10001,…})`，而 `exception_handlers.py:43` 用 `str(exc.detail)` 压成字符串，
  于是信封是 `{"code":400,"message":"{'code': 10001, …}"}`。按"不做假门禁/口径跟着事实走"的规矩就地改文档，
  不开新缺陷号：今天没有任何消费方按 `code` 分支（全仓 java 只有 `OidcService.java:160` 出现过 `"code"`，与此无关），
  所以这是**契约债**而不是活故障，要不要统一 401/403/400 三类信封是接口变更，本批不动

#### 改动
- 仅 `docs/PRODUCTION_OPS.md`：10.2 标题改为"第八十八批 python 侧 + 第八十九批 java 侧与跨服务互见"，
  新增 java 构建账（568.5s go-offline / 21.3s package / 89,704,407 字节全新 jar / `#12` 身份层 0.3s 通过）
  与 C1–C4 结果表，新增那条信封实测；把"这两条本批都没做""java 镜像从未构建"改成已测，
  并写清**还差的两级**（整栈 compose 的 `exec` 命令对、一次真实全链路解析）；10.3 首条从"配置层对齐 + 单侧可写"
  升级为"镜像层成对"，新增"业务码不可机器读"一条；10.3 慢网那条补上 java 侧同批无需该调整，
  同时点明 `go-offline` 带 `|| true`——它失败也不会让构建失败，真实判据是 `#14 package` 的退出码；
  10.4 第 3 步就地标注 10001 在线上是 message 文本；上线清单的卷可写性项同步为"java 侧已实测、集群侧与整栈未实测"

#### 验证
- 构建（未修改的 `deploy/Dockerfile.java`，context 与 compose 一致为 `java-backend`）：退出 0，
  `#10 [build 4/6] mvn dependency:go-offline` DONE 568.5s → `#13 COPY src/` → `#14 mvn -DskipTests package` DONE 21.3s
  → `#15 COPY --from=build /app/target/*.jar app.jar` → naming done；镜像内 `app.jar` 89,704,407 字节（全新构建，
  不是宿主 `target/` 那份 9 月旧 jar），`/app/uploads` 属主 `hfusionhub`
- 跨服务（`hfusionhub-java:b89` + `hfusionhub/python88:rc`，同一块 `b89-shared-uploads`）：
  C1 写 `.probe-b89`(32B, `9c09c7e6…`) 与 `b89-cross.txt`(82B, `a2cc7689…`) ⇒ C2 python 侧逐条同哈希读回并写
  `.from-python`(`c53384b0…`) ⇒ C4 java 侧 `cat` 到同一哈希；C3 服务带 `DOCUMENT_STORAGE_ROOT=/app/uploads/documents`，
  正例两次 **HTTP 200**（`Document parsing started in background`），负例两次 **400 code 10001**；
  探针自带 `/proc/self/mounts` 自证（第八十八批那条假绿规矩）
- 文档锚点复核：`DocumentServiceImpl.java:64`、`:528-529`、`VectorizationServiceImpl.java:730`+`:737`
  （`Map.entry("file_path", document.getFilePath())`）全部对得上，探针请求体按 java 实发字段对齐
  （`document_id`/`file_path`/`file_type`/`index_version` 四个必填）
- `static-checks.py` 全跑档：改文档前 exit 0（基线）、改后仍 exit 0；读 ops 文档的测试文件
  `test_eval_retention` + `test_upload_path_contract` + `test_container_identity` **49 passed**
- 全量回归（汇总行取自文件而非管道，teardown 的 MilvusLite 噪声会盖掉它）：**1981 passed, 8 skipped in 183.02s**，
  与第八十八批收口时同数；`--collect-only` 1989 = 1981 + 8 skipped，两条独立口径一致
- 本批无新增 `def test_`（纯实测＋文档），文档测试计数不动

#### 遗留（只登记不修）
- **整栈未跑**：10.2 末尾那对 `docker compose exec` 要 fullstack 档（mysql/redis 一起起），本机一次都没起过整栈；
  本批是在镜像层用等价命令证的，"起得来的栈里"那一层仍缺
- **C3 只到同步校验**：响应 200 后的后台解析在探针环境里没有向量库，容器日志报
  `pymilvus … AllocTimestamp … NotImplementedError`。一次真实文档全链路（上传→解析→回调）仍未做
- **错误信封把业务码压成字符串**（见结论第三条）：改它要同时决定 401/403/400 的统一形态，是接口变更
- **`mvn dependency:go-offline -q || true`** 让"依赖预热"这步永远不可能让构建失败，真正的门在 `package`；
  是否去掉 `|| true` 属构建脚本决策
- java 侧构建环境事实未进仓库：宿主 `mvn` 不可用（plexus `ClassNotFoundException`）、`~/.m2` 无 mirror，
  所以 CI 之外没人能脱离 maven 基镜像构建 java
- 前批遗留继续挂着：CI 从未跑（9 处 `pip install -r`）、锁仍是单平台产物、runner lock 仍被 sed 剥掉 `[standard]`、
  OTel 在 CI 永久 `importorskip`、judge 缓存淘汰、`UPLOAD_DIR` 键、plugin-runner uid 未进门禁、
  mysql/etcd/milvus/redis 无 pod securityContext、helm 未在 v4 复渲

### 第八十八批（2026-10-09：Docker 三项实测拿到了引擎，第一次真跑构建就把镜像装不出来 —— 同一个根因的三种形态）

#### 结论（先给判定性质）
- 待办是第八十四～八十七批反复写"本机无 docker 引擎，只到渲染层"的那三笔账。引擎起来后**第一次真实构建就失败**，而且失败的不是新东西：`python-ai/requirements.txt` 是 `pip-compile --generate-hashes` 在 Windows 宿主上**不带 `--python-platform`** 编出来的，于是它有三种"只在别的机器上发作"的形态，开发机一条都看不见——① 上游只在 Windows 上需要的包（`pywin32`、`win32-setctime`）没有 marker ⇒ linux 上 `from versions: none`；② 锁尾三条手工追加的裸 OTel pin ⇒ 任一条目带 `--hash=` 时 pip **自动**进入 `--require-hashes` 并整体拒绝裸 pin（任何平台都失败）；③ 与①同根、方向相反：`uvicorn[standard]` 的 `uvloop` 带 `sys_platform != 'win32'` marker，pip-compile 在 Windows 上按 marker 为假**直接跳过**，锁里从来没有它（另外 7 个 extra 依赖在 Windows 上不过滤，全进了锁），Linux 侧于是死于"extra 自带的 `>=` 规格不是 `==`"。所以本批不是"补个测试"，是**已 ship 的镜像构建必然失败**，且 prod 锁与 CI 的 9 处 `pip install -r` 同机制
- 第三条只能靠**读上游 metadata**发现：它在 diff 里不存在（不是被删，是从来没出现过），"在另一个平台编译一次"也不会报——`pywin32` 那条同样是编译产物的一部分。据此把反向清单（`NON_WINDOWS_ONLY_PINS`）写进门禁，与原有的 `WINDOWS_ONLY_PINS` 成对，新增此类依赖时两侧一起同步
- 顺带纠正一条错误的历史：`b69b0178` 撤掉 `sed 's/uvicorn\[standard\]/uvicorn/g'` 的前提是"`--require-hashes` 已不再使用"，这个前提是**错的**（①②都建立在它自动开启之上），它 commit message 里"为生产恢复事件循环"那句话因此从未成立过。撤掉之后这份 Dockerfile 再没被真实构建过，洞藏到本批
- **OTel 的归属选"移出锁"而不是"补进锁"**（D 方案）：补哈希要求它的 closure（`opentelemetry-proto`/`-semantic-conventions`/`-exporter-otlp-proto-common`/`googleapis-common-protos`/`deprecated`）全部进锁，那是一次**含 arq/redis 归属决定**的完整重编译，不该夹带在本批；移到 `deploy/Dockerfile.python` 与 arq 同侧显式钉版，代价按变量名写在 `requirements.in` 里并留一条测试钉住"OTel 只能有一处声明"。版本不能停在 1.29.0——其 `opentelemetry-proto` 要 `protobuf<6.0`，与锁里的 `protobuf==7.35.1`（`# via pymilvus`）冲突；1.45.1 放宽到 `<8.0`。**连带后果如实登记**：OTel 只在镜像里 ⇒ CI 环境永远没有它，`TestOtelTraceparentPropagation` 必须显式 `importorskip`（装了 12 passed，假装没装 10 passed + 2 skipped），否则 dev 锁 marker 一修好，CI 第一次走到 pytest 就红在那里
- 一个**看起来通过、其实没验证**的陷阱（写进 §10.2）：Git Bash 的 MSYS 在 spawn 外部程序时把形如 `key=/path` 的参数值改写成宿主路径，实测 `-e EVAL_HARNESS_DATA_DIR=/app/eval-harness` 进容器变成 `D:/college/Git/app/eval-harness`——POSIX 下这是相对路径 ⇒ 产物落进容器可写层，而 retention 探针照常打印"删了 3 个、跳过 0 个"。修法除了宿主侧 `MSYS2_ARG_CONV_EXCL='*'`，更根本的是**让探针自证**：目录必须绝对、且能在 `/proc/self/mounts` 里查见该挂载，否则 `SystemExit(2)`

#### 改动
- 两份锁（`python-ai/requirements.txt`、`requirements-dev.txt`，**必须一起改**，dev 锁由 `requirements-dev.in:4` 的 `-r requirements.in` 同源编译）：`pywin32==312`／`win32-setctime==1.2.0` 补 `; sys_platform == "win32"`；`uvloop==0.23.0` 整条加入（marker `sys_platform != "win32" and != "cygwin" and platform_python_implementation != "PyPy"` ＋ 该版本 61 个文件（60 wheel + sdist）的 sha256 升序，照 pip-compile 在 Linux 上会产出的形状；marker 必须留着，否则生成锁的那台 Windows 宿主自己装不上）；prod 锁尾三条裸 OTel pin 删除；两份文件头各加一段 provenance——**这两条不是编译产物，直接对现锁重编译会把它们抹掉，那不是修复而是把同一个失效方式放回锁里**
- `python-ai/requirements.in`：写明 OTel 刻意不在此处、为什么，以及"改这里之前先完成那次重编译"的前置条件
- `deploy/Dockerfile.python`：OTel 三条 `pip install` 显式钉版（与 arq 同形），注释更正为"`--require-hashes` 不需要谁显式开启，3cd5303 的 sed 绕的正是它"
- `scripts/static-checks.py` 新增检查 11 `check_requirements_platform_markers()`（＋ `--requirements-markers`，并入默认全跑档）：Windows-only 条目带 marker、**非 Windows 专属条目存在且 marker 排除 win32**、锁的哈希形态一致；纯文本核对，不需要 docker 或网络。同批修掉一个**门禁与测试共同的盲点**：`_lock_pins` 的包名正则不含 `[` ⇒ `name[extra]==ver` 形态两条锁都看不见（prod 实际 77 条只数出 74、dev 102 只数出 97），一个手工追加的无哈希 `foo[bar]==1.2.3` 恰好落在盲点上
- 新增 `python-ai/tests/test_requirements_platform_markers.py`（28 个方法 / 34 例）：三条规则、两份锁一起核、`[extra]` 形态必须被解析出来且两套解析器条目数一致、uvloop 的哈希集覆盖 `python:3.11-slim` 实际挑中的那个 wheel、钉住的版本落在 extra 自己的 `!=0.15.0,!=0.15.1,>=0.14.0` 里、OTel 只有一处声明、"两处都没有 ⇒ 追踪静默关闭"、构建期的 sed 绕法拒绝再出现
- `tests/test_trace_middleware.py`：OTel 传播用例加 autouse `importorskip` 前提（上一条连带后果的落点）
- 文档：`docs/PRODUCTION_OPS.md` 新增 **§12 依赖锁的可安装面**（三条规则的表、PyPI 原文 marker、历史线 3cd5303/b69b0178、解析器盲点、CI 推断段并明确标注"没有实测"、§12.1 两个锁外钉版为什么在锁外、§12.2 防回潮含"第三条没有便宜的复现命令"、§12.3 五条未收口）；**§10.2 由"只到渲染层"改写为实测事实**（构建四次、M0/M1/M2/M4 四条结论、MSYS 陷阱）；§10.3 的"没做过实测"按真实边界收窄为"java 镜像从未构建 ⇒ 单侧可写已证、互见未证"，并新登记慢网首次构建的超时面；§11.4 的"没有做过一次真实评测"补上已跑通的那半条（真卷写产物 → 换新容器读回）；`docs/python-ai.md` Setup 补反向规则；`docs/PROJECT_TOUR.md` 门禁十项→十一项；README/README_EN/ROADMAP 计数同步

#### 验证
- 红→绿**两轮**：21 例先对①②全红（现锁两条没 marker、锁尾三条裸 pin），改锁后绿；③暴露后补 13 例（含解析器盲区那两条）再次先红后绿，最终该文件 **34 passed**
- 真实构建四次，前三次各死在一个缺陷上：`#9 2582.1 ERROR: In --require-hashes mode … uvloop!=0.15.0,!=0.15.1,>=0.14.0`（①修好后走到 ③）、`#9 2964.6 TimeoutError: The read operation timed out`（锁已对，宿主网络面：23–60 kB/s，pip 默认 15 秒读超时掐死在 4 MB wheel 的 0.3 MB 处）。**这三次失败各自都要一整次构建才有反馈**（collect 2000–3000 秒），是 §12.2 里"第三条没有便宜的复现命令"的由来。第四次（验证副本 `Dockerfile.validate`）成功：`#9 2329.3 Collecting uvloop==0.23.0 (from -r requirements.txt (line 1472))` → `#9 2443.2 Successfully installed … uvloop-0.23.0 …`，随后 `arq-0.26.3 redis-5.3.1`、`opentelemetry-api-1.45.1` 各成一层的日志都在 scratch
- 四项运行时实测（`hfusionhub/python88:rc`，linux/amd64，三个空命名卷）：**M0** `User=hfusionhub WorkDir=/app`，`protobuf` 仍是 `7.35.1`（1.45.1 没有把它拖下去）；**M1** 三个挂载点 `uid=10001 gid=10001 mode=755` ＋ `WRITE_OK` ＋ 子目录 `mkdir` 成功（第八十四批"钉号 + 建目录"至今的第一次实证）；**M2** 真卷上 6 组由 `new_run_file`+`save_report` 写出的产物，`prune_runs(keep=2, protect=最新)` 删最旧 3 组及其 `_report.md`、`skipped=[]`、剩 3 组 = keep 2 + protect 1（`protect 不占名额`这条首次在真实文件系统上成立）；**M3** 换新容器挂同一块卷，`GET /runs` 列出 3 条含 `size_bytes`/`modified_at`，`GET /report?run_file=…` 取回正文，缺 token 回 **401**；**M4** root 属主的旧卷：写 `PermissionError [Errno 13]`，`prune_runs(keep=0)` **不抛**、两条记进 `skipped` 并各打一行告警 ⇒ 10.1 的一次性 chown 是有依据的
- 回归：全量 pytest **1981 passed / 8 skipped**（1947 ＋ 本批 34 例）；`scripts/static-checks.py` 全跑档通过（11 项）；`ruff check app/` 干净；计数按**用例数**口径 1813→**1842**，已同步 README 徽章＋3 处正文、README_EN 徽章、`docs/ROADMAP.md:16`
- **验证上限（不假装做过）**：CI 一次都没跑过（9 处 install 点的结论是从构建日志机制**推出来的**）；helm 侧无集群，仍是渲染层证据；`Dockerfile.java` 从未构建 ⇒ "java 写、python 读"未证；验证用的 `Dockerfile.validate` 与被验收的 Dockerfile 有两处已知差异（`PIP_DEFAULT_TIMEOUT=120`、cache mount 替 `--no-cache-dir`），生产那份在慢网上的首次构建仍未验证；探针与构建日志都在仓库外的 scratch，**未入库**，所以本文里的秒数与哈希无法从仓库复现

#### 遗留
1. **CI 上的结果仍未验收**：两条锁的 marker 都修了，但 `ci.yml:155/178/215/327`、`e2e.yml:61/200`、`eval-nightly.yml:76/168`、`plugin-security.yml:21/164` 要等下一次真实 run；本批只有本地镜像证据
2. **锁仍然不是跨平台锁**：marker 只补在两个 Windows-only 条目加一个非 Windows 专属条目上，其余条目仍是单平台编译产物。正解是 `--python-platform linux` 重新生成，而那次重编译必须同时决定 arq/redis 的归属（对照实验：原样 `.in` 编译成功但产物没有 OTel，并新增 `arq==0.28.0` + `redis[hiredis]==5.3.1`，与现锁 diff 174 行）
3. **runner 那份锁没跟上 extra**：`docker/Dockerfile.plugin-runner:12` 仍在 sed 剥 `uvicorn[standard]` ⇒ runner 容器没有 uvloop/httptools；与修好的锁兼容，但"runner 不跑 uvloop"写在构建命令里而不是锁里
4. **OTel 在 CI 上永久跳过**：追踪行为的真实执行位置只有镜像内，没有 CI 或镜像内的执行记录；接进去要在 CI 里真构建并真跑 pytest
5. **java 镜像从未构建**：`Dockerfile.java` 的 `adduser -u 10001` 与 `/app/uploads` 创建是按 Alpine 参数形态写的，第一次真实构建即是验收（§10.3）
6. **慢网首次构建的超时面没进生产 Dockerfile**：`--no-cache-dir` ＋ pip 默认 15 秒读超时在 23–60 kB/s 前会随机死在大 wheel 中途；是否收 `PIP_DEFAULT_TIMEOUT` 取决于构建环境，本批不动那份文件
7. judge 缓存无淘汰、`UPLOAD_DIR` 键空转、plugin-runner 镜像 uid 未进门禁、第三方镜像无 pod securityContext 等承第八十五～八十七批未收口清单

### 第八十七批（2026-10-08：产物上了卷之后新的失效方式变成"卷被写满"，而本仓两个清理函数都没有调用方）

#### 结论（先给判定性质）
- 第八十六批 遗留 3（"评测产物没有清理策略"）本批收口。三个口径候选（数量 / 天数 / 字节）与三个执行点（run 收尾 / 后台节拍 / 运维端点）里取"**数量 ＋ `/run` 收尾**"，依据不是偏好而是**本仓自己的证据**：`checkpoint.prune`（`app/core/agent/checkpoint.py:220`）与 `approval_store.cleanup_expired`（`app/core/agent/approval_store.py:153`）按符号名扫 `app/`＋`scripts/` 是**零调用方**，全仓唯一真在跑的清理是 `audit.py:315/337` 那种挂在自己写路径上的。做成"等人调的端点"大概率是第 3 个死函数；做成后台任务则要多一个常驻线程和它的关停口径（第八十一批刚为关停排空付过一次代价）
- 一次**先取证再判断**的转向：原本预计"删掉 python 侧文件会让 Java 的 `eval_harness_runs` 行悬空、界面点进 404"。取数否掉了后半句——该表在仓内**没有任何读点**（`EvalHarnessRun`/`EvalHarnessRunMapper` 只被 `EvalHarnessInternalController.java:81` 的一处 insert 引用；前端 `rag/Index.vue:452` 打的 `/rag/evaluation-runs` 走的是 python 侧 SQLite store，是另一张表）。删除对 UI 也无损：下拉数据来自 `/runs` 现列目录（`Index.vue:277`），文件没了名字就消失。所以留下的只是一行**无人读的聚合摘要**，本批**选择不删**（跨面改动，且现在没有任何读者会因它报错），代价按变量名写进 §11.3
- 顺登记一条同根的：`V79__eval_harness_runs.sql:23` 在 `run_file` 上有 `uk_eval_harness_run_file` 唯一索引，而 `runner.new_run_file` 的时间戳是**秒级** ⇒ 同 label 同秒的两条 run 会让 Java 侧 insert 直接撞键。这是第八十五批"秒级命名可撞"的另一侧，本批只记不修

#### 改动
- `app/utils/config.py` 新增 `EVAL_RETENTION_KEEP`（默认 50，宿主与容器同一默认）
- 新增 `app/core/eval_harness/retention.py`：`prune_runs(runs_dir, reports_dir, keep=None, protect=None)`。**淘汰顺序复用 `runner.list_run_files`** ⇒ "被删的那条"与"控制台认为最新的那批"同源，不会删掉界面还在列的文件；一组 = `<label>_<ts>.jsonl` ＋它派生的 `_scores.json`/`_report.md`/`_slides.html`（与 score/report/slides 三处 `save_*` 的命名一一对应）；**无主的派生产物一并删**（对旧 run 手动 `POST /score` 会重建报告，只按 run 文件淘汰就永远清不掉）；`protect` 不占 `keep` 名额 ⇒ 盘上最多 `keep+1` 组，`keep=0` 的含义是"只留本次"；`FileNotFoundError` 归为"对手副本先删的"（不计故障也不冒领），其它 `OSError` 记进 `skipped` 并告警；**不建目录**——挂载点属主归镜像（第八十四批那条规则）
- `app/api/eval_harness.py`：`start_run` 在 `save_report` 之后、Java 摘要回调之前 `await asyncio.to_thread(retention.prune_runs, runner_mod.default_runs_dir(), REPORTS_DIR, protect=run_file.name)`（同步 stat+unlink 不压事件循环，沿用第 54/81 批口径），整段 `try/except` 只告警——**结果已落盘，清扫失败不能把一次成功的评估判失败**。**`/run` 的响应体不加键**（`docs/api.md` 与前端 `rag.ts` 类型零改动），保留读数走日志行 `[eval-harness] retention keep=… runs=… artifacts=… skipped=… dir=…`
- **部署面零改动**：compose / prod compose / helm 三档都不设这个键，默认 50 全局生效。这与第八十六批"落点必须逐档配"相反且是有意的——那是**路径**（不配就落错地方），这是**策略**（不配也有合理值），放宽的责任在运维调 `EVAL_RETENTION_KEEP`，不在 chart
- 文档：`docs/ENVIRONMENT.md` 新增 `EVAL_RETENTION_KEEP` 行（含 `keep=0` 语义与"三档拓扑都不必配"）；`python-ai/.env.example` 补键 ＋"为什么不是端点"；`docs/PRODUCTION_OPS.md` 新增 **§11.3 保留口径**（口径、与 `/runs` 同源、触发点、protect 语义、孤儿规则、两副本并发清扫的预期行为），并如实列出**三处不在这个口径内**的（judge 缓存不受本口径管理、Java 摘要行不删、没有按字节/按天数的上限）；原 §11.3 未收口顺延为 **§11.4**，实测命令补一条 retention 日志行作为可核对证据
- 更正第八十六批的两处文档账：验证里"相邻五套 273 passed"按实测改 **274**（同一组文件重跑即暴露）；遗留 1 的 §11.3 锚点随本次插入改指 §11.4，遗留 3 标注已由本批收口

#### 验证
- 红→绿：新 `tests/test_eval_retention.py` **21 例**首跑**全红**（18 failed ＋ 3 例 fixture error，红因是 `retention` 模块不存在与 config 缺键），实现后 21 passed
- 两条是实现期暴露的自有缺陷，不是先想清楚再写的：① env 覆盖用例最初用 `importlib.reload(app.utils.config)`——reload 把模块属性 `config` 换成**新类**，而 app 代码在导入期就绑死了旧类 ⇒ `/run` 的四个用例集体 **401**（conftest 把 `INTERNAL_API_TOKEN` 设在旧类上），且"钉住默认值"的用例其实在读一份生产代码不再读的对象。改成子进程探针，理由写进该用例 docstring。② `flaky` 替身里 `retention._remove(path)` 在 patch 之后指回自己 → RecursionError；改为先取原函数引用再委托
- 语义钉子（三条非显然，各有用例）：protect 不占名额（`keep+1` 上限）、`keep=0` 是"只留本次"而不是"全删"、淘汰顺序来自 `list_run_files` —— 第三条的用例刻意让**真实 mtime 与伪装 listing 相反**，否则"复用了控制台顺序"这句话永远证不出来
- 容忍面各有独立用例：ghost 文件（对手副本先删）不进 `deleted_*` 也不进 `skipped`；`OSError` 进 `skipped` 且不抛；两个目录都不存在时空操作**且不建目录**
- 接线形状：`test_run_does_not_await_the_sweep_on_the_event_loop` 要求源码里出现 `to_thread(retention.prune_runs`；`test_run_prunes_after_its_own_artifacts_are_written` 用替身记录真实调用序列，要求清扫排在 `save_report` 之后（产物没写齐就扫会把它们当孤儿）、`protect` 是本次文件名、**`keep` 不在端点里写死**
- CI 面核对过本批不会打疼自己：`.github/workflows/eval-nightly.yml:142` 每次只跑 1 个 run、workspace 全新，`:151` 上传 `python-ai/data/eval_harness/reports/` 时不可能已凑满 50 组触发淘汰
- 回归：全量 pytest **1947 passed / 8 skipped**（1926 ＋ 本批 21 例）；相邻六套（评测落点 + 保留 + eval_harness + API 契约 + 容器身份 + 路径契约）**295 passed**；部署面三套（checkpoint / evaluation_runs / plugin_audit）**73 passed**；`ruff check app/` 干净（一条 I001 由 `--fix` 收：`retention` 并进 `from ..core.eval_harness import EvalSample, MetricResult, retention`）；`scripts/static-checks.py` 全跑档通过（10 项，本批**无新门禁**——没有部署面改动可钉）；文档计数按**用例数**口径同步 1792→**1813**（＋21，与 pytest 汇总行的 1947 不同口径，后者含参数化展开），已改 README 徽章＋3 处正文、README_EN 徽章、`docs/ROADMAP.md:16`

#### 遗留
1. **judge 缓存没有任何淘汰**：它不按 run 生长，但随评审次数单调增，本批口径管不到它；正解是换成键值存储，而不是再挂一个计数器（§11.3 已按变量名记着）
2. **没有按字节/按天数的上限**：`keep` 是唯一旋钮，与 `pythonAi.evalReportsSize`（2Gi）没有联动，卷写满之前不会有任何动作，也没有告警
3. **Java `eval_harness_runs` 的行不删**（仓内无读点，故是无害摘要而不是 404）；`uk_eval_harness_run_file` 与秒级文件名的撞键面同批登记未修。将来给这张表加读面（列表页 / A-B 选 run）时，必须先决定"悬空行怎么显示"
4. **并发清扫只有单元层证据**：本机无集群，没跑过两副本真在同一块 RWX 卷上同时删；`FileNotFoundError` 的容忍有测试，真实 NFS/SMB 卷的删除语义未验证
5. **只调 `/score` 的工作流不触发清扫**：淘汰只挂在 `/run` 上，孤儿规则能兜住它产出的文件，但要等下一次 run
6. 承第八十五/八十六批：`UPLOAD_DIR` 空转键、Java 侧 10 处 `R.fail(403,…)` 统一、plugin-runner 镜像 uid 未进门禁、第三方镜像无 pod securityContext、helm 结论未用 v4 复渲、ROADMAP Java 计数 703 vs 713、`tests/deploy_surface.py` 与 `test_upload_path_contract.py` 两份同构解析器尚未合并、**没有跑过一次真实评测**（§11.4）

### 第八十六批（2026-10-08：评测的三个落点写死在相对路径上，而没有任何一档拓扑把卷挂在那儿）

#### 结论（先给判定性质）
- 待办本是"CHECKPOINT_DB_PATH 的落点"，先取数就把它否掉了：`get_checkpoint_manager` 在 `app/` 下**没有任何调用方**（全仓扫描，只有模块自身与测试），所以讨论"它该落哪块卷"没有适用对象。但 `docs/ENVIRONMENT.md:120` 把它列为可配项——按第八十二批的口径，这类"文档声称有落点、代码没有写点"是假开关的兄弟形态，本批把措辞降级为"当前无生产写点"，并加一条**自我撤除**的文本断言：一旦 app/ 出现调用方而文档还带着这句限定，测试就红
- 顺着"谁的产物不在卷上"查下去，撞出的是**已上线的缺陷**而不是留缝：评测产物的三个落点全是模块级硬编码的相对目录（`app/api/eval_harness.py:31`、`app/core/eval_harness/runner.py:25`、`app/core/eval_harness/metrics/llm_judge.py:63`），容器里 `WORKDIR=/app` ⇒ `/app/data`，而三档 shipped 拓扑没有一档把卷挂在那（compose 只挂 `/data`，helm 连 `/data` 都不存在）。`/score`、`/slides`、`/report`、`/diff` 四个端点是按"文件还在"读回的（`eval_harness.py:211/220/236-237`）⇒ 容器或 Pod 一重建就全部 404，helm 两副本下副本 A 生成的报告对副本 B 根本不可见。与第八十/八十二批同一失效形态（键在全仓任何部署配置里都没出现过），只是这次坏的不是持久性而是一次完整评测跑不出结果
- **落点不能一把梭**，这是第八十二批"读语义决定拓扑"那条规则的又一次应用：runs/reports/scores 是"写一次、之后按文件名读回"⇒ 该共享（helm 必须 RWX，跨副本可见）；judge 缓存是整文件 read-modify-write（`llm_judge.py:73` 起）⇒ 与共享根同目录时副本互相静默丢条目，只能分面

#### 改动
- `app/utils/config.py:180-182` 新增 `EVAL_HARNESS_DATA_DIR`（默认 `data/eval_harness`）与 `EVAL_JUDGE_CACHE_PATH`（默认 `data/eval_harness/judge_cache.json`）——默认值逐字保持今天的相对布局，宿主开发态零变化；三处常量改为读这两把键（`REPORTS_DIR`/`_RUNS_DIR`/`_CACHE_PATH`）
- `docker/docker-compose.yml`：`python-ai` 与 `python-ai-worker` 各设 `/data/eval-harness`，缓存分面成 `.http.json` / `.worker.json` 两个文件（同根不同进程共用一个 JSON 就是自我覆盖；worker 今天不 import 评测模块，设值是给未来的 arq 评测任务留落点）
- `deploy/docker-compose.prod.yml`：`python-ai` 设 `/data/eval-harness` ＋ `/data/eval-judge-cache.json`（单进程写，理由按变量名写进注释）
- `deploy/helm/hfusionhub`：`templates/python.yaml` 新增 `<rel>-eval-pvc`（**ReadWriteMany**，容量取新键 `pythonAi.evalReportsSize`=2Gi）挂到 `/app/eval-harness`，env 走 `/app/eval-harness` ＋ `/app/eval-harness/$(POD_NAME)/judge_cache.json`（复用第八十批已有的 downward-API `POD_NAME`）；沿用第八十三批口径**不带 `| default`**；`values.yaml` 里把"为什么一个共享一个分面"按变量名写成注释
- `deploy/Dockerfile.python`：`mkdir -p` 补 `/app/eval-harness` —— 第八十四批的规则，空 PVC 的属主只在镜像该路径有内容时才继承，路径不存在就交给 provisioner
- `scripts/static-checks.py` 新增检查 10 `check_eval_harness_storage()`（＋ `--eval-harness-storage`，并入默认全跑档）：每个 python 工作负载要求两把键都设成绝对路径且落在挂载点内，helm 侧还要求该挂载点背后的 PVC 是 RWX，缓存与共享根同目录时必须含 `$(POD_NAME)` 分隔；compose 与 k8s 两种 env 写法统一走 `_declared_env()`（检查 9 的 `_declared_document_root` 现在只是它的一层薄壳）
- `docs/ENVIRONMENT.md:120` 降级 `CHECKPOINT_DB_PATH` 措辞，新增两行评测键；`python-ai/.env.example` 补两把键的默认值与"缓存为什么单独一键"的说明（`RAG_EVALUATION_DB_PATH` 此前也只在这儿出现，别让新键重复同一个孤证形态）；`docs/PRODUCTION_OPS.md` 新增 **§11 评测产物的落点**（五档落点表、"两条规则方向相反"的推导、跨 Pod 不命中缓存的代价如实记着、四条未收口）；§10.4 表内 prod compose 锚点随本次插入改指 `:249`/`:276`

#### 验证
- 红→绿：`tests/test_eval_harness_storage.py` 新增 **18 例**，其中 17 例首跑 **16 红 / 1 绿**（红：config 缺键两条、三处常量仍硬编码三条、四档落点核对四条、文档限定语一条、门禁六条），实现后 18 passed。共用的部署面读数抽到 `tests/deploy_surface.py`（与 `static-checks.py` 里的解析**各写一遍**，两边同时看错同一形状的概率远低于一方自证）
- 第 18 例是第八十四批那条规则的自动化：`test_python_image_creates_every_helm_mount_point` 从 `templates/python.yaml` 的 `mountPath` **派生**清单，要求每个挂载点都出现在 `Dockerfile.python` 的 `RUN mkdir -p` 里——下一批加卷而忘了建路径，这条会自己变红。判它有效：真实 Dockerfile 去掉 `/app/eval-harness` → 报红"镜像没有创建这些挂载点：['/app/eval-harness']"，用备份还原后转绿
- **一条真缺陷是测试逼出来的**：`_helm_rwx_mounts()` 最初用 `(\S+)` 取 PVC 名，而模板里的名字是 `{{ .Release.Name }}-eval-pvc`（含空格），于是每个名字都被读成 `{{`、所有 PVC 塌成一个键、访问模式互相顶包——把 eval PVC 真改成 ReadWriteOnce，门禁照样判绿。改为整行取值后，同一次注入（改真实文件、跑完用备份还原）报红"…没有挂在 ReadWriteMany PVC 上…"，还原后转绿；`test_gate_flags_an_rwo_eval_volume_in_helm` 把这条钉住
- 门禁真能红：tmp 夹具覆盖"两把键都没设"（报缺 `EVAL_HARNESS_DATA_DIR`）、"root 落在 `/app/data` 不在挂载点"、"缓存与共享根同目录且未按 POD_NAME 分"三种形态，另有"helm 同卷按 `$(POD_NAME)` 分目录"必须判绿的放行例
- 接线不可能哑火：`test_gate_is_in_the_default_all_mode` 要求 `args.eval_harness_storage` 在 parse 之后、首个 dispatch 之前出现 ≥2 次
- helm（v3.22.0，绝对路径调用，`secrets.*` 与 `pluginRunner.*` 全用 RENDER-CHECK 占位）：`lint` → 0 failed；`template` 退出 0、**23 个对象**（+1 = eval PVC）、732 行（+31）、0 个 `<no value>`，逐对象读渲染结果 `rc-eval-pvc` = ReadWriteMany/2Gi，`rc-python` env = `/app/eval-harness` ＋ `$(POD_NAME)` 分面的缓存路径，volumeMounts 含 `/app/eval-harness`，replicas 2
- 回归：全量 pytest **1926 passed / 8 skipped**（含本批 18 例）；相邻五套（本批 + 评测 + API 契约 + 容器身份 + 路径契约）274 passed；部署面三套（checkpoint / evaluation_runs / plugin_audit）73 passed；`ruff` 干净；`scripts/static-checks.py` 全跑档通过（10 项）；Python 计数 1774→**1792**，已同步 README 徽章＋3 处正文、README_EN 徽章、docs/ROADMAP.md:16

#### 遗留
1. **没有跑过一次真实评测**：本机无 docker 引擎、无集群，§11.1 的表是渲染层与文本层证据。判伪口径写在 §11.4（卷上 touch ＋ 跑一次 run、删 Pod、用新 Pod 读回同一份 report；第八十七批起还可核对 retention 日志行）
2. **RWX 能不能拿到取决于 storage class**：chart 不声明 StorageClass，只支持 RWO 的提供方会在 `Pending` 才暴露，渲染期不报错
3. **评测产物没有清理策略**：每次 run 都往卷里追加，`evalReportsSize` 是一口价 2Gi，无 TTL/归档 **（已由第八十七批收口：按数量淘汰，口径与仍不在口径内的三条见 §11.3）**
4. **两把键 import 时绑定**：改环境变量必须重启进程，`RUNS_DIR`/`REPORTS_DIR`/`_CACHE_PATH` 都是模块级常量（测试因此一律 monkeypatch 常量）
5. 承第八十五批：`UPLOAD_DIR` 空转键、Java 侧 10 处 `R.fail(403,…)` 统一、plugin-runner 镜像 uid 未进门禁、第三方镜像无 pod securityContext、helm 结论未用 v4 复渲、ROADMAP Java 计数 703 vs 713
6. `tests/deploy_surface.py` 这层共用读数目前只被本批的测试用着：`test_upload_path_contract.py` 里那份同构解析器还在原地（两边各写一遍是有意的，但两份重复该合并成一份"故意独立"的而不是两份"偶然相同"的）。本批没动它，以免一次改动盖住两批的回归面

### 第八十五批（2026-10-06：Java 与 python 之间传的是"路径"，而路径在两个容器里指向的不是同一个地方）

#### 结论（先给判定性质）
- 第八十四批 遗留 3 排查到底：Java→python 传的是**绝对路径**（`DocumentServiceImpl.java:64` 的 `UPLOAD_DIR="uploads/documents"` 在 `:528-529` 拼成 `user.dir`(=运行阶段 WORKDIR `/app`) 下的绝对路径，`VectorizationServiceImpl.java:737` 原样发出），python 侧 `validators.py:87-103` 要求它在**自己容器里**存在且在 `DOCUMENT_STORAGE_ROOT` 之下 ⇒ "共享 uploads 卷 + 同绝对路径"是契约本身。**本批同时收回上一批写下的判断**："prod compose 给 python 挂了它从不写的 `uploads-data:/app/uploads`"是错的——它与 `deploy/docker-compose.prod.yml:244` 的 root 是成对的必要配置，第八十四批 遗留 3 与 `docs/PRODUCTION_OPS.md` §10.3 的措辞已按此改写
- 真正坏的是 **dev compose 的 fullstack 档**：`docker/docker-compose.yml` 的 `python-ai` 与 `python-ai-worker` 既没设 `DOCUMENT_STORAGE_ROOT` 也没挂 `uploads-data` ⇒ root 退回镜像默认值 `../java-backend/uploads/documents`（WORKDIR=/app → `/java-backend/uploads/documents`），Java 的 `/app/uploads/…` 在 python 容器里不存在，**每个上传文档的解析都 400 code 10001**；反向的 `/api/ingest/url` 更糟，它要 `mkdir` 出 root（`app/api/ingest.py:53-56`），而非 root 用户在 `/` 下建不出 `/java-backend`
- 缺陷能活这么久是因为两头都照不到：宿主开发态（`mvn spring-boot:run` + venv，cwd=`python-ai/`）用同一个默认值恰好正确，而契约测试一律把 root monkeypatch 到 `tmp_path`（`test_api_contract.py:1552`、`test_internal_api_security.py:56`）——只有容器化档的这段配置处于无人核对状态

#### 改动
- `docker/docker-compose.yml`：`python-ai` 与 `python-ai-worker` 各补 `DOCUMENT_STORAGE_ROOT: /app/uploads/documents` ＋ `uploads-data:/app/uploads` 挂载（口径与 prod compose / helm 一致，那两档本批零改动）。上一批钉的 uid/gid=10001 是这次补齐的安全前提：java 与 python 现在**都往同一块卷写**（ingest 也写 root），co-write 靠的是同号的 runAsGroup/fsGroup
- `scripts/static-checks.py` 新增检查 9 `check_document_storage_root_contract()`（＋ `--document-storage-root`，并入默认全跑档）：期望路径**派生**自 `Dockerfile.java` 运行阶段的 `WORKDIR` 与 `DocumentServiceImpl.java` 的 `UPLOAD_DIR`（锚点任一变动 → 三档同时报红，而不是让门禁与代码各说各话）；每个 python 工作负载要求"root 等于派生值"＋"有卷挂在该路径或其祖先上"成对成立，缺哪侧报哪侧，文案带上会观察到的错误码。compose 与 k8s 两种 env 写法都支持，注释行跳过
- `docs/PRODUCTION_OPS.md`：§10.2 补"java 写、python 读"的成对实测命令（含读不到即契约未落地的判读）；新增 **§10.4 文档目录的同路径契约**——四步链路 ＋ 四档部署面（prod compose / helm / dev compose / 宿主开发态）状态表；§10.3 首条改为"只做到配置层对齐，未实测"

#### 验证
- 红→绿：`tests/test_upload_path_contract.py` 新增 **15 例**，首跑 **10 红 / 5 绿**（红：dev compose 两个服务各两条、四处 root 取值不唯一一条、门禁五条；绿：契约前提两条 + prod compose/helm 既有成对配置两条 + 派生值一条），实现后 15 passed
- 门禁真能红：对**真实** `docker/docker-compose.yml` 只删 `python-ai` 的 root 一行 → rc=1 且报"没有 DOCUMENT_STORAGE_ROOT…解析一律 400"，随后用改前原文写回还原；"设了 root 却没挂卷"与"root 与 java 不同号"两种半修形态由 tmp 夹具覆盖
- 锚点核实：`Dockerfile.java` 两处 WORKDIR 均为 `/app`（取 `FROM` 末段），派生值 `/app/uploads/documents` 与 prod compose/helm 的既有字面量逐字相同，故本批没引入第二个数字
- 接线不可能哑火：`test_gate_is_in_the_default_all_mode` 要求 `args.document_storage_root` 在 parse 之后、首个 dispatch 之前出现 ≥2 次（第八十三批那处缺陷的形态）
- 回归：全量 pytest **1908 passed / 8 skipped**（含本批 15 例）；`ruff` 干净；`scripts/static-checks.py` 全跑档通过（9 项）；Python 计数 1759→**1774**，已同步 README 徽章＋3 处正文、README_EN 徽章、docs/ROADMAP.md:16

#### 遗留
1. **"java 写、python 读"仍是纸面对齐**：本机无 docker 引擎，本批核验只到文本门禁层。10.2 末尾那对命令是唯一能证伪它的东西
2. **`UPLOAD_DIR` 是个空转的键**：三档 compose 都设 `/data/uploads`，而 python 侧只有 `app/main.py:238` 建目录、没有任何读写方（ingest 用 `DOCUMENT_STORAGE_ROOT`）。删它涉及"是否有历史数据留在 `python-data:/data/uploads`"，需先看一次真实卷内容再定
3. helm 的 python 是单 Deployment 多副本形态，若 `replicas>1` 且 uploads 卷为 RWX，两副本对 `/app/uploads/documents` 的并发写（ingest 同名文件）没有互斥——本批未触碰该语义
4. 承第八十四批：旧卷一次性 chown、plugin-runner uid 未钉、第三方镜像无 pod securityContext、`CHECKPOINT_DB_PATH` 落卷、Java 侧 10 处 `R.fail(403,…)`、ROADMAP Java 计数 703 vs 713、helm 结论未用 v4 复渲


### 第八十四批（2026-10-06：卷能不能写，取决于两个此前从未在任何地方对齐过的数字）

#### 结论（先给判定性质）
- 第八十三批把"无 fsGroup、uid 未钉"从未知变成已确认缺失，本批把它修成**三处同源的一个常量**：镜像里的 uid/gid ＋ helm 的 `runAsUser/runAsGroup/fsGroup` 必须同号，由新门禁核对
- 排查中确认这**不是 helm 独有的缺口**：`Dockerfile.java` 从未创建 `/app/uploads`，而 java 写的全部是 `user.dir`(=/app) 下的相对路径（`DocumentServiceImpl.java:64` uploads/documents、`ChatImageStorage.java:40` uploads/chat-images、`UserServiceImpl.java:72` uploads/avatars）。空命名卷/空 PVC 的属主只在镜像该路径**有内容**时才继承镜像属主，路径不存在则由 root 建 ⇒ compose 上 java 的第一次 mkdir 就是 AccessDenied，helm 上则是碰运气交给 provisioner
- 身份本身也是漂的：`Dockerfile.python` 用 `useradd -r`（Debian 系统池 100–999）、`Dockerfile.java` 用 `adduser -S`（Alpine 同类），号由基镜像当时占了哪些号决定，重建即可能换号；而 helm 若要写 fsGroup 就必须知道这个号——两处各写一遍、无人核对，正是第八十三批"模板读了一个不存在的键"的兄弟形态

#### 改动
- `deploy/Dockerfile.python`：`groupadd -r -g 10001` ＋ `useradd -r -u 10001 -g 10001`，并把两个 helm 挂载点 `/app/uploads`、`/app/audit-queue` 一并 `mkdir` 后交给 `chown -R /app`
- `deploy/Dockerfile.java`：`addgroup -S -g 10001` ＋ `adduser -S -u 10001 -G hfusionhub`，新增 `mkdir -p /app/uploads` ＋ chown（切换非 root 用户之前）
- `values.yaml:22-25` 新增顶层 `podSecurity`（runAsUser/runAsGroup/fsGroup 全 10001，理由与旧卷升级提示写在注释里按变量名可检索）；`templates/python.yaml`、`templates/java.yaml` 的 pod 层加 `securityContext: runAsNonRoot + 三个 values 引用`，沿用第八十三批口径**不带 `| default`**
- `templates/plugin-runner.yaml`：在已有的 pod securityContext 上补 `fsGroup: 1000`（与它的 runAsGroup 同号）。它是本类缺口的最近邻——`readOnlyRootFilesystem: true` 使 `/opt/plugin-artifacts` 成为唯一可写落点，而空 PVC 挂上来后镜像里的 chown 已被卷内容取代
- `scripts/static-checks.py:426-517` 新增检查 8 `check_container_uid_consistency()`（＋ `--container-uid`，并入默认全跑档）：两个 Dockerfile 钉的号与 helm `podSecurity` 三个号必须一致且同号；`-r`/`-S` 没配 `-u`/`-g` 直接判"未钉身份"；注释行跳过，避免说明文字被当成声明
- `docs/PRODUCTION_OPS.md` 新增「10. 卷属主与运行身份」：三处号码表、fsGroup 为什么是关键项、**旧卷的一次性 chown**（compose 命名卷一行命令 ＋ helm 一次性 Job 清单）、有集群/docker 时的实测命令、以及三条未收口

#### 验证
- 红→绿：`tests/test_container_identity.py` 新增 **13 例**先全红（`values.yaml 没有 podSecurity 段`、`Dockerfile.java 的用户必须用 -u 钉死 uid，实际找到 0 处`、`镜像没有创建挂载点 /app/uploads`、`templates/python.yaml 的 pod 层没有 securityContext`），实现后 13 passed
- 门禁真能抓漂移（对真实文件临时注入，跑完用改前原文写回还原，不用 `git checkout`）：把 `runAsUser` 改 10002 → rc=1，两个 Dockerfile 各报一条不一致；把 `fsGroup` 改 20001 → rc=1 报"三个号不相同"
- 接线不再可能哑火：`test_container_uid_gate_is_in_the_default_all_mode` 要求 `args.container_uid` 在 parse 之后、首个 dispatch 之前出现 ≥2 次（条件里一次、默认赋值链一次）。用第八十三批那次的破坏方式验证过这条测试本身是有效的——只删条件里那一处，它红
- helm：`lint` → `0 chart(s) failed`；`template`（`secrets.*` 与 `pluginRunner.*` 用 RENDER-CHECK 占位）退出 0、22 个对象、701 行（恰好 +10 行 = 两个模板各 5 行）、0 个 `<no value>`。逐工作负载读渲染结果：`hf-java`/`hf-python` = runAsUser/runAsGroup/fsGroup 10001 ＋ runAsNonRoot，`hf-plugin-runner` = 1000/1000/1000，frontend/mysql/redis/etcd/milvus 仍为空（见遗留）
- 回归：全量 pytest **1893 passed / 8 skipped**（含本批 13 例）；`ruff` 干净；`scripts/static-checks.py` 全跑档通过；Python 计数 1746→**1759**，已同步 README 徽章＋3 处正文、README_EN 徽章、docs/ROADMAP.md:16

#### 遗留
1. **"真的能写"仍未实测**：本机 Docker daemon 未运行、无集群，本批核验只到渲染层与文本门禁层。实测命令已写进 `docs/PRODUCTION_OPS.md` 10.2。两个镜像也**没有实际构建过**——`useradd -u/-g` 与 busybox `adduser -S -u/-G`、`addgroup -S -g` 的参数形态按各自手册写，首次真实构建即是它的验收
2. 升级前建下的卷，其内容属主仍是旧系统号 ⇒ 必须一次性 chown（10.1 给了 compose 与 helm 两份操作），否则老部署在换镜像后写旧文件 EACCES
3. compose 与 helm 的上传目录语义不等价（本条初稿判断有误，已随排查更正）：**prod compose 给 python 挂的 `uploads-data:/app/uploads` 不是死挂载**，它和 `deploy/docker-compose.prod.yml:244` 的 `DOCUMENT_STORAGE_ROOT: /app/uploads/documents` 是一对——Java 写的绝对路径要能被 python 读到，靠的就是"同路径 + 同卷"。真正的缺口在**dev compose 的 fullstack 档**：`docker/docker-compose.yml` 的 `python-ai`（:286-347）与 `python-ai-worker`（:349-376）都没有 `DOCUMENT_STORAGE_ROOT`、也不挂 `uploads-data`，于是 python 的容器内根目录落到默认值 `../java-backend/uploads/documents`（WORKDIR=/app ⇒ `/java-backend/uploads/documents`），而 Java 传来的 `file_path` 是 `/app/uploads/documents/...`，`validate_file_path` 的 `resolve(strict=True)` 必然 ENOENT ⇒ `/api/parse` 一律 400（code 10001）。宿主开发态（`mvn spring-boot:run` + venv uvicorn）不受影响——默认值就是为它设计的
4. plugin-runner 镜像的 uid 仍靠 `useradd` 默认分配（chart 硬编码 1000），未进 `--container-uid` 门禁
5. frontend/mysql/redis/etcd/milvus 无 pod securityContext（上游镜像以 root 起、入口脚本自 chown）
6. 承第八十三批：rollout 后旧 Pod 目录的审计残留、helm 评测历史不持久、`CHECKPOINT_DB_PATH` 落卷拓扑、Java 侧 10 处 `R.fail(403,...)`、ROADMAP Java 计数 703 vs 713、helm 结论未用 v4 复渲


### 第八十三批（2026-10-06：helm lint 把"记了但没验"判成了硬失败——这张 chart 从来渲染不出来）

#### 结论（先给判定性质）
- `helm lint deploy/helm/hfusionhub` → `[ERROR] templates/: template: hfusionhub/templates/python.yaml:51:31: executing ... at <.Values.python.taskQueueMode>: nil pointer evaluating interface {}.taskQueueMode`；`helm template`（带齐 `secrets.*` 占位值）同一错误直接终止
- **不是静默走 `default "inline"`**。Go 模板管道左侧的字段访问在 nil map 上就报错，`default` 没有执行机会 → `helm install` 从一开始就失败。第八十批的审计 PVC、第八十二批的评测决策，此前都处在"写进了模板但整张图从未渲染成功过"的状态
- 根级普查（模板用到的 `.Values.<root>` vs `values.yaml` 顶层键）：14 个引用根里只有 `python` 未定义，其余 13 个都有定义 → 单点笔误，不是系统性漂移

#### 改动
- `deploy/helm/hfusionhub/templates/python.yaml:51` → `.Values.pythonAi.taskQueueMode`（键已定义在 `values.yaml:67`），同时去掉 `| default "inline"`：全 chart 只有这一处用 `default`，其余模板一律直接读 values；而 `pythonAi` 整体缺键时 nil map 同样会炸，这个兜底既保护不了真实场景，又正是让笔误看起来无害的东西
- `scripts/static-checks.py:373-408` 新增检查 7 `check_helm_value_roots()`（＋ CLI 开关 `--helm-value-roots`，并入"全部检查"默认档）：模板引用的 `.Values` 根必须在 `values.yaml` 顶层存在。纯文本核对、不需要 helm 二进制——CI 和开发机都没有 helm，而这正是缺陷能活到本次的原因

#### 验证
- 红（两条独立路径命中同一处）：新门禁在未修模板时 → `✗ Helm 模板引用了未定义的 values 根: templates/python.yaml:51 引用 .Values.python`；`helm lint` 与 `helm template` 各失败一次（错误原文见上）。修模板后：门禁转 `[ok] Helm values 根一致性：13 个模板引用的根全部在 values.yaml 定义`、`helm lint` → `1 chart(s) linted, 0 chart(s) failed`（只剩 Chart.yaml icon 的 INFO）、`helm template` 退出 0
- 渲染产物核账（22 个对象 / 691 行 / **0 个 `<no value>`**，全部可被 `yaml.safe_load_all` 解析）——一次结掉 80/82 批留下的三条"未核验"：
  1. `TASK_QUEUE_MODE` 渲染成 "inline"（修复生效）
  2. python Deployment 里 `HFUSIONHUB_AUDIT_DB_PATH: /app/audit-queue/$(POD_NAME)`、`POD_NAME` 走 valueFrom、volumeMount 与 volume 指向 `hfusionhub-audit-pvc`，该 PVC 渲染为 `ReadWriteMany` / 1Gi，`replicas: 2` → 第八十批的卷设计在产物层面是真的
  3. 渲染后的 python 容器环境**没有** `RAG_EVALUATION_DB_PATH` → 第八十二批"helm 刻意不设"成立
- 回归面：`test_plugin_audit + test_evaluation_runs + test_checkpoint` **73 passed**（这些测试直接读 `python.yaml` 文本，改模板必须复跑）；`scripts/static-checks.py` 全通过；本批无新增 `def test_`，Python 计数仍 1746，文档无需再同步
- 环境：helm 取官方 v3.22.0 二进制，解在仓库外 `D:/college/development/tools/helm/`，未进 PATH、未装到系统；官方 latest 已是 v4.3.0，本批未用 v4 复渲（待确认）

#### 新定性的发现（本批只记不修）
- 渲染显示 8 个工作负载里**只有 `plugin-runner` 带 securityContext**（pod `runAsUser`/`runAsGroup=1000` ＋ `runAsNonRoot`），python/java/mysql/redis/milvus/etcd 的 pod 与容器 securityContext 全为空——第八十批记的"无 `fsGroup`"由此从"未知"变成**已确认缺失**
- 而且 uid 没法靠约定补：`Dockerfile.python:23` 用 `useradd -r hfusionhub` 不钉 `-u`，system uid 按可用区间顺分配，跨镜像重建不保证一致。合起来的真实风险是：非 root 容器 ＋ 无 `fsGroup` ＋ 卷属主由 provisioner 决定 → `/app/audit-queue`（以及同样挂 RWX 卷的 `/app/uploads`）能不能写，chart 层面没有任何保证
- 不进本批修的理由：这是部署面行为变更（要同时决定钉 `runAsUser` 还是加 `podSecurityContext.fsGroup`），而本机没有集群，改完只能证明"能渲染"，证明不了"能写进去"

#### 遗留
1. python（与挂 RWX uploads 卷的 java）的卷写权限方案：钉 uid ＋ `fsGroup`，还是 initContainer 改权限——需真集群验证
2. rollout 后旧 Pod 目录里的审计残留仍需运维手动发现（承第八十一批）
3. helm 拓扑里评测历史仍不持久、面板按应答副本显示局部历史（承第八十二批）
4. `CHECKPOINT_DB_PATH` 现在是真开关，但默认仍落镜像层，落卷要先定拓扑（承第八十二批）
5. 本批 helm 结论基于 v3.22.0，未在 v4.3.0 上复渲对比
6. Java 侧 10 处 `R.fail(403, ...)` 折叠成 HTTP 200 的状态码统一
7. ROADMAP Java 计数 703 与实测 713 的口径


### 第八十二批（2026-10-06：评测历史落卷只有一半能安全修，另一撞出来的是文档里的死键）

#### 两条发现（任务原问：`RAG_EVALUATION_DB_PATH` 是否在卷上）
- **是同一个失效模式，但修法不对称**。三处声称持久——"Durable, privacy-conscious history（`evaluation_runs.py:1`）"、`config.py:144-146` 的"survive AI-service restarts"（该注释已就地补上"持久性取决于拓扑"的限定）、`rag.py:233` 的 "durable metric history"——而默认值 `./data/rag_evaluation_runs.db` 在容器里解析成 `/app/data`（WORKDIR=/app，Dockerfile.python:5），该键全仓只出现在 `python-ai/.env.example:74`，三套 shipped 拓扑都没赋值。面板"最近评测"（`Index.vue:452`，经 `RagObservabilityController.java:215` 透传）随重建清空
- **compose 是简单的一半**：两个 compose 都没有 `replicas:`（单 HTTP 进程），唯一写点是 `rag.py:219`，`arq_worker.py` 从不 import 该 store → 落 `/data` 无共写
- **helm 是难的一半**：`values.yaml:77` 是 `replicas: 2`（HPA 到 8）。这个库是**读面**，第八十批的按 Pod 分目录规则会让面板只显示应答副本的历史；而 2 副本共写一个 SQLite 文件正是那条规则禁止的事
- **顺带查出的活缺陷（本批更严重的一条）**：`docs/ENVIRONMENT.md:120` 把 `CHECKPOINT_DB_PATH` 列为可配变量，但 `app/utils/config.py` 从未定义该属性，而 `checkpoint.py:111` 用 `getattr(config, "CHECKPOINT_DB_PATH", None)` 取它 → 恒为 None → **运维设了也完全不生效**，永远落模块兜底 `data/checkpoints.db`（容器里同样是 `/app/data`，且该库开 WAL）。判定顺序：这是"配置面声称 ≠ 代码事实"，比落点不在卷上更糟，因为它给运维一个假开关

#### 改动（用户选 A）
- `docker/docker-compose.yml:313` 与 `deploy/docker-compose.prod.yml:243`：`RAG_EVALUATION_DB_PATH: /data/rag_evaluation_runs.db`（与审计队列、`CHUNKS_STORE_PATH` 同一惯例）
- `config.py:154` 补 `CHECKPOINT_DB_PATH = os.getenv(...)`，默认值与 `checkpoint.py:38` 的 `_CHECKPOINT_DB_DEFAULT` 同源；`checkpoint.py:111` 同时把 `getattr(..., None)` 改成直读属性——以后这个键缺失会直接抛，而不是静默退回兜底路径
- helm **刻意不设**该键，并把原因按变量名写进 `deploy/helm/hfusionhub/values.yaml:72-76`：注释是测试的断言对象，防止下一个人当遗漏补上

#### 决策记录
- **第八十批那条规则的完整形式**："别让多副本共写一个 SQLite 文件"只说了一半，判据要看这个库的**读语义**是否 pod-local。审计队列是 outbox（各 Pod 只清自己的积压），按 Pod 分目录既安全又完整；评测历史是控制台聚合的 journal，按 Pod 分目录就把"丢数据"换成了"读到局部历史"。剩下的诚实选项只有三个：不声称持久、读侧跨 Pod 文件合并、换到真共享库（`EvaluationRunStore` 的类文档本身就预留了这个替换）
- **不选 B（per-pod 目录 + 读侧合并）**：它引入"目录（每 Pod 一文件）vs 单文件"两种配置形状，本仓无先例，且本机没有 helm client，渲染不出来就无法自称修好
- **不选 C（只改口径）**：compose 那一半的丢失是真丢，改文案不换修复
- **checkpoint 落卷不进本批**：它是第三个同类问题（默认相对路径 + WAL + 多副本），把死键修成开关是本批的收口范围，落点选择需要单独的拓扑判断

#### 验证
- 红：5 failed —— compose 2 例（`docker-compose.yml`/`prod` 均未配置该键）＋ helm 决策未记名 1 例 ＋ checkpoint 3 例（`AttributeError: ... has no attribute "CHECKPOINT_DB_PATH"` ×2、口径断言 ×1）；先绿后扩到 24 passed（`test_evaluation_runs.py` 5 + `test_checkpoint.py` 19）
- 新增 `tests/test_evaluation_runs.py:43` `TestEvaluationHistoryPersistenceConfigured`（compose 落点、helm 刻意不共享）+ `:92` `test_evaluation_run_store_honours_the_config_key`
- 新增 `tests/test_checkpoint.py:214` `TestCheckpointPathIsConfigurable`：`test_config_defines_the_key_with_the_documented_default`（同时钉住 ENVIRONMENT.md 那一行的默认值与代码兜底同源）、`test_manager_lands_on_the_configured_path`、`test_explicit_argument_still_wins`（显式入参优先级不被配置键覆盖）
- Python 全量 **1880 passed / 8 skipped**（163.21s，1740 → 1746）；ruff（.venv 0.16.3）All checks passed；`scripts/static-checks.py` 全通过；三个 YAML 文件解析后键值已核（compose 两处取到 `/data/...`，`values.yaml` 的 `replicas: 2` 未受影响）

#### 未核验
- 本机无 helm client：`values.yaml` 只做了 YAML 解析与文本断言，未 `helm lint` / `helm template`（承第八十批）
- 没有跑过两副本真实并发：helm 侧"共享单文件会互踩锁"依据是上游对 NFS 类卷上 SQLite 文件锁的说明与第八十批的同族判断，非本机实测

#### 遗留
1. helm 拓扑里评测历史仍不持久，且面板按应答副本显示局部历史——需要的是共享库而非卷路径（本批决策记录的三个选项之一）
2. `CHECKPOINT_DB_PATH` 现在是真开关，但默认仍落 `/app/data`（镜像层），且该库开 WAL，落共享卷前要先定拓扑
3. rollout 后旧 Pod 目录里的审计残留仍需运维手动发现（承第八十一批）
4. helm 存储类可写性与 `fsGroup`（承第八十批）
5. `.Values.python.taskQueueMode` 悬空引用（`python.yaml:51`，键实际在 `pythonAi` 下，需 helm client 才能安全处理）
6. Java 侧 10 处 `R.fail(403, ...)` 折叠成 HTTP 200 的状态码统一
7. ROADMAP Java 计数 703 与实测 713 的口径


### 第八十一批（2026-10-06：SIGTERM 前把审计队列排空——第八十批唯一会自我恶化的残留）

#### 问题
- 第八十批把队列落到按 `POD_NAME` 命名的目录后，留下的那条残留与其他遗留不同，它会**自己变严重**：
  `_flush_worker` 只在 `_FLUSH_INTERVAL = 30.0` 的节拍上出站，进程被终止时队列里最多压着 30 秒的未确认数据；
  而 Deployment 重建后 Pod 名变了，旧目录不会再有任何进程接手，残留只能靠运维偶然发现
- `_do_flush` 没有内部截止时间：批量 POST `timeout=30.0`（:381），整批失败回退逐条、每条 `timeout=10.0`（:410），
  积压 50 条最坏 500 秒——远超 K8s 默认优雅期。也就是说"等它跑完"不是一个可实现的方案
- 与第七十七~七十九批同族的诚实性风险：`get_sync_status()`（:541-547）把"库读不到"降级成
  `{total: 0, unsynced: 0, dead_letter: 0}`。退出路径若沿用它上报结果，"没确认"会被写成"已排空"

#### 改动
- `flush_on_shutdown()`（`app/core/plugin/audit.py:573-627`）：先 `_flush_stop.set()` 停后台线程，
  对在途线程 `join(timeout=budget/3)` 让它那次出站先跑完，再起 daemon 线程做最后一次 `_do_flush()` 并
  `join(timeout=budget)`；返回 `{flushed, remaining, timed_out, error, db_dir}`
- `_SHUTDOWN_FLUSH_BUDGET = 10.0`（:64）：预算远小于优雅期 30s，给在途请求留余量；上限只能来自墙钟，
  因为超预算就是 SIGKILL，继续等换不来同步成功
- 新增 `_queue_counts()`（:527-539）作为**只抛不降级**的读数口径，`flush_on_shutdown` 用它取
  `remaining = unsynced + dead_letter`；监控面 `get_sync_status` 保持旧的降级到零口径不变（两者故意分叉）
- 日志按处置结果分三级：未排空 WARNING、无法确认 ERROR、排空 INFO，三种都把 `_DB_DIR` 打进去——
  残留行躺在按 Pod 命名的卷目录里，不落点等于让运维去猜位置
- 接线在 lifespan 退出路径**第一位**（`app/main.py:108-122`，import :114、`asyncio.to_thread` :115）：
  排在 MCP client 关闭与共享 HTTP client 关闭之前（出站调用正需要这些连接还活着），
  `to_thread` 包住以免最多 10 秒的阻塞把 event loop 卡在退出路径上

#### 测试（先红后绿）
- 红：8 failed —— 7 例 `AttributeError: module 'app.core.plugin.audit' has no attribute 'flush_on_shutdown'`
  ＋ 1 例 `AssertionError: 退出路径没有排空审计队列`
- 新增 `tests/test_plugin_audit.py:543` `TestFlushOnShutdown` 7 例：
  `test_drains_the_queue_and_reports_zero_remaining`、
  `test_empty_queue_reports_zero_without_touching_java`（side_effect 直接抛，证明空队列不发 HTTP）、
  `test_rows_survive_when_java_refuses_and_the_location_is_logged`（caplog WARNING 必须含 `_DB_DIR`）、
  `test_stops_the_background_thread`、
  `test_returns_within_budget_when_java_hangs`（budget=1.0 断言 elapsed<3.0 且 unsynced 仍为 1）、
  `test_db_failure_is_reported_as_unknown_not_as_drained`（`remaining is None` 且 error 含 "db locked"）、
  `test_get_sync_status_still_degrades_to_zeros`（钉住监控面口径未被改动）
- 新增 `tests/test_api_contract.py:530` 源码位置测试 `test_lifespan_shutdown_drains_the_audit_queue`：
  把 `async def lifespan` 体按 `"    yield\n"` 切成 startup/shutdown 两半，断言 `flush_on_shutdown`
  只在后半出现且带 `to_thread`。不进入真实 lifespan（要跑 MCP startup 与 gateway warmup），钉的是"接线掉回
  startup 侧或被删"这类回归
- 关键判据：排空 == "没有待发项"，不是"表空了"——synced 行按 7 天保留（`_cleanup_synced:267-278`），
  故 drained 场景断言 `get_sync_status() == {"total": 2, "unsynced": 0, "dead_letter": 0}`
- 绿：`tests/test_plugin_audit.py` + 该契约测试 **50 passed**；Python 全量 **1874 passed / 8 skipped**
  （167.19s，1732 → 1740）；ruff（`.venv` 0.16.3）`app tests` All checks passed；
  `scripts/static-checks.py` 计数同步后转绿（README.md/README_EN.md/docs/ROADMAP.md 三处 1740）

#### 决策记录
- **不加内部 deadline 到 `_do_flush`**：`requests/httpx` 的超时只约束单次 IO，重试链与逐条回退的总量管不了；
  把截止时间塞进同步热路径会改动每批语义，代价大于收益。墙钟 + daemon 线程是唯一可靠的界
- **超时后不 cancel**：Python 无法安全强杀线程；`timed_out=True` 如实上报，daemon 线程随 SIGKILL 一起消失，
  数据仍在卷上——比"假装排空"好
- **`remaining=None` 与 `0` 严格区分**：读不到库时把 error 一起返回并走 ERROR 日志，绝不写成 0。
  这是信封盲区家族（77/78/79）在退出路径上的同一课
- **不做旧 Pod 目录回收**（新 Pod 扫 `/data` 下别人的目录）：跨 Pod 打开他人的 SQLite 文件正好违反第八十批的
  按 Pod 隔离前提；运维面已有 `get_sync_status` + `retry_dead_letters`(:549-570)，残留走显式处置
- **不动 `_MAX_RETRIES` / 重试间隔**：退出路径只跑一次 `_do_flush`，上限由预算决定，不需要第二层节流

#### 未核验
- 无真集群：`terminationGracePeriodSeconds=30` 与到点 SIGKILL 按上游文档，未在本环境实测
- 优雅期内"在途请求 + 10 秒排空预算"的实际余量未压测；helm 渲染仍无法验证（本机无 helm client，承第八十批）

#### 遗留
1. rollout 后旧 Pod 目录里的残留行仍需运维手动发现（本批只保证"退出时尽量排空 + 落点进日志"，没做自动回收）
2. helm 侧存储类可写性与 `fsGroup`（承第八十批）
3. `RAG_EVALUATION_DB_PATH` 是否落在卷上（同族 durability 问题）
4. `.Values.python.taskQueueMode` 悬空引用（`python.yaml:51`，需 helm client 才能安全处理）
5. Java 侧 10 处 `R.fail(403, ...)` 折叠成 HTTP 200 的状态码统一
6. ROADMAP Java 计数 703 与实测 713 的口径

### 第八十批（2026-10-06：dead-letter 回灌先定量——本机没有可回灌的历史行，真正的问题是审计队列在三套 shipped 拓扑里都不落在卷上）

#### 定量结论（原任务的答案，先给数）
- 开发机 `~/.hfusionhub/audit/plugin_audit.db`（20480 字节）实测 **`audit_queue` total = 0**，`GROUP BY synced, dead_letter` 与 `GROUP BY retry_count` 均为空集，表结构完整（`id, entry_json, synced, dead_letter, retry_count, created_at, last_attempt_at`）。**本机不存在第七十七批之前那批需要回灌的 dead-letter 行**
- 这个文件也不是使用痕迹：`tests/conftest.py:122-128` 的 autouse 隔离 fixture 在 setup 时 `_reset_db(tmp_path)`、teardown 时 `_reset_db(None)` 把落点还原成家目录，之后任何一次 `_get_db()` 就会走 `_init_db()` 的 `os.makedirs` + `sqlite3.connect` 建出空库（行数为 0 与此一致）
- 因此本批把"回灌"从"数据修复"改成"补上让回灌有意义的前提"：队列得先在三套 shipped 拓扑里都活得过容器/Pod 重建，且运维要能看见队列、能显式触发重放

#### Fixed
- **两处 shipped compose 的 `python-ai` 服务显式配置 `HFUSIONHUB_AUDIT_DB_PATH=/data/hfusionhub-audit`（`docker/docker-compose.yml:310`、`deploy/docker-compose.prod.yml:240`）**。`audit.py:48-52` 的默认落点是 `os.path.expanduser("~")/.hfusionhub/audit`，而这个键**此前在全仓没有任何部署配置写过**（只在 `audit.py:49,181` 被读，compose/prod/helm/`.env` 均按变量名核对、未取值）；`deploy/Dockerfile.python:22-26` 用 `useradd -r -d /app` + `USER hfusionhub` 运行，家目录只可能是 `/app`（passwd 里写的）或 `/root`（HOME 未显式设置的另一种走法），**两条都不在挂载点上**——卷只挂在 `/data` 与 `/app/uploads`（dev `docker-compose.yml:319-322`、prod `:263-268`）。后果：`_persist_to_sqlite:187-188` 的 "for crash recovery" 注释在 shipped 拓扑里本就不成立，容器一重建，未同步行与 dead-letter 行一起消失——第七十七批修好出站地址之后，这才是在积压场景下真正的丢数据路径
- **helm 的 python Deployment 补上第三处落点**：新增 RWX PVC `{{ .Release.Name }}-audit-pvc`（`templates/python.yaml:117-128`，容量键 `pythonAi.auditQueueSize: 1Gi`，`values.yaml:80`），挂到 `/app/audit-queue`（:108-109、:114-116），并设 `HFUSIONHUB_AUDIT_DB_PATH=/app/audit-queue/$(POD_NAME)`（:72-77，`POD_NAME` 走 downward API）。该模板此前只有 `shared-uploads` 一个 PVC（挂 `/app/uploads`），helm 拓扑里**没有 `/data`**——把 compose 的写法照搬过去只会伪装成已持久化、实际仍随 Pod 重建丢失

#### Added
- **`python-ai/app/core/plugin/audit.py:536-557` 新增 `retry_dead_letters() -> int`**：`UPDATE audit_queue SET dead_letter = 0, retry_count = 0 WHERE dead_letter = 1`，返回回灌条数并记 warning。`retry_count` 一并清零，每行重新拿到 `_MAX_RETRIES = 5`（:58）的完整预算；已 `synced = 1` 的行不动；DB 异常按模块既有风格返回 0 + `logger.error`，**不把行清掉**
- **`python-ai/app/api/plugin_admin.py:216-226` 两个运维端点**：`GET /api/plugin/audit/sync-status`（直读 `get_sync_status()`，:523-533）与 `POST /api/plugin/audit/dead-letters/retry`。此前 `get_sync_status()` **没有任何 router 暴露**，运维只能进容器查 sqlite
- **`python-ai/tests/test_plugin_audit.py`：`TestRetryDeadLetters` 7 例（:453 起）+ `TestAuditQueuePersistenceConfigured` 4 例（:543 起）**——回灌计数与 `dead_letter` 归零、`retry_count` 归零、**回灌后下一次 flush 真的把它再次出站**（`_post_to_java_backend_batch` 被调 1 次且状态转 synced，这条才是"回灌有用"的反证）、二次调用幂等、无 dead-letter 时是 no-op、`synced` 行不受影响、`_get_db` 抛错时返回 0 且行仍在；落点侧含 compose 双文件的 YAML 解析断言（键存在且以 `/data/` 开头）、helm 的 2 例正向断言（`HFUSIONHUB_AUDIT_DB_PATH` 必须等于 `/app/audit-queue/$(POD_NAME)`，且 `- name: POD_NAME` 排在它之前——K8s 只用**此前已定义**的变量做 `$()` 替换；审计 PVC 必须 RWX，因为 `pythonAi.replicas: 2`，RWO 会让第二个 Pod 卡在 Pending）、以及 `_reset_db(None)` 确实按环境变量取址的对照例
- **`python-ai/tests/test_api_contract.py`**：`PLUGIN_ADMIN_ROUTES` 增至 10 条（新 2 条自动纳入既有的"缺 token / 伪造 token 一律 401"参数表），另加 2 例端点契约（sync-status 原样回传三计数；retry 委托恰好一次并回 `{"retried": n}`）

#### 决策记录
- **helm 落点选"独立审计 PVC"而不是复用 uploads PVC**：队列确实只由 python 写，但 uploads 卷的口径是文档——Java 与 python 各挂一次（`DOCUMENT_STORAGE_ROOT=/app/uploads/documents`），往里加一个每 Pod 都在写的 SQLite 会让清理、备份、配额三类动作同时打在两种性质完全不同的负载上；审计队列体积上限可预测（未同步行 + dead-letter），单卷多花 1Gi 换部署面清晰划界
- **每 Pod 一个子目录（`$(POD_NAME)`）而不是共写同一个文件**：共享卷上同时打开同一个 SQLite 会跨进程争写锁，而模块只有进程内 `_db_lock`（:150），WAL 模式在 NFS 类共享卷上本就不可靠；分目录后每个队列仍是单写者，与"worker 服务不配同值"是同一条理由
- **审计路径不做成可关项**：队列是 `plugin_admin` 的固有依赖，没有"关掉持久化"这种配置，`pythonAi.enabled` 就是它的开关，故 env 与 volume 都写在模板主体里
- **worker 服务不配同一个值**：`app/core/tasks/arq_tasks.py` 只 import `app.utils.config`，不触碰插件 registry，故 dev 的 `python-ai-worker`（`docker-compose.yml:343`）不产审计行；把两个容器指向 `python-data` 上同一个 `plugin_audit.db` 会引入跨进程 SQLite 写锁竞争（模块只有进程内 `_db_lock`），属于用不必要的耦合换一个当前不存在的需求
- **回灌做成显式运维动作、不自动跑**：dead-letter 的语义本就是"停止自动重试并保留证据"（`_mark_dead_letter:212-223` + `_get_unsynced_entries:232` 的 `dead_letter = 0` 过滤），自动复活会让第七十七批修好之前那批坏批次无上限重放；把决定权交给看到 `sync-status` 数字的人
- **新端点不加端点内校验**：与第六十四批口径一致，`plugin_admin` 的鉴权只在 `app/main.py:176` 的 router 注册处（`tenant_dependencies` = internal token + 可验证租户），新 2 条与既有 8 条同档，由参数表统一钉住

#### 验证
- 红色先行分两轮取证（生产代码与配置均未改时）：
  - 第一轮 **13 例红**——`test_plugin_audit.py` 9 例（`TestRetryDeadLetters` 7 例 `AttributeError: retry_dead_letters`、compose 与 helm 各 1 例"未配置审计队列落点"）+ `test_api_contract.py` 4 例（新 2 条路由在鉴权参数表上是 404 而非 401、2 个新端点用例 404）。对照例 `test_the_module_still_honours_the_env_var` 本就该绿（模块一直读这个环境变量，缺的只是部署侧赋值），它绿在这一步恰好说明缺陷位置在配置而不在代码
  - 第二轮（把 helm 那条反向断言翻成正向、模板尚未改时）**2 例红**：`AssertionError: helm 未配置审计队列落点`、`AssertionError: 审计 PVC 应恰好一个`（`assert 0 == 1`）
- `tests/test_plugin_audit.py` 单跑 **42 passed**；与 `tests/test_api_contract.py` 同跑 **254 passed**
- Python 全量 **1866 passed / 8 skipped**（160.65s；第七十九批基线 1851 + 本批 15 个新实例 = 13 个新 `def test_` + 2 个新鉴权参数，零回归）
- `ruff check app tests`（0.16.3，`.venv` 内）**All checks passed**
- `scripts/static-checks.py` **全部通过**，测试计数 **Python 1719 → 1732**（README badge + 三处正文、`README_EN.md` badge、`docs/ROADMAP.md:16` 已同步）· Java 713 · 前端 101
- 两个 compose 文件仍 `yaml.safe_load` 通过（由新断言顺带验证）；Java 侧零改动；`audit.py` 既有函数签名与 flush/retry/dead-letter 语义不变，只增一个函数
- **未核验**：本机无 helm 客户端，`helm lint` / `helm template` 未跑（chart README 的 Validate 段是人工流程），新模板改动只经过文本级断言与和 `plugin-runner.yaml` PVC 写法的逐项比对

#### 遗留（不在本批范围）
1. **rollout 会留下孤儿队列目录**：Deployment 重建 Pod 时 `POD_NAME` 变，新 Pod 不接手旧目录里未同步的行——数据仍完整保存在卷上（可事后处置，比原先随镜像层消失好得多），但"退出前把队列排空"应当另批实现（SIGTERM 前 flush），那样这条遗留才真正归零
2. **新卷的写权限依赖存储类**：`_init_db` 要在 `/app/audit-queue` 下 `os.makedirs`，而 Pod 以非 root 的 `hfusionhub` 运行（`Dockerfile.python:23-26`）、chart 未设 `fsGroup`（全 chart 只有 plugin-runner 设 securityContext）——这与 `/app/uploads` 的既有假设同档，未在实集群验证
3. **同族第二处不持久路径**：`app/utils/config.py:147-149` 的 `RAG_EVALUATION_DB_PATH` 默认 `./data/rag_evaluation_runs.db`，容器 WORKDIR 是 `/app`（`Dockerfile.python:5`）→ 解析到 `/app/data`，同样不在卷上，且该键也没被任何部署配置赋值（已 grep 核实 compose/prod/helm）；评测运行历史随重建丢失，比审计队列轻，另批处理
4. **helm 渲染期的另一处悬空引用**（本批只记录未改）：`templates/python.yaml:51` 取 `.Values.python.taskQueueMode`，而 `values.yaml` 里该键挂在 `pythonAi` 下、全 chart 无 `python:` 顶级键——缺 helm 客户端，未能证实它是渲染报错还是回落到 `default "inline"`
5. 仓内其余 10 处 Java `R.fail(403,…)` 是否统一改判真实 HTTP 403
6. `docs/ROADMAP.md:16` 的 Java 703 口径

### 第七十九批（2026-10-06：旗标快照被 Java 拒绝时不再清空在用缓存——一次过期令牌不该让全平台开关静默回 default）

#### Fixed
- **`python-ai/app/utils/feature_flag.py:215-228` 在 `_fetch_all` 写缓存之前加入 `R` 信封码判定：`code != 200` 记 warning 并 `return`，`self._cache` 与 `self._last_fetch` 原样不动**。这是第七十七、七十八批同形状的第三处失明，而后果最重：`GET /api/internal/feature-flags/snapshot`（`FeatureFlagInternalController.java:41`）令牌不符时回 `R.fail(403,…)` = **HTTP 200 + 信封码 + `data:null`**，`resp.raise_for_status()`（:214）拦不住，旧写法接着算 `flags = data.get("data") or []` → **空列表**，然后照常执行 `self._cache = new_cache`（:245）与 `self._last_fetch = now`（:246）。三层后果：
  - **在用快照整体消失**——`feature_flags` 是模块级单例（:382），生产代码 **22 处调用分布在 8 个模块**（`api/runtime.py` 7、`core/agent/__init__.py` 4、`core/tools/registry.py` 4、`core/agent/react.py` 2、`core/rag/query_router.py` 2、`core/policy/guardrails.py`、`core/rag/reranker.py`、`core/rag/long_term_memory.py` 各 1），缓存一空，每个 `is_enabled` 都改走"无缓存"分支：按生产默认的 `fail_closed`（:90），`agent.write_tools.enabled` / `agent.web_search.enabled` 直接变 False，`rag.hybrid.enabled` / `rag.reranker.enabled` / `agent.enabled` / `agent.multi_agent.enabled` / `memory.long_term.enabled` 回落到 env 派生值，**五层 scope 覆盖（kb/user/tenant/environment 规则、percentage 灰度、时间窗）全部失效**——按 kb 打开的灰度会静默退回全局值
  - **重试被推迟**——`_last_fetch` 被推进后，:206 的 TTL 闸门在接下来 30 秒内让每次刷新直接 `return`，而 `_trigger_background_refresh`（:187-194）仍会为每次 miss 起一个立刻返回的守护线程
  - **零信号**——只留一行 `debug "Feature flags refreshed: 0 flags"`（:247）；而 except 分支的文案（:249 `using stale cache`）恰恰说明设计意图就是保留旧快照，只是这条路径不抛异常，所以那次"保留"从未发生
- **诚实边界（本缺陷不是安全豁免）**：`MUST_ENFORCE_FLAGS`（护栏总开关与 `approval.required_for_write`）在无缓存时降级为 **True**，即仍处强制方向，未知旗标也 fail-closed（`policy.admin_bypass_approval`，`core/tools/registry.py:1057` → False）。受损的是**能力旗标与灰度配置的正确性/可用性**，以及一次配置故障能不能被归因
- **`_fetch_all:216-217` 把"HTTP 200 但 body 不是 JSON 对象"也归入拒绝**（抛 `ValueError` 交 except：保留缓存 + warning），与前两批同一口径——失明不止 403，网关改写成正文非 `R` 对象的 200 同样不能当成"零旗标"

#### Added
- **`python-ai/tests/test_feature_flag.py`：`TestSnapshotRejectionKeepsStaleCache` 10 例（净 +10）**
  - 拒绝路径 6 例：缓存不被清空；`fail_closed` 下 `is_enabled("agent.write_tools.enabled")` 仍读到旧快照的 **True**（这条是"能力被静默关掉"的直接反证）；`_last_fetch` 不推进；拒绝必须记 **WARNING** 且文案含 `403`；非 force 的连续两次调用**都要**打网络（重试次数 2，钉住 TTL 闸门不被拒绝污染）；缺 `code` 键的 200 正文按拒绝处理
  - 对照组 4 例（防修复过度）：`code=200 + data=[]` 仍**清空**缓存并推进 `_last_fetch`（合法空快照不是故障）；成功快照正常填充并可读；真 HTTP 500 保留缓存 + warning；200 + body 不可解析保留缓存 + warning
- **`_FakeSnapshotResponse` / `_UnparseableSnapshotResponse` / `_client_with_flags` 替身**：按 Java `R` 三件套（`code`/`message`/`data`）构造，`raise_for_status()` 抛真实 `httpx.HTTPStatusError`（而非任意异常），URL 走 `http://java:8080/api/internal/feature-flags/snapshot`
- 本模块此前 **`_fetch_all` 零覆盖**：全仓 `grep "_fetch_all|force_refresh"` 除定义处无任何命中，两个既有旗标测试文件只测评估逻辑与"无缓存降级"分支。没有带 `code` 的 fake 就没有 seam，这是该缺陷能长期存活的原因（与第七十六/七十七/七十八批同形：**消费侧的信封失明总是先在测试替身上失明**）

#### 决策记录
- **保留旧快照而不是抛异常**：`_fetch_all` 跑在后台守护线程（:193）里，向上抛只会变成线程未捕获异常打印，而它的消费方 `is_enabled` 的正确语义本就是"拿不到新快照就用旧的"。所以拒绝路径的处理是 `warning` + `return`，把 `_cache`/`_last_fetch` 完整留给下一个周期——与第七十八批"写入被拒要向上抛"相反，因为那里的调用方需要知道没存进去，这里的调用方在另一条线程上
- **不改 Java 侧 `R.fail(403,…)`**（`FeatureFlagInternalController.java:41`）：与第七十七批同因，消费侧读码才覆盖"HTTP 200 但非成功信封"整类；该文案的 12 处里除第七十五批收口的 2 处外仍有 **10 处**（清单见第七十五批决策记录），统一改判真实 HTTP 状态属跨面口径工程，另批处理
- **判定只认信封码，不认 `data` 是否为空**：`code=200 + data=[]` 是"平台确实没配置旗标"的真实状态，若一并保留旧缓存就会把已删除的旗标永久钉在使用位上；这条边界由对照组钉死
- **未顺手改**：`docs/ROADMAP.md:16` 的 Java 703 口径（本批只按 static-checks 要求同步 Python 计数）

#### 验证
- 红色先行：10 例对 **HEAD 版本**的 `feature_flag.py`（改前 `git diff --stat` 该文件为空）跑 → **6 failed / 36 passed**，失败信息即缺陷痕迹：`assert 'agent.write_tools.enabled' in {}`、`assert False is True`、`assert 1791265856.6619103 == 0.0`、`AssertionError: 被 Java 拒绝却只记 debug，线上等同于静默` / `assert []`、`assert 1 == 2`
- `tests/test_feature_flag.py` + `test_feature_flag_degradation.py` **53 passed**（42 → 53，净 +10；11 例既有降级用例零改动仍绿）
- Python 全量 **1851 passed / 8 skipped**（160.63s；第七十八批基线 1841 + 本批净 +10，零回归）
- `ruff check app tests`（0.16.3，`.venv` 内）**All checks passed**
- `scripts/static-checks.py` **8/8**，测试计数 **Python 1709 → 1719**（README badge + 三处正文、`README_EN.md`、`docs/ROADMAP.md:16` 已同步）· Java 713 · 前端 101
- 消费面零改动：`is_enabled` / `_evaluate` / `_scope_matches` / 五层优先级 / 三种降级模式（:90）的签名与语义全部不变，改的只是 `_fetch_all` 写缓存的**前置条件**

#### 遗留（不在本批范围）
1. `audit.py` 历史 `dead_letter` 行的回灌（第七十七批遗留，需活库按 `get_sync_status()["dead_letter"]` 定量）
2. 仓内其余 10 处 Java `R.fail(403,…)` 是否统一改判真实 HTTP 403（第七十五批只收口了 `EvalHarnessInternalController` 的 2 处）
3. `docs/ROADMAP.md:16` 的 Java 703 口径

### 第七十八批（2026-10-06：长期记忆不再把 Java 的拒绝读成"这用户没记忆"——两个消费点改读信封码）

#### Fixed
- **`python-ai/app/core/rag/long_term_memory.py:55-80` 新增 `MemoryBackendRejected(RuntimeError)` 与 `_r_envelope_data(resp, endpoint)`，`:140`（读）与 `:239`（写）两条 Java 出站链路从 `resp.json().get("data") or …` 改为先读信封码再取 `data`**。`GET /api/internal/memory/relevant`（`InternalMemoryController.java:105-107`）与 `POST /api/internal/memory/entries`（:51-53）令牌不符时回 `R.fail(403,…)` = **HTTP 200 + 信封码**，`raise_for_status()` 拦不住；旧写法在 `data` 缺键时回落成 `[]` / `{"saved": 0}`，于是：
  - 读侧——`build_memory_context` 得到空列表，表现为"这个用户没有长期记忆"，而真实原因是内部 token 配置不对，**每个用户的记忆同时消失却无人知晓**
  - 写侧——`consolidate_conversation:271-273` 照样打 `info` 日志"extracted=N saved=0"，把一次鉴权故障记成一条数据事实（抽取成功、只是没存进去），Java 侧收到的响应体也是 `{"saved": 0}`
- **`build_memory_context:166-175` 的降级保留、但分级改掉**：`MemoryBackendRejected` 走 **warning**，其余异常（网络抖动、超时）仍是原来的 debug 降噪。返回空串这件事不变——记忆注入是尽力而为，不该因为 Java 不可达就打断回答；变的是"这条到底为什么是空"必须可归因
- **`_r_envelope_data` 对"HTTP 200 但 body 不是 JSON"同样抛错**（反代/网关改写、空响应），与第七十七批 `audit.py:_is_sync_accepted` 同一口径：失明不止 403

#### Added
- **`python-ai/tests/test_long_term_memory.py`：`TestJavaRejectionIsNotMaskedAsEmpty` 8 例（净 +8）**
  - 两条拒绝链路的**必抛错**（`fetch_relevant`、`persist_entries`，断言异常文案同时含 `403` 与 Java 的原样 message）
  - 两条**对照组**：`code=200 + data=[]` 与 `code=200 + saved=0` 是真·空、真·零，不得抛错——否则修复会从"伪装成功"翻车成"把空数据当故障"
  - 日志分级三例：被拒 → WARNING 且文案带 403；body 不可解析 → WARNING；`connection refused` 这类传输失败 → **不得**出现 WARNING（守住"不把降级路径变成告警风暴"）
  - 串联一例：`consolidate_conversation` 在写入被拒时向上抛，而不是返回 `{"saved": 0}` 让 `info` 日志把它说成"抽取到 1 条、保存 0 条"
- **`FakeResponse` 由"裸 payload"改为按 Java `R` 信封构造**（`__init__(data, *, code=200, message="success", status_code=200)`，9 处调用点随之收形），并补 `UnparseableResponse`（`json()` 抛 `ValueError`）。这一步是本批能做干净的前提：旧替身写成 `FakeResponse({"data": []})`，**根本不携带 `code`**，所以消费侧对信封码失明在测试里永远不可见——与第七十七批那个没有 `.json()` 的 `SimpleNamespace` 是同一种缺陷形状

#### 决策记录
- **新增异常类而不是直接抛 `RuntimeError`**：`build_memory_context` 需要把"Java 说不了"与"联系不上 Java"分开记日志，靠 message 匹配既脆也脏；`MemoryBackendRejected` 继承 `RuntimeError`，因此所有只认 `RuntimeError` 的上游（`_safe_consolidate:319-323` 的 warning、FastAPI 端点的 500、`react.py:_safe_memory_context` 的兜底 except）行为不变
- **Java 侧这 4 处 `R.fail(403/400/500)` 不改真实 HTTP 403**：与第七十七批同因——消费侧读码才覆盖"200 但 body 不是成功信封"整类；且 `relevant` 的 `R.fail(500,…)`（:115）一旦变真实 500，`raise_for_status` 抛错会让整轮对话的记忆注入直接失败，而它现在选择的是降级为空。改判状态码属于跨面口径统一，需要单独一批
- **可见行为的两处变化（都是刻意的）**：① `/api/internal/memory/consolidate` 在 Java 拒绝时从 `200 {"saved":0}` 变成 500——调用方 `AiClient.consolidateMemoryOnConversationDeleted`（:1262，出站 :1277-1280，`catch (Exception)` 后 `log.warn` :1281-1283）本就 fire-and-forget，不受影响，且 500 比"保存了 0 条"诚实；② 后台每 N 轮触发路径不变，异常仍由 `_safe_consolidate` 收敛成 warning
- **未顺手改的同族站点**：`utils/feature_flag.py:214-234` 形状一模一样（`raise_for_status` + `data.get("data") or []`），而它被拒时把 `self._cache` 整体替换成 `{}`、还照常推进 `_last_fetch`——**令牌一失效，全平台开关静默回到 default，且 except 分支的"using stale cache"文案恰恰说明它本该保留旧缓存**。这是独立且更大的blast radius，另起一批

#### 验证
- 红色先行：新 8 例对 **HEAD 版本的生产代码**跑 → **5 failed / 19 passed**（另外 3 例是对照组与既有行为守护，本就该绿）。失败里直接可见伪装痕迹：`DEBUG … long-term memory fetch failed (degraded to empty): Expecting value: line 1 column 1 (char 0)`——一次契约破坏只留下一行 debug
- `tests/test_long_term_memory.py` **24 passed**（16 → 24，净 +8）
- Python 全量 **1841 passed / 8 skipped**（159.33s；第七十七批基线 1833 + 本批净 +8，零回归）
- `ruff check app tests`（0.16.3，`.venv` 内）**All checks passed**
- `scripts/static-checks.py` **8/8**，测试计数 **Python 1701 → 1709**（README badge + 三处正文、`README_EN.md`、`docs/ROADMAP.md:16` 已同步）· Java 713 · 前端 101
- Java 侧零改动；`fetch_relevant` / `persist_entries` / `build_memory_context` 的签名与返回类型不变，`is_enabled` 门控、category→type 映射、超长截断、重要性钳制、每 N 轮触发等既有契约全部由原有用例继续钉住

#### 遗留（不在本批范围）
1. `utils/feature_flag.py:214-234`：拒绝时清空快照而非保留旧缓存（见决策记录），建议下一批优先处理
2. `audit.py` 历史 `dead_letter` 行的回灌（第七十七批遗留）
3. `docs/ROADMAP.md:16` 的 Java 703 口径

### 第七十七批（2026-10-06：插件审计同步的两处盲区一起收——被拒批次不再谎报"已同步"，出站地址归一到 `config.JAVA_BACKEND_URL` + `/api`）

#### Fixed
- **`python-ai/app/core/plugin/audit.py:337-359` 新增 `_is_sync_accepted(resp)`，两条出站链路（批量 `_post_to_java_backend_batch:379`、逐条 `_post_to_java_backend:408`）的判定从"只看 `resp.status_code == 200`"改为"状态 200 **且** 信封 `code == 200`"**。它们打的 `POST /internal/plugin/audit-logs`（`InternalPluginController.java:99-104`）令牌不符时回 `R.fail(403,…)`，即 **HTTP 200 + 信封码**（第七十五批已把这条形状钉成仓内共识），旧判定因此返回 True → `_do_flush`（:296-312）把整批 `_mark_synced`，条目从本地队列**永久摘除**：不重试、不进 dead-letter、日志还写"审计日志已同步到 Java 后端: N 条"。后果是插件 install/enable/disable/uninstall/工具执行审计**双侧同时丢失**（Java 从未落库、Python 也不再留存）且零告警——比第七十五批那条评估摘要更重，因为它把唯一副本也删了
- **顺带把"解析不出信封"纳入未同步**：非 JSON、反代改写成的 HTML、空 body 一律 fail-closed（:348-352），保留 `_increment_retry` 与 `_MAX_RETRIES = 5` 的 dead-letter 语义；这三类在 HTTP 层都是 200，旧代码同样判成"已同步"。非 200 状态保持原 warning + `resp.text[:200]`（:345-347）
- **`audit.py:366,394` 的出站地址从 `os.environ["JAVA_BASE_URL"]`（默认 `http://localhost:8080`）改为 `config.JAVA_BACKEND_URL`，`:55` 的端点常量补上 `/api` 前缀（现为 `/api/internal/plugin/audit-logs`）**。这是同一对函数里的第二个独立成因，与上面的判定缺陷不同：旧键**从未被部署侧赋值**——`python-ai/.env:29`、`docker/docker-compose.yml:301,354`、`deploy/docker-compose.prod.yml:228`、`deploy/helm/hfusionhub/templates/python.yaml:52` 配的都是 `JAVA_BACKEND_URL`（四处均按变量名核对，未取值）；而 `JAVA_BASE_URL` 是**前端 Playwright e2e 的变量**（`hfusionhub-frontend/e2e/helpers.ts:3`、`e2e/fixtures/base.ts:10`，默认 `http://localhost:8080/api`，由 `.github/workflows/e2e.yml:130,269` 注入），python-ai 借了这个名字却配了一条不带 `/api` 的路径，而 Java 的 `server.servlet.context-path` 正是 `/api`（`application.yml:3-4`）。结果：容器里主机名与路径双错、开发机默认值下少 `/api`，**审计同步在任何环境都从未成功过**——404 命中状态码分支，所以这里不撒谎，只是每条审计重试 5 次后进 dead-letter。仓内 Python→Java 内部出站共 **9 处**读 `config.JAVA_BACKEND_URL`（`app/utils/config.py:62`）并自带 `/api/...`：`api/eval_harness.py:66`、`core/llm/model_gateway.py:281`、`core/plugin/quota.py:33`、`core/rag/long_term_memory.py:98,191`、`core/tools/execution_token.py:50`、`core/tools/registry.py:72`、`core/tools/write_note_tool.py:72`、`utils/feature_flag.py:112`；本批把最后一个例外并入该口径

#### Added
- **`python-ai/tests/test_plugin_audit.py`：`TestBackendSyncEnvelopeJudgement` 5 例（净 +5）**——批量信封 403 → False、逐条信封 403 → False、**被拒批次留在队列**（`flush_to_backend() == 0` 且 `get_sync_status()["unsynced"] == 1`，这条才是"永久摘除"缺陷的直接反证）、503 → False、200 + body 不可解析 → False
- **`TestBackendSyncAddress` 3 例（净 +3）**：两条链路各用**诱饵环境变量** `JAVA_BASE_URL=http://decoy:9999` 跑一次，断言 URL 恰等于 `http://java-backend:8080/api/internal/plugin/audit-logs` 且不含 `decoy`——旧代码实测产出 `http://decoy:9999/internal/plugin/audit-logs`，键选错与缺 `/api` 在同一条断言里一起暴露；第 3 例用 `inspect.getsource(audit)` 断言 `JAVA_BASE_URL` 已从审计模块消失（防回潮，避免有人"两处都读、取其一"改回去）
- **两个信封 fixture `_rejected_response` / `_accepted_response`（:216-232 起）按 Java 真实形状构造**（拒绝：`{"code":403,"message":…,"data":null}`；接受：`{"code":200,"data":{"inserted","skipped","total"}}`，对应 `InternalPluginController.java:172-175`）。同时把 `TestBackendSyncToken` 两例原先的 `SimpleNamespace(status_code=200, text="")` 换成 `_accepted_response(MagicMock())`——那个假响应**没有 `.json()`**，正是旧判定能自证清白的原因；新 fixture 下两例仍须 patch `httpx.post`（而非被测函数本身）才测得到真链路
- **两例既有 token 测试的 URL 断言由 `endswith("/internal/plugin/audit-logs")` 收成全等**（:184、:202）——`endswith` 对一条缺 `/api` 的地址同样成立，正是它让地址缺陷在测试里隐形

#### 决策记录
- **选"Python 侧读信封码"，不选"Java 侧改真实 403"**（第七十五批走的那条）：① 本批弱点不止 403，还包括任何"HTTP 200 但 body 不是成功信封"（网关/反代改写、空响应），改 Java 状态码修不了这些；② 与第七十六批 `container_runner.py:209-211` 同口径，插件面两条出站链路判定一致；③ 不动 Java 就不触碰其余 10 处 `R.fail(403)` 站点的既有契约，改动面收敛在一个文件；④ 本仓同类判定已有先例可循：`core/plugin/quota.py:48-51` 状态与信封双判、`core/tools/write_note_tool.py:86-91` 先 `is_error` 再判 `code`、`core/tools/registry.py:77-78` 按 `code == 200` 才取 `data`、`core/llm/model_gateway.py:296` 用 `RuntimeError` 表达"Java 后端拒绝"，而 `core/rag/long_term_memory.py:112` 只看 `data`（码失明，另记为候选）
- **不读 `inserted/skipped/total` 参与判定**：Java 对重复条目 `skipped++`（`InternalPluginController.java:133,167`）是正常幂等，若把 `inserted == 0` 判成失败会造成永远重试、条目最终被 dead-letter；本批只回答"Java 是否接受了这次调用"，计数留给后续可观测性
- **地址缺陷并入本批（用户选 A）而非另起一批**：两处缺陷同在 `_post_to_java_backend_batch` / `_post_to_java_backend` 这同一对函数里，且**只修判定会让本批交付一个"失败不再撒谎、但同步依旧不可能成功"的半成品**——测试会钉住"被拒不谎报"，却仍没有任何一条审计能落到 Java。这与第七十六批"两个不相关的插件写路径不进同一提交"不冲突：那条规则针对的是**跨函数的范围膨胀**，此处是同一对函数的两个成因，改的是同一处 `java_url` 赋值
- **`JAVA_BASE_URL` 这个键保留、e2e workflow 不动**：它仍被前端 Playwright e2e 正当使用（`e2e/helpers.ts:3`、`e2e/fixtures/base.ts:10`），`.github/workflows/e2e.yml:130,269` 的注入是对的，只是 python-ai 不该读它。改动严格限定在 `python-ai/app/core/plugin/audit.py`，不触碰 CI 配置面

#### 验证
- 红色先行分两轮：
  - **判定缺陷**：5 例新测试对未改动的生产代码 → **4 failed / 24 passed**。第 5 例（503）在旧代码下即通过，它钉的是"别把状态码分支弄丢"，属既有行为保留而非回归；4 个红点正是三条新链路（批量 403、逐条 403、批次被拒仍留在队列）与不可解析 body
  - **地址缺陷**：URL 断言收成全等 + 新增 3 例后，对未改动的生产代码 → **5 failed / 26 passed**，失败原文为 `assert 'http://decoy:9999/internal/plugin/audit-logs' == 'http://java-backend:8080/api/internal/plugin/audit-logs'`——一条断言同时坐实"读错了键"和"少了 `/api`"
- `tests/test_plugin_audit.py` **31 passed**（23 → 31，净 +8）
- Python 全量 **1833 passed / 8 skipped**（159.63s；第七十六批基线 1825 + 本批净 +8，零回归）
- `ruff check app tests`（0.16.3，`.venv` 内）**All checks passed**
- `scripts/static-checks.py` **8/8**，测试计数 **Python 1693 → 1701**（README badge + 三处正文、`README_EN.md`、`docs/ROADMAP.md:16` 已同步）· Java 713 · 前端 101；其中"内部契约锚点 5 处"不含本端点（锚点表覆盖 `internal_auth.py` / `vectorization.py` 等），故路径加 `/api` 不影响门禁
- Java 侧与部署侧零改动；`_post_to_java_backend*` 的签名与返回类型 `bool` 不变，`_do_flush` 的批量→逐条回退、`_increment_retry`、dead-letter 路径均未动。对外变化只有两件事：**什么算同步成功**，以及**请求打到哪个 URL**

#### 遗留（不在本批范围）
- **历史 dead-letter 存量不追溯回灌**：地址缺陷使历史审计长期 404 → 重试 5 次 → `audit_queue.dead_letter = 1`（:212-223），而 `_get_unsynced_entries` 的过滤是 `synced = 0 AND dead_letter = 0`（:231-232），所以这些行**永不再自动重试**。本批只保证新条目从此能同步；存量规模上线后读 `get_sync_status()["dead_letter"]`（:523-531）即可量化，是否回灌属数据修复，列为下一批候选

### 第七十六批（2026-10-06：修掉 fetch_plugin_versions 的信封迭代缺陷——灰度插件执行此前必失败）

#### Fixed
- **`python-ai/app/core/plugin/container_runner.py:208-226`：`fetch_plugin_versions` 不再把 Java 的 `R<List<Map>>` 信封当列表迭代**。`GET /api/internal/plugin/{pluginId}/versions` 由 `InternalPluginController.java:53-65` 返回 `R<List<Map<String,Object>>>`，即 `{"code":200,"message":"success","data":[...]}`，而旧代码 `data = resp.json()` 后直接 `for v in data`——迭代字典得到 `"code"/"message"/"data"` 三个字符串键，`v["version"]` 立即抛 `TypeError: string indices must be integers`（`container_runner.py:212` 旧行号），于是 `execute_with_canary`（:321-330）每次都兜成 `error_code="version_fetch_failed"`，**灰度路由下的插件执行整条路不可用**，且与 token、插件状态无关
- **同一处补上"拒绝"判定**：Java 内部面的拒绝（403 令牌、404 插件不存在）是 **HTTP 200 + 信封码**，`resp.raise_for_status()` 拦不住，旧代码会一路走到迭代、以 `TypeError` 面目出现。现按 `envelope.get("code") != 200` 抛 `RuntimeError`（带 `code` 与 Java 的 `message`），让调用方日志里的 `version_fetch_failed` 说的是真因；本仓同类出站已有先例可对照——`registry.py:79` 按 `code == 200` 取数、`quota.py:48-57` 状态与信封双判、`write_note_tool.py:87-90` 先判状态再判码，`model_gateway.py:296` 则用 `RuntimeError` 表达"Java 后端拒绝"
- **字段名不需要改**：`PluginServiceImpl.java:465-471` 写的是 `LinkedHashMap` 显式键 `version` / `container_image` / `image_digest` / `canary_weight` / `status`（snake_case），与 Python 侧读的一致；`is_stable` 依赖的 `status` 是 `VARCHAR(20) NOT NULL DEFAULT 'active'`（`V29__tool_plugin_sandbox.sql:21`），`== "active"` 的口径成立

#### Added
- **`python-ai/tests/test_plugin_container.py`：`TestFetchPluginVersions` 由 1 例假守护改为 3 例真缝测试（净 +2）**
  - 旧例 `test_fetch_parses_correctly` 用 `patch("...container_runner.fetch_plugin_versions", new=_mock_fetch)` **把被测函数本身换掉**，`_mock_fetch` 里重抄了一遍同样的解析逻辑、喂的是**裸列表**，所以断言永远为真、缺陷永远看不见——这是"测试替身盖住被测对象"的典型
  - 现改为 patch `app.core.plugin.container_runner.get_shared_client` 返回一个 `AsyncMock` 客户端（`.get` 给出 `raise_for_status()` 空操作、`.json()` 给出信封），驱动**真实函数**：`test_parses_the_java_envelope_rows`（两行版本，校 `version`/`container_image`/`canary_weight` 与 `is_stable` 的两种取值）、`test_empty_version_list_is_not_an_error`（`data: []` → `[]`，仍走调用方的 `no_version` 而非报错）、`test_envelope_rejection_raises_with_the_java_reason`（403 与 404 两码 → `RuntimeError` 且文案含该码）
  - 另在文件头部的 `from app.core.plugin.container_runner import (...)` 补 `fetch_plugin_versions`——旧例从不 import 它，正是它能自证清白的原因

#### 决策记录
- **拒绝时抛错而非返回空列表**：`execute_with_canary` 把"抛错"报成 `version_fetch_failed`、把"空列表"报成 `no_version`（:321-340）。令牌不对若返回空列表，日志会谎称"这插件没有可用版本"，把配置问题伪装成数据问题；抛错保留真因，且两条路径都是 fail-closed
- **不给 `canary_weight` 为 NULL 加兜底**：`float(v.get("canary_weight", 0))` 在值为 `None` 时会抛（列是 `DECIMAL(3,2) DEFAULT 0.00`，`V30__plugin_container_isolation.sql:7` 可空），但 `ALTER TABLE ... DEFAULT` 会回填既有行、新建路径也都带该列，构造不出 NULL 场景；本批不写一个无法用测试落地的分支，若线上真出现再按数据修复处理
- **不顺手改 `audit.py` 的同族缺陷**：`app/core/plugin/audit.py:354,386` 两条审计同步路径同样只判 `resp.status_code == 200` 就返回"已同步"，而它打的 `POST /internal/plugin/audit-logs`（`InternalPluginController.java:100-104`）正是 `R.fail(403,…)` 站点之一——token 不匹配时整批插件审计被标记 synced 后从本地队列永久摘除，比丢一条评估摘要更重。已在第七十五批的审计更正里记为下一批候选；本批只做 `fetch_plugin_versions`，因为两者的修法选择（Java 侧改真实 403 vs Python 侧加码判定）需要一起定口径，混在一批里会把插件面两个不相关的写路径捆进同一个提交
- **全仓"直接迭代 `resp.json()`"已穷尽**：按 `= resp.json()` 后接 `for ... in <该变量>` 与 `for ... in resp.json()` 两种形态 grep，仅剩 `app/core/rag/long_term_memory.py:112-114` 命中，而它写的是 `.get("data") or []`（形状正确，其弱点是信封码失明，另记）

#### 验证
- 红色先行：3 例新测试对**未改动的生产代码**跑 → `3 failed`，失败原文均为 `TypeError: string indices must be integers, not 'str'`（`container_runner.py:212`），含"空列表"与"拒绝信封"两例——证明缺陷对任何响应形状都成立，而非只在特定数据下
- `tests/test_plugin_container.py` **36 passed / 6 skipped**（42 收集，6 为需 Docker 守护进程的集成例）；`ruff check`（0.16.3，`.venv` 内）对改动文件与被改测试文件均无告警
- Python 全量 **1825 passed / 8 skipped**（160.17s；第七十五批基线 1823 + 本批净 +2，零回归）
- `scripts/static-checks.py` **8/8**，测试计数 **Python 1691 → 1693**（README badge + 三处正文、`README_EN.md`、`docs/ROADMAP.md:16` 已同步）· Java 713 · 前端 101
- Java 侧本批零改动；`fetch_plugin_versions` 的签名、返回类型 `list[PluginVersionInfo]`、`execute_with_canary` 的 `ContainerResult` 形状均不变，变的只有"能解析出真实 Java 响应"

### 第七十五批（2026-10-06：内部面的令牌拒绝改判真实 HTTP 403——被拒的评估回调不再记成 callback ok）


#### Fixed
- **`java-backend/src/main/java/com/hfusionhub/controller/EvalHarnessInternalController.java:60,90`：令牌校验失败不再 `return R.fail(403, ...)`，改为 `throw new BusinessException(StatusCode.FORBIDDEN, 同一句文案)`**。区别不在报文而在状态行：`R` 是普通返回体，`return R.fail(403,...)` 走的是 **HTTP 200 + 信封 `code:403`**；而 `GlobalExceptionHandler.handleBusinessException`（`common/exception/GlobalExceptionHandler.java:31-42`）对 400–599 的码做 `HttpStatus.resolve` 直映射，于是同一份 `R.fail(code,msg)` 现在带 **真实 403**。响应体逐字段不变（`{"code":403,"message":"Forbidden: invalid or missing X-Internal-Token"}`），只有状态行从 200 变 403
- **修的是第七十四批决策记录里点名的那条静默数据丢失**：唯一调用方 `python-ai/app/api/eval_harness.py:_notify_java_record` 只判 `resp.status_code >= 400`（:91-93），旧形状下"内部 token 不对/未配"会被记成 `[eval-harness] Java record callback ok`，而 `eval_harness_runs` 里那一行从未写入——运维看日志以为记账成功。改判后同一场景走 warning 分支并带 `resp.text[:200]`

#### Added
- **`EvalHarnessInternalControllerTest` 9 → 12 例，其中 3 例走 `MockMvc`**：`MockMvcBuilders.standaloneSetup(controller).setControllerAdvice(new GlobalExceptionHandler())`——挂真 advice 是关键，否则单元级 `assertThrows` 只证明"抛了异常"，证明不了"调用方看到的是 403 状态行"（本仓此前只有 `tenant/CallbackSignatureRealPathTest.java:53` 用 standaloneSetup，且不带 advice）
  - `invalidTokenRejectsWithARealHttp403NotADefault200`：错 token + 合法租户头 → `status().isForbidden()` + `jsonPath("$.code") == 403` + `insert` 零调用（本批的红色例）
  - `missingTenantHeaderRejectsWithARealHttp403`：第七十四批的租户拒绝同样钉到状态行层——它在改动前即通过，正好独立复核了 `BusinessException → 真实 403` 这条映射链在本仓成立
  - `acceptedCallbackStillReturnsHttp200WithOkEnvelope`：放行路径仍是 200 + `code:200` + `data.recorded == true`，防"收紧拒绝面时顺手改坏成功形状"
  - 原 `invalidTokenIsRejectedBeforeTenantValidation` 从"断信封 code"改为断 `BusinessException` 的 code **与 message**——令牌无效且租户头也缺时，回的是令牌那句，把"先认身份再认租户"的顺序契约钉得更死

#### 决策记录
- **只改这 2 处，不动其余 10 处同构 `R.fail(403, ...)`**：全仓该文案共 12 处、分布在 8 个内部控制器（`AgentApprovalInternalController:50`、`FeatureFlagInternalController:41`、`InternalMemoryController:52,106`、`InternalNoteController:47`、`InternalPluginController:45,56,72,104`、`InternalPluginQuotaController:44`）。逐个核了 Python 侧调用方的判法，只有 `_notify_java_record` 会把"200 + 信封 403"误判成成功：`execution_token.py:68-89` 先判状态码、再读嵌套 `data.consumed`（拒绝 → `False`，fail-closed 正确）；`quota.py:48-57` 要求 `status == 200 且 envelope.code == 200`；`registry.py:79` 按 `code == 200` 取数；`write_note_tool.py:87-90` 状态与信封双重检查。故本批不制造"同一内部面两种拒绝形状"的无谓扩散，只补真有后果的那条
  - **本条审计不完整，第七十六批补记一处反例**：当时漏了 `python-ai/app/core/plugin/audit.py:354,386`——两条审计同步路径都只判 `resp.status_code == 200` 就返回"已同步"，而它打的 `POST /internal/plugin/audit-logs`（`InternalPluginController.receiveAuditLogs`，:100-104）正是 `R.fail(403)` 那批站点之一。后果比评估摘要更重：token 不匹配时整批插件审计被标记 synced 后**从本地队列永久摘除**，不重试、不报警。修法与本批同型（要么 Java 侧改抛真实 403，要么 Python 侧加信封码判定），属插件审计面，记为下一批候选，本批结论"只补真有后果的那条"应读作"只补评估面那两条"
- **审计中顺带查到一处独立的真缺陷（本批不修，记下来）**：`container_runner.py:201-218 fetch_plugin_versions` 对 Java `GET /api/internal/plugin/{pluginId}/versions` 的响应做 `data = resp.json()` 后直接 `for v in data`，而该端点回的是 `R<List<Map>>` 信封（`InternalPluginController.java:53-65`）——迭代字典得到 `"code"/"message"/"data"` 三个字符串键，`v["version"]` 必抛 `TypeError`。调用方 `container_runner.py:321-330` 把它兜成 `error_code="version_fetch_failed"`，所以是"灰度插件执行整条路必失败"而非静默错数据；守护它的 `tests/test_plugin_container.py:481-514` 用 `patch(fetch_plugin_versions, new=同一套解析逻辑)` 把被测函数本身替换掉了，且喂的是**裸列表**，因此从未见过真实形状。修复属插件面，与本批评估面不同轨，留作单独一批 **（已由第七十六批收口，其守护测试同时改为打真 HTTP 缝）**
- **仍然存在的下一处弱点（本批未修）**：`InternalMemoryController` 的两个读端点被 Python 以 `resp.raise_for_status()` + `.get("data") or []` 消费（`app/core/rag/long_term_memory.py:111-112,205`），HTTP 200 + 信封 403 时表现为"记忆为空"而非"被拒"——不会谎报成功，但会把鉴权失败伪装成正常的无数据。改它要连带 Python 侧改成区分信封码，且本仓无该面的契约测试，故单列
- **不改方法返回类型为 `ResponseEntity<R<...>>`**：那会改动 2 个 `@Hidden` 端点的签名与 OpenAPI 形状，而 `BusinessException` 路径的响应体与旧 `R.fail` 逐字段相同、只换状态行，是更小的刀口；也顺带与本批已用的租户拒绝形状统一
- **CI 与浏览器面均不经这条路**：`.github/workflows/eval-nightly.yml:130` 的语料导入走 `POST /api/demo/import-corpus`（`satoken`，`DemoController.java:50`），:142 打的是 Python 的 `/api/eval-harness/run`，全流程没有一处 curl `/internal/eval-harness/**`；`docs/api.md`、`docs/ACCESS_MAP.md` 亦无该内部面对外形状的描述，无文档需要跟改

#### 验证
- 红色先行：3 个 MockMvc 例与改写后的顺序例，对**未改动的生产代码**跑 → `Tests run: 12, Failures: 2`，失败原文即 `Status expected:<403> but was:<200>`（令牌例）与 `Expected BusinessException to be thrown, but nothing was thrown`；租户 403 例与成功例改动前即通过
- 改后 `EvalHarnessInternalControllerTest` **12/12**；Java 全量 `mvn -o test` **BUILD SUCCESS，Tests run 711 / Failures 0 / Errors 0 / Skipped 52**（第七十四批 708 + 本批 3，零回归）
- `scripts/static-checks.py` **8/8 通过**，测试计数 **Java 710 → 713**（README badge + 三处正文、`README_EN.md` 已同步）· Python 1691 · 前端 101
- Python 侧本批零改动（`_notify_java_record` 一行未动，它的 `status_code >= 400` 分支正是本批要喂真的那条）
- 生产改动 1 个文件的 2 行（+ 类 javadoc 说明形状），测试文件 +3 例；两处路径、请求体、成功响应体、拒绝响应体文案均不变，仅状态行 200 → 403

### 第七十四批（2026-10-06：内部评估回调面删掉默认租户——缺头改判 403，不再记到 tenant 1 名下）

#### Fixed
- **`java-backend/src/main/java/com/hfusionhub/controller/EvalHarnessInternalController.java`：`record` 与 `import-corpus` 两个内部端点不再把租户/用户默认成 1**。旧实现两处都是 `@RequestHeader(value = "X-Tenant-Id", defaultValue = "1")`（原 :55、:90）+ `catch (NumberFormatException) { tenantId = 1L; }`（原 :62-65、:97-103），`import-corpus` 的 `X-User-Id` 同构（原 :91）。这个默认值之所以是 fail-open 而非便利：`/internal/eval-harness/**` 同时被排除在 Sa-Token 登录白名单与租户拦截器的 `excludePathPatterns` 之外（`SaTokenConfig.java:42,115`），内部 token 是该面唯一守卫，头里的租户是**唯一**归属依据——缺头或写了非数字时，`TenantContext.runAs(1L, ...)`（原 :79、:106）会把评估摘要 / 整批语料文档记进 tenant 1 的分区，调用方却拿到 `R.ok`。现改为 `required = false` + 统一校验 `requirePositiveId(...)`：strip 后为空、非数字、或 `< 1` 一律 `BusinessException(StatusCode.FORBIDDEN, 头部名与原值)`，且校验排在 `evalHarnessRunMapper.insert` / `evalCorpusImportService.importCorpus` **之前**（令牌守卫仍最前，保持"先认身份再认租户"的原有顺序）

#### Added
- **`java-backend/src/test/java/com/hfusionhub/controller/EvalHarnessInternalControllerTest.java`（新文件，9 例）**——该控制器此前**零 Java 测试**
  - `record`：缺头 / 纯空白 / `"seven"` / `"0"` / `"-3"` 四种入参各断 `BusinessException` + `StatusCode.FORBIDDEN` + `insert` 零调用（前四种是旧代码会静默写入的路径，`"0"`/`"-3"` 是旧代码会照收并 `runAs(0)` 的路径）
  - `record` 正向：`X-Tenant-Id: 7` 时，在打桩的 `insert` 内部读 `TenantContext.requireTenantId()` 必须为 7（证明租户上下文真在建行前建立），并按 `ArgumentCaptor` 校 `run_file` / `record_count` 落进实体
  - `import-corpus`：缺 `X-Tenant-Id` 或缺 `X-User-Id` 各一例（`importCorpus` 零调用）；正向例设外层 `TenantContext` 为 99、调用后要求**还原成 99**——`runAs` 必须回滚而不是留下 9 给同线程后续工作
  - 令牌无效 + 缺租户头时返回 `R.fail(403)` 而不抛 `BusinessException`，把"校验顺序"钉住
  - 打桩口径沿袭第七十三批：`mock(EvalHarnessRunMapper)` + `mock(EvalCorpusImportService)` 走构造注入，`ReflectionTestUtils` 注 `expectedToken`，`@AfterEach TenantContext.clear()`

#### 决策记录
- **回 403 而非 400（第七十二批记的待定项）**：与本仓自己的两处口径一致——`TenantContextInterceptor.rejectNoTenant`（:201-205）用 `SC_FORBIDDEN` + `"Tenant context required but not resolved"`，本类原有的令牌守卫也回 403；Python 侧 `TenantMiddleware` 用 400，是因为它面对全部入站流量、把"头值不合法"当请求问题。这里缺租户不是形状错误而是"无法为任何租户授权写入"。选 `BusinessException` 而非继续 `R.fail(403, ...)` 有实际后果：`GlobalExceptionHandler.handleBusinessException`（:31-42）会把 400–599 的码映射成**真实 HTTP 状态**，于是 Python 的 `_notify_java_record`（只判 `resp.status_code >= 400`，`python-ai/app/api/eval_harness.py:91-93`）能看见拒绝并打 warning；而 `R.fail(403,...)` 是 HTTP 200 + 信封码，会被记成"callback ok"
- **`X-User-Id` 一并收紧（略超出"租户"字面范围）**：它与租户头共用同一个 `try/catch`，只收紧租户会留下"语料静默归到 user 1"这半条 fail-open；且二者同构，同一个 `requirePositiveId` 覆盖，无额外分支。若你希望本批只动租户，回退这一处是独立的两行
- **现网影响面已核**：`/record` 唯一调用方是 Python `_notify_java_record`（第七十二批起恒带真实租户，`.github/workflows/eval-nightly.yml:142` 显式发 `X-Tenant-Id: 1` 也照旧通过）；`/internal/eval-harness/import-corpus` 在本仓**无调用方**——全仓 grep 只有 CI 的浏览器路径 `/api/demo/import-corpus`（`eval-nightly.yml:130`，带 `satoken`，走 `DemoController.java:50`，不经本类）。风险仅剩仓外初始化脚本若曾省略这两个头，将从"记到 1"变成"403 拒绝"，这正是本批想要的 fail-closed
- **令牌拒绝仍是 HTTP 200 + 信封 403**：`R.fail(403,...)` 在两条路径上都没改成真实状态码（本批不动，避免把契约测试的响应形状一并重写）。后果是 Python 把"token 不对"记成 callback ok、丢一条摘要而无人报警——留作待办 **（已由第七十五批收口：两处改抛 `BusinessException`，走真实 403）**

#### 验证
- 红色先行：新测试对**未改动的生产代码**跑 → `Tests run: 9, Failures: 6`，6 条全是 `Expected BusinessException to be thrown, but nothing was thrown`（即缺头/空白/非数字/非正数/缺 user 头五类静默路径）；改完 9/9 通过
- Java 全量 `mvn -o test` **BUILD SUCCESS，Tests run 708 / Failures 0 / Errors 0 / Skipped 52**（第七十三批 699 + 本批 9，零回归）
- `scripts/static-checks.py` **8/8 通过**，测试计数 **Java 701 → 710**（README badge + 三处正文、`README_EN.md` 已同步）· Python 1691 · 前端 101；"内部契约锚点"一项仍 5 处头名/路径两侧一致
- Python 侧本批零改动（未跑全量；无生产文件变动）
- 生产改动 1 个文件（两处签名 + 一处私有校验 helper），新增测试文件 1 个；两条路径、请求体、`R` 成功响应体与 `EvalHarnessRun` 字段映射均不变，只有"缺租户/缺用户头"的响应从 `R.ok` 变成真实 403

### 第七十三批（2026-10-06：Java 评估网关按当前租户转发——补上第七十二批上游那处写死的 "1"）

#### Fixed
- **`java-backend/src/main/java/com/hfusionhub/controller/EvalHarnessController.java:145-158`（`internalHeaders()`）：不再把 `X-Tenant-Id` 写成 `"1"`**（原第 151 行）。该控制器是浏览器 → python-ai 的纯转发网关，这组头是它所有转发（`get()` / `post()` 两条 helper）唯一的租户来源，写死意味着：登录用户属于哪个租户、平台管理员用 `X-Target-Tenant` 代管哪个租户（`TenantContextInterceptor.java:82-85,167`），到评估面全部被抹平成 tenant 1；而第七十二批之后 Python 会把收到的租户原样回传给 `/api/internal/eval-harness/record`，于是 `eval_harness_runs` 的归属也跟着错。现改为 `TenantContext.getTenantId()`，**取不到时不带该头**（与同仓既有口径 `RagObservabilityController.java:294-299` 一致）——缺上下文时 Python 的 `require_tenant` 会 400，而带回 "1" 是静默把请求塞进 tenant 1 的检索空间与记账命名下。浏览器可达的 `/eval-harness/**` 既在 Sa-Token 登录检查内、也在租户拦截器内（`SaTokenConfig.java:42,115` 只排除 `/internal/eval-harness/**`），故正常请求始终能解析出租户，本次不改任何现网可见行为

#### Added
- **`java-backend/src/test/java/com/hfusionhub/controller/EvalHarnessControllerTest.java`（新文件，4 例）**——该控制器此前**零 Java 测试**
  - GET `/runs` 与 POST `/score` 各一例：`TenantContext` 设为 7 / 3 时，出站 `HttpEntity` 头必须是 `"7"` / `"3"`，且 `X-Internal-Token` 同在——把 GET/POST 两条 helper 共用一处实现这一"同一租户口径"钉住
  - 无租户上下文时 `X-Tenant-Id` **必须缺失**而非 `"1"`——这条正是旧代码的行为差异点
  - 内部 token 未配置时抛 `BusinessException(INTERNAL_ERROR)` 且 `restTemplate` 零调用
  - 打桩只需 `mock(RestTemplate)` + `ReflectionTestUtils` 注入两个 `@Value` 字段（转发路径不经 `JwtUtils`，故不必搭 Sa-Token 上下文，对比 `RagObservabilityControllerTest` 的 `MockSaTokenContext`），并在 `@AfterEach` `TenantContext.clear()`——ThreadLocal 不清会串到后续用例

#### 决策记录
- **红色验证先行**：把那一行改回 `headers.set("X-Tenant-Id", "1")` 后重跑 → **3 例失败**（`expected: <7> but was: <1>`、`expected: <3> but was: <1>`、`expected: <null> but was: <1>`），"token 未配置" 1 例不受影响仍绿；随后从备份恢复实现。三例失败即本批契约的证据，而非靠断言自证
- **不一并改 `EvalHarnessInternalController` 的 `defaultValue = "1"`**：`record`（:55）与 `import-corpus`（:90）都用 `@RequestHeader(defaultValue = "1")` + 解析失败兜 `1L`，而 `/internal/eval-harness/**` 同时被排除于登录检查与租户拦截器，内部 token 是唯一守卫——缺头时"默认记到 tenant 1"属 fail-open，与刚修的 `internalHeaders()` 是同一问题的另一侧。不在本批动，是因为改它要先定 Java 回 400 还是 403、并核 `.github/workflows/eval-nightly.yml:142`（它显式发 `-H "X-Tenant-Id: 1"`，本身不受影响）之外的 Python 侧调用面；本批之后 Python 恒带真实租户，该默认值已从"实际生效路径"降级为"缺头兜底"，风险显著变小 **（已由第七十四批收口：两个内部端点改为缺头/非数字/非正数直接 403）**
- **不给评估网关加 `X-User-Clearance`**：`RagObservabilityController.internalHeaders()`（:284-286）会按 admin 角色带该头，本控制器不带，Python 侧走"头缺省 → `clear_clearance()`（`app/api/tenant_middleware.py:71-72`）→ `get_clearance()` 按最低权限 `general`"（`app/core/security/clearance.py:27,61-63`），是 fail-closed 一侧。评估是知识库所有者触发的运维面，收紧口径与前端无关，留待多租户 ACL 真需要时再对齐
- **`docs/ROADMAP.md:16` 的 "Java 703" 未动**：该行自注为 2026-09-08 口径的历史快照，且 static-checks 的对账只读 README badge / AGENTS.md / CLAUDE.md（后两者本仓不存在）。本批把 README 与 README_EN 同步为 701，ROADMAP 那行仍是旧数，属文档自称不一致而非测试计数漂移——是否一并刷新留给你定

#### 验证
- 新增 `EvalHarnessControllerTest` **4/4 通过**；Java 全量 `mvn -o test` **BUILD SUCCESS，Tests run 699 / Failures 0 / Errors 0 / Skipped 52**（52 为 Testcontainers 集成用例，本地无 Docker 时跳过）
- `scripts/static-checks.py` 八项全绿，测试计数 **Java 697 → 701**（README badge + 三处正文、`README_EN.md` 已同步）· Python 1691 · 前端 101。注：门禁统计的是 `@Test/@ParameterizedTest/@RepeatedTest` **注解数**，与 surefire 的"执行数"不同口径
- Python 侧本批零改动，全量套件仍是第七十二批的 1823 passed / 8 skipped
- 生产改动 1 处（`internalHeaders()` 的租户取值 + 缺上下文不带头），新增测试文件 1 个；`R` 响应体、7 个端点签名与前端 `hfusionhub-frontend/src/api/rag.ts` 调用面均不变

### 第七十二批（2026-10-06：eval_harness 出站租户改从请求上下文取——删掉写死的 tenant 1）

#### Fixed
- **`python-ai/app/api/eval_harness.py`：两条出站链路的 `X-Tenant-Id` 不再写死 `"1"`**。该常量 `TENANT_ID_HEADER = "1"`（原 :29）喂给 Java 摘要回调头，`/run` 给 runner 的自调用头里另有同字面量（原 :142）——两处各自决定一件不同的事：
  - runner 用这组头**自调用本服务**的检索/对话端点（`config.EVAL_BASE_URL`），租户决定查哪个租户的向量分区与文档；
  - Java `EvalHarnessInternalController.record`（`java-backend/src/main/java/com/hfusionhub/controller/EvalHarnessInternalController.java:55,62,79`）按回调头的 `X-Tenant-Id` 建租户上下文后才 `insert` `eval_harness_runs`。

  现 `start_run` 以 `tenant_id: int = Depends(require_tenant)`（`app/api/deps.py:16`，缺租户 400 fail-closed）取入站租户，两处出站统一用 `str(tenant_id)`，`TENANT_ID_HEADER` 删除；`_notify_java_record` 相应加一个显式形参。**当前部署行为不变**：现网三个调用方（`EvalHarnessController.java:151`、`.github/workflows/eval-nightly.yml:142`、前端经 Java）都只发 tenant 1，故出站值仍是 `"1"`；本批消除的是"调用方声明了别的租户、Python 却按 1 执行并记账"这类静默串租户

#### Added
- **`tests/test_api_contract.py` +2 用例（收集 206 → 208）**
  - `test_eval_harness_run_propagates_the_requesting_tenant_to_both_outbound_calls`：以 `X-Tenant-Id: 7` 打 `/run`，断言 runner 位置参数里的 `headers["X-Tenant-Id"] == "7"` 且 Java 回调头同为 `"7"`——把生产代码改回硬编码该用例即红（本批已实测：回退后 1 failed / 1 passed）
  - `test_eval_harness_run_without_tenant_header_fails_closed_before_running`：有效 token 但无租户头 → 400，且 `run_dataset` **零调用**（评估一跑就是真实生产链路流量，不许"先跑再拒"）
  - 第七十批两处只断言 `X-Internal-Token` 的头断言收紧为整字典相等，把租户一并钉住

#### 决策记录
- **用 `Depends(require_tenant)` 而非在函数体读 contextvar**：`asyncio.to_thread` 会复制上下文，线程里读 `get_tenant_id()` 同样取得到值，但那样租户成了"隐式全局"，`_notify_java_record` 的签名也不体现它依赖租户；显式形参让依赖在签名层可见，并复用同一处 fail-closed 守卫，新增 0 条判断分支。router 级已挂 `require_tenant`（`app/main.py:165`），端点级再声明只是取回同一个值，不改变校验顺序
- **上游 Java 侧仍有一处写死，本批不动**：`EvalHarnessController.java:151` 的 `internalHeaders()` 把 `X-Tenant-Id` 写成 `"1"`，而同仓 `RagObservabilityController.java:296-298` 已经是 `TenantContext.getTenantId()`、取不到就不带头让 Python fail-closed。改它属 Java 面且要一并核 `record`/`import-corpus` 两个内部端点的 `defaultValue = "1"` 兜底，故单列一批；Python 侧先收口，是为了让"直连内部面"的调用方（脚本、CI）传什么都不会被静默改写 **（`internalHeaders()` 已由第七十三批收口；两个内部端点的 `defaultValue = "1"` 已由第七十四批收口）**
- **对外契约零变化**：7 个端点的请求体、响应体、OpenAPI 参数均不变（`require_tenant` 无入参、读的是 header 派生的上下文），`_RunRequest` 字段不动

#### 验证
- `tests/test_api_contract.py` **208/208**（206 → 208）；`tests/test_eval_harness.py` 15/15 一并通过
- Python 全量 **1823 passed / 8 skipped**（155.62s；第七十一批基线 1821 + 本批 2 例，零回归）
- `ruff check .`（python-ai）全绿；static-checks 八项全绿，测试计数 **1689 → 1691**（README badge + 三处正文、`README_EN.md`、`docs/ROADMAP.md` 已同步）
- 生产改动集中在 `eval_harness.py`：删 1 个常量、2 处出站头取值、1 个函数形参；7 个端点的请求体/响应体/OpenAPI 参数不变

### 第七十一批（2026-10-06：test_eval_harness 的 API E2E 改走真实守卫——不再绕鉴权、不再污染仓库 data/、不再真出网）

#### Changed
- **`tests/test_eval_harness.py::test_api_runs_and_score_flow` 重写为"真实守卫 + 真实链路"**。该用例此前是仓内**唯一**用 `app.dependency_overrides` 把 `require_internal_token` / `require_tenant` 替换成空实现的 API 测试（全仓 `grep dependency_overrides` 现仅剩一条注释），于是它看起来"覆盖了评估 API"，实际从不经过任何鉴权；本批改用 `create_app()` 自建实例 + conftest 的真实内部 token，并新增"缺 token 必须 401 且不落任何产物"的断言。零生产代码改动
- **同用例的三个副作用一并堵掉**：① 只 patch `runner_mod.default_runs_dir` 而不 patch `app.api.eval_harness.REPORTS_DIR`（模块级常量 `Path("data/eval_harness/reports")`，CWD 相对），历次运行把 `_report.md` 直接写进仓库 —— 修复前该目录已积累 **99 个文件**（靠 `.gitignore` 的 `python-ai/data/` 兜住才没进版本库），修复后本轮新增 0 个；② `_notify_java_record` 每轮都对 `config.JAVA_BACKEND_URL` 发一次真实 HTTP 请求（未起 Java 时是 502 + 白等）；③ 结尾 `app.dependency_overrides.clear()` 清空的是**全局 app** 的覆盖表，一旦中途断言失败就跳过清理、或把别的用例设的覆盖一起清掉。现三处统一改为 tmp_path / `httpx.Client` 打桩
- **覆盖顺带补齐**：同一 E2E 里补跑 `/score`（分数文件 + 幻灯片落盘，正是第七十批修掉的 `request.label` 500 的回归位）与 `/diff`（同一运行自比 `has_regression=False`），使这条链路在"真 runner + 真评分 + 真报告"下全程可达，而不只像第七十批那样在打桩契约层验证

#### 决策记录
- **不删历史产物文件**：`python-ai/data/eval_harness/reports` 的 99 个文件是 gitignored 运行产物，其中最早的可追到 2026-08-30；删除属不可逆动作且可能有人拿去比对历史评分，留给你决定是否清空 **（同日追加：你已明确要求清空，`reports/` 99 个文件与 `runs/` 5 个 `.jsonl` 已删除；此后该目录只由评测运行重新填充）**
- **保留"真链路"而不把这条也改成全打桩**：第七十批的契约测试已把 runner/score/report/slides 四个函数全替身；本用例的价值恰在跑真内核（真 JSONL 落盘、真指标计算、真报告渲染），两者互补。若这里也打桩，评估 API 就没有一条用例能证明"模块之间参数对得上"
- **`create_app()` 而非全局 `app`**：与 `tests/test_api_contract.py` 的 `client` / `bare_client` fixture 同一口径，也避免用例间共享 override 表

#### 验证
- `tests/test_eval_harness.py` **15/15 通过**（用例数不变，函数增删为 0）；Python 全量 **1821 passed / 8 skipped**（与第七十批基线逐项一致，零回归）
- `ruff check .`（python-ai）全绿；static-checks 八项全绿；测试计数仍为 **1689**（本批未新增 `test_` 函数）
- 生产代码零改动；`python-ai/data/eval_harness/reports` 本轮新增 0 个文件（以 mtime 核验）

### 第七十批（2026-10-05：eval_harness 评估中枢契约测试收口 R15-21——/score 必 500、/diff 缺目录穿越守卫）

#### Fixed
- **`app/api/eval_harness.py:182`：`POST /api/eval-harness/score` 此前必然 500**。端点把不存在的 `request.label` 传给 `save_slides(title=...)`，`_ScoreRequest`（:163-168）只有 `run_file / enable_judge / judge_model / judge_runs / retrieval_k` 五个字段，于是 `AttributeError: '_ScoreRequest' object has no attribute 'label'` 在 `score_run` 与 `save_scores` **都成功之后**才抛——分数文件已写、幻灯片未写、调用方拿到 500 且响应体里的 `scores_file` 永远不存在。真实调用方在位（`hfusionhub-frontend/src/api/rag.ts:234`、`java-backend/.../EvalHarnessController.java:63`）。改为 `title=request.run_file`：`/score` 是重放评分、没有运行标签可用，用 run 文件名做幻灯片标题至少可追溯到具体一次运行，与 `/run` 侧 `title=request.label` 的"标题须可追溯"意图一致
- **`app/api/eval_harness.py`：`/diff` 缺 `/slides`、`/report` 同款目录穿越检查**。两处产物读取端点各自内联 `"/" / "\\" / ".."` 拦 422，`/diff` 直接把 `base_run`/`candidate_run` 交给 `score.load_scores`（`score.py:103` 做 `reports_dir / run_file.replace(...)`）。实测 `base_run="../outside.jsonl"` 返回 **200 并读出 `REPORTS_DIR` 之外的 JSON**。抽出 `_guard_run_file()`，`/score`、`/slides`、`/report`、`/diff`（两个入参）共用。顺带修好同一道守卫缺位下的第三处表现：`/score` 的穿越串原先会漏进 `runner.load_run_file`（`runner.py:64-65` 抛 `ValueError`，端点只捕 `FileNotFoundError`）呈 500，现与其余端点一致在入口 422

#### Added
- **`tests/test_api_contract.py` +24 个用例（+47 收集，159 → 206）**，覆盖 `/api/eval-harness` 全部 7 个端点，**R15-21 列出的零测试路由就此收口**
  - **鉴权挂载 ×14**：7 条路由 ×（缺 token / 伪造 token）401、×（有效 token 无租户 / `X-Tenant-Id: acme`）400；router 级守卫先于 pydantic 校验，故 `json={}` 也断言 401
  - **`/run` 的位置参数契约**：`start_run` 以 10 个位置参数 `asyncio.to_thread(runner_mod.run_dataset, ...)` 驱动 runner，位置一错就把 `top_k` 当并发用而不报错。用例断言实参恰为 10 个，并用**真实** `run_dataset` 签名 `inspect.signature(...).bind()` 逐位核对 `base_url/kb_id/top_k/concurrency/timeout/runs_dir/label/progress`（替身须在导入真实签名之后再打桩，否则绑到替身的 `*args` 上取不到字段）
  - **样本来源与白名单**：内联样本 / `dataset_name` 二选一，缺两者与空数组 → 422；`query_id` 缺省按 `case-<序号>` 兜底；`dataset_name` 含 `/`、`\`、`..`、非 `.jsonl`、无扩展名一律 422 且不触达 runner；白名单内 `.jsonl` 逐行解析（空行跳过、`tags`/`history` 原样进 `EvalSample`）、缺失 404、全空白文件 "no usable samples"
  - **产物读取**：`/runs` 直接透传 runner 清单；`/datasets` 只列 `.jsonl` 且排序、目录不存在回空数组；`/slides`、`/report` 先 404 后按文件名读回正文；`/diff` 用**真实** `diff_metrics`/`has_regression` 比对，分数缺失 404
  - **Java 摘要回调**：`/api` 后缀裁掉后拼 `/api/internal/eval-harness/record`，请求体逐字段核对（`overall` 原样、`failed_case_ids={"failed":[...]}`、`X-Internal-Token` 取 `config`）；失败用例 ID 截 200；**回调抛错或回 4xx/5xx 时评估仍 200** —— 结果已落盘，不因 Java 不可达而判评估失败
  - 测试侧把 `REPORTS_DIR`/`DATASET_DIR` 两个模块级常量、四个 core 模块函数、`httpx.Client` 全部打桩：不打桩会往 `python-ai/data/eval_harness/reports` 与 `scripts/eval_sets` 写真实文件，并对 `JAVA_BACKEND_URL` 真出网（实测单例 3.5s 花在那次 502 上）

#### 决策记录
- **`/score` 标题选 run 文件名而非新增 `label` 字段**：补字段要同步改前端与 Java 透传层请求体，而该端点语义是"对既有运行重放评分"，文件名本身就是运行的唯一标识；等真要自定义标题时再加字段不迟
- **穿越守卫抽函数而非在 `/diff` 内联两份**：三处内联副本已经证明"漏一处"的成因，`/diff` 有两个入参，再内联就是把同一判断复制第四、五遍
- **两处缺陷在改动前先用红色用例呈现**：本批先交付按期望契约断言的 2 个用例（`/score` 200 + 三件套、`/diff` 422），把失败输出作为缺陷证据，再动生产代码——与第六十八批"不固化可疑行为成契约"的口径一致
- **`TENANT_ID_HEADER = "1"` 与 `/run` 自调用头硬编码租户 1（:29、:132）本批不改**：单租户部署下无实际后果，多租户化时会静默串租户；改动涉及从请求上下文取租户，与评估运行器自调用链路一起处理更稳 **（已由第七十二批按该口径收口）**
- **既有 `tests/test_eval_harness.py:171` 的覆盖假象留作下一批**：该用例用 `dependency_overrides` 绕过内部 token 与租户守卫，且只 patch `default_runs_dir` 不 patch `REPORTS_DIR`，一直在往 `python-ai/data/eval_harness/reports`（gitignored）写真实文件。它是仓内唯一"看起来覆盖了评估 API、实际从不经过守卫"的测试，值得改成走真实守卫 + 全量打桩，而非在本批顺手带改

#### 验证
- `tests/test_api_contract.py` **206/206 通过**（159 → 206 收集）；Python 全量 **1821 passed / 8 skipped**
- `ruff check .`（python-ai）与 static-checks 八项全绿；测试计数 **1665 → 1689**（README badge 与三处正文、`README_EN.md`、`docs/ROADMAP.md` 同步）
- 生产改动集中在 `app/api/eval_harness.py`（`_guard_run_file` 新增 + 5 处调用 + 1 处 `title=` 修正），响应结构不变；`docs/OPTIMIZATION_PLAN.md` R15-21 由 🟡 部分完成改判 ✅ 完成

### 第六十九批（2026-10-05：ingest 正文空白改判 400——收口第六十八批留下的分级不一致）

#### Fixed
- **`app/api/ingest.py:51`：目标网页无可提取正文由 500 改判 400**。第六十八批把 URL 策略拒绝归到 4xx 后，"URL 合法、抓取成功、但页面没有可读正文"仍抛 `ParsingException` → 500 + "文档解析失败:" 前缀，与相邻的输入拒绝分级不一致：调用方换一条 URL 即可修正，服务端并没有故障。现统一为 `HTTPException(400, "该网页没有可提取的正文内容")`，端点的分级收敛为**入站可修正 → 400 且原因原样；服务侧故障（httpx 传输异常）→ 500 且文案泛化**

#### Changed
- `tests/test_api_contract.py::test_ingest_url_rejects_blank_extracted_text_without_writing` 由断言 500 前缀信封改为 400 原样文案，并补注该分支的语义；"失败不建目录、不留残档""抓取器被调用一次"两条断言保持不变
- `docs/OPTIMIZATION_PLAN.md` R15-21 的 ingest 行补记该分级收口

#### 决策记录
- **选 400 而不是 422**：422 在本仓表示请求体形状/取值不合契约（本批的 5 例 422 就是这类）；正文空白通过了全部校验，是"这个目标地址取不到可用内容"，与 SSRF 拒绝同属调用方可换输入解决的一类，故沿用 400 + 原因原样
- **Java 侧可见行为仍不变**：`AiClient.ingestUrl`（`java-backend/src/main/java/com/hfusionhub/client/AiClient.java:835,840`）对 4xx/5xx 一律落进同一 `catch (Exception)` 并返回自己的通用提示，因此本批改判只影响 HTTP 语义与 `hfusionhub.trace` 日志的错误归因，不改动前端文案；仓内除该端点与本次测试外没有别处引用这条消息
- **不再往下扩**：`file_path` 写入失败（磁盘/权限）仍会抛未捕获异常并由全局 handler 记为 500 泛化文案，属真实服务故障，分级正确，不改

#### 验证
- `tests/test_api_contract.py` **159/159 通过**（用例数不变，仅一处断言随契约更新）；Python 全量 **1774 passed / 8 skipped**
- `ruff check .`（python-ai）保持全绿；static-checks 八项全绿；测试计数仍为 1665（本批未新增 `test_` 函数）
- 生产改动 1 行（`ingest.py:51`），`UrlIngestResponse` 字段不变

### 第六十八批（2026-10-05：ingest URL 摄取面契约测试 + URL 策略拒绝归 400、空白标题不再吞掉网页标题）

#### Fixed
- **`app/api/ingest.py:43-45`：URL 策略拒绝由 500 改判 400**。抓取器的 `ValueError` 是调用方可修正的输入问题（`app/utils/ssrf_guard.py:58,60,63,70` 的 https/公网/凭据白名单拒绝，`app/core/ingest/url_fetcher.py:118,123` 的超 2MB 与非 HTML），此前被包成 `ParsingException` → `code=500` + "文档解析失败:" 前缀，把客户端错误记成服务端故障。现改抛 `HTTPException(400, str(exc))`，原因原样回传（`{"code": 400, "message": "仅支持公开的 HTTPS 网页地址"}`）；真实服务故障（httpx 传输异常）仍走 `ParsingException` 的 500 且文案泛化。**已核实现有调用方不受影响**：唯一调用者 `java-backend/.../AiClient.java:835` 用 `restTemplate.exchange`，4xx 与 5xx 都落进同一个 `catch (Exception)` 分支并返回它自己的通用提示，所以本次改判不改变 Java 侧可见行为，收益在 HTTP 语义正确、日志与错误归因不再把输入错误算作服务故障
- **`app/api/ingest.py:57`：纯空白标题覆盖不再吞掉网页标题**。`(request.title or title or request.url).strip()` 里 `"   "` 是 truthy，会赢过网页 `<title>` 再被 `.strip()` 清空，导致文档 H1 与响应 `title` 同时为空串。现按本仓 `mcp_admin` 的"先 strip 再判空"归一口径改为 `((request.title or "").strip() or title or request.url)`（`title=None` 不得再触发 `AttributeError`，故 strip 前先兜空），超 200 字符截断保持不变。**Java 侧本来就不会传空白标题**（`AiClient.java:829` 已用 `!title.isBlank()` 过滤），该缺陷只在直连 HTTP 面可达，本批属边界加固

#### Added
- **`tests/test_api_contract.py` +11 个用例（+23 收集）**，覆盖 `POST /api/ingest/url`
  - **守卫先于任何出网动作**：该端点会驱动服务端向外部 URL 发请求（SSRF 面），故 4 类非法请求（缺 token、伪造 token、有效 token 无租户、`X-Tenant-Id: acme`）必须分别 401 / 401 / 400 / 400，且 `fetch_and_extract` **一次都不调用**——鉴权失败不得留下任何对外请求痕迹
  - **暂存产物形状**：响应 `file_type="md"`、`message="网页已抓取并暂存，等待解析"`、`file_path` 落在 `DOCUMENT_STORAGE_ROOT` 下且文件名恰为 `[0-9a-f]{32}\.md`；落盘正文为 `# {title}\n\n来源: {url}\n\n{正文}\n`；`content_length` 与文件内容逐字符一致（标题行与来源行也计入，不是正文字数）
  - **标题优先级 6 例**：显式 `title` > 网页 `<title>` > 原始 URL；`""`、`"   "`、`" \t "` 一律视为未提供并逐级回落；超 200 字符截断
  - **文件名与用户输入无关**：`title="../../etc/passwd"` 时 `file_path` 仍在暂存目录内、目录内只多出那一个 uuid 文件——穿越串只进正文标题，不参与路径构造
  - **三条错误分级各自成文**：URL 策略 `ValueError` → 400 且原因原样；httpx 类传输异常 → 500 且泛化为 `文档解析失败: 网页抓取失败，请稍后重试`（断言响应不含 `10.0.0.1` 等内部地址细节）；正文全空白 → 500 `文档解析失败: 该网页没有可提取的正文内容`。三类失败都不产生文件，甚至不创建暂存目录
  - **存储根自动建**：`DOCUMENT_STORAGE_ROOT` 指向不存在的多级目录时按 `parents=True` 创建再写入
  - **请求形状先于分发**：缺 `url`、`url` 为 null / 数字 / 数组、只给 `title` 共 5 例 422 且零抓取
  - 测试侧一律把 `DOCUMENT_STORAGE_ROOT` 改到 `tmp_path`：默认值 `../java-backend/uploads/documents` 直指 Java 上传目录，契约测试不得写真实暂存区
- **测试计数 1654 → 1665**：README badge 与三处正文、`README_EN.md`、`docs/ROADMAP.md` 同步
- `docs/OPTIMIZATION_PLAN.md` R15-21 剩余无 API 层测试端点由 8 收窄到 7（仅 `eval_harness`）

#### 决策记录
- **两处可疑行为都选 B（改生产代码）而非"按现状钉死"**：本批先只写测试、把两处行为摆出来后再动手，避免把 500 误分级和空白标题吞没固化成契约。改后仍保留"错误路径不建目录、不留残档"的全部断言，因为它们与状态码分级无关
- **严重度经调用方核实后下调，但方向仍按 B 落地**：唯一 Java 调用方把 4xx/5xx 折叠成同一条通用提示、且不会传空白标题，所以这两处都不会造成线上可见故障。仍值得改的理由是：HTTP 层语义正确性、`hfusionhub.trace` 日志不再把输入错误记为服务故障，以及直连面（MCP Inspector、运维手测、后续网关）确实读 Python 的原始状态码与 message
- **`ValueError` 通道经核实只承载输入拒绝**：`fetch_and_extract` 及其依赖（`ssrf_guard.validate_public_https`、`url_fetcher` 的大小与 content-type 检查）抛出的 `ValueError` 全部是调用方可修正的原因，无内部 bug 混入，所以整体改判 400 不会把真实故障伪装成客户端错误——这是 B 成立的前提
- **正文空白仍留 500（待确认）**：`该网页没有可提取的正文内容` 与刚改判的 400 分级不完全一致。区别在于它不是请求本身非法（URL 合法、抓取成功），而是目标内容不可用，Java 侧按解析失败处理也讲得通；本批不动它，若要一并归 4xx 请单独示下
- **`X-Tenant-Id: acme` 的 400 来自中间件而非端点**：断言按实际信封 `{"code":400,"message":"Invalid X-Tenant-Id header"}` 落，与 `require_tenant` 的 "Tenant context required but missing" 是两处不同来源，分别覆盖

#### 验证
- `tests/test_api_contract.py` **159/159 通过**（本文件 136 → 159 收集）；Python 全量 **1774 passed / 8 skipped**（第六十七批基线 1751 + 23 收集，既有用例零受影响）
- `ruff check .`（python-ai）保持全绿；static-checks 八项全绿
- 本批含 2 处生产代码改动（`app/api/ingest.py`），均为响应分级与标题归一，无接口形状变化（`UrlIngestResponse` 字段不变）

### 第六十七批（2026-10-05：mcp 运行时 JSON-RPC 面契约测试——按方法分级鉴权首次成文）

#### Added
- **`tests/test_api_contract.py` +16 个用例（+27 收集）**，覆盖 `POST /mcp` 与 `/mcp/health`、`/mcp/tools` 共 3 个运行时端点。**本批零生产代码改动**
  - **鉴权按 JSON-RPC 方法分级，不是整面一刀切**：`initialize` / `notifications/initialized` / `tools/list` 三个握手与 schema 发现方法**必须无 token 可达**（否则外部 MCP 客户端连不上），其余方法（含未知方法）一律要 `X-Internal-Token`——缺失 401、伪造 403，且两种失败都**一次都不调用** `mcp_sse_endpoint`
  - **服务端未配置密钥时 fail-closed**：`config.INTERNAL_API_TOKEN` 为空 → 携带任何 token 都 403，工具执行不下发
  - **`search_knowledge_base` 的知识库边界**：该工具缺 `X-HFusionHub-KB-ID` 直接 400；头值无法解析（`abc` / 空串 / `1.5`）按"未提供"处理、同样 400，不会退化成无边界检索；其他工具（如 `get_current_time`）不受该头约束，`knowledge_base_id` 以 None 下发
  - **转发体不得含 null 占位**：通知请求没有 `id`/`params` 时，交给协议层的 body 恰为 `{"jsonrpc","method"}` 两键（`model_dump(exclude_none=True)`），避免下游"键存在即有效"的误判
  - **协议错误留在 JSON-RPC 层表达**：`jsonrpc` 非 2.0 时 HTTP 仍 200、由端点回 `-32600`；端点对通知返回 None 时 HTTP 层补 `{"jsonrpc":"2.0","result":null}` 而不是空响应体
  - **形状校验先于分发**：缺 `method`、`method` 非字符串、`params` 非对象、`id` 为对象等 6 类请求体 422 且零分发
  - **两张公开读侧的形状**：`/mcp/health` 固定 `status=healthy` + `protocol=json-rpc-2.0` + `tool_count == len(tools)` + `tools` 只列名字；`/mcp/tools` 回完整 schema 且完全不需鉴权
  - **两套 MCP 面边界相反且均有意为之**：对照用例把"运行时面公开握手 / 管理面必须内部 token"并置断言（`/mcp/tools`、`/mcp/health` 200 与 `/api/mcp/servers` 401）
- **测试计数 1638 → 1654**：README badge 与三处正文、`README_EN.md`、`docs/ROADMAP.md` 同步
- `docs/OPTIMIZATION_PLAN.md` R15-21 剩余无 API 层测试端点由 11 收窄到 8（`eval_harness` 7 / `ingest` 1）

#### 决策记录
- **本批不删 `/mcp` 的端点内鉴权（与第六十四批方向相反，须辨清）**：plugin_admin 的病灶是"router 守卫 + 端点自校验两套等价锁叠加"且校验的键恒空导致 403-by-construction；`app/api/mcp.py:65-74` 的端点内校验却是**唯一**鉴权点（`app/main.py:171` 注册 `mcp_router` 时不带依赖），因为它必须按方法分级放行握手。后续任何"鉴权去重"改造若把它当冗余删除，等于把工具执行面变成公开面——本批的 401/403 用例就是这道防线
- **未把"服务端密钥未配置"从 403 改为 503**：`require_internal_token` 在 `INTERNAL_API_TOKEN` 未配置时回 503（服务侧配置错误），`/mcp` 回 403（视作凭证无效）。两者都 fail-closed，只差可观测性；改齐要动运行时面语义，本批按现状钉死，是否统一待确认
- **未在 API 层重复 `knowledge_base_id > 0` 边界**：`X-HFusionHub-KB-ID: 0` / `-5` 会原样转发，真正的拒绝在 registry（`app/core/tools/registry.py:662` 对 ≤0 直接 `SCOPE_DENIED`），因此越界值不会变成无边界检索；是否把边界提前到 HTTP 层（失败更早、报错更准）待确认
- **`/mcp` 的 500 文案仍回传内部异常文本**（`app/api/mcp.py:90`，`MCP error: {exc}`）：与第六十四批 plugin_admin 同一口径、同一未闭合问题，本批按现状断言
- **公开面暴露范围已核实**：Java 侧只调用管理面 `/api/mcp/servers`（`java-backend/src/main/java/com/hfusionhub/client/AiClient.java:849,864`），仓内未见对 `/mcp` 的网关透传配置，故握手/schema 公开仅在 Python 服务端口直连时可达；若日后经网关对外，需重新评估 schema 披露面

#### 验证
- `tests/test_api_contract.py` **136/136 通过**（本文件 109 → 136 收集）；Python 全量 **1751 passed / 8 skipped**（第六十六批基线 1724 + 27 收集，既有用例零受影响）
- `ruff check .`（python-ai）保持全绿；static-checks 八项全绿（含测试计数同步）
- 本批生产代码零改动

### 第六十六批（2026-10-05：mcp_admin 契约测试——管理面密钥不回传、校验失败走 200 契约）

#### Added
- **`tests/test_api_contract.py` +11 个用例（+17 收集）**，覆盖 `/api/mcp/servers` 全部 4 个管理端点。**本批零生产代码改动**
  - **鉴权挂载**：4 端点参数化断言缺 token / 伪造 token 一律 401；token 有效但缺 `X-Tenant-Id` 时 400（router 级 `tenant_dependencies`，`app/main.py:177`；本仓另一处 `mcp_router` 无守卫注册，属运行时面，留作后续）
  - **管理面不得回传密钥**：`_server_payload` 只暴露 id/name/url/transport/status/tool_count/error_message 七个可见字段，测试用哨兵密钥（`api_key="sk-mcp-sentinel-key"`）断言响应文本内既不含哨兵值、也不出现 `api_key` 这个键名——将来给 payload 加字段很容易顺手把连接对象里的密钥一起带出去
  - **状态与传输枚举落为字符串**：整份 `{"servers": [...]}` 全等断言，`transport`/`status` 必须是 `TransportType`/`ConnectionStatus` 的 `.value`（`connected` / `disconnected` / `error`），`tool_count` 由 `len(tools)` 得出，空 `error_message` 归一为 `None` 而非 `""`
  - **校验失败按 200 + `success=False` 回给 Java 透传层**（而非 4xx）：空 id/url、非 http(s) 地址（含 `ftp://` 与 `//host/path` 形式）、`transport` 越界（`stdio` 不接受，配置期即拒）共 6 类，且**校验失败时 manager 一次调用都不发生**（不产生"注册了但配置非法"的残条目）；只有请求体本身不是 JSON 对象才 422（`null` / `[]` / `"str"` / `7`）
  - **入参归一化必须落在转发给 manager 的配置上**：`" notion "`、`" https://… "`、`" Streamable-HTTP "`、`api_key: "  "` 转发后恰为 `{"id":"notion","name":"notion","url":"https://mcp.notion/sse","transport":"streamable-http","api_key":None}`（name 缺省取 id、空 api_key 归 None），随后才 `connect`；响应消息为 `MCP 服务器 'notion' 连接成功`
  - **连接失败不回滚注册**：`connect` 返回 False 时条目保留、`status="error"`、`error_message` 原样回传，调用序列恰为 `[add_server, connect]`——若实现改成失败即删除，前端就没有可重试的服务器条目了
  - **重连与移除的顺序契约**：未知 id 的 reconnect 只 `get_server`、绝不 `connect`；已知 id 走 `[get_server, connect]` 并回报结果；remove 一律**先 disconnect 再 remove_server**，且对不存在的 id 同样执行（幂等，200 + `success=False`，不是 404）
- **测试计数 1627 → 1638**：README badge 与三处正文、`README_EN.md`、`docs/ROADMAP.md` 同步
- `docs/OPTIMIZATION_PLAN.md` R15-21 剩余无 API 层测试端点由 15 收窄到 11（`eval_harness` 7 / `mcp` 3 / `ingest` 1）

#### 决策记录
- **不断言"移除未知服务器必须跳过 disconnect"**：现有实现无条件先断连再摘除，对未知 id 也如此——`disconnect` 在 manager 内部本就按 id 查表、无连接即空操作，多一次无害调用换来移除路径单一。测试因此把"未知 id 也走 `[disconnect, remove_server]`"钉成现状而非缺陷
- **`transport=stdio` 在 HTTP 面拒绝，不改 manager**：`TransportType` 含 `stdio`，但管理 API 只接受 sse / streamable-http 两种远程传输——stdio 需要本机进程与命令白名单，不能由前端透传层任意注册，这条边界属于安全约束，测试把它固化为契约
- **裸 app 与真实 app 继续并存**（承接第六十五批）：本批 4 端点全部走 `create_app()` 挂载，鉴权与租户守卫在同一层受测；`app/api/mcp.py`（运行时 MCP 调用面，3 端点、无守卫注册）语义更重，单独成批处理

#### 验证
- `tests/test_api_contract.py` **109/109 通过**（本文件 92 → 109 收集）；Python 全量 **1724 passed / 8 skipped**（第六十五批基线 1707 + 17 收集，既有用例零受影响）
- `ruff check .`（python-ai）保持全绿；static-checks 八项全绿（含内部 token 键一致性、内部契约锚点与测试计数同步）
- 本批生产代码零改动

### 第六十五批（2026-10-05：agent_observability 契约测试——观测面首次经过真实鉴权挂载）

#### Added
- **`tests/test_api_contract.py` +15 个用例（+30 收集）**，覆盖 `/api/agent/observability` 全部 7 端点。**本批零生产代码改动**
  - **先补上"守卫从未被测过"这一层**：既有 `tests/test_agent_evaluation.py:24-26` 自建裸 `FastAPI()` 再 `include_router(obs_router)`，因此 `/evaluate/run` 的九条业务用例**从不经过内部 token 与租户守卫**——router 若被改回无依赖注册，那批用例一条都不会红。本批用真实 `create_app()` 参数化断言 7 端点缺 token / 伪造 token 一律 401，并断言 token 有效但缺 `X-Tenant-Id` 时 400（fail-closed，不默认租户）
  - **分页 total 与当页过滤同源**：`/runs` 必须把 `knowledge_base_id/status/error_only` 三元组同时交给 `store.list` 与 `store.count`，只给一侧就会造成"总数与筛选条件互相矛盾"的静默错位；默认值逐项钉死（`limit=50, offset=0, error_only=False`），6 类越界查询参数 422（`limit` 0/201、`offset` -1/1001、`kb_id` 0、`status` 31 字符）
  - **`POST /runs` 字段集封闭**：以 `AgentTrace.__dataclass_fields__` 反查，payload 必须覆盖除 `created_at` 外的全部 14 个字段并逐字段等值透传——将来给 `AgentTrace` 加字段而端点忘记透传，Java 侧推送的 trace 会静默丢列，这条断言会立刻指出
  - **参数改名即失败**：`/stats` 的 `days` → `window_days`、`/stale-runs` 的 `max_running_seconds` 默认 120.0 且响应回显阈值、`count == len(stale_runs)`
  - **写侧校验**：`run_uuid` 空/超 64、`status` 空、`token_usage` 值非 int、`duration_ms` 非数值全部 422，且校验失败时 `store.record` 一次都不调用（不产生半条 trace）
  - **`/evaluate/run` 在真实挂载下的三条边界**：未知维度静默丢弃、`dimensions: []` 回落全量维度、**缺 `knowledge_base_id` 时绝不构造 Agent**（把 `get_agent` 换成抛断言的桩）——离线已答题原样送评、`ground_truth` 只参与打分不冒充答案、`agent_call.agent_status == "skipped"`；批形状校验 6 例（空 cases、缺 query、空 case_id、超时上下界、201 条上限）
  - **`/evaluate/regression-check` 只回报阈值**：自定义阈值确实交给 `AgentRegressionGate`，空请求体可接受（该端点字段全可选，真正评测在 `/evaluate/run`）
- **测试计数 1612 → 1627**：README badge 与三处正文、`README_EN.md`、`docs/ROADMAP.md` 同步
- `docs/OPTIMIZATION_PLAN.md` R15-21 剩余无 API 层测试端点由 22 收窄到 15（`eval_harness` 7 / `mcp_admin` 4 / `mcp` 3 / `ingest` 1）

#### 决策记录
- **不重复覆盖 `/evaluate/run` 的评测语义**：`test_agent_evaluation.py` 已用真实评测器覆盖三条必测回归场景（引用一致性、无证据引用、越权抑制）与超时/异常降级，本批只测**挂载 + 请求契约 + 未覆盖的 skipped 分支**，两套测试按"语义 vs 契约"分工，不互相替代
- **`_FakeEvalReport.to_dict()` 必须带 `cases`**：端点是先回填 `report.cases` 再 `{**report.to_dict()}`（`agent_observability_api.py:313,320`），替身若省略 `cases` 就会把"响应里没有逐用例结果"这种真实形状错误掩盖掉——首版即因此漏测，修正后断言才落在实际契约上
- **裸 app 测试暂不迁移**：`test_agent_evaluation.py` 用裸 app 是有意绕开鉴权以聚焦评测语义，改动它会牵动 9 条既有用例的桩装配；本批用真实 app 补一层，两层并存，迁移留作后续（若要合并需先确认评测器桩在 `create_app()` 下的导入路径可用）

#### 验证
- `tests/test_api_contract.py` **92/92 通过**（本文件 62 → 92 收集）；Python 全量 **1707 passed / 8 skipped**（第六十四批基线 1677 + 30 收集，既有用例零受影响）
- `ruff check .`（python-ai）保持全绿；static-checks 八项全绿（含内部 token 键一致性与测试计数同步）
- 本批生产代码零改动，全部结论均由测试侧暴露

### 第六十四批（2026-10-05：plugin_admin 恒 403 缺陷修复 + 8 端点契约测试——插件审计同步恢复）

#### Fixed
- **`app/api/plugin_admin.py`：删除端点内的第二套鉴权，`/api/plugin/*` 8 个端点恢复可用**。建测试时发现的既存生产缺陷（此前零测试所以从未暴露）：`_verify_internal_token` 校验的是 `HFUSIONHUB_INTERNAL_TOKEN`，而全仓部署只配置 `PYTHON_AI_INTERNAL_TOKEN`（`app/utils/config.py:74`、`docker/.env` / `deploy/.env` 变量名清单），该键在任何环境都为空 → `if not expected` 分支恒真 → **每个端点无论携带什么凭证都返回 403**。守卫实际挂在注册处（`app/main.py:176` 的 `tenant_dependencies`），端点内自校验既冗余又致命
  - 移除 helper 及 8 处调用、各端点的 `x_internal_token` 形参与随之无用的 `Header` 导入（255→211 行）；权威守卫仍是 router 级"内部 token + 可验证租户上下文"，行为口径与本仓其余 data-touching 路由一致
- **`app/core/plugin/audit.py:342,373`：插件审计出站同步改用服务权威 token**。两处 `_post_to_java_backend*` 同样读 `HFUSIONHUB_INTERNAL_TOKEN`，取空即 `logger.warning("…跳过审计同步")` 直接返回 False——**审计只落本地 SQLite，Java 侧 `plugin_audit_log` 静默收不到任何条目**（接收端 `InternalPluginController.java:99` 一直在等）。现统一为 `config.INTERNAL_API_TOKEN`，与入站守卫、Java `python-ai.internal-token` 共用同一密钥（单一共享密钥双向复用的既有设计）

#### Added
- **`tests/test_api_contract.py` +18 个用例（+28 收集）**：8 个 plugin_admin 端点脱离零测试
  - **鉴权挂载与"不得二次校验"同时钉死**：8 端点参数化断言缺 token / 伪造 token 一律 401（守卫在注册处，业务逻辑触达之前）；再以"有效 token + 合法租户 → 200"这条正向断言锁死本次修复——回归成 403-by-construction 即红
  - **租户 fail-closed**：token 有效但缺 `X-Tenant-Id` 或头非法（非正整数）时必须 400，不默认租户
  - **写侧顺序契约**（用有序记录器替换全部写侧协作者）：`install` 成功后才 `record_install`；`enable`/`disable` 先改状态再记审计；**`uninstall` 先记审计再注销插件**（`unregister_plugin` 抛错也必须留下卸载痕迹）
  - **幂等短路不产生审计**：`already_enabled` / `already_disabled` 既不调用 `enable_plugin`/`disable_plugin`，也不写审计条目——否则启停面板会被无变化操作刷满
  - **错误映射**：`PluginLoadError`→400（业务拒绝，不是服务故障）、未预期异常→500、`expected_hash` 缺失→422（无哈希的 wheel 不得进入安装流程）、未知 plugin_id 在 enable/disable/uninstall/verify 四处均 404 且体为 `{"code": 404, "message": "插件不存在"}`（全局 handler 的响应形状，非 FastAPI 默认 `detail`）
  - **读侧形状**：`/list` 管理视图必须含停用插件（`enabled_only=False`）并逐插件给出 `tool_count`；`/tool-specs` 只暴露启用插件（`enabled_only=True`）；`/verify` 报告哈希漂移（`valid=False` + 双侧哈希）；`/audit-logs` 透传 `plugin_id`/`limit`（默认 50）
- **`tests/test_plugin_audit.py` +3 例**：批量与单条同步都必须以 `config.INTERNAL_API_TOKEN` 作为 `X-Internal-Token` 发出（并在环境里塞入 `HFUSIONHUB_INTERNAL_TOKEN` 哨兵，证明旧键不再被读取）；token 未配置时直接返回 False 且**不发任何 HTTP 请求**
- **测试计数 1591 → 1612**：README badge 与三处正文、`README_EN.md`、`docs/ROADMAP.md` 同步
- `docs/OPTIMIZATION_PLAN.md` R15-21 剩余无 API 层测试端点由 26 收窄到 22，并记录本批发现的鉴权缺陷

#### 决策记录
- **修复方向选 A（删冗余自校验）而非 B（补配置该键）**：两套 token 并存本身就是事故源——router 级守卫已经是权威，端点内再校验一个不同变量名没有任何安全增益，只增加"看起来有两道锁"的误导。B 会让同一服务同时接受两个不同密钥，且 `HFUSIONHUB_INTERNAL_TOKEN` 在部署侧仍需新配，收益为零
- **未一并收紧 `install` 的 500 响应文案**（`plugin_admin.py:122` 把内部异常文本拼进 `message`）：与 `general_exception_handler` "不回传实现细节"的口径不一致，但这是内部管理员 API、由 Java 侧透给操作者看失败原因，属有意信息量，本批按现状钉死；是否统一为通用文案 + 日志留痕，留待确认
- **`audit.py` 顶部新增 `from app.utils.config import config`**：`app/utils/config.py` 只依赖 stdlib 与 dotenv，无循环导入风险；改在调用点读取（而非导入期快照）保证 monkeypatch 生效

#### 验证
- `tests/test_api_contract.py` + `tests/test_plugin_audit.py` **85/85 通过**；Python 全量 **1677 passed / 8 skipped**（第六十三批基线 1646 + 31 收集，无既有用例受影响）
- `ruff check .`（python-ai）保持全绿；static-checks 七项全绿，含"内部 token 键一致性"与测试计数同步
- 本批生产改动仅限 `plugin_admin.py`（删鉴权helper 及其形参）与 `audit.py`（两处 token 取值来源），无检索/对话链路行为变化

### 第六十三批（2026-10-05：运维面 API 契约测试——gateway/guardrails/memory/tools 脱离零测试）

#### Added
- **`tests/test_api_contract.py` +14 个用例（+25 收集）**，覆盖 R15-21 剩余路由中运维面四类。这批契约是"读代码推不出来、但错了就出事"的那类：
  - **鉴权守卫挂载**（8 端点参数化）：缺 token 与伪造 token 都必须 401。守卫挂在 `app/main.py:173-185` 的注册处而非各端点，任何人把某个 router 改回无依赖注册，测试立刻红
  - **gateway 不泄漏承诺首次可执行**：`app/api/gateway.py:11-12` 的 docstring 声明"绝不暴露 API key、provider URL 与提示词内容"，此前无任何保护。现以携带哨兵 key/URL 的真实 `ModelGateway` + `ProviderConfig` 走 `/status`、`/models`，断言响应体不含二值，且 provider 字段集合封闭在 11 个运维字段内（新增字段即失败，逼作者先想清楚是否敏感）
  - **guardrails 是诊断端点不是拦截器**：命中 critical 注入必须返回 **200 + `allowed=False` + `blocked_reason`**，而不是 4xx——把拦截改成 HTTP 错误会让调用方无法区分"内容被判危险"与"服务故障"。另钉 kill-switch 关闭时完全不检查、check-input/check-output 共用校验模型、5 类畸形请求 422（空/超长/channel 枚举/ID 下界/必填缺失）、status 端点只给开关计数与审计元数据
  - **memory consolidate 形状先行**：Java 侧消息快照的角色白名单、内容非空、ID 为正、100 条上限全部 422 拦截；未启用记忆时短路返回 `{"enabled": False, "saved": 0}` 且不得触达抽取
  - **tools/registry 降级契约**：token 有效但缺租户上下文时 400（fail-closed，不默认租户）；registry 构造失败时返回 `{"tools": [], "total": 0, "error": …}` 而非 500
- **测试计数 1577 → 1591**：README badge 与三处正文、`README_EN.md`、`docs/ROADMAP.md` 同步
- `docs/OPTIMIZATION_PLAN.md` R15-21 更新为 🟡 部分完成，并列出剩余 26 个无 API 层测试的端点（`eval_harness` 7 / `plugin_admin` 8 / `agent_observability` 7 / `mcp_admin` 4 / `mcp` 3 / `ingest` 1）

#### 验证
- 本文件 34/34 通过；Python 全量 **1646 passed / 8 skipped**（新增 25 例收集，无既有用例受影响）；`ruff check .` 保持全绿；static-checks 七项全绿
- 本批零生产代码改动——所有失败模式均由测试侧暴露

### 第六十二批（2026-10-05：lint 债务清零——`ruff check .` 首次全绿，关闭第五十九批 Known debt）

#### Fixed
- **CI `python-lint` 作业的 9 项既存命中全部清除**（工作目录 `python-ai`，与 `.github/workflows/ci.yml:135` 的 `ruff check .` 同口径）。这些债务是 CI 自 2026-09-09 账户级停摆期间无人拦截留下的，第五十九批曾逐项记录
  - 5 项 `I001` + 1 项 `F401` 由 `ruff --fix` 安全修复：`demo_business_tools.py`（`RiskLevel, ToolSpec` 排序）、`test_acl_regression_36.py` / `test_subject_acl.py`（app.* 导入块排序）、`test_eval_baseline.py`（`compute_citation_*` 排序）、`probe_sse.py`（未使用的 `import json`）——**纯重排，无一条改变解析结果**
  - 2 项 `E741`：`probe_sse.py:20,22` 读取 `.env` 的列表推导变量 `l` → `raw`（`l` 与 `1` 视觉歧义）
  - 1 项 `F841`：`test_acl_matrix.py:106` 的 `store = _matrix_store(...)` 是**死设置**——该用例只断言 `build_acl_metadata_filter(None) == build_acl_metadata_filter("general")` 的 fail-closed 契约，桩 store 从未参与，删除该行并去掉随之无用的 `monkeypatch` 形参（本文件的 clearance 用例本就直接调用 `clear_clearance()`，不依赖 monkeypatch 还原）

#### 验证
- `ruff check .`（python-ai）**All checks passed**——本仓 Python 侧门禁首次回到绿色
- 受影响 4 个测试文件 87/87 通过；Python 全量 **1621 passed / 8 skipped**，与第六十一批基线逐条一致（本批零行为变更的判据）；static-checks 七项全绿（计数仍 1577，本批不增测试）

### 第六十一批（2026-10-05：RetrievalPipeline 直接单测——检索编排首次获得独立可测面）

#### Added
- **`python-ai/tests/test_retrieval_pipeline.py`（19 例）**：第六十批抽出的编排此前只能经 `ReactAgent` 间接覆盖，现按模块直接测，**本批零生产代码改动**
  - **两条入口的口径分叉逐项钉死**：`retrieve_context`（转发历史 / `retrieval_top_k` 覆盖规划值 / 异常降 `None`）与 `retrieve_context_for_stream`（不转发 / 不覆盖 / 异常升格）——把"有意保留的分叉"升级为有断言保护的既定契约，将来统一时测试会精确指出改的是哪一条
  - **空召回 vs 服务故障**：`("", [], kb_id)` 与 `None` 的语义区分（M10 口径），以及流式入口故障必须抛出
  - **`safe_compress` 四条路径**：空上下文短路（压缩器不得被创建）、策略拒压时回落原文、过激压缩守卫（压缩比 <25% 且原文 >500 token 时回退并取全块号）、正常压缩放行
  - **`decompose_retrieve_merge_context`**：单子问题返回 `None` 交回单路检索；依赖层间串行、层内并行的实际检索次序；跨子问题内容去重；`execution_plan` 漏项的兜底检索；依赖未登记子问题整条路径跳过；全部子问题失败升格 `RuntimeError`（`__cause__` 保留末次异常）；部分失败按空结果降级不拖垮整批
  - **`empty_context_reply`**：库空文案 / 证据不足文案 / store 不可达时的保守回落（不误报"库是空的"）
- **测试计数 1558 → 1577**：README badge 与三处正文、`README_EN.md`、`docs/ROADMAP.md` 同步
- 桩件选型：压缩器以 stub 注入且分解类用例让 `safe_compress` 直通，使编排断言不受压缩策略演进影响；`SubQuestion` / `DecompositionResult` 使用真实数据类而非 mock，以保住 `can_execute` 的依赖判定语义

#### 验证
- 新文件 19/19 通过；Python 全量 1621 passed / 8 skipped；`ruff check` 对新文件全绿（既存 9 项债务仍在本批未触碰文件）；static-checks 七项全绿

### 第六十批（2026-10-05：检索编排自 react.py 抽出——RetrievalPipeline，R15-20 前半程）

#### Changed
- **新增 `python-ai/app/core/agent/retrieval_pipeline.py`（380 行）**，迁入 12 个原 react.py 模块级/私有实现（只依赖知识库作用域 `knowledge_base_id` / `retrieval_top_k`，与 ReAct 循环、工具协议无关）：
  - 模块级：`NO_SUFFICIENT_EVIDENCE_REPLY`、`RETRIEVAL_UNAVAILABLE_REPLY`（M10 文案）、`_MIN_COMPRESSION_SAFETY_RATIO`、`_SOURCE_LABELS`、`_format_numbered_context` → `format_numbered_context`
  - 实例/静态方法：`_safe_compress`、`_decompose_retrieve_merge_context`（含依赖分层并行内核 `_sub_retrieve`）、`_empty_context_reply`（含 `_all_chunks`）、`_evidence_gate_threshold`、`_below_evidence_gate` 收为 `RetrievalPipeline` 成员
  - `_retrieve_context` / `_retrieve_and_compress` 的实现合并为 `_retrieve_core(..., *, forward_history, override_top_k, reraise)`，两条入口按各自历史口径实例化参数
- **`ReactAgent.__init__` 持有 `RetrievalPipeline`，保留 `_retrieve_context` / `_retrieve_and_compress` 两个薄委托**：单测以 `agent._retrieve_context = <stub>` 替换检索（`test_agent_v1_contract.py` 四处猴补丁依赖该桩），委托必须留在实例上；其余调用点全部改走 `self._retrieval`
- **react.py 2178 → 1879 行**（净 -299）；顺带消解第五十九批记录的 react.py lint 三连（I001/F401/F811，源于第五十七批把 `get_query_decomposer` 改为函数内导入后模块级导入未删）——迁走导入后自动清除，`ruff check` 对本批两个 app 文件全绿
- **猴补丁锚点随模块迁移**：4 个测试文件中 `app.core.agent.react.get_retriever` / `rag.get_query_decomposer` 的补丁改指 `app.core.agent.retrieval_pipeline.*`；`react.get_llm`、`rag.get_intent_classifier` 的补丁不变（消费点仍在原模块，运行时查表生效）。4 处陈旧注释锚点（`context_compressor.py:42,419`、`eval_baseline.py:414`、`eval_offline.py:70`）改指新符号
- **顺带修正类型注解 bug**：`_retrieve_and_compress` 原声明返回 5 元组，实际返回 6 元组（缺 `visible_numbers`）

#### 决策记录：两条检索入口的分叉原样保留
- `retrieve_context`（`run` / `_run_stream_react` 用）转发 `conversation_history`、以 `retrieval_top_k` 覆盖 `plan.top_k`、异常回落 `None` 走降级；`retrieve_context_for_stream`（`run_stream` 单路检索用）三者皆无、异常升格抛出走 `retrieval_error` 事件。**同一问句在"命中业务工具"与"未命中"两条路径下召回集合可以不同**——这是既存事实而非本批引入，本批只做等价搬迁，分叉已写进两个方法的 docstring
- 统一它需要离线冻结套件 + 真机对比背书（会改变检索结果），留待独立批次
- 范围边界（与本批规划一致）：ReAct 协议解析（`_parse_action` / `_parse_structured_action` / `_parse_final_answer`）与答案质量判据（`_is_groundless_answer` / `_answer_support_score` / `_parse_cited_chunk_ids`）留在 react.py——前者是工具循环协议、后者是答案侧判据，均不属检索规划

#### 验证
- Python 全量 **1602 passed / 8 skipped**，与拆分前逐条一致（本批"零行为变更"的判据）；被改动的 5 个测试文件单独运行 143 passed
- `ruff check .` 从 12 项既存债务降至 9 项（剩余全部为本批未触碰文件，见第五十九批 Known debt）；static-checks 七项全绿（Java 697 / Python 1558 / 前端单测 101——本批不增测试，计数不变）
- `docs/OPTIMIZATION_PLAN.md` R15-20 标注部分完成（检索/压缩已共享；三份循环的组装与容错仍在收敛范围）

### 第五十九批（2026-10-05：修复流式业务工具路由的 NameError——命中即整体失败）

#### Fixed
- **`react.py:2052` `log.info` → `logger.info`**：本文件只有模块级 `logger`，`log` 从未导入。触发条件为流式 ReAct 路径同时满足"检索上下文非空"与"命中演示业务工具"——而 `_run_stream_react` 的入口判据本身包含 `demo_tool_matched`（`run_stream` 内 1677 行），故该组合**必然**抛 `NameError`，被 2161 行的兜底 except 转成 `run_error` 事件；用户侧表现为：只要业务工具命中且知识库有召回，流式回答整体失败（非降级、非空答，而是终止）
- 回归测试 `tests/test_react_stream_routing.py`（2 例）：一条断言不再发 `run_error` 且终答流出，一条以"stub LLM 收到的用户消息含 `query_order_logistics`、不含 `<reference_material>`"证明路由分支确实被执行——此前该分支无任何测试覆盖，故此类错误可长期存活

#### Known debt（本批不处置，仅记录）
- `ruff check .` 在本工作区有 12 项既存命中（`react.py` 的 I001/F401/F811 三连源于第五十七批把 `get_query_decomposer` 改为函数内导入后模块级导入未删；其余分布在 `demo_business_tools.py`、根目录 `probe_sse.py`、3 个测试文件）。CI 自 2026-09-09 账户级停摆期间未拦住这批 lint 债务，与 TODO.md P0-0 记录的窗口一致

### 第五十八批（2026-09-22：sendMessageStream 阶段化拆分——397 行方法收敛为编排 + 会话类）

#### Changed
- **`sendMessageStream` 397 → 137 行**：主方法只保留编排（校验 → 幂等 → 持久化 → 任务创建 → 订阅接线）
  - 前置守卫抽为 `validateStreamTarget()`（对话存在/归属/知识库可用可读，失败即 emitter 错误收尾）
  - 用户消息幂等持久化抽为 `persistUserMessageIfAbsent()`（查重 → 插入 → DuplicateKey 回落查询）
  - 三个 Reactor 终端回调（onNext 分发 ~125 行 / onError 收敛 ~47 行 / onComplete 兜底 ~55 行）收敛进内部类 `StreamSession`——共享状态（responseBuilder / accumulatedSources / usageFinalized / assistantSaved 等）从散落局部变量变为具名字段，DONE 哨兵、取消信号各自成方法
- **行为零变更**：所有回调代码原样搬迁，仅 `assistantSaved[0]` 数组标记改为会话字段（Flux 信号串行保证安全）；`StreamSession` 为内部类，直接复用外部服务的 `saveStreamAssistantMessage` / `aiUnavailableMessage` / `chatUsageRecorder` / `agentTaskService`

#### 决策记录：AiClient 拆分本批不实施（设计已定稿）
- 深入检查后发现拆分触及面大于预期：`AiClientTest` 以反射直接注入 AiClient 的 `@Value` 私有字段（抽取共享管道后须重写为注入 Support 实例）；标书 4 方法有 8 个调用文件。设计已定稿并记录：`AiInternalHttpSupport`（包私有 @Component：baseUrl/internalApiToken/internalHeaders/addInternalToken/addUserProviderConfig/mapClearance）+ `AiBidClient`（标书域）+ AiClient 保留一行委托门面（调用方零改动）——留待独立批次执行
- `AiClient` 的 77 方法中 12 个 chat 重载的宽签名是另一处债务，需与调用方签名收敛一起做

#### 验证
- `mvn compile` 通过；`ConversationServiceImplTest` 11/11 全绿（jacoco 覆盖率棘轮在单类运行下的告警与测试无关）；Python 全量 1600 passed；static-checks 七项全绿

### 第五十七批（2026-09-22：分解语义统一——上下文合并取代答案拼接，react.py 循环合一的前置解锁）

#### Changed
- **新增 `_decompose_retrieve_merge_context()` 共享实现**：按依赖层并行检索子问题（`execution_plan` 分层 + `can_execute` 依赖判断 + 层内 `asyncio.gather`）→ content 去重合并编号上下文 → 统一压缩。`run()` 与 `run_stream()` 共用，终结两条路径自 M12 以来"只对齐触发条件、合并语义分叉"的状态
- **`run()` 分解分支改为检索侧生效**：分解不再提前返回，而是产出合并上下文后继续走统一管线——证据门、Groundedness 重试、引用编号空间（单一编号空间替代跨子答案冲突的局部编号）、`token_count` 真实计费全部恢复
- **`run_stream()` 内联顺序检索块删除**：顺序遍历（无依赖分层、无并行）由共享实现取代；检索异常事件与直连 LLM 降级口径保持不变
- **移除三条旧方法**（-137 行）：`_decompose_and_handle` / `_handle_sub_question` / `_merge_sub_answers`——其中合并步骤从未真正合成（返回"请综合以上信息回答原始问题"模板原文给用户）、`token_count=0` 绕过计费、绕过守卫，属未完成实现而非可选设计

#### 决策记录
- "答案合并 vs 上下文合并"原计划数据背书后取舍；实施时确认旧答案合并路径**本身是坏的**（模板拼接即最终答案），不存在可回归保护的质量基线，故直接统一到上下文合并并移植其依赖分层并行机制
- 离线冻结套件只测检索指标、不经过 agent 循环，对本变更不敏感；建议在本地全栈跑一条多跳问题目测流式/非流式两条路径的一致性（如"A 和 B 两个方案各自的优缺点对比"）

#### 验证
- agent 相关 281 测试全绿；Python 全量 1600 passed；离线评测门禁零回归（recall@5=0.932）；static-checks 七项全绿；react.py 2214→2180 行（净 -34 行 + 两处拷贝消除 + 依赖并行机制保全）

### 第五十六批（2026-09-22：生产纵深留缝——观测/检查点存储后端契约化）

#### Added
- **`AgentTraceBackend` / `CheckpointBackend` 协议**：把两个存储类 docstring 里"多副本部署可替换同类后端"的口头约定升级为正式 `Protocol` 契约（record/get/list/count/stats/stale_runs/clear；save/load/load_at_step/list_for_run/delete/prune/count）
- **注册表工厂 + env 选择点**：`AGENT_TRACE_BACKEND` / `AGENT_CHECKPOINT_BACKEND`（默认 `sqlite`，未知值警告后回落）——未来 MySQL/Postgres/Redis/OTLP 后端实现协议并登记注册表即可接入，调用方与单例工厂零改动；本批不实现第二后端，只留缝
- **ENVIRONMENT.md 补 4 行**：上述两个选择点 + 此前漏记的 `AGENT_TRACE_DB_PATH` / `CHECKPOINT_DB_PATH` 两个库文件路径（权威清单补全）

#### 验证
- 观测/检查点相关 58 测试全绿；Python 全量 1600 passed；离线评测门禁零回归；static-checks 七项全绿

### 第五十五批（2026-09-22：react.py 去重第一刀 + 三循环合一的可行性结论）

#### Changed
- **ReAct 循环真重复片段去重**：新增 `_approval_observation_data()`（审批载荷解析）与 `_collect_search_sources()`（search_knowledge_base sources 采集 + `_last_sources` 同步），非流式 `run()` 与流式 `_run_stream_react()` 各删除一份 try/except 拷贝——审批检测与 sources 采集从"两份手抄"收敛为单一实现，行数基本持平但漂移温床消除

#### 明确记录：三循环完全合一暂缓（决策依据，非拖延）
- 深读后发现 **`run_stream()` 不是 `run()` 的近似拷贝**，而是一条语义不同的 RAG 快路径：分解检索在流式路径"合并子问题上下文"、在非流式路径经 `_decompose_and_handle` "合并子答案"——M12 只对齐了触发条件，合并语义是两套设计。盲目统一必然改变其中一条的行为
- 真正近似的只有两条 ReAct 工具循环（非流式 run() 内层 vs `_run_stream_react()`），本次已抽其共享片段；完全合一需要：① golden-master 双轨录像（SSE 事件序列 + AgentResponse 逐字段对比）先冻结现状；② 对分解语义做出产品决策。两项都不适合静默自动完成
- 前批"2201→~1200 行"的估计基于"三份近似拷贝"的判断，深读后修正：安全可省的是重复片段而非整段循环

#### 验证
- agent 相关 208 测试全绿；Python 全量 1600 passed；离线评测门禁零回归；static-checks 七项全绿

### 第五十四批（2026-09-22：正确性堵缺——exactly-once 收口 + task 条件守卫 + 静默降级可观测 + 事件循环卫生）

#### Changed
- **执行令牌签发 fail-closed（第五十三批遗留缺口修复）**：`decideApproval` 的令牌签发前移至 task/run 迁移之前并纳入 M2 事务——签发异常或命中 0 行时整体抛出 `BusinessException` 回滚本次决定（approval 回到 pending，可重试），不再带着 null token 调 Python resume。Python 侧消费本就 fail-closed（空 token → 409），旧版静默降级的实际后果是 approved 的 run/task 被误收敛为 failed。顺带修正与 `@Transactional` 矛盾的过时注释
- **task 表状态写入全面条件守卫**：新增 `AgentTaskMapper.transitionTaskGuarded`（`WHERE id=? AND status IN (...)`）与 `AgentConstants.NON_TERMINAL_STATUSES`，替换 decideApproval 全链 6 处 check-then-act / 无条件 `updateById`（approve → running、deny → failed、恢复失败收敛 ×2、恢复完成终态回写）——并发下只有真正赢得迁移的一方生效，与 run 侧 `completeRunGuarded` 约定对齐
- **沙箱静默降级可观测**：`sandbox_runner.py` 9 处裸 `pass` 分类处理——rlimit 失败（CPU/内存/fd 未生效）warn、网络/Popen/fork 守卫补丁 API 变更（`AttributeError`）以 "SANDBOX DEGRADED" warn、平台不支持的 ImportError 保持静默；行为零变更，降级从不可见变为可告警
- **ReAct 循环静默吞噬留痕**：`react.py` 非流式/流式共 4 处 `except (JSONDecodeError, TypeError): pass` 补 debug 日志（审批检测跳过 / sources 采集跳过），纯文本工具输出按设计跳过的行为不变
- **事件循环卫生**：eval API 的 `_notify_java_record`（同步 httpx，最长阻塞 10s）与 chat 链 `_build_chat_response` 的 4 个 async 路由调用点统一下沉 `asyncio.to_thread`——后者内部含外部审核 HTTP 与全文正则扫描，配置审核引擎后此前会阻塞事件循环；`runner.py` 的同步 httpx 经确认整体运行于 `start_run` 的 to_thread 内，无需改动

#### Added
- **竞态回归测试 ×3**（`AgentApprovalRaceGuardTest`）：签发命中 0 行 / 签发抛异常 → 断言抛 BusinessException 且绝不调 Python resume、绝不迁移 run；task 守卫落选 → 断言全链路不再出现无条件 `updateById`

#### 验证
- `AgentApprovalRaceGuardTest` 9/9（含新增 3 例）+ `AgentTaskExecutionTokenTest` 全绿；`mvn compile` 通过
- Python 1600 passed / 8 skipped；离线评测门禁零回归（recall@5=0.932、引用 F1 过阈值）；static-checks 七项全绿（Java 计数同步 697）

### 第五十三批（2026-09-22：架构减法——运营数仓扩展包拆分 + 文档声称对账）

#### Removed
- **HFusionData Analytics 运营数仓扩展包整体迁出**至独立仓库 [HFusionData](https://github.com/xiaodu55/HFusionData)：`bigdata/`（Spark/Flink/Hive/ClickHouse/DolphinScheduler/Superset/血缘/基准 60 文件）、`docs/BIGDATA_ARCHITECTURE.md`、`docker-compose.analytics.yml`、平台侧对接层 22 个 Java 文件（AnalyticsController/InternalAnalyticsController/AnalyticsService×2/Ads*×5 实体+Mapper/AnalyticsRealtimeMetric/BigDataBatchRunLog/双调度器）及对应测试、前端 `/analytics` 大屏页与 API 封装、`hfusionhub.analytics/batch` 配置段。主平台与数仓以批处理调度解耦，恢复联动只需将文件放回原路径
- **V86 drop 迁移**：移除 V82/V83 建立的 8 张扩展包表（历史迁移保留，`check-h2-schema-drift.py` 新增 DROP TABLE 解析支持）
- **README/文档过时声称清理**：图谱召回（已按 GRAPHRAG_REVIEW 复评移除）、"七种 IM"（实际飞书/钉钉/企业微信三种）、Electron 客户端、Bash 子命令校验、PreToolUse 术语——当前态文档全部对齐代码实际
- **悬空导出**：`rag/__init__.py` 移除无实现的 `KnowledgeGraphManager`/`KnowledgeGraphFactory` 导出（GraphRAG 移除时残留）

#### Changed
- **招投标标书助手降级为示例应用**：保留全部代码与文档，不再作为核心特性叙事
- **`static-checks.py` 新增文档声称对账检查**：6 个当前态文档禁用已移除能力的声称词，防复发
- **修正第五十二批**：移除误粘贴的外部项目（craft-agents）commerce 条目，本批为纯导航与 README 改版

#### 验证
- `static-checks.py` 七项全绿（新增文档声称对账通过；Java 计数 703→694 与实测同步；Flyway 窗口 V1–V86 同步）
- Java `mvn compile` 通过；离线评测门禁 `eval_offline.py` 零回归零门禁失败；Python 全量 pytest 通过；前端 vitest 101 全绿（含修复存量 `useLocale` 期望漂移）
- Testcontainers 集成测试（真实 MySQL 全迁移链含 V86）通过

## [1.1.0] — 2026-09-09

### 第五十二批（2026-09-19：导航分组 + README 改版；2026-09-22 修订——移除误粘贴的外部项目条目）

#### Added
- **导航分组折叠**：侧栏四组（使用与知识库 / 业务应用 / 构建与评测 / 系统管理）可折叠、激活组自动展开，低频项降级至首页「更多功能」分组网格
- **README 改版**：首屏三张界面截图、特性亮点拆分、RAG 模块表 / 高级功能矩阵下沉 `docs/python-ai.md`、端口表下沉 `docs/ACCESS_MAP.md`

#### 验证
- 导航分组与 README 改版改动经前端单测 + 构建验证
- 修订说明：本批原稿误粘贴了另一项目（craft-agents）的 commerce 场景条目，涉及代码（`src/commerce/`、`container/agent-runner/`、FTS5/Case Memory schema v70 等）在本仓不存在，已整体移除
### 第五十批（2026-09-09：R18 压缩误杀修复——ADR-006 后记实施）

#### Changed
- **压缩率单一来源化 + 默认 0.8**：`react._safe_compress` 硬编码 0.6 改读
  `RAGConfig.compression.target_ratio`（`RAG_COMPRESSION_TARGET_RATIO`
  可覆盖），默认 0.5→**0.8**——ADR-006 后记的消融实验（0.8/1.0 各修复
  3/5 insufficient_evidence 误杀）支撑；runtime 基线重冻结
  （citation_acc 0.743→0.757、faithfulness 0.564→0.579、refusal 0.9625
  持平、token 800 在 R17-2 门禁内）

#### 验证
- Python 全量 **1600 过 0 挂 8 跳**；方法论注记：单次 runtime 跑批的
  LLM 方差显著（同配置两次 P95 16.4s vs 28.9s），答案层结论以 nightly
  累积观测为准（双口径设计动机）

### 第五十一批（2026-09-09：R18 groundless 判据改写容忍——R16-15 五例全修复）

#### Changed
- **groundless 判据统一为"分数先行"**：`_is_groundless_answer` 的两判据
  重组——答案存在支持度达阈值的实质句即不判无依据（即使模型同时输出
  自认无证据的犹豫文案）；marker + 无实质支持仍拒，A4 修洞②的
  字面脱节幻觉防护不变。动机：ADR-006 后记实测 nq-005/007 在检索命中
  （ret=1.00）下被模型自认文案硬拒——过度自谦不应把有依据的回答
  变成硬拒答

#### 验证
- 真机复跑原 2 例模型侧误杀：均 `completed`、recall=1.00、答案带 [1]
  引用——**R16-15 的 5/5 误杀全部修复**（3 例压缩修复 + 2 例判据容忍）
- `tests/test_react_evidence_gate.py` 14/14 全绿（含 marker+高支持新
  行为路径）；Python 全量 **1600 过 0 挂 8 跳**

### 第四十九批（2026-09-09：R16-15 开放点定位 + R17 真机基线复测）

#### Added
- **R16-15 开放点定位（真机对照实验）**：normal 20 例纯检索 recall
  **1.000** vs 答案层 0.750——5/25% 被 insufficient_evidence 误杀
  （检索已命中）。ADR-006 新增后记：① 压缩预设 target_ratio=0.3 过激
  丢答案句（3 例，消融实验可复现修复）② 模型侧过度自认无证据（2 例，
  token 减半同源的漂移）；修复（0.3→0.5 + 判据改写容忍 + 基线重冻结）
  排 R18 评测周期
- **R17 真机性能基线**：`docs/baselines/baseline-20260909.txt`（对比
  baseline-v1-20260905：RAG 检索 P95 2261→1229ms -46%，其中 P50 203ms
  为 R16-5/6 查询缓存命中口径；文档端到端 39.7→29.8s -25% 为 R16-7
  batch 32×2 生效；Lighthouse 跳过）

#### Fixed
- run-all-benchmarks 迭代数文档-脚本不一致（100→50）

### 第四十八批（2026-09-09：R17 批次 4——发布与叙事）：评测双轨门禁（离线阻断 + nightly 双口径：纯检索轨解耦
> 检索质量与模型行为）· 主体级文档可见性 ACL（检索层 fail-closed）·
> 招投标垂直模块与大数据分析扩展包 · 插件沙箱纵深防御 · MCP 双向 ·
> 结构化 JSON 日志 · IT 集成测试 8/8 真库 · R16/R17 两轮优化
> （指标归因方法、chat 状态机、覆盖率棘轮）· 44+ 批自审修复。

### 第四十八批（2026-09-09：R17 批次 4——发布与叙事）

#### Changed
- **v1.1.0 发布接线（R17-16）**：`release.yml` 新增 CHANGELOG 摘要提取
  步骤（按 tag 版本匹配 `## [1.1.0]` 小节写入 release 正文，
  `generate_release_notes` 保留叠加）
- **README 叙事升级（R17-17）**：核心工程点新增「指标归因方法」条目
  （纯检索探针解耦检索栈/答案层、模型漂移甄别）；「质量与验证口径」
  改写为七维验证口径清单表；README_EN 测试徽章同步（1532/702/57 →
  1556/703/101）
- **R17-18**：R15-27 cpolar 固定域名的 Windows 服务注册指引复核完成，
  真机执行项已在 TODO.md 标注

#### Fixed
- **CHANGELOG 结构（R17-15）**：修复「第二十一批」标题重复；
  版本脉络说明落盘（[1.0.0] → [1.1.0]）

### 第四十七批（2026-09-09：R17 批次 3——前端第二轮）

#### Added
- **chat 会话组件拆分（R17-12）**：`MessageItem`（消息体/操作按钮/
  流式分支）、`ChatApprovalCard`（审批卡片）、`KnowledgeSources`
  （合并 router-link/div 两个重复分支为动态外壳）；Detail.vue
  1368→1159 行。消息列表 store 化与 MessageList 容器拆分经评估与
  messagesContainer ref 深耦合，留待与后续重构同批
- **页面组件单测（R17-13）**：+24 例（MessageItem 流式分支/错误检测/
  反馈高亮、ChatApprovalCard decide 事件、KnowledgeSources 链接回退
  评分），前端 77→**101** 全绿 + vue-tsc 通过

#### Changed
- E2E 回归由 CI e2e job 在 push 时执行（本地栈未跑浏览器套件）

### 第四十六批（2026-09-09：R17 批次 2——技术债清零）（2026-09-09：R17 批次 2——技术债清零）

#### Removed
- **legacy 死代码清除（R17-6/7）**：`GatewayResult.degraded` 死字段 +
  model_gateway/gateway_llm 失实 docstring（legacy 降级链已于 2026-08-29
  退役，注释仍声称委托旧链）；`/api/chat/agent-runs` 两条零调用路由 +
  退役告警函数；`JwtUtils.logout/getCurrentUserIdStr`（hasPermission 经
  编译验证为 UserServiceImpl 在用，保留）
- **ReAct 热路径脱离 legacy 入口（R17-7）**：react.py 4 处
  `execute_tool(...)` 改为新私有 helper `_execute_tool_observation`
  （Registry 直调 + JSON 序列化，语义与原 registry 分支一致）；
  tools/__init__.py 的 `get_tools/execute_tool` 重新定位为 **MCP 支持路径**
  （非 deprecated），移除每进程一次的退役告警

#### Changed
- **Java 流式接口收敛（R17-8，安全子集）**：`streamChat` 5 参零调用重载
  删除（3 处测试引用补齐 userId/intentContext）；非 KB 分支迁 V1 涉及
  产品级行为变更（普通对话→Agent 管线）且 E2E 未覆盖，**挂起待
  非 KB V1 行为验证后执行**，`/api/chat/stream` 旧端点暂保留
- **双鉴权分工文档化（R17-9）**：`docs/java-backend.md` 新增鉴权体系
  分工表（Sa-Token 拦截器+注解=认证授权主体；JwtUtils=当前用户读取器 +
  StpInterface 权限源；新代码禁新增 StpUtil 直接调用）
- **后台线程租户包装收尾（R17-10）**：`AgentQueueGauge` 包 runAsSystem
  （修复队列深度恒 0 → `AgentQueueBacklogHigh` 告警失效的功能缺陷）；
  `RealtimeThresholdScheduler`/`BigDataBatchScheduler` 显式 runAsSystem
  固化平台级 -1 口径；审计结论：16 个调度组件 13 个已正确包装、
  @Async 2 处安全、python 侧显式参数式无风险

#### 验证
- Java **703 过 0 挂 1 跳 BUILD SUCCESS**（`JwtUtils.hasPermission` 经
  编译验证为 UserServiceImpl 在用——探索期误判零调用，已恢复）；
  Python **1600 过 0 挂 8 跳**（含 agent_v1_contract/mcp_server 全绿）

### 第四十五批（2026-09-09：R17 批次 1——评测双口径升级）

#### Added
- **纯检索轨道进 nightly（R17-1）**：`eval_retrieval_live.py` 升级双模式
  （进程内本地归因 / HTTP 走目标栈 `/api/rag/eval` 生产检索链），文档名
  优先读 chunk metadata 的 `document_title`（HTTP 由端点响应
  `document_name` 暴露，`/api/rag/eval` 相应增强），`--docmap` 降级为旧
  语料可选回退；新增 `--report/--markdown` 落盘、`--fail` 门禁退出码、
  `evaluation/baseline/retrieval_baseline.json`（suite_sha256 钉扎，
  HTTP 模式冻结：recall@5=0.793，绝对下限 0.75 + 回退容差 0.03）；
  `eval-nightly.yml` 新增纯检索 step（与答案层口径解耦的稳定检索质量
  监测）
- **token 漂移门禁显式化（R17-2）**：`eval_baseline.py` GATE_ORDER 增
  `tokens_per_task`（lower-is-better），`eval_runtime.py` 新增
  `--maximum-tokens-per-task`（默认 2000，nightly 显式传参）——token
  1582→774 式模型漂移自动告警；`check_gates` 语义经单测验证
- **检索延迟分解埋点（R17-3/4）**：`record_rag_retrieval`（retriever
  finally 处）/`record_embedding_request`（generate 成功路径）/
  `record_embedding_cache(hit)`（查询缓存命中/未命中）接入生产路径，
  `/metrics` 暴露 `hfusionhub_rag_retrieval_latency_seconds`、
  `hfusionhub_embedding_latency_seconds`、
  `hfusionhub_embedding_query_cache_{hits,misses}_total`（真机验证：
  2 次检索即见 miss/hit 与延迟分布）

#### Changed
- **SCALING.md 分解口径（R17-5）**：RAG 检索基线小节明确"现行 P95 含
  embedding（推理成本非工程缺陷）"，新增 2.1 分解口径表（全管线墙钟 /
  纯检索质量 / embedding 延迟 / 缓存命中率四指标）与 GPU 化预估收益；
  修正迭代数文档-脚本不一致（100→50）
- `/api/rag/eval` 响应 results 增 `document_name` 字段

#### 验证
- Python 全量 **1600 过 0 挂 8 跳**；ruff 全绿；探针双模式真机验证
  （进程内 0.8295 / HTTP 0.7932，基线钉扎与回退判定经单测）

### 第四十四批（2026-09-09：runtime 检索指标残余差异归因闭环）

#### Added
- **纯检索归因探针 `scripts/eval_retrieval_live.py`**：绕过 LLM 答案层，
  对冻结套件逐用例直接检索并按 expected_document_names 计算 doc 级
  recall@5（permission 按主体语义走 general + 附 admin 老口径对照），
  用于把 runtime 轨检索指标变化拆分为「检索栈 vs 答案层」

#### Changed
- **归因闭环（真机实测）**：纯检索 OVERALL recall@5 = **0.830**
  （normal 0.986 / cross_document 0.983 / long_document 1.0 / tool 0.9 /
  injection 0.84 / refusal 1.0 / permission 0——ACL 正确拦截；permission
  按 admin 老口径 = 1.0），与 2026-09-06 旧基线检索水平（0.856，其中
  permission 老口径满贡献）一致——**检索栈健康，与 R16 代码改动无关**；
  runtime 0.550 与纯检索 0.830 的差值在答案层丢 sources（与单任务
  token 1582→774 同源的模型侧行为漂移）。`docs/CI_GATES.md` 口径注记
  与 R16-1 行同步更新

### 第四十三批（2026-09-09：R16-12b IT 迁移收口——ADR-008 达成 8/8）

#### Changed
- **PromptTestSetIntegrationTest / CostWebhookGateIntegrationTest 迁移
  it profile**（ADR-008 最后两例）：`queue-enabled` 两 profile 均为
  false（无 worker 竞争）；PromptTestSet 的三个并发用例 worker 线程补上
  生产同款 `TenantContext.runAs(tenantId)` 包装（生产调度器
  PromptTestSetRunWorkerScheduler 200-213 行本就正确包装，测试裸线程
  在租户拦截器开启的 it profile 下失败属未复刻生产语义）；CostWebhookGate
  域内清理保留为防御

#### Fixed
- **CostWebhookGate 间歇失败根因（原「混跑 1 例失败」）**：DATETIME(0)
  秒级取整 × `created_at <= endDate` 上界的秒末竞态——秒末插入的记录被
  舍入到下一秒、越出汇总窗口（daily SQL 无上界故总过）。测试跨秒界后
  稳定（ADR-008 第 2 类问题变体）；断言补实际值诊断信息
- atomicWrite 子用例复跑全绿——「MySQL 行锁语义与 H2 不同」的初步怀疑
  不成立：真实根因是窗口用例的 cancel 线程缺租户上下文（worker 线程
  已补而 cancel 线程漏补），`requireOwnedRun` 直接「运行记录不存在」
  瞬间完成、根本未到锁争用；补上生产同款 `runAs` 包装后行锁阻塞语义
  在真实 MySQL 下验证成立。断言保留 cancelError 诊断输出

#### 验证
- 两类真库：23/23 全绿；全量 `mvn test` **703 过 0 挂 1 跳
  BUILD SUCCESS**（无 Docker 时全部干净跳过的双向行为此前已验证）
- ADR-008 更新为 8/8 收口；ROADMAP/R16 文档同步

### 第四十二批（2026-09-09：R16-1 runtime 基线重冻结——真机跑批 + 2 项环境级缺陷修复）

#### Fixed
- **检索成功被调试快照拖垮（R16-20）**：`QueryRouter._debug_candidates`
  对 `content=None` 的检索结果切片崩溃（真机冒烟实录：检索已命中、
  sources 正常，却在 debug 快照 `'NoneType' object is not subscriptable`
  处整次请求以 retrieval_error 失败——"知识库检索服务暂时不可用"）。
  调试快照空内容容错；同族加固 VectorChannel 构造 SearchResult 时
  `content=None → ""`
- **本机 pymilvus 版本漂移（R16-21）**：已装 2.4.15 vs 锁定 3.0.0
  （milvus-lite 3.1.0 需 3.x 配对）——写读回环直测证实 content 恒为
  null（读路径转换 bug，连既有数据也读不出），且是 4 个既有
  `test_milvus_tenant_migration_real` "nullable" 失败的根因。
  `pip install pymilvus==3.0.0` 按锁恢复：4 测试全绿、回环正常

#### Changed
- **runtime 基线重冻结（R16-1）**：真机栈（Docker/Ollama/Java/Python +
  kb 101 重播种）后全量 220 用例跑批，`runtime_baseline.json` 重冻结于
  2026-09-09T03:06Z——**拒答正确率 0.625 → 0.9625**（旧值为 ACL 前
  口径：permission 0/30 被答出；现 30/30 拒答）✅、P95 21.7s→16.4s、
  token/任务 1582→774、错误率 0、越界 0
- 检索/引用指标 0.85→0.55 下移的归因（如实记录）：permission 30 例按
  ACL 语义拒答后不贡献召回（口径变化，非回归）；残余差异疑模型侧行为
  漂移（token 减半、答案变短）——reranker lexical/disabled 对照实验无
  差异、本轮检索路径改动仅 embedding 缓存与空内容加固。runtime 轨为
  非阻断监测轨，残余归因挂 eval-nightly 持续监测（`docs/CI_GATES.md`
  口径注记）
- ADR-008 补记 `RequireMySqlCondition`（ExecutionCondition）跳过机制
  修复背景

### 第四十一批（2026-09-08：R16-18 chat 发送单飞状态机收口）

#### Added
- **`useChatSending` composable（R16-18）**：发送单飞状态机——
  `runExclusive(task)` 单一进入方式（空闲执行并自动复位、并发拒绝、
  异常也复位），守卫持有权绑定到具体调用：forceIdle 后新任务接管
  守卫位时，旧在途任务的收尾不会误清新任务的守卫（+6 专项测试，
  含持有权隔离用例）
- **chat/Detail.vue 接线**：`handleSend` 拆为守卫入口 + 无守卫主流程
  `runSendFlow`（retry/regenerate 复用重发旧提问）；重试/重新生成把
  "删除在途 + 重发"整体纳入同一守卫，删除请求在途期间双击防护不再
  依赖手工时序——**组件内 `sending.value =` 手工置位/复位全部清零**
  （第三十六批 retry/regenerate 数据丢失缺陷的模式根除）

#### Changed
- "停止生成"（handleStopGeneration）与卸载清理（cancelOngoingRequests）
  改走 `forceIdle()` 强制释放，语义与旧实现一致

#### 验证
- vitest 77 全绿（+6）、`vue-tsc -b` 通过、README/ROADMAP 计数同步
  （前端 77）

### 第四十批（2026-09-08：R16 批次 4——结构化 JSON 日志 + 前端组件单测首批）

#### Added
- **结构化 JSON 日志双端落地（R16-17）**：
  - Java：`logback-spring.xml` 双 appender——默认保持 yml text pattern（经
    `${CONSOLE_LOG_PATTERN}` 绑定，行为与旧配置一致）；激活 `json-logs`
    profile（`SPRING_PROFILES_ACTIVE=json-logs`）后 console 走
    LogstashEncoder，MDC 的 trace_id 自动进字段。新依赖
    `logstash-logback-encoder:8.1`
  - Python：`app/utils/logging_config.py`（自 main.py 收口）——
    `LOG_FORMAT=json` 切换 JSON 行格式，字段
    `@timestamp/level/logger_name/message/trace_id`（与 Java 对齐，
    Loki/ES 按行采集就绪）；+7 专项测试
- **前端共享组件单测首批（R16-13）**：MarkdownRenderer 7 例（**XSS 关键
  面**：script 标签剥离、内联 onerror 事件剥离、代码块复制按钮、空内容、
  列表/链接渲染）+ ConfirmDialog 7 例（confirm/update:open 事件、loading
  态、destructive 变体）——前端 57→71 全量绿
- **ENVIRONMENT.md 补录**：`LOG_FORMAT`（Python）、`json-logs` profile
  （Java）、SSE 线程池三键（第三十八批遗漏补录）

#### Fixed
- **trace_id 恒为 "-"（R16-17 顺带修复）**：Python `TraceFilter` 原挂在根
  logger 上——标准库语义下根 logger 的 filter 只对直接经根 logger 发出的
  记录生效，app.* 子 logger 传播上来的记录不经过它；移到 handler 级后
  全局注入生效

#### 待办（如实记录）
- R16-15 / R16-16：答案标注率定位、DeepSeek tool_calls 稳定性——需模型栈
  配合，**待真机执行**
- R16-13 余量 / R16-18：页面组件单测与 chat store 状态收口——下批联动
  重构；R16-1 基线重冻结、R16-12b IT 迁移、R16-19 运维债——**待真机**

### 第三十九批（2026-09-08：R16 批次 3——质量加固 + ACL 矩阵抓出 3 个真实端点缺陷）

#### Fixed（矩阵测试即时产出）
- **chunk detail 端点 404 语义失效（R16-14 矩阵抓出）**：`/api/chunks/detail/{id}`
  对不可见/缺失分块抛 `ValidationException(..., code=404)`——该签名不存在，
  TypeError 被外层 `except Exception` 包成 MilvusException 返回 500。第 36 批
  "按不存在处理（不泄漏存在性）"的语义在 HTTP 层从未真正生效。改抛
  `HFusionHubException(code=404)` 并在 `except` 链中先于兜底重抛
- **chunk detail / search 端点 outline_path 未解析（同族 2 处）**：co-store
  落盘的 `outline_path` 为 JSON 字符串，`VectorChunkResponse`/`SearchResult`
  响应模型要求 list——列表端点有解析而 detail/search 漏掉，携带该字段的
  正常记录直接 pydantic 校验失败返回 500。新增 `_coerce_outline_path`
  统一收口（容错解析、非 list 归空）

#### Added
- **ACL 越权回归矩阵（R16-14）**：`tests/test_acl_matrix.py` 13 例，补第 36 批
  未覆盖的两条通道——① 向量通道「超额召回 → ACL 谓词后过滤 → 截断
  top_k」端到端（含 JSON 字符串 metadata、legacy 无 visibility 分块、
  admin 无过滤直取、超量截断保序）；② 直读端点按请求主体 clearance
  强制（general 不可见、admin 全可见、未设主体 fail-closed 按 general）。
  跨租户维度复用 per-tenant co-store 隔离测试不重复。53 个 ACL 测试全绿
- **IT 无 Docker 干净跳过（R16-12a）**：`AbstractItMySQLTest` 新增
  `RequireMySqlCondition`（JUnit `ExecutionCondition`）——旧实现依赖
  @BeforeAll 的 assume，但 `@DynamicPropertySource` 在上下文加载期即解析
  数据源属性，容器未就绪时 context 直接 error（跳过永不生效）。现于
  实例创建之前裁决；本机 `mvn test` 701 过 0 挂、29 跳、BUILD SUCCESS

#### Changed
- **覆盖率棘轮（R16-11）**：实测（本机 IT 跳过口径）Java LINE 46.15% /
  BRANCH 34.86%、Python TOTAL 75%。JaCoCo 新增 BUNDLE BRANCH ≥ 0.34
  下限（LINE 维持 0.46——上调 0.55 需 CI 含 IT 实测数据，避免本机误红）；
  CI pytest 加 `--cov-fail-under=74`（留 1pt 平台缓冲）

#### 待办（如实记录）
- R16-12b：PromptTestSet / CostWebhookGate 两类真库迁移需 Docker 验证
- R16-13：前端组件单测（5 个高风险组件）转下批
- R16-1 / 性能复测：runtime 基线重冻结与 k6 延迟留档待本机服务栈可用

### 第三十八批（2026-09-08：R16 批次 2——性能应用层优化，不动模型与部署）

#### Added
- **查询向量缓存（R16-5/6）**：`EmbeddingService.generate_query/get_query_embedding`
  （LRU+TTL，key=provider|model|sha256(空白折叠文本)）；milvus lite/cluster
  检索路径切换至缓存版。同请求内重复嵌入（Agent 预检索与 ReAct 循环内
  search_tool 命中同一文本）与跨请求同问法直接命中，省一次 CPU 推理
  （bge-m3 实测 ~2.5s/次）。文档分块路径不入缓存防挤占热点；命中返回副本
  防调用方污染；`EMBEDDING_QUERY_CACHE_TTL_SECONDS=600`（0 禁用）/
  `EMBEDDING_QUERY_CACHE_MAX_ENTRIES=256`；`get_query_cache_stats()` 供压测
  核对实际省掉的推理次数。+8 专项测试
- **文档索引批量嵌入配置化（R16-7）**：`EMBEDDING_DOC_BATCH_SIZE=32`
  （原硬编码 16）+ `EMBEDDING_DOC_BATCH_CONCURRENCY=2` 批间并发（信号量
  限流、批次序号保序、进度按完成分块数计）——Ollama /api/embed 请求 60s
  超时约束下以并发换吞吐而非无限放大单批
- **SSE 线程池 MDC 传播**：`TaskDecorator` 把提交线程 MDC（trace_id）带进
  池内线程并在结束后还原，异步流式日志不再断 trace 链；四个执行器统一应用

#### Changed
- **SSE 线程池容量模型（R16-8）**：core5/max20/queue100 → core32/max64/queue32
  （`app.sse.executor.*` 配置化）+ 空闲线程 120s 回收。JDK 线程池「先填满
  队列再扩容」语义下旧参数在 50+ 并发流时仅 5 个流真正推进——k6 爬坡
  100 VU 拐点（P95 3018ms）主因；核实 TenantContext 由任务内 `runAs`
  显式传递、不依赖线程继承，容量调整无上下文语义风险
- **N+1 收口（R16-9）**：`TenantPlanBindingServiceImpl` 三处循环 selectById
  （listActiveBindings / resolveCurrentTier / hasIndustry——探索期仅报两处，
  hasIndustry 测试驱动复查补齐）→ `selectBatchIds` 批量预取
- **无界查询审计收口（R16-10）**：service impl 实测 86 处 selectList 逐类
  审计——列表/统计路径此前已收口（R15 §1.8/R15-17 遗产）：会话历史
  LIMIT 60/100、记忆 LIMIT 200、指标聚合 period 封顶 30 天均已有界；
  真实高危 3 处补防御性上限：`listUnresolvedAlerts` LIMIT 500、任务队列
  RUNNING/RETRYABLE 恢复扫描各 LIMIT 500（调度自愈，余量下轮收敛）
- `.env.example` / `docs/ENVIRONMENT.md` 同步 4 个新环境变量

#### 验证（如实记录）
- Java：`TenantPlanBindingServiceImplTest` 9/9 绿；全量套件见本批提交说明。
  5 个 IT 类（Testcontainers）在本机报 context 加载 error——**HEAD 复现
  确认为既有环境现象**（Docker Desktop 未运行），非本批引入；ADR-008 的
  「无 Docker 整类跳过」在 context 加载阶段未生效，列入批次 3 改进
- Python：1579 通过 / 8 跳过；`test_milvus_tenant_migration_real` 4 例失败
  在 HEAD 同样失败（milvus-lite adapter CreateCollection "nullable"，环境
  问题，非本批引入）
- 性能复测（k6 chat-stream/ramp、文档端到端）待本机服务栈可用后按
  `k6/results/SUMMARY.md` + `docs/baselines/` 流程留档

### 第三十七批（2026-09-08：R16 优化方案落盘 + 批次 1 基线与一致性收口）

#### Added
- **R16 优化方案落盘**：`docs/OPTIMIZATION_PLAN.md` 追加第十六轮（R16-P0~P3 四批：基线收口 / 性能达标（仅应用层，不动 bge-m3 与部署）/ 质量加固 / 评测与工程卫生）；`docs/ROADMAP.md` 新增 Phase 7 与待排期对账
- **ADR-001~005 补写**（ADR-006 头部遗留「待补写」清零）：双语言 CQRS 边界 / Milvus 选型 / HMAC 回调与幂等索引 / 租户行级隔离 / 插件沙箱纵深防御，格式对齐 ADR-006~008，ADR-006 交叉引用同步更新

#### Changed
- `docs/ROADMAP.md` 测试计数更新为 2026-09-08 口径（Python 1531 / Java 703 / 前端 57 单测 + 73 E2E）
- `TODO.md` 状态对账：P0-0 CI 恢复（第三十六批已回绿）、P3-12 eval-nightly GitHub 配置就绪，均勾销

#### Removed
- 根目录 7 个本地调试 `.log`（`eval-permission-retest.log` 等；`.gitignore` 已覆盖属未跟踪杂物，permission 复测 30/30 数据已在第三十五批 CHANGELOG 留痕，无信息丢失）

### 第三十六批（2026-09-07：全仓 bug 审查修复——ACL 收口 + 数据一致性 + 门禁恢复绿）

#### Fixed
- **前端重试/重新生成数据丢失（高危）**：`Detail.vue` 的 `handleRetryMessage`
  / `regenerateMessage` 先置 `sending=true`（误信"handleSend 会重置"），删除旧
  轮次后调用的 `handleSend` 被自家守卫（`sending===true` 直接 return）拦下——
  旧问答对已被服务端删除而新请求从不发出。修复为发送前复位 `sending`
  （删除请求在途期间仍保持 true 防双击）
- **BM25/关键词通道被 ACL 过滤清空（高危）**：lite 模式 co-store 的
  metadata 以 JSON 字符串落盘，`KeywordChannel` 未解析即传给
  `_matches_metadata_filter`（对非 dict 恒 False），自第三十五批起所有
  clearance<admin 请求的关键词通道命中为 0（混合检索静默退化为纯向量），
  Batch 5 的 block_type 过滤同样受累。修复：谓词内部容错解析 JSON 字符串
  （兑现 docstring 承诺）+ 通道侧显式解析；`_expand_heading_context`
  邻块扩展同样过过滤（防未来按块过滤时借标题扩展泄漏）
- **Java→Python `X-User-Clearance` 透传缺失（高危）**：第三十五批遗留项收口。
  `AiClient.doChat`/`agentV1ChatStream`（新增 `userRole` 参数）、
  `RagObservabilityController`、`VectorizationServiceImpl` legacy 分块兜底
  均传播 clearance（admin→admin，其余→general fail-closed）；后台队列
  （`AgentTaskQueueServiceImpl`）无 JWT，从库内用户角色解析；OpenApi 链路
  与同步路径一致取 `user`（保守）
- **Agent 分块工具绕过 ACL（高危）**：`read_chunk_tool` /
  `list_document_chunks_tool` 只校验 KB 归属，确定性 chunk_id
  （`{doc}_chunk_{n}`）可被枚举越权读取任意可见性分块全文。修复：
  `clearance.subject_can_see_metadata` 闸门（未知 visibility fail-closed 按
  最敏感处理）；直读端点 `/api/search`、`/api/chunks/{id}`、
  `/api/chunks/detail/{id}` 同规则（不可见按不存在处理，不泄漏存在性）
- **文档编辑内容永不入索引（高危）**：`update` 置 PENDING 后重索引只发
  `file_path`，DB 新文本与索引旧内容永久分叉。修复：文本类文档
  （md/txt/csv/html/htm）编辑时回写源文件再触发重索引；二进制文档拒绝
  在线内容编辑（明确报错），杜绝静默错位
- **重索引 Milvus 重复插入（高危）**：chunk_id 确定性 + `client.insert`
  不去重 + `stale_ids = old - new` 恒空 → 重析后全部分块双份存储、旧文本
  继续可被检索。修复：`milvus_lite`/`milvus_cluster` 的 `insert_chunks`
  改 `client.upsert`（按主键替换）
- **上传白名单 MIME 兜底旁路**：`application/octet-stream` 在白名单内，
  任意非法扩展名声明该 MIME 即绕过校验进入解析管线——移除该 MIME
  （合法文件本就由扩展名检查通过）
- **KB 共享权限只作用于 upload**：read/read_write 被授予者此前无法读取共享
  KB 的任何文档（read 名不副实）、read_write 上传的文档永远 PENDING（无法
  触发解析/编辑/删除）。修复：读取面（getById/getContent/getDocumentName/
  listByKnowledgeBase/listByCurrentUser 含"全部"分支并入共享 KB）按有效权限
  放行；管理面（update/delete/parseDocument/createFromUrl）对 read_write 放开
- **聊天历史同秒乱序 + 过滤占槽**：仅按秒级 `created_at` 排序无 tiebreaker，
  同秒消息可能倒序喂给模型；先 LIMIT 20 后过滤导致被过滤消息占槽。修复：
  `orderByDesc(createdAt, id)` 双键 + 取 3 倍量过滤后截尾部 20 条
- **删除 vs stale 恢复竞态孤儿向量**：`recoverStaleIndexJobs` 重派时不检查
  DELETING，删除步骤 0 清完向量后可能被重新插入。修复：DELETING 文档的
  stale 任务直接置 FAILED，不重派
- **schema-h2 漂移（CI 红）**：document 表缺 V85 `visibility` 列——补列对齐
- **文档/脚本漂移（CI 红）**：`docs/database.md` 新迁移窗口 V85+→V86+；
  README 徽章 Python 测试计数与 H2 口径（单测 H2 + 集成 Testcontainers，
  见 ADR-008）、迁移链描述（V1–V85）按实际回填；ADR-008 环境变量名
  `HFH_IT_JDBC_PASSWORD`→`HFH_IT_JDBC_PASS`（与代码读取一致）；
  `AbstractItMySQLTest`/`application-it.yml` 的 V1..V84→V1..V85；
  前端 `handleReparsen`→`handleReparse`；k6 `chat-stream.js` 增
  `[DONE]` checks 阈值绑定（流截断不再静默通过）；
  `tests/test_task_queue.py` 断言同步 dispatch payload 的 `visibility`
  字段（第三十五批透传时遗漏）
- **visibility 修正闭环（B4）**：`DocumentUpdateDTO`/`DocumentInfoDTO`/
  `DocumentFromUrlDTO` 增 `visibility`，URL 创建可指定、创建后可修改
  （等级变化触发重索引重盖 Milvus metadata）；前端上传/网页抓取对话框
  增可见性选择、列表增机密徽章
- **低危清理**：缓存版本 bump 推迟到事务提交后（`KnowledgeBaseServiceImpl`
  4 处，消除提交前并发读回填脏数据）；`SchedulerLock` javadoc 与实现对齐
  （默认 fail-closed + 明示无续期约束）；Ollama embedding 客户端
  `EMBEDDING_MAX_RETRIES<=0` 时至少尝试一次（不再隐式返回 None 炸
  TypeError）+ 重试间复用 httpx 连接池；`@Async` 限定 `housekeepingExecutor`
  （多执行器下避免回退无上界的 SimpleAsyncTaskExecutor）；`listRecycleBin`
  批量预载 KB/用户名消除 N+1；离线 `RetrievalEvaluator` 增可选
  `metadata_filter`（默认 None，不改离线基线）；`milvus_cluster` 分块读取
  死代码清理；SSO 回调令牌改 URL fragment（`#token=`，不进历史/代理日志/
  Referer，前端 SsoCallback 解析并即读即清，query 形态灰度兼容）

#### Notes
- 重索引从 insert 改 upsert：依赖 chunk_id 主键语义，存量重复数据需一次
  重建索引（或等自然重析收敛）才能清零
- 二进制文档（pdf/docx 等）在线内容编辑现为显式拒绝（此前为静默分叉），
  属行为变更
- OpenApi 流式链路显式 `user` clearance：管理员经 OpenApi 应用调用不继承
  其管理员 clearance（与同步路径一致，fail-closed）

### 第三十五批（2026-09-06：主体级 ACL——文档可见性 + 检索按主体 clearance 过滤）

#### Added
- **Flyway V85**：`document.visibility VARCHAR(20) NOT NULL DEFAULT 'general'`
  （等级模型按敏感度升序：general < confidential，与 Python 侧共用同一张表）
- **Java**：Document 实体增 `visibility`；upload API 增可选 `visibility` 参数
  （白名单校验，非法值 fail-closed 拒绝）；向量化派发（`/api/parse` 请求体）
  透传 visibility
- **Python**：`app/core/security/clearance.py`（clearance contextvar + 等级
  归一化 + ACL 过滤器构造）；`TenantMiddleware` 传播 `X-User-Clearance`
  （缺省按最低权限 general，非法值与租户头同策略 400）；`/api/parse` →
  inline/arq 派发 → 后台任务全链路透传，分块（含 QA 生成块）metadata 统一
  打标 `visibility`；`_matches_metadata_filter` 扩展集合成员语义 + visibility
  缺省 general（V85 前存量向量无需回填）；`MultiChannelRetriever` 与
  `search_tool` 检索入口叠加 ACL 过滤（调用方无法经显式 filter 越权放宽）
- **评测（runtime 轨道）**：`eval_runtime.subject_for_case` 双主体策略——
  permission 类用例切低权限主体（`X-User-Clearance: general`），其余 admin；
  同一 section 的"必答/必拒"矛盾由主体区分化解（cd-025 管理员答 ✓ /
  pt-007 低权限拒 ✓），用例数据与 baseline SHA 保持冻结；`seed_eval_kb.py`
  对受控文档（security-policy / employee-privacy-policy / permissions-matrix /
  it-support-runbook）以 `confidential` 上传
- 测试：`tests/test_subject_acl.py` 27 项（等级模型/谓词/中间件/主体策略）；
  query_router、RAG access contract、eval runtime contract 等存量回归全绿

#### Fixed
- **seed_eval_kb.py purge 流量 bug（存量）**：直接对活文档调 purge 端点恒 400
  （purge 只作用于回收站文档），导致 KB 101 跨次播种累积 3 批重复文档、
  Milvus 实体数与 document_chunk 对账漂移（277 vs 870）——修复为
  软删除进回收站 → purge 彻底删除（连带向量），状态轮询增加非 JSON 容错重试

#### 验收（2026-09-06 · 单机全栈实测 · 权限类复测）
- **permission 拒答正确率 0/30 → 30/30**（第三十二批记录的已知 ACL 缺口收口），
  30 例全部 `insufficient_evidence`、sources 为空——受控文档在检索层被
  ACL 过滤，不依赖模型自觉拒答；
- 同一 section 双主体化解：cd-025（admin）13.7s 应答并引用 3 篇受控文档
  （信息安全策略/员工隐私政策/IT 运维手册）；pt-007（general）0.2s 拒答、
  sources 为空；
- 过度屏蔽对照：nq-001 / nq-050（admin，general 文档）正常应答 ✓；
  进程内直查验证：同 query 无过滤命中 confidential 分块、general 过滤后
  仅剩 general 分块。

#### Notes
- 部署：arq payload 新增 `visibility` key，API 进程与 arq worker 需同批升级
  （旧 worker 收新 payload 会因未知参数报错）；存量向量按 general 语义兼容
- 后续：Java 会话 → Python chat 的 `X-User-Clearance` 注入（当前缺省 general，
  fail-closed，admin 主体在真实聊天链路生效需接通）；chunk 级工具
  （read_chunk/list_document_chunks）与直查端点 `/api/search` 的 ACL 接入

### 第三十四批（2026-09-05：B3 热点读缓存——知识库列表 + 版本化失效）

#### Added
- **HotReadCacheService**（[ADR-007](docs/adr/ADR-007-hot-read-cache.md)）：
  统一防雪崩（TTL ±20% 抖动）/ 防穿透（空结果哨兵缓存）/ 主动失效
  （版本号失联，免模式扫描竞态）三件套；**key 强制携带 tenant_id**
  （多租户缓存隔离为第一约束）
- 接入 `KnowledgeBaseServiceImpl.listByCurrentUser`（无名称过滤的前 10 页
  常规分页，空页也缓存）；create/update/delete/restore 四个写路径 bumpVersion
- 首查~1.9s 的检索链路缓存命中后 <10ms 量级（写路径代价：每次变更一次 INCR）
- FeatureFlag 修正：此前已有进程内缓存（方案信息过时），维持不动
- 测试：KnowledgeBaseServiceImplTest 补 HotReadCache mock，Java 全量 702 过

### 第三十三批（2026-09-05：C1 集成测试迁移真实 MySQL——H2 掩盖的 4 类问题现形）

#### Added
- **it profile + Testcontainers 集成基类**（[ADR-008](docs/adr/ADR-008-it-mysql-testcontainers.md)）：
  - `AbstractItMySQLTest`（PER_CLASS）：真实 MySQL + 完整 Flyway V1..V84，
    数据源二选一（`HFH_IT_JDBC_URL` 外部库 / Testcontainers mysql:8.0），
    无 Docker 时整类跳过；每类 @BeforeAll 全 schema 清空 + 重播核心种子
  - 迁移 6/8 个 @SpringBootTest 到真库全绿（mvn test 702 全过）；
    PromptTestSet（异步时序需 Awaitility 化）与 CostWebhookGate（需每类
    独立库隔离）两例暂缓并文档化
- **真 MySQL 揪出 H2 掩盖的 4 类问题**（迁移过程实录，全部修复/绕行）：
  - sys_user 在租户拦截器忽略表，插入必须显式 tenant_id（H2 列默认值掩盖）
  - DATETIME(0) 秒级取整：scheduled_at 存库后四舍五入到下一秒，立即查询差 1 秒
  - MySQL 容器 UTC vs JVM +8：NOW()/按天聚合差 8 小时（connection-init-sql 对齐）
  - agent_task↔agent_run FK 环 + 逻辑删除行：MP update/delete 命不中
    逻辑删除行，清理需 JdbcTemplate 裸 SQL + FK 免检 + runAsSystem 重试
- **runtime 基线重冻结**：工具路由（OPERATION 意图追加工具优先指令）后
  工具成功率 0.05→0.10；引用忠实度 0.707 / F1 0.698 / 召回 0.658 / 越界 0

### 第三十二批（2026-09-05：runtime 轨首次实测——A 线机制的真实流量验证）

#### Added
- **runtime 评测基线冻结**（`evaluation/baseline/runtime_baseline.json`，
  suite 1.1.0）：播种环境（kb_id=101 + DeepSeek-v4-flash 全栈）220 用例
  0 错误、越界检索 0。首次拿到答案层的真实数字：
  - 引用忠实度 **0.707**（F1 0.698）——按答案实际标注的引用评估（A3 生效）
  - 拒答正确率 **0.6125**，分解：注入 25/25 + 超纲 25/25 全部通过，
    **权限类 0/30 = 已知 ACL 缺口**（服务无访问控制层，非拒答机制缺陷）
  - 答案标注率约 50%（30 例样本，类别波动，长文档/多跳偏低待定位）
  - runtime 召回 0.658 vs 离线 0.932（生产检索栈 vs 合成轨的固有差异）
  - 工具成功率 **0.05→0.10**（工具路由生效后翻倍；上限受业务工具集
    缺失所限，见下）
  - P95 24.6s：DeepSeek 全链路多次 LLM 调用，本机实测仅作基线
- **工具路由（OPERATION 意图）**：run()/run_stream() 对操作类请求
  追加工具优先指令——模型正确尝试调用工具而非仅文字作答（验证跑
  工具成功率翻倍）
- **缺口收敛分析（ADR-006 增补节，不假实现）**：
  - 权限类拒答 0/30 根因 = 套件设计矛盾：权限用例与可答用例**共享
    同一批 section**（交集 10 个，如 permissions-matrix#hr-access 同时
    是 cd-028"必答"与 pt-013"必拒"的目标）——任何文档/section/关键词
    守卫都无法区分，唯一自洽机制是主体级 ACL（独立特性，列后续工作）
  - 证据门校准定案：实测融合分超纲 [0×5, 0.35~0.62] vs 正常
    [0.57~1.0]，阈值 0.63 可拦全部超纲但误杀 17% 正常查询——
    **维持默认关闭**，测量数据存档
  - 业务工具集（subscribe_plan 等 8 个）代码库不存在且无后端可挂，
    补齐属独立特性

#### Fixed
- **系统提示词引用格式对齐**：`[来源: 文档名称]`（且模型会编造文档名）
  改为 `[n]` 资料编号约定——旧格式与 RAG prompt 冲突导致 cited 解析为空
- 测试 +0（本轮 react 补丁由既有 31 个 react 测试与全量 1529 覆盖）

### 第三十一批（2026-09-05：B1 性能基线留档 + 全栈联调排障——模型降级链落地）

#### Added
- **全局模型降级链 `MODEL_FAILOVER_CHAIN`**：ModelGateway 支持配置化的全局
  fallback 链（如 `deepseek,ollama`）——任一请求主渠道失败/熔断后按序尝试
  后续渠道，与 per-request fallbacks 合并去重；此前 failover 只在调用方
  显式传 fallbacks 时生效，主渠道挂掉即全军覆没（联调时 DeepSeek 欠费
  402 暴露）。`docker/.env` 示例：`MODEL_FAILOVER_CHAIN=deepseek,ollama`
- **runtime 评测环境播种脚本 `scripts/seed_eval_kb.py`**：把合成评测 KB
  （10 篇，标题取自 kb_manifest）以 kb_id=101 上传/解析/索引到目标环境，
  重复执行先清库（runtime 轨的 staging 前提，README 评测节早有约定）
- **性能基线留档 `docs/baselines/baseline-v1-20260905.txt`**（单机全栈实测）：
  Java API 五个读端点 P95 21~130ms；RAG 检索 P95 2261ms（瓶颈=本地 CPU
  查询向量化，GPU/云端可显著下降）；文档处理端到端 P50 39.7s/篇

#### Fixed
- **eval_runtime 缺 X-Tenant-Id**：多租户 fail-closed 下批量请求被整体拒绝
  （eval-nightly 定义了 EVAL_TENANT_ID 却从未被读取）；补 `--tenant-id`
  参数与请求头；请求超时 60s→180s（RAG+LLM 全链路在 DeepSeek 高峰超 60s，
  超时被记成 error 污染 error_rate 门禁）
- **意图分类阈值接配置**：`HybridClassificationStrategy` 硬编码 0.7 改读
  `RoutingConfig.confidence_threshold`（该配置字段的真实语义归属）
- **证据门默认关闭（实测校准）**：runtime 实测合法查询融合分 0.626 被
  0.7 阈值拒答（单通道命中时融合分上限≈0.5-0.7，而超纲查询分数与正常
  不可分）——门机制保留，阈值改 `RAG_EVIDENCE_GATE_THRESHOLD` 默认 0
  （关闭），待 runtime 校准后显式开启
- **run-all-benchmarks.ps1 编码加固**：控制台固定 UTF-8（否则中文标题与
  curl 响应体按 GBK 解码，ConvertFrom-Json 直接失败）
- 测试 +5（降级链组装/去重/关闭语义），Python 全量 1529 过

### 第三十批（2026-09-05：A4 证据门 + groundedness 守卫修洞——A 线收官）

#### Added
- **证据门（[ADR-006](docs/adr/ADR-006-faithfulness-metric-recalibration.md) 增补）**：
  run()/run_stream() 在检索后、生成前判定——检索最高融合分（RRF 归一化
  0-1）低于 `routing.confidence_threshold`（默认 0.7，`RAG_ROUTING_CONFIDENCE_
  THRESHOLD` 可调）时走 `insufficient_evidence` 通道拒答；有非检索工具时
  让位 ReAct 循环（与空上下文分支同策略）。`routing.confidence_threshold`
  与 `ReflectionConfig.confidence_threshold` 两个死配置全部接入消费方
- **groundedness 守卫分数判据**：`_answer_support_score` 计算答案实质句对
  上下文的最大词元覆盖率（跳过 <10 字短句防误杀应答句），全部实质句低于
  `ReflectionConfig.confidence_threshold`（默认 0.6，新增
  `RAG_REFLECTION_CONFIDENCE_THRESHOLD` env）即判无依据——固定文案匹配之外
  补上分数判据，抓住词元层面完全脱离资料的幻觉

#### Fixed
- **groundedness 守卫洞①**：`was_compressed=False` 时守卫从不触发——短
  上下文路径的"无依据"答案直接以 completed 放行；现未压缩时走
  insufficient_evidence（流式按 content_reset 替换协议改发拒答），
  压缩过则保留原重试链路
- 测试 +13（证据门判据/支持分/守卫组合），Python 全量 1525 过

### 第二十九批（2026-09-05：A3 生成侧逐论断引用约束 + 答案标注引用接入度量）

#### Added
- **RAG 逐论断引用约束（[ADR-006](docs/adr/ADR-006-faithfulness-metric-recalibration.md) 增补）**：
  - `_build_rag_prompt` 要求每个论断末尾标注依据资料编号 `[n]`（多资料 `[1][3]`）
  - **保溯源压缩** `compress_numbered_blocks`：编号块上下文在合并文本上全局
    选句、按块归属重建——`[n]` ↔ `sources[n-1]` 对应关系贯穿压缩全程
    （编号是引用可溯源的基座；此前压缩会破坏编号）
  - 答案解析 `_parse_cited_chunk_ids`：`[n]` → 来源 chunk_id（越界/不可见
    忽略），`AgentResponse.cited_chunk_ids` → `ChatResponse.cited_chunk_ids`
    透出，流式路径在 sources 事件携带；groundedness 重试用全文时可见块恢复全集
- 分解/非分解流式检索路径统一 `_format_numbered_context` 编号格式

#### Changed
- **runtime 评测引用对齐**：`eval_runtime` 的 cited 集从"检索到的文档"改为
  "答案实际标注的引用"（未标注回退检索集），key-facts 忠实度同步按标注引用
  评估——runtime 轨从此量到生成质量；前后对比数字待真实服务实测采集
- **离线引用模拟与生产共用同一份压缩实现**：`compression_surviving_chunks`
  改为构造编号文本重放 `compress_numbered_blocks`（消除口径漂移），
  4 套基线重冻结（主套件 F1 0.7409，±0.0005 级变化）
- 测试 +11：编号格式化/标注解析/越界与不可见忽略/保溯源翻转/守卫旁路/
  契约回退，Python 全量 1512 过

### 第二十八批（2026-09-05：A2 压缩阶段——query 信号 + 引用模拟压缩感知）

#### Changed
- **抽取式压缩评分加入 query 重叠信号（A2）**：原四项权重（事实密度
  0.50/长度/位置/关键词）全部与问题无关，会把与问题直接相关但不含数字/
  日期的句子无差别压掉；新增 query 重叠项（0.40 事实密度 / 0.30 query
  重叠 / 其余 0.10×3；无 query 回退旧行为）。`react._safe_compress` 及
  全部 4 处调用点透传 query
- **离线引用模拟升级为压缩感知（ADR-006 增补）**：合并上下文按生产
  target_ratio=0.6 重放压缩，句子全被压掉的 chunk 不可引用
  （`compression_surviving_chunks` 与生产共用 `rank_sentences`，口径不漂移）；
  4 套基线重冻结：主套件 F1 0.7404 / P 0.7028 / R 0.8942，recall@5 不变
- **实测结论**：当前合成套件上压缩不是忠实度瓶颈（期望证据块存活率
  99.51%→100%，仅 1 条边缘 case），修复价值在事实密度不均的真实 KB，
  机制由确定性翻转单测锁定；忠实度真实杠杆在生成侧（A3）
- 分词器抽至 `app/core/rag/tokenization.py`（压缩器/评测共用，
  synthetic_index 保留 re-export）

#### Fixed
- **压缩缓存键缺 query**：`ContextCompressor._get_cache_key` 未含 query，
  不同问题对同一文本会互串压缩缓存；纳入后缓存键与压缩结果决定因素一致
- 测试 +6：query 信号机制（得分提升/权重回退/端到端存活）、
  `compression_surviving_chunks`（翻转夹具/守卫旁路/ratio=1.0），
  Python 全量 1501 过

### 第二十七批（2026-09-05：A1 评测度量口径修正——忠实度 0.355 正名）

#### Changed
- **离线引用指标口径重构（[ADR-006](docs/adr/ADR-006-faithfulness-metric-recalibration.md)）**：
  - 数据侦查推翻原假设：套件期望证据最多 2 块（{0:31, 1:158, 2:31}），固定 top-3
    引用窗口结构性偏大，精确率口径天花板 ≈0.388（实测 0.355 已贴近上限）；
    直觉方案"窗口 3→5"实测反而恶化（F1 0.50→0.35），否决
  - 引用窗口改为**相关性自适应**（`select_cited_chunks`：score ≥ 0.5×首块分数才算
    被引用，`--citation-top-k` 降级为硬上限默认 5）；新增 `citation_recall` /
    `citation_f1` 双报指标（离线/runtime/仿真三轨与基线 diff 全贯通）
  - 数字：精确率 0.3545→**0.7015**、召回率 **0.894**（新增）、F1 **0.739**（新增）；
    Recall@5 / nDCG 不变。**检索与生成未动，数字变化全部来自度量修正，
    不作为系统改进宣称**（对照留档 `python-ai/evaluation/reports/
    offline_metric_recalibration_20260905.md`，含窗口策略敏感度表）
- **门禁收紧**：CI 主套件显式加 `--minimum-citation-recall 0.85 --minimum-citation-f1 0.70`；
  4 套基线（offline / bid / bid_construction / bid_it）随口径重冻结（suite 1.0.0→1.1.0）

#### Fixed
- **套件类别契约**：25 条 category=refusal 超纲用例 `refusal` 字段漏标 none→required
  （runtime 轨拒答计分覆盖 55→80 条），`build_suite.py` 增加校验规则防回归
- **eval_offline `--min-score` 接线断裂**：参数此前传给 `SyntheticRouter` 而打分过滤
  实际发生在 `SyntheticIndex`——从未生效；接线修正，默认 1.0→0.0（BM25 原始分
  未归一化，1.0 底线会误杀 5 条用例的期望块）
- **CI 4 处坏导入**：套件完整性校验步骤 `from app.core.rag.eval_baseline import ...`
  指向不存在的模块，修正为 `scripts/eval_baseline.py`（CI 恢复时不再必红）
- **PYTHONSAFEPATH 兼容**：eval_offline / eval_local_sim / eval_runtime / eval_reranker
  显式插入脚本目录到 sys.path（`python -P` 环境下兄弟模块导入不再失败）
- eval 单测 +5（自适应窗口 / 引用召回 / F1 / 双报聚合 / 套件契约），Python 全量绿

### 第二十六批（2026-09-04：P1 收官——语义分块 + content_reset 桥接 + i18n 骨架 + 语音贯通）

#### Added
- **语义分块（实验档，RAG_SEMANTIC_CHUNK_ENABLED 默认关）**：
  - text_chunker：入库时按相邻句 embedding 余弦相似度找语义断点
    （`RAG_SEMANTIC_SIM_THRESHOLD=0.55` / `RAG_SEMANTIC_MIN_CHUNK=120`），
    替代固定窗口——句子永不切断，单句超长硬切兜底
  - embedding 失败/向量错位自动回退固定窗口，ingestion 绝不因实验特性失败；
    TABLE 块保持行对齐；与 Parent-Child 正交（可叠加）
  - 测试 8 个（断点/回退/最小长度/表格/硬切/零向量/直通）
- **content_reset Java 桥接（第二十四批遗留回归项）**：Python groundedness 重试
  路径的 `{"content_reset":true}` 此前在 Java SSE 桥被静默丢弃（无 event/content
  键掉出解析块）——现重置持久化缓冲并转发清空事件，前端气泡清空后重试内容
  替换重放；回归测试断言持久化只含重试文本 + 事件转发次数
- **前端 i18n 骨架（开源向）**：vue-i18n 10 + `useLocale`（localStorage 持久化，
  镜像 useTheme 模式）+ zh-CN/en-US 语言包（导航 27 项/分组/聊天输入/页头键，
  键结构一致性有单测守卫）+ 页头语言切换按钮；侧边栏与聊天输入区已接线，
  其余页面按需增量迁移
- **英文 README**（README_EN.md，与主 README 互链）
- **语音 STT language 贯通**：`transcribeAudio` 增加浏览器语言提示参数
  （`navigator.language` → `/voice/transcribe?language=`）+ API 单测 4 个。
  语音链路 Batch 10 已全端接线（前端麦克风/朗读按钮→Java 转发→Python
  OpenAI 兼容引擎），启用方式：`VOICE_ENABLED=true` + OpenAI 兼容语音凭据

#### Changed
- 测试计数：Java 701→**702** · Python 1443→**1451** · 前端单测 49→**57**

### 第二十五批（2026-09-04：God class 收尾——Vectorization 回调持久化分离）

- **`VectorizationServiceImpl` 1104→892 行，God class 三批拆分全部收官**：
  - 回调持久化（`updateDocumentStatus` 链路：签名回调→job/document 终态落库→
    V2 分块元数据整体替换）拆入新 `VectorizationCallbackService`；
    `VectorizationService` 接口删除 `updateDocumentStatus`，回调 Controller 直连
  - INDEX_CHUNKS 账本生命周期（预占/结算/退回 + 估算 + 预占键 + 租户解析）
    收口新 `IndexChunkLedger`——预占键格式贯穿 reserve→settle/release 三方，
    必须单点维护（编排侧失败退回与回调侧终态结算共用同源实现）
  - 行为零变化：ImplTest 32 个（编排/回调全保留，手动构造双服务+共享账本）、
    CallbackSignatureRealPath 换目标验证回调直达新服务
- 上一批（第二十四批）顺延说明作废：God class 三批已全部完成

### 第二十四批（2026-09-04：A 档深化——Parent-Child 检索 + schema-h2 真对齐 + God class 第三批·Agent 决策链路）

> God class 第三批本批完成 **AgentTaskServiceImpl 审批决策链路拆分**；
> ~~VectorizationServiceImpl 回调持久化分离仍顺延下一批首项~~（已于第二十五批完成）。

#### Added
- **Parent-Child 父子分块检索（实验档，RAG_PARENT_CHILD_ENABLED 默认关）**：
  - chunker：同一 block 切出多窗口时，各子块 metadata 附着块级父内容
    （`parent_id` + `parent_content`，截断 2600 字；metadata 预算守卫超限自动降级丢弃）
  - postprocessor：rerank/top_k 之后做父展开——子块 content 替换为父正文 +
    同父去重（只保留最高分子块）；门控/去重仍按子块粒度评估（插在 top_k 之后，语义不变）
  - citation 保持子块 chunk_id（溯源与"知识来源"面板不变）
  - 测试 10 个（附着/预算守卫/展开/去重/flag 关直通）
  - eval 离线门禁实测零回归（regressions: [], gate_failures: []）
- **schema-h2 真对齐 V84（漂移零容忍）**：补齐 6 张缺失表（memory_entry/note/
  system_notice/notice_recipient/eval_harness_runs/table_lineage，H2 兼容翻译：
  剥内联索引/ENGINE 尾缀/FK/ON UPDATE）+ 10 表 tenant_id 列 + 5 个 embedding 列 +
  tenant_plan_binding.deleted + V74 全部租户索引；漂移基线清空为**零容忍**
  （此后任何新迁移不同步 schema-h2 直接 CI 红）
- **God class 第三批（Agent 决策链路）**：`AgentTaskServiceImpl` 1414→**975 行**——
  - `decideApproval`/`resumeAgentAfterApproval`/`getChatHistoryForTask`
    拆入新 `AgentTaskDecisionService`（M2 afterCommit 语义原样迁移，含并发结算
    守卫告警；Controller 直连决策服务，`AgentTaskService` 接口删除 decideApproval）
  - 审批令牌哈希（签名/校验必须同源）与时长钳制收口 `AgentTaskSupport`
    共享纯函数，消除拆分副本（哈希规则漂移会导致全部审批恢复失败）
  - impl 顺带移除不再使用的 messageMapper 依赖（13 构造参数）
  - 测试同步：RaceGuard 直测决策服务；Clamp 换 AgentTaskSupport 静态引用；
    其余构造器同步；行为零变化（35 个定向测试全绿）

#### Changed
- Python 测试 1411→**1443**（多模态 12 + QA 生成 8 + 回退 2 + Parent-Child 10 + 计数同步）
- Flyway 窗口语义不变（仍 V84，本批只补 schema-h2 与索引）

### 第二十三批（2026-09-04：全功能审查修复——25 项真 bug）

### 第二十二批（2026-09-04：A 档改进——对话图片输入 / QA 对生成 / 演示脚本）

#### Added
- **对话图片输入（实验档，三端贯通）**：
  - Python：`/api/chat/stream` 等四个聊天端点的消息体新增 `images`（data URL，≤4 张、单张 ≤5MB）；
    新增 `app/utils/vision.py`（魔数/大小校验 + Ollama 视觉模型逐图中文描述 + 上下文组装），
    `CHAT_MULTIMODAL_INPUT_ENABLED` 门控（默认关；关闭时带图请求 400 用户可读文案，不被兜底转 500）。
    路线为"图片→VLM 中文描述→并入提问"——不要求对话模型自身具备视觉能力
  - Java：`V84` 迁移（`message.images` TEXT，相对 URL JSON 数组）+ schema-h2 同步（漂移防护零新增）；
    新增 `ChatImageStorage`（魔数校验/UUID 签发/路径穿越防护/URL→base64）+ `ConversationController`
    上传与回源端点（回源需登录态，fetch+blob 模式与头像一致）+ `AiClient` 四条链路 images 透传
    （doChat 委托化，既有调用方零改动）
  - 前端：聊天输入区图片选择/预览/移除（≤4 张），用户气泡渲染图片（乐观渲染用 objectURL，
    历史加载经登录态 fetch 转.objectURL），普通与流式发送体携带 images
  - 测试：Python 12 个（校验/门控/组装/端点 400 与 query 组装）+ Java 8 个（存储组件全覆盖）
- **知识库 QA 对生成（实验档，RAG_QA_GENERATION_ENABLED）**：`app/core/rag/qa_generator.py`
  ——文档解析入库时用对话 LLM 从分块生成问答对（问句入 BM25/向量双通道），`block_type="QA"`
  独立分块类型（前端 amber chip）；去重（标点不敏感）/总量上限/失败软化（单分块失败只跳过）；
  新增 8 个纯逻辑测试；`Chunks.vue` 类型筛选与主题新增"问答"
- **演示/运维脚本**：`scripts/demo-trace.ps1`（追踪一键演示：带 W3C traceparent 发请求→
  Tempo 按 id 检索→打印 Grafana 查看指引）+ `scripts/eval-report.ps1`（离线评测门禁一键运行，
  JSON+Markdown 报告；实跑通过）

#### Fixed
- **会话图片不持久显示（双根因，E2E 发现）**：①流式/队列路径内联保存用户消息，
  绕过 `saveUserMessage`——`images` 从未落库；②`MessageMapper.xml` 的
  resultMap/列清单缺 `images`（连带 `request_id`）映射——落库后也查不出。两处补齐后，
  回答完成与历史加载均正常显示图片（objectURL 双保险 + `<img>` 同源 cookie 可加载）
- **会话打开滚动定位停在顶部**：Markdown/图片异步渲染导致首帧滚动后容器高度继续增长——
  加载后 200/600ms 校正滚动 + 消息图片 `@load` 贴底（near-bottom 保护，不拉扯上翻阅读）

#### Fixed
- **模型网关 dict 消息崩溃**：`_estimate_tokens` 假定消息必为 ChatMessage 对象，标准 dict
  messages 调用 GatewayLLM 直接 AttributeError——已兼容对象/dict 两种形态（E2E 自验发现）
- **qa_generator**：prompt 模板含 JSON 花括号示例，`str.format` KeyError——改 replace；
  消息改用项目原生 `ChatMessage`（Gateway 链路原生类型）
- **VLM 超时过紧**：CPU 冷启动（模型卸载后重载）实测超 90s 默认值——放宽到 180s

#### Added
- **队列模式图片透传**：`AgentTaskQueueServiceImpl` Worker 按 task.requestId 取回用户消息，
  解析 images → base64 → agentV1ChatStream/streamChat 新重载（构造器与测试桩同步）；
  队列模式下图片同样进入视觉管线
- **绑库会话图片拒答回退**：V1 流式对图片消息缓冲内容，KB 证据门控拒答时替换为
  基于图片描述的直答（不再对无关图片一律"未检索到依据"）；KB 正常作答时原样保留；
  新增 2 个端点测试（拒答替换 / 正常保留）
- **Enter 偶发不发送结论**：非 bug——上一轮流式生成期间输入框设计性禁用（防并发流），
  生成完成即恢复；浏览器 5 轮复现测试 2 轮成功、第 3 轮超时即该锁所致

#### Changed
- Flyway 版本窗口 V83→**V84**（`message.images`），文档五处同步；Python 测试 1411→**1433**（多模态 12 + QA 生成 8 + 回退 2 + 计数同步）、
  Java 693→**701**（图片存储组件 8 个测试）


### 第二十一批（2026-09-04：全仓巡检修复——编码/构建/文档）

#### Fixed
- **5 个 PowerShell 脚本缺 UTF-8 BOM**（`restart-modules.ps1`/`run-all-benchmarks.ps1`/
  `backup-data.ps1`/`plugin-builtins-e2e.ps1`/`plugin-e2e-acceptance.ps1`）——Windows
  PowerShell 5.1 按 ANSI 解析中文脚本，字节错拆导致 `run-all-benchmarks.ps1` 直接解析
  失败（"哈希文本不完整"/未终止字符串）；补 BOM 后全部 ps1 语法校验通过
- **前端 `npm run build` 是坏的**：`MainLayout.vue` 菜单项对象使用 `sidebar` 属性但内联
  类型未声明（侧边栏瘦身提交引入，dev 模式不做类型检查故未暴露，4 个 TS2353/TS2339）；
  补 `sidebar?: boolean` 类型，build 恢复通过
- eslint 自动修复 93 → 25 警告（0 错误；剩余为 no-explicit-any 类非自动可修项），
  修复后 build + vitest 49/49 复验通过

#### Changed
- CLAUDE.md 结构性计数对齐实测：Controllers 53→55（`bot/` 3 个 IM bot）、Services
  40→41 接口 + 3→4 独立 @Service、Entities 64→71
- ACCESS_MAP.md 补监控栈（Grafana 3001 / Prometheus 9090 / Tempo 3200）访问入口与端口速查
- TROUBLESHOOTING.md 新增两条实测故障：dind 元数据卷损坏（bbolt panic）重建、
  hive-server2 残留 PID force-recreate
- 监控 compose：mysqld/redis exporter 加 `profiles: ["exporters"]`（独立启动监控栈时
  无 mysql8/redis7 网络可连，原会进重启循环）

### 第二十批（2026-09-04：P0 补强三连——分布式追踪 / H2 漂移防护 / 备份异地化）

#### Added
- **跨服务分布式追踪（全链路打通）**：
  - Java：`micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp`（Boot BOM 管版本），
    `TRACING_ENABLED` 默认关（零开销）；开启后 RestTemplate/WebClient 调 Python 自动注入
    `traceparent`，span 经 OTLP 导出到 Tempo
  - **WebClientConfig 修复**：改注入 Boot 自动定制的 `WebClient.Builder`（原裸
    `WebClient.builder()` 会绕过 ObservationWebClientCustomizer，SSE 流式链路追踪断链）
  - Python：`TraceMiddleware` 新增 W3C `traceparent` 提取——OTEL 启用时开服务端 span
    并入 Java 同一调用链；`requirements.txt` 补 otel 三件套（1.29.0，未安装则优雅降级）；
    `telemetry.py` 弃用 API（semconv ResourceAttributes）替换为稳定字符串键
  - 监控栈：新增 Tempo 2.7.0（OTLP 4318 / 查询 3200，本地存储 72h）+ Grafana Tempo
    数据源自动装配；`docker-compose.monitoring.yml` 校验通过
  - 生产 compose：java/python 服务透传 `TRACING_ENABLED`/`OTEL_ENABLED`/
    `OTEL_EXPORTER_OTLP_ENDPOINT`/`TRACING_SAMPLING`（`deploy/.env.example` 带注释样例）
  - **实弹验证（Tempo 真机）**：Java 与 Python 的 span 均导入 Tempo；以同一 W3C
    traceparent 分别请求两侧，`/api/traces/{id}` 返回**同一条 trace 内同时含
    hfusionhub-backend 与 hfusionhub-python-ai**，两侧 server span 的 parentSpanId
    均正确指向上游 context——跨服务调用链组装闭环
- **H2 测试 schema 漂移防护（R15-22 收尾）**：`scripts/check-h2-schema-drift.py` 静态解析
  V1–V83 迁移链（CREATE/ALTER 全语义，含反引号/字符串内逗号）对比 schema-h2.sql；
  现存 23 条历史漂移（6 张缺表 + 17 缺列）已入 `h2_schema_drift_baseline.json` 基线，
  **新增漂移即 CI 报错**；已挂进 `static-checks.py`（`--h2-schema-drift`，默认开启）
- **备份异地化**：`backup-mysql.sh` 支持 `BACKUP_REMOTE_CMD`（`{}` 占位文件路径，
  rclone/rsync/scp 皆可）推第二存储；`COMPOSE_FILE` 可环境变量覆盖（开发栈也能备份）；
  顺手 `--no-tablespaces` 消除 mysqldump PROCESS 权限警告。实测：开发栈真实备份 +
  模拟异地推送成功

#### Changed
- 测试：新增 2 个 traceparent→OTel span 集成测试（含父级/trace id 断言），
  Python 1409 → **1411**（README/AGENTS/CLAUDE 计数同步）

### 第十九批（2026-09-03：修复收尾 + 运维脚本补齐）

#### Fixed
- **全仓乱码清零**：`StatusCode.java`「分块不存在」注释截断修复；`schema-h2.sql` 32 处注释乱码（29 处 UTF-8 截断 + V52/V53/V54 三行 GBK 串码，经字节级正向模拟还原原文：应用发布的 API Key / 知识库共享 / 操作审计日志）；`pdf_parser.py` 坏字符统计 U+FFFD 双重计数 bug（约 2.5% 替换符即被误判到 5% 拒稿阈值）
- **backup-mysql.sh 校验环节 SIGPIPE 误判**：pipefail 下 `zcat|head|grep -q` 恒返回 141，成功备份会被误判损坏而删除；改为先截取头部字节再匹配

#### Changed
- **R15-24 第二批 God class 拆分**：`MessagePersistenceService` 自 ConversationServiceImpl 收口（用户/助手消息落库 requestId 幂等 + Message→MessageInfoDTO 转换 + 幂等查找），1595→1373 行；会话相关 15 测试全过
- **R15-22 真机复核**：`TenantInterceptorIsolationTest` 连真实 MySQL（完整 Flyway V1–V83 链）2/2 通过
- **R15-29 状态确认**：前端 chat 断线重连（幂等 requestId 重试 + rAF 滚动）此前已实现，文档补记

#### Added
- `scripts/restore-mysql.sh`：MySQL 备份恢复/演练脚本（重建库→灌 dump→关键表行数核验）；开发栈真实演练通过（78 表、9 张关键表行数逐一吻合）
- `scripts/rotate-db-password.sh`：数据库密码轮换"落实"脚本（.env 新密码经 stdin ALTER 到 root/hfusionhub 账户，`--check` 重启后复核；开发栈跳过/复核路径实测正常）

### 大数据扩展包批（2026-08-31 第十八批：HFusionData Analytics）

#### Added（个人项目 + 可上线产品双形态的分析扩展包）
- **总体**：以 Hadoop 生态为主线的运营数仓扩展包（HDFS/YARN/Hive/Spark/
  MapReduce/Sqoop-等价/Flink CDC/ClickHouse/Superset），独立 compose profile
  （`docker/docker-compose.analytics.yml`），主产品零依赖、默认关闭。
  完整架构/数据字典/部署运维/演示动线见 `docs/BIGDATA_ARCHITECTURE.md`
- **采集层**：`full_import.py`（Spark JDBC 全量，dt 分区幂等）+ 经典 Sqoop
  命令单 + `jsonl_to_hdfs.sh`（评测 JSONL 入湖）+ Flink CDC 作业
  （binlog→Kafka→HDFS，checkpoint 断点续传，主产品零侵入）
- **数仓**：Hive 四层 HQL 七件套（ODS/DIM/DWD/DWS/ADS/查询示例）；
  计算存储解耦设计（外部表指向 Spark 写入的同一 Parquet，规避 metastore
  客户端版本耦合）
- **离线计算**：PySpark 四作业（dwd 租户回补/dws 聚合/ads 回写 MySQL/
  quality 六类规则门禁，不合格阻断下游；按 dt 回补幂等）；MapReduce
  经典词频作业（CJK bigram，mvn 编译通过）
- **实时链路**：Flink SQL 1min 窗口聚合 → `analytics_realtime_metrics`；
  `RealtimeThresholdScheduler` 采样暴露 3 个 Micrometer gauge，
  新增 `hfusionhub_slo_analytics` 告警组（延迟/成本尖峰/链路停滞）
- **应用层**：V82 迁移（实时指标/5 张 ADS 镜像/批处理日志，全部含
  tenant_id）+ `AnalyticsController`（/analytics 六端点，服务端租户强制
  隔离，普通用户仅本租户）+ `BigDataBatchScheduler`（@SchedulerLock
  日结，默认关闭）+ 内部回补端点（X-Internal-Token 保护）
- **可视化**：Vue3 大屏页 `/analytics`（概览/成本趋势/模型占比/步骤成功率/
  评测质量/实时区 30s 轮询，零新前端依赖）+ Superset 配置与 5 看板说明
- **数据制造器**：`seed_generator.py`（FK 安全链式造数，长尾租户/双峰
  时段/对数正态 token，百万级）+ ClickHouse 标准档初始化脚本
- **测试**：AnalyticsControllerTest 4 例 + AnalyticsBatchRunnerTest 5 例
  （模板替换/SKIPPED/失败中止/质量门禁阻断 ADS/全绿管线）

### 技术债清偿批（2026-08-30 第十七批：文档漂移/依赖健康/竞态行锁/租户桶/缓存模糊命中/巨型类拆分）

#### Verified（2026-08-31 全链路实跑验证）
- **离线链路端到端跑通**:seed 15 万行合成事件 → Spark JDBC 全量导入
  HDFS(178,945 行 Parquet)→ DWD/DWS 四表 → 质量门禁 **14 条规则全绿**
  (实跑中还抓到主产品 2 条负延迟脏数据与 meter 枚举清单过期——门禁真实有效)
  → ADS 四表回写 MySQL(279/1120/248/1342 行,`/analytics` 大屏数据就绪)
  → Spark SQL 与 Hive 同口径查询验证通过
- **实时链路端到端跑通**:Flink CDC(MySQL binlog→Kafka,增量快照+chunk key)
  → Flink TVF 1 分钟窗口 → MySQL `analytics_realtime_metrics`
  **12,879 个窗口行**;RealtimeThresholdScheduler 采样与
  `hfusionhub_slo_analytics` 告警组数据源就绪
- **12 条实测踩坑记录**沉淀到 docs/BIGDATA_ARCHITECTURE.md §5.2.1
  (NN 格式化/PG 驱动/SERVICE_NAME/fs.defaultFS/网络归属/Tez NPE/
  CDC 认证与快照模式/upsert-kafka/jar 挂载持久化/密码注入校验)

#### Fixed（文档与仓库卫生）
- **CLAUDE.md 全面漂移修复**：Spring Boot 3.2.5→3.5.16、测试数 1247/567→1344/595、
  Controller/Service/Entity 计数（25/25/42→53/43/64）、前端页面 13→43 路由、
  失效引用 `test_retriever.py`→`test_adaptive_retrieval.py`；AGENTS/README/
  docs/java-backend.md/docs/database.md 的 Flyway 窗口统一为 V1–V81 / V82+；
  `static-checks.py` 新增检查 3 的 CLAUDE.md 测试表校验 + **检查 4
  （Flyway 版本窗口文档同步）**，迁移目录再进版本后文档漂移会被 CI 拦截；
  ACCESS_MAP.md 首尾日期对齐；清理入库调试产物（verify-body.json、
  measure_stream.py/.ps1、chinese-test.json）
- **CI 运行时对齐**：4 个 workflow 的 Python 3.12→3.11（与锁文件/本地 venv/
  pyproject 一致）、Java 21→17（与 pom/Dockerfile 一致）；
  `deploy/Dockerfile.java` 构建与运行镜像同步降为 temurin-17

#### Changed（依赖健康）
- **PyPDF2→pypdf 6.16.2**：PyPDF2 已废弃停更（并入 pypdf）；`pdf_parser.py`
  切换 import（API 兼容），requirements.in/requirements.txt（hash 锁）同步，
  移除锁文件 `--trusted-host mirrors.aliyun.com`（削弱传输校验语义且非必需）

#### Added（测试覆盖）
- **query_rewriter**（原零覆盖）：33 例（指代替换/拆分/术语扩展/单例），
  顺带修 `original_query` 语义 bug（误存替换后文本）与 `_split_query`
  全角问号被改写为半角的粗糙行为（保留用户标点风格）
- **agent/checkpoint**（原零覆盖）：save/load/load_at_step/INSERT OR REPLACE
  幂等/删除/清理/并发/`build_checkpoint_from_agent` 映射，共 19 例
- **LLM 响应缓存**：+4 例模糊命中（归一化命中/开关关闭/TTL 过期/api_key+model
  仍参与键）
- **VoiceController**（原零覆盖）：8 例（转发/内部令牌注入/空体 400/降级 503）
- **AgentObservabilityController**（原零覆盖，25 端点）：27 例全端点契约测试
- **NoteServiceImpl / WebhookSubscriptionServiceImpl**（原零覆盖）：10+13 例
  （归属校验/校验规则/分页/投递历史/testFire 委托）
- **审批竞态守卫回归**（AgentApprovalRaceGuardTest，6 例）：deny/approve/expire/
  resume 失败收敛四条路径——只有条件 UPDATE 真正迁移成功的一方结算账本
- **MinioArtifactStore**（原零覆盖）：5 例（租户桶写入/默认桶/旧对象回退/解析）
- Java 侧 JaCoCo 棘轮 45%→46%（实测 47.4%）

#### Changed（行为与架构）
- **S3/M3 审批竞态升级为完整行锁**：`AgentRunMapper` 新增
  `transitionRunStatusGuarded`（WHERE status=?）与
  `transitionRunStatusFromAnyActive`（WHERE status NOT IN 终态）两条条件
  UPDATE；deny/approve/expire/resume 失败收敛四处迁移由 check-then-act 改为
  数据库行级原子判定，仅迁移成功方结算用量（原"守卫级"标记清除）
- **AgentRunLifecycleService 收口**（AgentTaskServiceImpl 拆分第一步）：
  守卫迁移 + 用量账本结算 + 租户归属解析统一入口（1412→约 1360 行）
- **ChatUsageRecorder 收口**（ConversationServiceImpl 拆分第一步）：
  账本结算/退回 + 模型用量落账 + 预占估算统一入口（1647→1595 行）
- **SchedulerLockAspect fail-open→fail-closed 默认**：Redis 故障时跳过本轮
  调度等待下一周期补偿，不再无锁并发执行；`SCHEDULER_LOCK_FAIL_OPEN=true`
  可回退历史行为（测试同步更新）
- **MinIO per-tenant bucket 隔离（R15-28 收尾）**：插件工件上传写入
  `hfusionhub-t<tenantId>` 租户专属桶（自动建桶 + 桶缓存）；读取/删除/
  预签名优先租户桶、未命中回退默认桶兼容旧对象；旧签名保留 @Deprecated
- **LLM 响应缓存归一化模糊命中**（OPTIMIZATION_PLAN P2 收尾）：精确 miss 后
  以空白折叠+casefold 的归一化键二次查找；写入同步维护两条索引；
  `LLM_RESPONSE_CACHE_FUZZY_ENABLED`（默认开）可关

#### 顺延（明确记录）
- **grpcio 1.67.1 升级**：pip-compile --upgrade-package 在国内镜像下挂起，
  为避免手工升级 pymilvus 传递依赖风险，保留 1.67.1（无已知未修复 CVE），
  待网络窗口期重新 pip-compile
- **react.py 三管线渐进重构（第一批）**：提取 `_build_react_messages` /
  `_retrieve_and_compress` / `_empty_context_reply` 三个共享助手，消除
  run/run_stream/_run_stream_react 三份重复的提示词+记忆注入、检索+压缩、
  空上下文提示逻辑；ReAct 循环本体合并仍列渐进项
- 生产部署侧（TODO.md P0）为真机操作：deploy/.env 六个密钥已是强随机，
  HTTPS/CORS 白名单/Swagger 关闭的仓库侧配置与脚本均已就绪

#### Verified & Hardened（2026-08-31 阶段二:产品化加固实测)
- **安全复核清零**:`rotate-secrets.sh --check` 原报 2 项——MINIO_ROOT_USER 弱默认
  (minioadmin)已轮换为强用户名(MinIO 重启实测 live 200,Java 侧同步
  MINIO_ACCESS_KEY/SECRET_KEY);MODEL_CREDENTIAL_ENCRYPTION_KEY 补配(32 字符)
- **告警规则校验**:promtool check rules **28 条全部合法**(含 analytics 组)
- **CDC 断点续传实测**:restart TaskManager → CDC/实时作业自动从 checkpoint
  持久卷恢复 RUNNING,窗口行 PK upsert 防重;运维复杂度固化为
  `bigdata/scripts/start_realtime_jobs.sh` 一键重建(先 cancel 全部→生成运行时
  SQL→密码 md5 校验→提交,实测重建双作业 RUNNING)
- **备份恢复演练**:一致性 dump(1.7s/4.4MB)→ 临时库恢复 **RTO 14.3s** →
  四表精确 COUNT 对账 100% 一致(model_usage_record 50,028/usage_event
  100,354/agent_step 19,852/analytics_realtime_metrics 38,383)
- **grpcio 1.67.1→1.83.1**:锁文件手动换条目(51 平台哈希,aliyun simple API),
  venv 升级后 Python 全量 **1415 passed**(pymilvus 兼容验证)
- **VectorizationServiceImpl 拆分(1205→1101 行)**:进度估算/阶段映射纯计算族
  收口为 `VectorizationProgress`(9 个单测锁定行为:估算钳制/阶段迁移/
  动态估算边界/copyIfPresent)
- **负延迟源头修复**:AgentTaskServiceImpl 提取 `clampDuration`(completeRun
  fallback 与审批恢复路径统一钳制),6 单测覆盖时钟回拨场景;流式路径
  durationMs=0 的 fallback 不再产出负 latency
- **Java 重启排障记录**:spring-boot 本地启动需 DB_PASSWORD(非
  MYSQL_PASSWORD)/SPRING_DATA_REDIS_PASSWORD 等变量,.env 有 BOM 需剥离,
  .env 扩展名不被 Spring 识别——复制为 target/env.properties 经
  SPRING_CONFIG_ADDITIONAL_LOCATION 注入

#### Fixed（2026-08-30 收官冒烟）

- **网关流式不可用**：`ModelGateway._stream_provider` 误用 `async def` + `return`
  内层生成器——所有 `/api/chat/stream` 真实调用报 "'async for' requires an object
  with __aiter__"。单轨化（08-29）引入，单测 mock 掉该方法未暴露、CI 停摆无冒烟
  兜底；改普通 `def` 直接返回 async generator，并新增防回归用例
  （inspect.iscoroutine 反向断言）。Python 全量 1378 passed。

### 权限细化 + 语音 + GraphRAG 复评批（2026-08-30 第十六批，Batch 10 收官）

#### Added
- **资源级授权矩阵**：`kb_share.permission` 两档生效（`read` | `read_write`）——
  `KbShareService.share` 支持档位与重复共享=更新；新增
  `getEffectivePermission(userId, kbId)`（owner/read_write/read/null）；
  `DocumentServiceImpl.upload` 放行 read_write 共享（read 明确拒绝，
  删除/管理仍所有者专属）；分享 API 带 `permission` 字段 + 知识库详情页
  分享对话框权限下拉
- **语音 STT/TTS**（`VOICE_ENABLED` 默认 false，关闭时端点 503/按钮不渲染）：
  - Python `app/api/voice.py`：`/api/voice/transcribe`（原始音频字节 +
    X-Audio-Filename 头，避免引入 multipart 依赖）、`/api/voice/synthesize`
    （文本→mp3 二进制）、`/api/voice/status`；引擎为 OpenAI 兼容
    /v1/audio/*（通义/OpenAI）
  - Java `VoiceController`（/voice/**，登录态）：字节流转发 + 内部令牌注入
  - 前端：`api/voice.ts` + 聊天页语音输入按钮（MediaRecorder→STT→填入输入框）
    与助手消息播报按钮（TTS→Audio 播放）
  - 测试：`test_voice.py` 7 例（503 门控/格式与空体校验/状态能力位）
- **GraphRAG 数据驱动复评**（docs/GRAPHRAG_REVIEW.md）：离线确定性轨道
  （220 case 冻结套件）实测 cross_document 30 case **Hit@5=100%**、
  Recall@5=0.900，整体 Recall@5=0.932 / nDCG@10=0.903——多跳场景混合检索
  已达高位，GraphRAG 边际收益不足，**不立项重建**；文档载明重开条件
  （cross_document Hit@5<0.85 持续出现且归因为实体关系跳接缺口）

### 多 Agent 模式批（2026-08-30 第十五批）：supervisor / handoff 编排（无 DSL）

#### Added
- **`BoundedMultiAgentWorkflow` 新增 `mode` 参数**（三种有界编排模式，全部复用
  同一 delegate / KB scope / 超时 / 确定性证据门控，不引入 DSL）：
  - `pipeline`（默认）：原 P10 行为不变（researcher → critic → synthesis）
  - `supervisor`：检索研究员产出初答后，按确定性规则分派一个「补充分析」专家
    （同一 delegate + 查漏限定提示），产出经证据门控后确定性合并
    （【补充要点】追加 + 来源按 chunk_id 去重合并；"无补充"/无证据/异常时
    回退初答）——不引入自由 LLM 汇总，sources 只能来自同 KB delegate 产物
  - `handoff`：顺序移交——检索棒证据不足时移交扩展检索棒（改写提示重跑，
    handoff 事件留痕），移交次数 `max_handoffs` 硬上限（默认 1），全部失败走
    既有 insufficient 语义
- **流式**：supervisor/handoff 非流式执行后按 run_started → step_completed →
  文本 → run_completed 事件契约一次性发流；pipeline 流式路径不变
- **配置**：`RAG_MULTI_AGENT_MODE`（pipeline|supervisor|handoff，默认 pipeline）
- **测试**：`test_multi_agent_modes.py` 10 例（补充合并/无证据丢弃/查漏回退/
  拒答保留/早退/移交改写/上限/流式契约/pipeline 透传/非法模式拒绝）+
  既有 test_multi_agent_workflow.py 回归

### 任务队列外置批（2026-08-30 第十四批）：arq worker + compose python-ai-worker

#### Added
- **`core/tasks/queue.py`**：`dispatch_document_processing` 按 `TASK_QUEUE_MODE`
  分发解析/向量化任务——`inline`（默认，BackgroundTasks 进程内，零依赖）|
  `arq`（入 Redis 队列）；arq 入队失败自动降级 inline（告警日志）
- **arq worker**：`app/core/tasks/arq_tasks.py`（process_document 任务复用
  vectorization 生产链路全流程，job_timeout=1800 / max_jobs=4）+
  `python-ai/arq_worker.py` CLI 入口（`python -m arq arq_worker.WorkerSettings`）
- **compose**：新增 `python-ai-worker` 服务（同镜像，dev/fullstack 栈默认启用，
  python-ai 与 worker 均设 `TASK_QUEUE_MODE=arq`）；`deploy/Dockerfile.python`
  显式钉版安装 arq==0.26.3（锁文件哈希不受扰动，requirements.in 声明意图）
- **配置**：`TASK_QUEUE_MODE` / `ARQ_REDIS_DSN`（默认 redis://localhost:6379/2）
- **测试**：`test_task_queue.py` 5 例（inline 直通/转交 kwargs/arq 入队 payload/
  失败降级/worker 任务函数委托）——arq 延迟导入 + sys.modules 假模块，
  测试环境无需安装 arq

### 可插拔审核批（2026-08-30 第十三批）：外部内容安全 provider

#### Added
- **`core/policy/moderation_provider.py`**：审核引擎抽象（ModerationProvider 协议
  + ModerationVerdict）+ `HttpModerationProvider`（通用 REST：POST {text, kind}，
  响应 dot-path 解析 flagged/category/score，适配阿里云内容安全/网易易盾等）。
  `MODERATION_PROVIDER=local`（默认，零行为变化）| `http`
- **ContentModerator 集成**：check_input/check_output 在本地规则之后调用外部引擎，
  命中即硬阻断（flag `external_moderation:<category>`）；外部失败 **fail-open**
  （告警放行，本地规则仍生效）——与仓库"外部引擎失败只跳过"取舍一致
- **配置**：`MODERATION_HTTP_ENDPOINT/API_KEY/TIMEOUT_SECONDS/FLAGGED_PATH/
  CATEGORY_PATH/SCORE_PATH`
- **测试**：`test_moderation_provider.py` 8 例（工厂/请求构造/dot-path 解析/
  输入输出阻断/fail-open/local 不变）

### 发布渠道批（2026-08-30 第十二批）：可嵌入挂件 + 飞书/钉钉/企微机器人

#### Added
- **`POST /openapi/chat/stream`**（SSE）：开放 API 流式对话——与 `/openapi/chat`
  同一套 Key 解析/限流/计费（run_completed token_usage 提取入 app_call_log），
  经 Agent V1 通道转发（要求应用绑定知识库）
- **可嵌入聊天挂件**：前端新路由 `/embed/chat?key=<开放API Key>`（无需登录态，
  iframe 友好）：独立聊天壳（SSE 流式渲染/Markdown+DOMPurify/取消/历史携带），
  接入文档 docs/PUBLISH_CHANNELS.md
- **IM 机器人适配器**（`com.hfusionhub.bot`，全部默认关闭，统一复用开放 API
  鉴权/限流/计费链路）：
  - 钉钉（企业内部机器人 HTTP 模式）：timestamp+sign HMAC-SHA256 加签校验
    （常量时间比较），sessionWebhook 回复
  - 飞书（事件订阅明文模式）：url_verification challenge 回显 + verification
    token 校验 + tenant_access_token 缓存 + IM API 回复
  - 企业微信（自建应用回调）：官方加解密协议纯 JDK 实现（WeComCrypto：
    SHA1 签名 + AES-256-CBC/PKCS7，round-trip 测试）+ 应用消息主动回复
  - `BotChatService`：平台消息 → 开放 API chat，异常全部降级为用户可读兜底文案
- **配置**：`bots.dingtalk/feishu/wecom.*`（BotProperties），含每 bot 的
  appKey 与平台凭证
- **测试**：BotAdaptersTest 8 例（钉钉签名/企微 round-trip+篡改拒绝/飞书
  challenge/服务降级/默认关闭）+ docs/PUBLISH_CHANNELS.md

### Embedding 多通道批（2026-08-30 第十一批）：云端 embedding + 检索元数据过滤

#### Added
- **`OpenAICompatibleEmbedding`**（`core/embedding/openai_compatible.py`）：通义/OpenAI
  等任意 `/v1/embeddings` 端点；复用共享连接池 + P3 有界重试；**维度 fail-closed 校验**
  （异维向量拒绝写入，保护 Milvus collection 完整性）
- **EmbeddingService 双通道路由**：`EMBEDDING_PROVIDER=openai_compatible` 且配置齐全时
  优先云端通道，失败回落 Ollama；测试随机降级路径不变。新增 env：
  `EMBEDDING_PROVIDER` / `EMBEDDING_OPENAI_BASE_URL` / `EMBEDDING_OPENAI_API_KEY` /
  `EMBEDDING_OPENAI_MODEL` / `EMBEDDING_OPENAI_DIMENSION`
- **检索元数据过滤**（`metadata_filter={field: value}` 等值谓词）：
  - 存储层：`_matches_metadata_filter` 共享谓词 + lite/cluster 超额召回（top_k×4，下限 20）
    后过滤截断，无 Milvus schema 变更
  - 通道层：VectorChannel 透传、KeywordChannel 候选过滤
  - API 层：`retriever.retrieve(...)`、`/api/rag/debug/search`、`/api/rag/eval`、
    `search_knowledge_base` 工具 schema（`metadata_filter` 可选 object 参数）
- **测试**：`test_embedding_channels.py` 13 例（云端解析/维度校验/路由优先级/失败回落/
  过滤谓词/lite 后过滤/通道透传）

### 文档解析扩展批（2026-08-30 第十批）：PPTX / HTML / 图片 OCR + 表格感知分块

#### Added
- **三个新解析器**（全部零第三方依赖，不翻搅 pip-compile 哈希锁文件）：
  - `pptx_parser.py` — stdlib zipfile+ElementTree 读 OOXML：标题占位符→HEADING、
    正文段→PARAGRAPH、`<a:tbl>`→TABLE（TSV）、演讲者备注（metadata source=speaker_notes）
  - `html_parser.py` — stdlib html.parser：h1-h6 层级、p/li、table(tr/td|th TSV)、
    script/style/head 跳过；UTF-8→GB18030 降级解码
  - `image_parser.py` — 独立图片（png/jpg/jpeg）复用既有 Tesseract OCR 通道
    （MultimodalEvidenceExtractor._ocr），`RAG_MULTIMODAL_OCR_ENABLED=false` 时
    明确报错不静默入库空文档
- **表格感知分块**：TextChunker 对 TABLE 块按行打包（不再走句子边界启发式切断行），
  续块自动带表头前缀「（表格续，表头同上）」，metadata 标注 table_row_aligned；
  单行超限才硬切兜底
- **三端格式白名单同步**：Java ALLOWED_EXTENSIONS/MIME + Python
  validators.SUPPORTED_FILE_TYPES + 前端两处 upload accept 属性
  （新增 .pptx/.html/.htm/.png/.jpg/.jpeg）
- **测试**：`test_parser_extensions.py` 10 例（最小 OOXML zip 仿真/HTML 块语义/
  OCR 门控/表格行对齐断言）

### 性能债核实批（2026-08-30 第九批）：OPTIMIZATION_PLAN Python P1 四项对账

#### Fixed
- **docs/OPTIMIZATION_PLAN.md 与代码实现对账**（此前批次修复后文档未同步）：
  - 2.5 BM25 语料/倒排索引缓存 ✅ — `KeywordChannel._corpus_cache` 按 (store id, KB)
    缓存预解析语料，co-store mtime/size 变化自动失效
  - 2.7 流式多 Agent 绕过证据审查 ✅ — 流式首个文本 chunk 前对 retrieval sources
    执行与非流式同一确定性门控 `_validate_sources`（空 sources 放行为委托层
    拒答门控的文档化设计）
  - 2.8 文件重复读取 ✅ — co-store 按租户 + mtime+size 缓存，热路径零重读
  - 2.9 事件循环阻塞 ✅ — embedding 模块级线程池复用 + Ollama 探测 TTL 缓存线程池化
  - P2 LLM 响应缓存精确命中已覆盖流式（chat_stream 缓存路径），模糊命中留待后续
- 全量回归佐证：Python 1324 passed / Java 581 passed（含上述各专项测试）

### 原生 function calling 批（2026-08-30 第八批）：provider 原生 tool-calls + max_steps 配置化

#### Added
- **LLM 接口层**：`LLMResponse`/`GatewayResult` 新增 `tool_calls` 字段；
  `ModelGateway._call_openai_compatible` 提取响应中的 tool_calls，
  `_call_ollama` 支持 `tools`/`tool_choice` 透传并把 Ollama dict arguments
  归一化为 OpenAI JSON 字符串形态（GatewayLLM 门面全链路转发）
- **ReAct 原生分支**：新增 `ReactAgent._chat_step`——flag 开启时优先以原生
  tool-calls 调用（tools 由 `ToolSpec.input_schema` 转 OpenAI function 形态），
  命中则把调用序列化回写 assistant content 保持消息历史纯文本延续；
  provider 报错/不支持自动降级文本 Thought/Action 协议；flag 关闭零行为变化。
  run 与 _run_stream_react 两个循环均已接入
- **治理**：V81 迁移注册 `agent.native_tool_calls.enabled` flag（默认 FALSE）；
  env `AGENT_NATIVE_TOOL_CALLS_ENABLED` 降级回退；AVAILABILITY_FLAGS 映射
- **max_steps 配置化**：`RAG_AGENT_MAX_STEPS` 默认 5 → **12**；ReactAgent 构造器
  未传时回落配置；请求字段 `max_tool_steps` 上限 10 → 24
- **测试**：`test_native_tool_calls.py` 11 例（gateway 提取/Ollama 归一化/原生命中/
  异常降级/flag 关闭/schema 转换/max_steps 配置）

### 长期记忆接线批（2026-08-30 第七批）：memory_consolidator 激活 + 上下文注入 + 会话删除回调

#### Added
- **长期记忆闭环**（此前三个休眠组件 MemoryConsolidator / MemoryManager / Java MemoryService 首次连通）：
  - 触发 1（对话中）：chat 四端点（/api/chat、/api/chat/stream、/api/agent/v1/chat、/api/agent/v1/chat/stream）
    轮次收尾计数，每 N 轮（`MEMORY_CONSOLIDATE_EVERY_TURNS`，默认 6）后台 LLM 抽取记忆
  - 触发 2（会话删除）：Java `ConversationServiceImpl.delete` 删除前快照消息（≤100 条），
    `@Async` 回调 Python `POST /api/internal/memory/consolidate` 做最终抽取
  - 存储：抽取结果批量落 Java `memory_entry`（新增 `InternalMemoryController`：
    `POST /internal/memory/entries` 按 user+content 去重 + `GET /internal/memory/relevant`
    重要性+词命中排序，均 X-Internal-Token 常时比较保护）
  - 注入：ReactAgent 三路径（run / _run_stream_react / _handle_chitchat）组装上下文前经
    `LongTermMemoryService.build_memory_context` 拉取相关记忆，以「非指令」标注块拼入 system prompt
- **治理**：V80 迁移注册 `memory.long_term.enabled` flag（默认 FALSE）；
  env `MEMORY_LONG_TERM_ENABLED`/`MEMORY_CONSOLIDATE_EVERY_TURNS`/`MEMORY_CONTEXT_MAX_ENTRIES`/
  `MEMORY_CONTEXT_MAX_TOKENS`/`MEMORY_INTERNAL_TIMEOUT_SECONDS` 作为降级回退；
  flag 加入 AVAILABILITY_FLAGS 降级映射
- **测试**：Python `test_long_term_memory.py` 16 例（门控零开销/类别映射/截断钳制/归一化/
  静默降级/每 N 轮触发/抽取落库串联）+ Java `InternalMemoryControllerTest` 9 例

#### Fixed
- **修复 main 上 Java 测试无法编译的既有问题**（CI 计费停摆期间未被发现）：
  sa-token 1.46 的 `SaTokenContext` 接口变更（新增 setContext/clearContext/getModelBox 抽象方法、
  getRequest 等转 default）导致 12 个测试文件内嵌 `MockSaTokenContext` 编译失败——统一升级为
  ModelBox 装配式实现并补齐缺失 import

### 评估中枢收尾批（2026-08-30 第六批）：V79 写入接线 + 切片汇总 + judge 缓存 + nightly 接入

#### Added
- **V79 写入接线**：`EvalHarnessInternalController`（/internal/eval-harness/record，
  InternalTokenGuard 常时比较 + X-Tenant-Id 显式租户上下文）+ `EvalHarnessRun` 实体/Mapper；
  python 评估完成后自动回调 Java 落库（失败仅告警），「回答效果」A/B 列表可跨重启持久
- **切片汇总**：score 按 tags 任意维度拆检索指标（intent_l1/difficulty/trap_type…，
  单一取值维度自动跳过），落在 `meta.by_tag`
- **judge 结果缓存**：按 (model, query, answer, ground_truth) 哈希缓存评分，
  同答案跨 run 不重复评审（省 token 成本）
- **eval-nightly 接入**：新增 `eval-harness` job（CI 起服务栈 → 导入评测语料 →
  跑评估 → 上传报告/幻灯片 artifact；真实 LLM 评审在 staging 配置下启用）

#### Fixed
- Java 内部控制器编译（lambda final 变量、IdType import）；SaTokenConfig
  登录检查与租户拦截器分别放行 `/internal/eval-harness/**`（内部通道自行 runAs）
- eval-harness 数据集目录解析修正（app/api 两级 parent → python-ai 三级）

### 评估中枢 eval_harness（ragenteval × HFusionHub 结合，2026-08-30 第五批）

#### Added
- **评估内核**（python-ai `app/core/eval_harness/`，record/score 分离架构，方法论源自 ragenteval 工具包）：
  - runner 驱动生产链路：`/api/rag/eval`（检索 bypass）+ `/api/chat/stream`（SSE 对话，TTFT=首个 content delta），并发执行、逐条落 JSONL 可重放评分
  - 指标：检索 Hit@K/Recall/MRR（仅 requires_rag 样本）+ 行为红线（该答未答/回退话术/过度检索）+ TTFT P50/均值 + LLM-as-judge 三指标（忠实度/答案正确性/相关性，走 ModelGateway 单轨 + judge_gate + N 次均值）
  - report（markdown）/ diff（阈值化 A/B 回归门禁）/ slides（自包含 16:9 HTML 幻灯片，XSS 转义）
  - API：`/api/eval-harness/run|score|runs|report|slides|diff|datasets`（internal-token + tenant 守卫、数据集白名单防穿越）
- **评测语料入库**：ragenteval 120 篇中文业务 markdown → `resources/eval-corpus/`；
  `EvalCorpusImportService` 幂等导入（KB「评测语料库」，文档标题=业务码，
  复用 demo-import 真实解析模式），`POST /demo/import-corpus` 返回业务码→文档ID映射；
  150 样本评测集适配入库 `scripts/eval_sets/hfusionhub_v1.jsonl`
- **回答效果页升级**：新增「生成质量评估」（选数据集/KB 运行，指标卡 + 失败明细 +
  报告/幻灯片下载）与「A/B 回归对比」（双 run 阈值化对比 + 回归标记）两个区块
- **V79**：`eval_harness_runs` 表（聚合指标摘要 + tenant_id）
- 单测 10 项（指标/runner 持久化/score 重放/diff 门禁/API 流）


## [1.0.0] — 2026-08-30


### Low 批清偿 + 覆盖率门禁批次（2026-08-30 第四批，源自 docs/REPAIR_ROADMAP.md Low 批）

#### Fixed（Python AI）
- **A1 DeepSeek 流式解析**：空 choices / 非字典载荷按心跳行跳过（此前仅捕获 JSONDecodeError，choices 为空 IndexError 直接崩流）
- **A2 网关流式缓存键错位**：put 侧改用 resolved_model 与 get 对齐（fallback 命中时两键错位导致缓存永不命中）
- **A3 中文 token 估算校准**：CJK ≈ 1 字/token、ASCII ≈ 4 字符/token（旧 chars//4 低估中文成本约 4 倍）；回归测试 1 项
- **A4 回调通知**：复用共享 httpx 池（get_shared_client，此前每次新建客户端）+ 指数退避重试 3 次（4xx 确定性失败不重试）
- **A5 get_chunks 分页语义**：index = 分页 offset + 页内序号（此前硬编码 0）
- **A6 Milvus 对账截断**：query_iterator 游标迭代（无 16384 窗口限制），不可用时回退原单次 query
- **A7 EMBEDDING_MODEL 默认 unknown → 空**，回调元数据回退 OLLAMA_EMBEDDING_MODEL
- **A8 feature_flag 后台刷新**：加锁串行化线程创建（check-then-start 竞态）
- **A9**：移除 rag/__init__ 重复的 get_workflow_engine_instance 死导出（无引用）。
  评估报告所称 execute_tool 死分支经实测**不成立**（审批流 tool dict 携带 _registry 在用），已保留并补注释
- **S6 回调收敛**：回调重试耗尽后不再 raise（索引已落库且旧版本已删，标 FAILED 会造成对账漂移并触发重复重析）；
  改按完成收尾 + ERROR 告警，document 状态由 Java stale 恢复调度幂等收敛

#### Fixed（Java）
- **AiClient onStatus 三处**：Python 原始错误 body 只进日志（截断 500 字），客户端异常改友好文案（信息泄露）
- **internalApiToken 启动期校验**：@PostConstruct 空值大声 error（生产 compose :?required 已强制，dev 不阻断）
- **V78 迁移**：回填 agent_alert_rule/event 无 user 系统行的 NULL tenant_id → 默认租户 1（V32 遗留，生产实测 4+11 行）
- 依赖小版本：sa-token 1.37→1.46、hutool 5.8.25→5.8.47、mapstruct 1.5.5→1.6.3（全量回归通过）

#### Fixed（前端）
- **SUPERSEDED 终态守卫**：useDocumentProcessor 轮询补 SUPERSEDED（被取代文档此前会永久轮询）
- **request.ts 空响应体**：204/空 body 直接放行（此前 res.code 访问报错）
- **类型对齐**：uploadDocument/createKnowledgeBase 返回 R<DocumentInfoDTO>/<KnowledgeBaseInfoDTO>（原 number）；cost.ts 四个接口改 ApiResponse<T> 泛型
- **SSRF 权衡注释**：custom_provider 私网段放行是为自托管 Ollama 的有意设计，补注释防止误加固

#### Added（质量门禁）
- **JaCoCo check**：BUNDLE 行覆盖 ≥45% 棘轮起点（当前基线 ~47%，防恶化不追历史）
- **CI pytest 加 --cov=app --cov-report=term-missing**（报告可见，阈值观察后另设）
- badge 双份经核实已在前端主题统一重构中解决（CLEANUP_BACKLOG C 项关闭）

### 头像上传（2026-08-30）

#### Added
- **头像上传端到端**：`POST /user/avatar`（multipart，≤2MB，JPG/PNG/WEBP/GIF 扩展名 + 文件魔数双重校验防伪装文件）落盘 `uploads/avatars/{userId}.{ext}`（uploads-data 卷持久化，可 `app.avatar.dir` 覆盖）；`GET /user/avatar/{userId}` 读取头像（SaToken 放行——`<img>` 无法携带 satoken 头，仅返回图片字节；Cache-Control 1h）。DB `user.avatar` 存标准相对路径标记，`UserInfoDTO.avatar` 统一转换为 `/api/user/avatar/{userId}`
- **个人中心头像交互**：横幅头像可点击上传（hover 相机蒙层、前端预校验类型/大小、成功后刷新 store 并以时间戳参数破缓存）；有头像显示图片、无头像回退首字母渐变
- **侧边栏头像**：MainLayout 用户区同步显示已上传头像（object-cover 裁剪），未设置保持首字母
- **回归测试**：updateAvatar 落盘/相对路径标记、换扩展名替换旧文件、超大拒绝、伪装扩展名拒绝、不存在头像返回空——5 项

#### Fixed（头像上传上线首日修复）
- **SaToken 放行误伤 POST**：`/user/avatar/*` 曾整体加入免登录清单（SaToken 路径匹配不分 HTTP 方法），匿名上传直接 500——移除放行，上传/读取均需登录；头像改为前端 fetch+blob 携带 satoken 头加载（新增 `useAvatarImage` composable，axios 拦截器豁免 blob 响应）
- **入口不可发现**：上传入口原为 hover 才出现的蒙层——改为头像右上角常驻相机徽章 + 用户名旁说明文字
- **405/415 语义**：GlobalExceptionHandler 补 HttpRequestMethodNotSupportedException（405）与 HttpMediaTypeNotSupportedException（415），不再落入 500 兜底误导排障

### 评估修复第二批 + 依赖升级批次（2026-08-30）：S4/S5 竞态、M4–M13 全量、Spring Boot 3.5.16、FastAPI 0.141（源自 docs/REPAIR_ROADMAP.md）

#### Fixed（Java 竞态/事务）
- **S4 双重入队**：V77 迁移 `agent_run (task_id, attempt_number)` 唯一索引（含存量重复行清理 DELETE）；`enqueueRun/retryTask/requeueTask` 改 `selectByIdForUpdate` 行锁 + `MAX(attempt_number)+1` 计算 + DuplicateKeyException 转友好冲突错误
- **S5 向量化重处理并发**：supersede 旧 job + 退预占 + 插新 job 收进 `TransactionTemplate` 文档级行锁短事务；attempt 改 `MAX(attempt)+1`（软删除表无法部分唯一索引，代码级锁守卫）
- **M4 孤儿重派竞态**：`requeueOrphan` SQL 加 `AND status='running'` 守卫；0 行受影响时跳过退预占/删步骤等副作用（防回调已写终态的 run 被误重置）
- **M5 afterCommit 文件提交**：失败不再抛异常（Spring 吞掉且响应不确定）；标记文档 FAILED 并保留临时文件供对账
- **M7 孤立消息**：非流式 sendMessage 配额预占移到用户消息落库前，超配额不再产生"有问无答"
- **M8 SSE 轮询池**：固定 2 线程 → 可配置 `agent.status-event.sse-poll-threads`（默认 max(4, CPU/2)）
- **Low**：TaskEventSseManager null userId NPE 防护

#### Fixed（Python AI）
- **M10 检索故障伪装**：`_retrieve_context` 失败返回 None 与"无结果"区分；run() 返回 `retrieval_error` 状态、run_stream() 发 `run_error` 帧（Java 映射 failed），不再伪装"证据不足"
- **M11 工作流错误伪装**：workflow_runtime 超时/异常改发结构化 `run_error` SSE 帧（Java 已有消费逻辑），不再把错误文案当内容块下发
- **M12 run/run_stream 分叉**：run_stream 查询分解补 `needs_decomposition` 判据，与 run() 对齐
- **M13 资源泄漏**：`classify_sync` 共享线程池（4 workers）；`_task_status_store` LRU 上限 10000；`MemoryEmbedder` 嵌入缓存 LRU 2048；评估缓存上限 2000（按时间戳淘汰）；`MemoryStorage._sessions` 上限 1000（淘汰非活跃会话）

#### Fixed（前端）
- **M9 SSE 401 割裂**：`request.ts` 抽取 `handleUnauthorized401` 共享函数；`utils/sse.ts` 与 `chat/Detail.vue` 两处 SSE 401 接入统一登出

#### Changed（依赖升级）
- **Spring Boot 3.2.5 → 3.5.16**（3.x 最新稳定线）：全量 565 测试回归通过；surefire argLine 改 `@{argLine}` 前缀以兼容 JaCoCo agent
- **FastAPI 0.109.0 → 0.141.1、pydantic 2.5.3 → 2.13.5、httpx 0.27 → 0.28.1、starlette 0.35.1 → 0.52.1**：`requirements.in` 提升最低版本约束并 pin `starlette<1.0`，pip-compile 重新生成 hash 锁定文件；全量 1281 测试回归通过
- **生产安全收口**（TODO.md P0）：prod compose 默认 `SPRINGDOC_API_DOCS_ENABLED/SWAGGER_UI_ENABLED=false`；新增 `APP_CORS_ALLOWED_ORIGINS` 白名单透传；新增 `scripts/backup-mysql.sh`（一致性 dump + 校验 + 按天清理）

#### Added
- **覆盖率基线**：Java JaCoCo 0.8.12（`mvn test` 后报告落 `target/site/jacoco/`）；Python `pytest-cov>=6.0` 入 dev 依赖（`pytest --cov=app` 按需开启，不影响默认 CI 速度）
- **回归测试**：S4 attempt 计算 + 唯一索引冲突 2 项、S5 行锁+supersede 1 项、M11 run_error 帧 2 项、M13 共享线程池 1 项
- **static-checks 检查 3**：`--test-counts` 静态统计三端测试数与 README 徽章 / AGENTS.md 行比对，测试计数漂移直接 CI 失败

#### Docs
- 测试计数全面对齐（实测口径）：Java 567 · Python 1247 · 前端 49 单测 + 74 E2E（README 徽章、CLAUDE.md、AGENTS.md、ROADMAP、CLEANUP_BACKLOG、OPTIMIZATION_PLAN、python-ai.md）
- ENVIRONMENT.md 补录 4 个新配置项；TODO.md P0 项 3/4/5 更新为已收口状态
- REPAIR_ROADMAP.md 修复进度表：S4/S5/M4–M13/Low(部分) 全部标注 ✅（第二批）

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
