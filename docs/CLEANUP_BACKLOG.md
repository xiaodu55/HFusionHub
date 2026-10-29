# 冗余功能与死代码清理清单

> 2026-08-29 前端主题统一改造时盘点生成。本次**只登记不删除**，逐项评估后处理。
> 删除前先确认测试基线（Java 718 · Python 1936 · 前端 117）仍全绿。

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
- [ ] **`JAVA_OPTS` 是死开关**（第九十六批登记）—— 三处声明：`docker/docker-compose.yml:269`、
  `deploy/docker-compose.prod.yml:199`、`deploy/helm/hfusionhub/templates/java.yaml:68`（值来自
  `values.yaml:68` 的 `javaBackend.javaOpts`）。消费方 **0 处**：`deploy/Dockerfile.java:26` 的
  `ENTRYPOINT ["java", "-jar", "app.jar"]` 是 exec 形式，没有 shell 去展开 `$JAVA_OPTS`，
  所以那行 `-Xmx512m -Xms256m` 从未进过 JVM。两条出路是**行为决策**而非清理：删掉这三处声明
  （堆上限交回 `deploy.resources.limits` + `-XX:MaxRAMPercentage`），或把入口改成
  `["sh","-c","java $JAVA_OPTS -jar app.jar"]`（那会真的把堆钉到 512m，而 helm values 里
  的 requests/limits 是按别的数配的）。第九十六批只登记未动，同时纠正了
  `docs/OPTIMIZATION_PLAN.md:220` 把 `JAVA_OPTS -Xmx512m` 当成生效堆上限的那句。

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

## F. 已取证、未修的缺陷（只登记，处置时逐项划掉）

- [x] **流式会话的终止事件有两个出口**（第一百零一批取证并修）—— CI `java` job 在**零 Java 改动**下
  从 success 翻成 failure：run 38134153636（第九十九批 `3dba7e3d`）报
  `ConversationStreamingPersistenceTest.asyncContentResetClearsAccumulatedContentAndForwardsResetEvent:334
  expected: <4> but was: <5>`（`Tests run: 717, Failures: 1`），而第九十六批 run 38099630611、
  第九十七批 run 38115360383 的 `java` 都是 success。本地把该单例连跑 8 次 **0/8 复现**
  ⇒ 竞态而非稳定错误。
  机制：`StreamSession` 的 `[DONE]` + `complete()` 有 5 个出口，Python 正常收尾时哨兵
  （`handleDone`）与 Reactor `onComplete` 兜底**必然都走到**，"线上不重复"只依赖
  "`complete()` 之后再 `send()` 会抛异常、异常被 `catch (Exception ignored)` 吞掉"这一实现细节——
  任何包装 emitter（装饰器、按次计数的测试替身）都不再抛，重复当场显形，断言读数取决于线程交错。
  **处置（第一百零一批）**：`ConversationServiceImpl:1028` `terminalEmitted` + `:1151` `emitTerminal()`
  收成唯一终止出口，`:1165/:1189/:1207/:1223/:1258` 五处全部改调它；红判据是新增的同步流用例
  `ConversationStreamingPersistenceTest:353`（改前 `[data:{content=…}, data:[DONE], data:[DONE]]`
  ⇒ expected 2 but was 3）。既有 `== 4` 断言**未放宽**，闸门落地后它成为确定性判据。
  全量 `mvn --batch-mode test`：718 run / 0 fail / 1 skip，jacoco `check` 通过。
  **待补证**：CI `java` job 上 718/0 fail 才是竞态消失的运行时证据（本地 8/8 只证明机制）。
  同形出口已扫：`OpenApiServiceImpl:194`、`AgentTaskQueueServiceImpl:361`、
  `ConversationServiceImpl:545`（幂等重放）各自只有一个终止出口，不在缺陷面内。

- [x] **插件子进程的 fd 上限不看继承面**（第九十七批取证，第九十九批按 A 方案修）—— CI `python` job 里
  `tests/test_plugin_sandbox_runner.py` 那 5 条红是同一条链：报错都是
  `[Errno 24] Too many open files: '<插件目录>/__init__.py'`，`error_code` 全是
  `plugin_execution_error` ⇒ 异常发生在**子进程**的 `_subprocess_worker` Step 3 import，
  不是父进程调用处。改前的生产码在 fork **之后**把 `RLIMIT_NOFILE` 钉成
  `(config.max_open_files, 同值)`（默认 64，`:45`；改前位于 `:99`，本批该文件 +38 行，现由
  `:132-141` 的分支调 `_apply_fd_budget`），而子进程此刻已经继承了父进程当时打开的全部 fd，
  这些同样计入那 64 的额度。

  容器内实测（镜像 `hfusionhub/python88:rc`，只测量、未改生产码）：

  | 量 | 结果 |
  |---|---|
  | 裸 `python` 父进程 fd 基线 | 4（stdio 3 + `/proc/self/fd`） |
  | 一次成功调用里子进程看到的 fd | 9（继承 4 + multiprocessing 的 pipe 等 5），`getrlimit(RLIMIT_NOFILE)=(64, 64)` |
  | 三条分支各跑 15/8/8 次的父进程 fd | **before=after=after_gc=4，净增 0** |
  | 父进程灌到 64 / 70 / 80 / 100 / 150 / 200 | 六档**全部** `Errno 24`，且都栽在子进程第一个 import 上 |
  | 父进程 150 时改 `max_open_files` = 64 / 128 / 256 | 64 红、128 红、**256 绿** |

  两条结论：① **"父进程漏 fd"这个假设被否掉**——超时分支 `:568`、异常退出分支 `:577` 确实
  绕过了 `finally: parent_conn.close()`（`:611`），但 CPython 在栈帧展开时按引用计数关掉连接，
  三条分支实测零增长，所以这条不能作为缺陷登记（此前的怀疑撤回）；
  ② 真正的限制变量是**上限 vs 继承数**，不是父进程的绝对 fd 数——所以 CI 那 5 条红等价于
  "pytest 父进程在那一刻已经握着 ≥64 个 fd"（CI 里子进程连插件 `__init__.py` 都没能打开）。

  同形状的 `sandbox.py:229`（`_apply_posix`）**在生产路径不可达**：`apply_resource_limits`
  的"调用方"只有 `:262` 那段 docstring 示例，全仓无真实调用点，故本条不涵盖它。

  本地永远看不见这条：Windows 没有 `resource` 模块，`:116` 的 `ImportError` 分支把 CPU/内存/fd
  三项限制全部跳过并只打一条 warning ⇒ 同一份代码本机全绿、Linux 恒红。

  三条出路（第九十九批按 **A** 修，B/C 未采纳）：A（推荐）设限前先读 `os.listdir('/proc/self/fd')` 或
  `getrlimit` 的当前值，把上限钉成"继承数 + 预算"，且只抬 soft、hard 留给运行期调；
  B 让子进程不继承（`spawn`/`close_pipe_fds`/exec 起干净进程），改动面最大但把两类 fd 账本彻底分开；
  C 只在测试里抬 `max_open_files`——这只让 CI 变绿，缺陷留在生产码，属本清单反对的形态。

  **处置（第九十九批，2026-10-11）**：已按 A 落地。新增 `sandbox_runner.py:72` `_FD_SCAN_CAP`、
  `:75` `_count_open_fds()`、`:91` `_apply_fd_budget()`，`:132-141` 的 fd 分支改为调用它——
  soft = 设限时已打开的 fd 数 + `max_open_files`，只按继承 hard 夹（不按继承 soft 夹，否则继承 soft
  比预算小又会退回 0 额度），hard 不再被钉死。判据 `tests/test_sandbox_fd_budget.py`（11 例）：
  父进程灌 200 fd 后子进程仍能新开满预算、hard 保持继承值可被子进程自己抬回、预算不越过继承 hard、
  `/proc` 计数与 fstat 扫描恒定差 1（`os.listdir` 数到自己那个目录 fd ⇒ 声明预算实为"预算 + 1 富余"）、
  无 `resource` 模块时只 warning 不抛。容器内改前 6 例红、改后全绿；CI 那 5 条红的形态用
  session-start 灌 fd 的插件在 HEAD 代码上原样复现（`5 failed, 24 passed`），换修复后代码转绿。
  `sandbox.py:229` 那个同形状点位**本批仍未动**（生产不可达，见上），如需一并收口另立批次。

- [x] **容器轨的 6 条 ERROR：无镜像的 job 在跑只有 owner job 才跑得动的文件**（第九十七批登记，第一百批处置）——
  `tests/test_plugin_container.py` 的 fixture 在没有本地标签镜像时
  `pytest.fail("Integration tests require a tagged local Python base image …")`。三个选项的取舍：
  改成 skip（CI 绿，但"容器轨没跑"这件事再次变成无信号——正是第九十七批在评测门上抓到的形态）、
  CI 步骤预拉/预构建镜像（绿且真跑，代价是 job 时间与网络依赖）、保留 `pytest.fail`（红着提醒）。

  处置（第一百批，两个面都动，未采纳 skip）：

  - **归属**：`.github/workflows/ci.yml:177` 的 `python` job 加 `--ignore=tests/test_plugin_container.py`，
    owner 唯一定为 `python-container`（`:200` 预拉 `python:3.12-slim`、`:215` 跑该文件并接 skip 门禁）。
    判据 `python-ai/tests/test_ci_workflow_gates.py:292` `TestContainerLaneOwnership`（4 例）钉四件事：
    `python` job 的每个 pytest 步骤都必须带该 `--ignore`；排除只针对这一个文件（`pytest -q tests` 面、
    `--cov=app`、`--cov-fail-under` 原样，`--ignore` 恰好出现一次）；`python-container` 里 pytest 恰好
    一步且跑的是那个文件、仍接 `check_container_skips.sh`；**预拉的标签必须出现在守卫自己的候选表里**
    （候选表由 `:276 guard_candidate_tags()` 从守卫源码解析，绝不抄第三遍）。
  - **可诊断性**：`_resolve_local_python_image` 改为先 `client.images.list()`，把"daemon 问不到"
    （报「Docker 守护进程不可达」并带上异常类型与 DOCKER_HOST 提示）与"daemon 可达但无带标签镜像"
    （报候选表）分成两条文本，fail-not-skip 语义与候选优先级不变。判据 `:359`
    `TestContainerImageGuardDiagnostics`（5 例，注入 fake client）：daemon 故障不得再说成缺镜像、
    缺镜像不得再说成 daemon、多个在位时按候选顺序取 `python:3.12-slim`、非候选的 `python:*` 仍可兜底、
    无标签镜像不得被静默拿去 `FROM`。

  成本实测（改前声明判据"文件级排除造成的 TOTAL 损失 < 0.5 个百分点才用 `--ignore`"）：
  本地全量含该文件 `2068 passed / 17 skipped`，`TOTAL 19163 stmts / 4281 miss`；
  加 `--ignore` 后 `2032 passed / 11 skipped`，`TOTAL 19163 / 4350` ⇒ 覆盖 77.66% → 77.30%，
  **损失 0.36 个百分点（69 条语句，全部落在 `app/core/plugin/container_runner.py`：79% → 33%）**，
  判据满足，故保留文件级排除而非"只摘 `TestRunnerIntegration`"。棘轮 74 的余量随之从 ~3.7pp 降到 ~3.3pp。

  **就地纠正本条登记时的归属**：原文写的是「`python-container` job 的 6 条 ERROR」。第九十七批的
  CI run 38115360383 里 `python-container` 是 **success**，6 条 ERROR 出在 **`python` job**
  （`5 failed, 2047 passed, 7 skipped, 6 errors`，逐条都是 `TestRunnerIntegration::*`，
  报错文本为那句 `Integration tests require a tagged local Python base image`，行号
  `tests/test_plugin_container.py:761` = 守卫的 `pytest.fail`）。

- [x] **python 侧的钟面不在 UTC 口径内**（第九十六批登记于 `docs/PRODUCTION_OPS.md:13.3`，第一百零二批处置）——
  第九十六批把 java 的三张钟面（JVM `-Duser.timezone` / MySQL `--default-time-zone` / JDBC `serverTimezone`）
  钉成 UTC 并立检查 13，同时留下一句：python 侧不收口。留下的事实是两条——
  `python-ai/app/core/tools/time_tool.py:21` 用无参 `datetime.now()`（取**进程**时区，容器里等于宿主/节点时区），
  而当时没有任何一档拓扑给 python 工作负载声明 `TZ`。也就是说同一个瞬间，java 侧按 UTC 落库、
  python 侧按 +08 墙钟答给模型，两侧都"自洽"且互相矛盾。

  处置（第一百零二批，两面都做，不做单面赌注）：

  - **代码面**：`time_tool.py` 改 `datetime.now(UTC)`，输出补 `caliber: "UTC"` 与 `iso8601`（带 `+00:00`），
    把口径写进结果而不是让调用方猜。判据 `python-ai/tests/test_tool_clock_caliber.py`（3 例）：
    口径声明与碎片字段自洽、`TZ=Asia/Shanghai` 下输出不翻（`tzset` 缺失时 skipif，且翻转前先自证
    " naive 读数确实变了"——否则免疫断言是空过）、以及把 `app/**/*.py` 的裸无参墙钟读法钉成用例。
    最后一条的正则跑在 `tokenize` 涂白后的"代码表面"上，与门禁的 `ast` 是两套 oracle（注释/文档串不得算违规）。
  - **部署面**：dev compose 的 `python-ai`/`python-ai-worker`/`plugin-runner`、prod compose 的
    `python-ai`/`plugin-runner` 各加 `TZ: "UTC"`；helm 两个模板 `- name: TZ / value: {{ .Values.<root>.tz }}`
    与 `values.yaml` 的 `pythonAi.tz`/`pluginRunner.tz` 成对，双向都核（键存在但没人读＝死配置，第八十三批的反形态）。
  - **门禁**：检查 15 `--python-clock-caliber`（并入默认全跑）。工作负载按**镜像 marker**枚举而非服务名——
    改名会让门禁"没认出任何 python 工作负载"，那必须是红而不是绿；拓扑文件缺失同样报红。

  **待补证**：CI `python` job 里那条 `tzset` 免疫用例在 Linux runner 上真跑（本地 Windows 只能 skip），
  以及 `helm` job 渲染出的 `TZ` 值。第一百零二批的本地替代证据是容器内跑通同一判据 + `helm template` 实测。

- [x] **两条依赖审计门是红的**（第一百零二批取证，第一百零三批处置）—— run 38135767897 的 `python-container` 与
  `java` 转绿后，main 上仅剩两条红：pip-audit `Found 29 known vulnerabilities in 5 packages`
  （pypdf / python-dotenv / requests / starlette / urllib3）与 `npm audit --audit-level=high`
  `15 vulnerabilities (7 moderate, 8 high)`（逐条都标着 "fix available via npm audit fix"）。
  处置方向只能是升级或写明豁免策略，**不得靠放宽 `--audit-level`、加 `--ignore-vuln` 或调阈值把门改绿**。
  **就地纠正**：这句里的"main 上仅剩两条红"当时只核了 `ci.yml` 一条工作流，范围写宽了——
  `plugin-security.yml`（push 碰到 `python-ai/requirements*.in` 即触发）在 run 38134153670 里
  红了 3 个 job；锁修干净之后 run 38145150133 红的还是那 3 个，说明三条都与锁无关，
  见下面"三个从未过的 job"那条。核对方式：
  `gh api repos/xiaodu55/HFusionHub1/actions/runs/<run>/jobs` 看每个 job 的 `conclusion`，
  而不是只看 `ci.yml` 那条 run。
  处置＝**升级**，且门一字未动（本批 diff 里没有任何 workflow 文件）：主锁 4 条直接依赖 +
  1 条传递依赖（`urllib3` 只由 `requests` 带进来，**不**写成直接依赖，否则 `.in` 与锁尾的
  `# via` 不同源）钉到 pip-audit 给出的最早修复版本；`requirements.in` 的下限同步改成**漏洞下限**
  ——只钉锁不改 `.in`，下一次 `pip-compile` 会照旧下限重新解析回带 PYSEC 的版本，同一批 CVE 静默复活。
  npm 侧用不带 `--force` 的 `npm audit fix`（`changed 39 packages`）后 `found 0 vulnerabilities`，
  `package.json` 里 5 个带公告的直接依赖把范围下界抬到修复版本，与 python 侧同一条纪律。
  **就地纠正**（判据来自 run 38145150133 的 job 日志，不是读 workflow）：本批**没有**关掉
  `plugin-security.yml:72-108` 的 `vulnerability-scan`。该 job 有两处叠着的缺陷，前一处一直把
  后一处挡在后面——① `pip-audit -r requirements.txt --desc --output … --format json` 自己在
  有漏洞时退出 1（run 38134153670 死在这里）；② 锁修好后这一步打印
  `No known vulnerabilities found` 并退出 0，但下一步的解析脚本按"顶层是 list"读 pip-audit 的
  JSON，而它现在写 `{"dependencies": […]}`，于是
  `AttributeError: 'str' object has no attribute 'get'`（runner 日志第 284 行）。
  ⇒ 这个 job 从诞生起就没有绿过的能力。见下面"三个从未过的 job"那条。
  **runner 级结论（run 38145150155 ＝ `06ea5607`）**：`ci.yml` 的 11 个 job 全 `success`——
  `python-lint` 打印 `No known vulnerabilities found`，`frontend` 打印 `found 0 vulnerabilities`
  且 `Test Files 16 passed (16)`，`python` 打印 `2056 passed, 7 skipped`、
  `Total coverage: 77.09%`（棘轮 74），收集总数与本机 2051+12 同为 2063。
  这也是"新 dev 锁在 Linux 上可安装"的 runner 证据（`--require-hashes` 自动生效下 `pip install
  -r requirements-dev.txt` 成功）。
- [ ] **dev 锁没有任何审计门，且里面有一条 PYSEC**（第一百零三批取证，未处置）——
  `ci.yml:149-152` 只审 `requirements.txt`（`pip-audit -r requirements.txt --disable-pip`），
  而 `python` job 实际装的是 `requirements-dev.txt`（`ci.yml:161-177`）。以 CI 同款命令实测这把
  dev 锁：`Found 2 known vulnerabilities in 1 package` ＝ `pytest 8.3.5 → PYSEC-2026-1845`
  （修复版本 9.0.3；表里两行是同一公告的别名，按 OSV 去重后是 1 条）。**没有**在本批顺手把
  dev 锁纳入门禁——那会立刻造出一条计划外的红。处置需要 pytest 主版本升级 ＋
  `pytest-asyncio 0.25.3`/`pytest-cov` 的兼容链 ＋ 2087 例重跑。
- [x] **`plugin-security.yml` 三个 job 从未过过：旗标/解析形态与已装版本对不上**（第一百零三批
  取证，第一百零四批处置）—— run 38134153670（第九十九批 `3dba7e3d` 的 push；路径含 `requirements*.in`
  才触发本流）里 3 个 job 红，第一百零三批把锁修干净之后 run 38145150133 **仍是同样这 3 个红**，
  而 `signature-verify`/`hash-verify`/`plugin-runner-build` 绿——所以它们与锁无关：
  `sbom-generation` 死在 `cyclonedx-py environment -o ../sbom-python.json --format json`
  ⇒ `error: unrecognized arguments: --format`（runner 装的是 `cyclonedx-bom 7.5.0`，未钉版；
  该子命令不再收这个旗标，格式由输出文件扩展名决定）；`license-check` 死在 `pip-licenses -f table`
  ⇒ `invalid choice: 'table'`（runner 装 `pip-licenses 5.5.5`，可选值是
  `plain / markdown / json / csv / …`）；`vulnerability-scan` 的解析脚本按 list 读 pip-audit 的
  dict 顶层（见上面那条就地纠正）。三条都是"写门的人用的 CLI 与 runner 实际装的版本不同源"，
  与第八十八批那条 SBOM 缺陷同族——那批修的是哈希缺失，这次是旗标与解析形态。
  **处置时不得删掉这三个 job，也不得加 `continue-on-error` 变绿；把 `pip install cyclonedx-bom`
  与 `pip install pip-licenses` 钉版也只是把漂移冻住，仍需按当版本的正确旗标改。**
  处置＝按 runner 实测版本钉版 + 换成当版本真实存在的旗标（`--output-format JSON`、
  `--format=plain`），并把 pip-audit 报告的解析从内联 `python -c` 搬进
  `scripts/ci/vuln_report_gate.py` 使它能被测试执行；三条门的判据在
  `python-ai/tests/test_plugin_security_gates.py`。**结果不是三条全绿**：旗标修好后
  `license-check` 暴露出一条真实的清单语义红，登记为下面那条。
  **CI 补证（run 38226827011 ＝ commit `488fa32d`，手工触发）**：`vulnerability-scan` 与
  `sbom-generation` 均为该 job 历史上**首次 success**（前者日志里 helper 自己打印
  `No known vulnerabilities found (76 packages audited)`，后者 `SBOM contains 35 components`），
  `license-check` ＝ failure，红句是
  `license BSD License not in allow-only licenses was found for package webcolors:25.10.0`。
  **钉版来源就地纠正**：`Install CycloneDX` 一度钉成未钉版当时解析到的 7.5.0，而
  `python-ai/requirements-dev.txt:452` 钉的是 7.3.1（eval-nightly 从锁装的也是 7.3.1）⇒ 改钉 7.3.1，
  并加一条测试把"workflow 的钉版必须等于锁里的钉版"钉住；两版 `environment` 的旗标表实测一致。
- [ ] **`license-check` 的 `--allow-only` 清单不认 SPDX 复合表达式 ⇒ 修好旗标后是一条真红**
  （第一百零四批实测，未处置）—— 容器内（`python:3.11-slim`，`pip-licenses 5.5.5`）用正确旗标实测：
  `pip-licenses --from=mixed --format=plain --allow-only="MIT;Apache-2.0;BSD-2-Clause;…"` ⇒
  `license Apache-2.0 OR BSD-2-Clause not in allow-only licenses was found for package packaging:26.3`
  ＋ 退出 1。这条不是 CLI 漂移：主锁 `python-ai/requirements.txt:809` 钉的 `packaging==26.2`，
  其 PyPI 元数据 `license_expression = "Apache-2.0 OR BSD-2-Clause"`（两个成分**都**在允许清单里，
  但 `--allow-only` 是整串精确匹配，复合表达式永远匹配不上）。同一 job 的第二步
  `Verify no disallowed licenses` 用的是**另一套**更宽的字面清单，还带 `'MIT' in lic` /
  `'Apache' in lic` 的子串放行——两道门对同一份数据持有两份不同的策略，本身就是缺陷。
  处置方向（第一百零五批）：把许可证策略收敛成一个可测试的来源（清单住在脚本里、只读一份），
  按 SPDX 表达式逐成分判定，**且不得**让 `GPL-3.0-only OR MIT` 这类"含 copyleft 的双许可"被
  OR 语义放行——判定语义要写死并测：任一成分不在允许集合即红。不得靠往 `--allow-only`
  里追加复合表达式字符串把门改绿（那是逐包手工放行，不是策略）。
  **runner 上的第二种形态已经出现**（run 38226827011）：红的是
  `license BSD License not in allow-only licenses was found for package webcolors:25.10.0`
  ——`BSD License` 既不是 SPDX id 也不是复合表达式，是 pip 元数据里的**裸文本**许可名。
  同一份依赖面用 `cyclonedx-bom 7.3.1` 生成的 126 组件里，许可证串共 14 种形态，除 SPDX id 外还有
  分类器原文（`License :: OSI Approved :: Apache Software License`）、
  `PSF-2.0`、`Python-2.0`、`MIT-0`、`MIT-CMU`，以及
  **`License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)`**
  ——允许清单里只有 LGPLv3，**没有 LGPLv2+**，所以策略收敛之后这一条要么按 copyleft 判红、
  要么把该包从依赖面里换掉，不能靠给清单加名字放行 copyleft。
- [x] **`sbom-generation` 描述的对象不是产品依赖面（35 个组件 ＝ runner 自带环境），空组件表只打印
  `WARNING` 不判红**（第一百零四批 CI 补证时发现，第一百一十四批处置）—— 那个 job 全程没有
  `pip install -r requirements.txt`，`cyclonedx-py environment` 读的是当前解释器已装的包，
  于是产物里是 runner 的 35 个组件，而同一条流水线 `vulnerability-scan` 审的是 `requirements.txt`
  的 76 个包——两条产物不是同一个对象，SBOM 作为供应链凭证的价值目前是 0。
  本地对照实测：对 `python-ai/.venv` 生成的是 126 组件（scratch `b104_sbom_731.json`），
  数量差异本身就说明了对象错位。处置方向（第一百一十四批，原写作第一百一十批、再改第一百一十一批；
  后者已被第一百一十一批的 e2e 前端服务契约占用，登记前没先核号）：先装 `requirements.txt` 再生成
  （或显式把 `<python>` 指到一个装有产品依赖的环境），组件数与锁的 pin 数做一致性判定，
  同时把"空组件表"从 `WARNING` 改成退出码非 0。**改的是产物描述的对象，不是把门放宽。**
  **处置（第一百一十四批）**：`sbom-generation` 的 `Generate SBOM` 步骤补
  `pip install -r requirements.txt`（形状沿用同流水线 `license-check`，那条 run 38332373261 的
  日志 `:345` 实测它在同一个 ubuntu runner 上 90 秒装完 76 个包），组件面判定从内联 `python -c`
  搬进 `scripts/ci/sbom_lock_coverage_gate.py`：锁的**每一个当前平台适用 pin**都要在 SBOM 里且
  版本与锁一致，否则退出 1；空组件表/读不出形态退出 2（不再打印 `WARNING` 后继续绿）。
  适用面按 `sys_platform` marker 算——锁里 `pywin32` / `win32-setctime` 在 ubuntu 上装不到，
  写死名单会让门**天生红**（第八十八批补 marker 的同一条因果）。
  判据是把改前的真产物喂给改后的门：run 38332373261 那份 `sbom` artifact 报
  **42 缺失 ＋ 9 版本不符 / 76 适用 pin**，退出 1；门的门 17 例（`test_plugin_security_gates.py`
  新增两个类）。
  **runner 补证（第一百十四批 push 后取到）**：这条流水线是**路径过滤**触发
  （`python-ai/plugins/**`、`requirements*.in`、`app/core/plugin/**`），改 workflow 本身的那笔
  push 不会跑它 ⇒ 用 `workflow_dispatch` 在 `de9247f6` 上补跑（run 38384621875，job 115253222329）。
  `Generate SBOM` 步骤 **success**，日志 `:442` 打印
  `SBOM covers all 76 applicable locked packages (77 components; extras describe the tool itself and
  are not judged)`；产物本体从 **35 组件变 77**，按同一份门重算：76 适用 pin **缺失 0、版本不符 0**，
  锁外组件**只有 `pip` 一个**。同一条 run 的其余 job：`hash-verify`／`signature-verify`／
  `plugin-runner-build`／`vulnerability-scan` success，`license-check` 仍是第一百零四批登记的那条
  预期红（日志原文 `license BSD License not in allow-only licenses was found for package
  webcolors:25.10.0`，一句话都没变）。组件个数**不是判据**（下界判定），所以这里记 77 而不是"对上 78"。
- [x] **`_reset_db()` 关连接不持锁，与后台 flush 线程竞争 ⇒ 解释器崩溃**（第一百零三批实测踩到，
  第一百零四批补证时再次踩到并拿到崩溃栈，第一百零六批处置）—— `python-ai/app/core/plugin/audit.py:165-188`（改前）
  的 `_db_conn.close()` 与 `_DB_DIR/_DB_PATH` 换绑整段不在 `with _db_lock:` 内，而 `:128` 的连接是
  `check_same_thread=False`；`tests/conftest.py:126,128` 每条用例前后各调一次。
  **机理纠正（第一百零四批，按崩溃栈改写；本条内的 `:128`/`:158-162`/`:165-188`/`:256-257`/`:271-272` 等行号均为改前形态）**：原先写的是"execute 中途被关连接"，暗示线程没拿锁——
  不对。`_increment_retry`（`:256-257`）和 `_cleanup_synced`（`:271-272`）都在
  `db = _get_db()` **之后**才 `with _db_lock:`，而 `_get_db()` 本体（`:158-162`）读全局也不持锁。
  ⇒ 锁只排开"execute vs execute"，排不开"**锁外取到的连接对象** vs `close()`"：线程先握住旧对象，
  再等 `_reset_db` 释放锁，然后对一个已经 `close()` 的对象 `execute`，sqlite3 在原生层
  access violation，Python 的 `except Exception`（`:278`）接不住。
  ⇒ 所以第一百零三批记的"推荐 A：`_reset_db` 全程持 `_db_lock`"**单独做仍然留窗口**，处置必须两半同做：
  (i) `_reset_db` 的 close＋换绑全程持锁，(ii) 连接引用只能在锁内取（把 `_get_db()` 挪进
  `with _db_lock:`，或让它自己持锁）。
  **新增触发路径（不需要低概率也能打开窗口）**：`flush_on_shutdown(budget_seconds=…)`（`:573`）
  在预算用尽时**带着仍在跑的线程返回**（`:603` `result["timed_out"] = final.is_alive()`），
  调用方随后 `_reset_db()` 就是在关一个正在被使用的连接。
  实测形态：①第一百零三批——同一镜像、同一缓存卷、同一命令，第一次 `pytest -q` 退出码 0，
  第二次 62% 处 `Fatal Python error: Segmentation fault`（`PYTEST_EXIT=139`）；②第一百零四批补证跑
  套件——67% 处 `Windows fatal exception: access violation`、`PYTEST_EXIT=139`，**Current thread**
  栈逐帧点名：`audit.py:596 _run`（`audit-shutdown-flush`）→ `:337 _do_flush` → `:273 _cleanup_synced`，
  同一 dump 里主线程在 `_pytest/fixtures.py` 的 fixture teardown（scratch `b104_pytest_full2.log`）。
  ②把归因从推断升成"崩溃栈直接点名"。CI 的 `python` job 在同一把锁上给的是 `2056 passed / 7 skipped`，
  所以这是**本地跑才有概率命中**的窗口，不是环境问题。
  `app/` 下当前无 `_reset_db` 调用方（生产今天不受影响），但任何把"重定向审计库"接进运维路径
  的改动都会走进同一窗口。
  **判据方向（第一百零六批）**：行为侧确定性红（持锁时起线程调 `_reset_db`，断言它尚未完成）
  ＋ 形态侧静态红（同一函数里 `db = _get_db()` 出现在 `with _db_lock:` 之前即判红——这条不赌时序）。
  **处置（第一百零六批，两条判据都先量到红再改）**：
  ①行为侧 `python-ai/tests/test_plugin_audit.py::TestDbConnectionLifetime` 两例——
  `test_reset_db_waits_for_the_db_lock` 改前红（"锁还被占着，`_reset_db` 已经跑完"），
  `test_concurrent_first_use_builds_exactly_one_connection` 改前是**稳定红而非概率红**：
  8 线程并发首用量到 **8 个连接**（每个都真开了文件并跑完建表），原先写的"靠运气"据此纠正；
  ②形态侧新增 `scripts/static-checks.py` 检查 16（`--db-lock-lifetime`，CI 无参全跑已覆盖）：
  对 HEAD 的 `audit.py` 量到 **13 处**违规（10 处 `db = _get_db()` 在锁外 ＋ `_reset_db` 里 3 处
  `_db_conn` 读写），改后 **0 处**，两侧核对到的引用数同为 13 ⇒ 不是靠少扫得到绿。
  实现＝`_reset_db` 的 close＋换绑整段持锁、10 处取连接全部挪进 `with _db_lock:` 体内、
  `_get_db` 的 docstring 写明"调用方必须已持锁"。锁**没有**换成 `RLock`：约定是调用方持锁后再取，
  `_get_db` 本体不取锁，因此不产生重入需求；并用 AST 核过锁内没有再调用本模块任何 DB 函数。
  改后本地全套件连跑三次——前两次（只含行为判据）`2068 passed / 12 skipped`，第三次
  （加上检查 16 的 12 例门禁测试）`2080 passed / 12 skipped`，退出码全 0
  （scratch `b106_pytest_run1/2/3.log`），三份日志里 `access violation` 与 `Segmentation fault` 0 命中。
  崩溃本身没有被复现第三次，关掉的是它赖以发生的**形态**。
  **第四次（完整日志留档 `b106_pytest_run4.log`）不是绿的**：`1 failed, 2079 passed / 12 skipped`，
  红的是 `TestRetryDeadLetters::test_second_retry_is_idempotent`。已按同一套确定性编排对 **HEAD 与工作区
  各跑一遍、两边都红**，判定为下面那条独立缺陷（与本批无关，既不算进本批的"三次绿"，也没有放宽那条断言）。
  **未随本批处置的观察（不是本批引入）**：`flush_on_shutdown`（改前 `:573`）预算到点仍会
  **带着仍在跑的 daemon 线程返回**——改后那个线程只会阻塞在 `_db_lock` 上，不会再拿着已关闭的连接，
  所以崩溃没了；但"退出函数返回时仍有出站未确认"这一事实保留，判据方向是让它返回时把在途线程的
  身份交给调用方（或干脆不另起线程，改为在预算内轮询 `outcome`）。生产侧今天无 `_reset_db` 调用方，
  优先级低于第一百一十一/一百一十二批。
- [x] **审计 flush 的超限判定读的是快照而不是行的当前状态：一条在途的 flush 可以把运维刚回灌的
  dead-letter 行再翻回 dead-letter**（第一百零六批第四次全套件踩到并取证，第一百零七批处置）——
  `python-ai/app/core/plugin/audit.py:309` 的 `_do_flush()` 是
  「`_get_unsynced_entries()`（`:239`）取快照 → 锁外做出站 I/O → 用**快照里的** `entry.retry_count`
  判 `>= _MAX_RETRIES`（`:336`）→ `_mark_dead_letter()`（`:225`）」，`_db_lock` 只保证每条语句原子，
  从来不覆盖"快照 → 回写"这段距离。于是：后台 `audit-flusher` daemon（`record_audit` 经
  `_ensure_flush_thread`（`:430`）起了，30s 一轮）取到快照时那一行还是 unsynced＋retry 超限，
  运维随后调 `retry_dead_letters()`（`:558`，`SET dead_letter = 0, retry_count = 0`）把行回灌，
  daemon 再把自己的判定落下去 ⇒ **运维这次回灌等于没生效**，行又变成 dead-letter 且
  `retry_count` 被加回。测试面同一个机理还解释了全套件的偶发红：`tests/conftest.py:122-128` 的
  autouse fixture 只 `_reset_db()` 换库、**不停后台线程**，所以任何一条到点的 flush 都会写进
  "当下那条用例"的临时库。
  **取证（确定性编排，不靠复现率）**：脚本用 events 把"取快照"与"落标记"卡在 `retry_dead_letters()`
  两侧 ⇒ 对 HEAD 与工作区（第一百零六批改后）各跑一遍，**两边都红**
  （`stray 看到的 retry_count=[2] first=1 second=1`），同脚本的单线程对照组给
  `first=1 second=0` ⇒ 一条 drain 只会产生一次标记，套件那次失败日志里同一 id 打了两行
  "超过最大重试次数"（42.107 / 42.113）必然是第二条线程（scratch `repro_stale_snapshot_requeue.py`、
  `b106_pytest_run4.log`）。
  **判据方向（第一百零七批）**：①把那条确定性编排做成 `test_plugin_audit.py` 里的红判据——
  运维回灌之后，一条拿着旧快照的在途 flush **不得**再把该行翻回 dead-letter；
  ②实现方向是"判定读当前行"：在同一个 `with _db_lock:` 里先 `retry_count = retry_count + 1`，
  再按 `WHERE id = ? AND retry_count >= ?` 落 `dead_letter = 1`（预算值仍走绑定参数，测试对
  `_MAX_RETRIES` 的 patch 不能失效），`_do_flush` 不再自己判超限；
  ③测试串台那一半单独处置：autouse fixture 在换库前后把 `_flush_stop` 置位并 join 掉
  `audit-flusher`，别让 daemon 写进别人的临时库——**这是修隔离，不是放宽任何断言**。
  不得改成把 `assert retry_dead_letters() == 0` 放宽成 `<= 1`，也不得给该用例加 skip/重跑。
  **处置（第一百零七批，2026-10-12）——两处都按判据方向改掉，没有任何断言被放宽**：
  ①实现侧删掉 `_mark_dead_letter`（改前 `:225`）与 `_increment_retry`，合成
  **`_register_failed_attempt(entry_id)`（现 `:249`）**：`retry_count` 的读、自增、落 `dead_letter = 1`
  三步共用**同一次** `with _db_lock:`，超限与否比的是"自增之前读到的当前行计数"，与旧判定同形，
  只是从快照抬到当前行；`_MAX_RETRIES` 仍走 Python 侧比较而**不是** SQL 常量拼接，
  测试对 `_MAX_RETRIES` 的 patch 照旧生效。`_do_flush`（现 `:312`）不再自己判超限，
  只按 `_register_failed_attempt` 的返回值决定要不要打那条 warning（现 `:339`）。
  ②测试侧把取证用的确定性编排做成 `tests/test_plugin_audit.py::TestFlushVerdictReadsCurrentRow`：
  在途 flush 的 `_post_to_java_backend` 被 patch 成"发出 `snapshot` 事件后卡在 `release` 上"，
  主线程在这段窗口里跑完一轮 `_do_flush()` ＋ `retry_dead_letters()`，再放行在途线程
  ⇒ 改前红（`first=1 second=1`，回灌的行又被翻回 dead-letter，且 `get_sync_status()["dead_letter"] == 1`），
  改后绿（`first=1 second=0`，`dead_letter == 0`）。
  ③串台那一半单独改成修隔离：`tests/conftest.py` 的 autouse fixture 在 `_reset_db()` **之前和之后**
  都调用新的 `_stop_audit_flusher()`（置 `_flush_stop`、摘走 `_flush_thread` 句柄、join 30s，
  join 不掉就 `pytest.fail` 并写明"它会把这次 flush 写进下一条用例的临时审计库"）——
  换库前先停线程，避免上一条用例留下的 daemon 写当下这条用例的库。配套
  `TestAuditFlusherIsolation::test_record_audit_really_starts_the_daemon` 是反空判定：
  先证明 `record_audit` 确实留下一个活着的 `audit-flusher`，否则"没有残留线程"那条会凭空绿。
  **改前那批行号（`:309/:239/:336/:225/:430/:558`）记的是取证时的位置，现行为**
  `_do_flush :312 / _get_unsynced_entries :225 / _register_failed_attempt :249 / 调用点 :339 /
  _ensure_flush_thread :432 / retry_dead_letters :560`（`grep -n "^def "` 于 `audit.py` 复核）。
  验证：`tests/test_plugin_audit.py` 51 → **54 passed**；检查 16 的反空阈值按构成从 `>= 13` 改成 `>= 12`
  （9 个 `_get_db()` 调用点 ＋ `_reset_db` 里 3 处 `_db_conn` 读写——第一百零六批量到 13 是因为那时
  `_mark_dead_letter` 里还有第 10 个调用点，本批把它折进 `_register_failed_attempt` 少了一个；
  是构成变了、不是规则匹配不上，`test_db_lock_lifetime_gate.py` 的 docstring 里写明了这笔账）；
  `scripts/static-checks.py` 全模式退出 0，检查 16 那行现为"扫描 1 个碰共享连接的模块、12 处引用"；
  全套件连跑两次绿（`2083 passed, 12 skipped`，日志 `b107_pytest_run1/2.log`）。
- [x] **Flyway 迁移步骤在 `e2e.yml` / `eval-nightly.yml` 从诞生起就没过过：插件只认
  `-Dflyway.*`，而步骤给的是 `SPRING_DATASOURCE_*`（四处站点，`ci.yml` 里已有写对的那一份）**
  （第一百零四批取证，第一百零八批处置）—— run 38221938525（＝ `8054f32e`）的 `e2e-full` job 死在这一步，日志原文：
  `FlywayException: Unable to connect to the database. Configure the url, user and password!`
  （scratch `ci_e2e_flyway.log` 第 617 行）。这一 `conclusion` 不是今天才有：2026-10-10 / 10-11（三次）/
  10-12 连续 **5** 条 run 的 `e2e-full` 都死在**同一个步骤**（逐 run 核过
  `gh run view <id> --json jobs --jq '.jobs[]|{name,conclusion,failed:[.steps[]|select(.conclusion=="failure")|.name]}'`），
  中间另有几次是 `cancelled`——**原写作"取消来源不能从日志判定：`e2e.yml` 里没有 `concurrency` 键，日志里也没
  有 timeout 声明，所以这些 `cancelled` 既不能算'过'、也不能归因成'被新 run 挤掉'"，第一百一十五批·补证就地纠正**
  （那句话把"日志文本里没有 timeout 字样"当成了"没有 timeout 声明"，而声明写在 workflow 里：`e2e.yml:165` 给
  `e2e-full` 设了 `timeout-minutes: 20`，`:13` 给 `e2e-smoke` 设 15）。逐 run 量作业窗口
  （`gh run view <id> --json jobs --jq '.jobs[]|select(.name=="e2e-full")|{conclusion,startedAt,completedAt}'`
  ＋ `gh api repos/.../actions/runs/<id>/jobs --jq '.jobs[]|select(.name=="e2e-full")|.steps[]|select(.conclusion!="success" and .conclusion!="skipped")|.name'`）：
  **7 条** `cancelled` 的 `e2e-full`（`38135767903`／`38137950016`／`38140336693`／`38145150097`／
  `38226782059`／`38395206533`／`38399840606`）每条从 job 起算跑 **20m05 s–20m19 s** 就断，且 **7/7 停在同一步
  `Install Python dependencies`**（`e2e.yml:211-213`）⇒ 归因是**那条 20 分钟作业超时把还在装依赖的 job 杀掉**；
  "`e2e.yml` 没有 `concurrency` 键"这一半原判定仍成立，所以"被新 run 挤掉"确实不成立，但正确的因果不是"不可判定"
  而是"有上限、上限到了"。随之要摘出去：这 7 条**从没走到 Flyway 那一步**，不属于上面"连续 5 条死在同一
  `flyway:migrate` 步骤"的家族（那 5 条是真正 `failure` 且步骤名对得上的）。
  对照组：`ci.yml` 通篇没有 `timeout-minutes`，同一天同一镜像限流下的 CI run `38395206325` 跑到 **44 分钟**也没被
  取消，只有设了 20 分钟上限的 `e2e-full` 被杀 ⇒ 取消判据是那道声明，不是并发。
  更早的 2026-09-22、09-29 两次 `failure` 的失败原因不在
  step 列表里（`.steps` 全空），**本条没有把它们算进"同一步红"**，要归因得单独取日志。
  机理核对：`.github/workflows/e2e.yml:75-82` 给步骤设的三个变量是
  `SPRING_DATASOURCE_URL/USERNAME/PASSWORD`，而 `mvn --batch-mode flyway:migrate` 执行的是
  flyway-maven-plugin，它读 `-Dflyway.url/user/password`、`flyway.conf` 或 `FLYWAY_*` 环境变量，
  **不**读 Spring 的那三个名字；`java-backend/pom.xml` 里也**没有** `flyway-maven-plugin` 的
  `<configuration>`（`:103-108` 只有 `flyway-core` 与 `flyway-mysql` 两个依赖），于是插件从
  Maven central 前缀解析到最新版（日志里是 `flyway:11.7.2`，两次
  `Could not transfer metadata … HTTP Status: 401` 就是那次解析的噪声）并拿到空配置。
  ⇒ 与第一百零四批同族：**"runner 装了什么/工具读什么"与"门里写了什么"不同源**，而且这里的
  插件版本也未钉住。**同一缺陷的对照证据（第一百零四批顺带取证）**：`ci.yml:382-383` 的
  `Validate Flyway migrations against MySQL` 用的是正确形态
  `mvn --batch-mode flyway:migrate -Dflyway.url=… -Dflyway.user=… -Dflyway.password=…`，
  它在 runner 上是绿的——所以这不是"MySQL 起不来"，是**同一个仓里已经有一份写对的**；
  另外三处（`e2e.yml:82`、`e2e.yml:221`、`eval-nightly.yml:96`）都只给 `SPRING_DATASOURCE_*`。
  `Nightly Evaluation (Runtime)` run 38224268851 的 `eval-harness` job 同样死在
  `Run Flyway migrations`。**该 run 的第二条红已归因，但它是另一个缺陷**（`Run runtime evaluation
  gate` ＝ 活栈不可达被折叠成"错误率退化"），见下面那条独立条目，本条不重复它的判据。
  四处站点、三条工作流 ⇒ 处置时**四处一起改**，并在 `java-backend/pom.xml` 里显式声明并钉住
  `flyway-maven-plugin`（现在四个 run 都在从 central 前缀浮动解析版本）。
  处置方向（不得靠删这一步或加 `continue-on-error` 变绿）：把插件真读的那三个值传进去，
  判据要证明迁移确实发生（表结构落到 e2e/eval 库），而不是只把步骤跑绿。
  **第一百零四批 CI 补证对本条的影响**：该批的 `E2E` run 38226782059 在
  `Run pip install -r requirements.txt` 停 19 分 22 秒后被取消，**没有走到 Flyway 那一步**，
  所以本条的判据仍然只用 run 38221938525 那一族历史日志；补证没有为"改后是否还红"取到任何证据。

  **第一百零八批处置（2026-10-12）**：四处站点按对照证据统一成块标量＋三个 `-Dflyway.*` 旗标
  （`e2e.yml:76-83`、`e2e.yml:215-222`、`eval-nightly.yml:90-97` 为改后锚点；上文 `:75-82` / `:82` /
  `:221` / `:96` 是改前锚点，保留作取证原文），同时删掉那一步里空转的 `SPRING_DATASOURCE_*`
  三个键（`Start Java backend` 步骤仍保留它们——那边读的是 Spring，不是插件）。旗标值不手写：
  `python-ai/tests/test_flyway_cli_gate.py::TestFlagsMatchServiceCredentials` 按 PyYAML 解析
  每个 job 的 `services.mysql.env`，断言 url 的库名、user、password 三项与 service 声明逐字相等
  （`ci.yml` 是 `hfusionhub_test/testuser/testpass`，另两条是 `hfusionhub/e2e/e2e-pass`）——
  形状对但指错库，这条也会红。
  `java-backend/pom.xml:211-219` 显式声明 `flyway-maven-plugin`，版本写 **`${flyway.version}`**
  （引用而非数字）：`flyway-core` 依赖不带 `<version>`、由父 BOM 的同一个属性管理，于是插件与
  运行时同版本是**结构保证**；`spring-boot-dependencies:3.5.16` 里 `<flyway.version>11.7.2</flyway.version>`，
  与该 run 日志里浮动解析到的版本一致 ⇒ 本批钉版**没有**改变今天实际执行的版本，它消除的是
  "central 哪天发新版就悄悄换插件"这一条。解析已核：`mvn -o flyway:info` 报出的 goal 坐标是
  `org.flywaydb:flyway-maven-plugin:11.7.2:info`（离线只缺两个 jackson jar，旗标已生效）。
  行为侧判据在活库上量，不由文本门冒充：本机起 `mysql:8.0`（46）容器，库 `hfusionhub`、用户
  `e2e/e2e-pass`，与 workflow 的 service 同凭据——
  ① 旧形状（只给 `SPRING_DATASOURCE_*`）复现日志原文 `Unable to connect to the database.
  Configure the url, user and password!`（scratch `b108_head_form.log:41`）；
  ② 新形状 `Successfully applied 87 migrations to schema hfusionhub, now at version v86`
  （`b108_fixed_form.log:106`）；③ `flyway:info` 绿（`b108_info.log`）；
  ④ 库内侧核对 `SELECT COUNT(*), SUM(success=1), MAX(installed_rank) FROM flyway_schema_history`
  ＝ `87 / 87 / 87`，schema 共 70 张表（迁移文件 87 个：V1-V86 加一个 V10_1）。
  门禁：新增 `scripts/static-checks.py` 检查 17（`--flyway-cli`，已并入默认全跑档），规则四条——
  缺任一 `-Dflyway.*`、flyway 步骤的 env 里出现 `SPRING_DATASOURCE_URL/USERNAME/PASSWORD`、
  步骤带 `continue-on-error: true`、每个 workflow 的 flyway 调用数与 `FLYWAY_STEP_EXPECTATIONS`
  （ci 2 / e2e 2 / eval-nightly 1）不符；适用面为空（一处 flyway 调用都找不到）本身判红，
  所以"删步骤/改 goal"不会把门变绿。`test_flyway_cli_gate.py`（19 个用例）是这条门的门。
  诚实边界：本批未跑 e2e 全栈（改后的这一步要在下一个 push 的 runner 上才见真章），
  `hfusionhub` 库里的数据只是迁移产物、没有业务行；旧 run 的 `cancelled` 归因仍按上文口径不变。
- [ ] **`eval-runtime` 把"活栈不可达"折叠成"错误率退化"——nightly 的红读起来像模型回归**
  （第一百零四批归因，未处置）—— run 38224268851 的 `eval-runtime` job（114727802659）里
  `Run runtime evaluation gate` 打的是：220 个用例**每一个都在 ≈0.1 秒内 ERR**，汇总
  `error_rate: 1.0`（基线 0.0），判据句 `错误率=1.000 exceeds maximum 0.020`，
  `regressions` 同一条。而该步骤前置的那道检查只看**变量有没有值**
  （`if [ -z "$EVAL_INTERNAL_TOKEN" ] || [ -z "$EVAL_BASE_URL" ]`），
  `EVAL_BASE_URL` 是一条 cpolar 隧道（`https://aa9fbd2.r36.cpolar.top`），有值≠可达。
  ⇒ 0.1 秒/例的 100% 错误率只可能是连接层，不是检索或生成质量；今天的形态是**看日志的人会被
  指向"评测退化"**，而真实结论是"被测环境没起来"。
  处置方向（第一百一十二批，原写作第一百一十一批；不得靠放宽 `--maximum-error-rate` 或把门跳过）：在跑用例**之前**做一次
  可达性/健康探针（对 `EVAL_BASE_URL` 的一个已知端点取一次成功响应，失败即单独判红并打印
  "活栈不可达"这句话）；并把"全部用例同因失败"这种形态本身做成判定——例如错误率＝1 且
  p95 时延接近 0 时输出连接类错误样本，而不是只报一个百分数。**判据要能区分"环境没起来"与
  "模型变差"，两者都不许绿。**
- [x] **整栈第一次真跑量出的四处"配置写了、容器里没有对应实体"**（第一百零九批取证并处置）——
  这四处都不是假想，是 `docker/docker-compose.yml` 9 服务（含 mysql/redis/milvus/minio/etcd）
  第一次起来之后逐个量出来的；共同形状是**容器起得来、健康检查不红、API 正常，死的是别处**：
  ① `python-ai-worker` 的 command 是 `python -m arq arq_worker.WorkerSettings`，而
  `deploy/Dockerfile.python` 只 `COPY app/ app/` ⇒ 容器内 `ModuleNotFoundError`，
  `RestartCount` 14，`arq:queue` 那条 job 滞留 83.69s 无人消费，python-ai 的 API 日志还在写
  "dispatched via arq"；② dev compose 的 redis7 以 `--requirepass "$REDIS_PASSWORD"` 起，
  java-backend 只给 `SPRING_DATA_REDIS_HOST` ⇒ 登录 500 `RedisConnectionFailureException`
  （traceId `40bb29cf73464ff28f01caa37cbb40b8`）；prod 同一段一直是成对的
  （`deploy/docker-compose.prod.yml:176`），所以这条只在整栈上暴露；③ `application.yml` 的
  `python-ai.base-url` / `python-ai.engine.url` 是裸字面量 `http://localhost:9000`，而三档拓扑
  只设 `AI_SERVICE_URL` ⇒ `POST /api/document/204/parse` 400 I/O error（traceId
  `9dae81714a9a41a1812c0cb3155fca89`），请求打到 java 自己身上；④ worker 继承镜像里给 uvicorn
  写的 `HEALTHCHECK`（:9000）⇒ `Up (unhealthy)` 而 `probe_http=000`、`curl exit=7`，进程活着、
  心跳在写，假红盖住了真要看的崩溃循环。
  **处置（2026-10-12，四条都是用户逐条拍板的方案）**：① `COPY arq_worker.py .`（镜像里补实体，
  而不是改 command 去迁就残缺的镜像）；② dev compose 补 `SPRING_DATA_REDIS_HOST` +
  `SPRING_DATA_REDIS_PASSWORD: ${REDIS_PASSWORD:-}`（与 prod 同形）；③ yml 两个键并入
  `${AI_SERVICE_URL:...}`，键名保留、来源收成只有一个；④ worker 块写 `healthcheck.disable: true`，
  存活信号看 redis db2 的 `arq:queue:health-check`。活栈复测逐条转绿：`health=<none> restarts=0`、
  `0.50s → …process_document({'document_id': '204'…})` 且 `arq:queue` zcard=0、登录 `code=200`、
  parse `HTTP=200` 且 java 日志写明 `调用Python引擎: http://python-ai:9000/api/parse`。
  门禁：`scripts/static-checks.py` 检查 18（`--container-runtime-contract`，已并入默认全跑档），
  四条规则各按拓扑钉数量、适用面为空本身判红；`test_container_runtime_contract_gate.py`（39 例）
  是这条门的门，command 与 application.yml 两处文本解析各配一个 PyYAML oracle。建门时门自己
  纠正了一次：`_image_probe_port` 第一版按物理行匹配，真仓库那行 `HEALTHCHECK` 带 `\` 续行 ⇒
  端口恒为 `None`，"自定义探针仍打服务端口"那一支永不触发——已改为先拼逻辑行。
  诚实边界（仍开着）：全链路的最后一环在活栈上是**按外部依赖失败**的——worker 消费后嵌入调用
  `OLLAMA_BASE_URL=http://host.docker.internal:11434` 报 `Network is unreachable`，文档 204
  终态 `status=3 / chunk_count=0`，但回调确实回到了 java 并写了库（`文档状态已更新: 204 -> FAILED`）。
  ⇒ 链路已通到"有真嵌入服务就能成功"这一步，缺的是一个可达的嵌入端点，不是配置；这条留在
  `docs/PRODUCTION_OPS.md` 10.3 的第一条未收口里。
- [x] **e2e 轨"测试步骤写了、:3000 上的进程没有"**（第一百一十一批取证并处置）
  第一百零八批那条 Flyway 修绿之后，`Run full E2E suite` 从出生起第一次真的执行（run
  38332373255，push `779fd23b`），于是暴露出它下面那一层：35 失败 / 28 通过 / 10 跳过，
  35 条报错同一条 `Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000/…`。
  三次历史对照证明这不是回归——38233532705 / 38134153616 / 38025985552 的 `failed_steps`
  都是 `["Run Flyway migrations"]` 且测试步骤 `skipped`，即套件从未跑过；README 里那个
  "73 E2E" 一直是用例总数而不是通过数。
  根因是两处各自都"说得通"的配置合起来没有实体：`.github/workflows/e2e.yml` 两个 job 都是
  `npm ci` → `playwright install` → `npx playwright test`，中间没有一步起前端；而
  `hfusionhub-frontend/playwright.config.ts:31-38` 写 `webServer: CI ? undefined : {…}`
  （本地开发靠它起 `npm run dev`）。同 job 的 `Wait for Java backend` / `Wait for Python AI`
  两条轮询都绿，缺的正是前端那一条。
  处置（人拍板选 A：工作流里加显式步骤，不动 config）：两个 job 各补
  `Start frontend dev server`（`npm run dev &`）＋ `Wait for frontend dev server`
  （`curl -sf http://localhost:3000/`，30×2s，超时 `exit 1`），形态照搬同 job 已有的两条轮询。
  本地实测把这条新步骤的效果量出来而不是让文本门冒充：vite 起来后 `curl -sf :3000/` = 200
  （冷启动 `ready in 10354 ms`），`/api/health` 经 vite 代理 = 502（本机无 8080，CI 上有 java），
  杀进程后同一请求 000/refused ＝ 那 35 条红的签名。
  门禁：检查 19（`--e2e-frontend-server`，已并入默认全跑档）——起前端存在、排在 `npm ci` 之后、
  测试前有带端口的探针、探针端口与 config 的 `baseURL` 同源、探针超时必须 `exit 1`，
  适用面按 job 名下界钉 `{e2e-smoke, e2e-full}`（改名/删步骤判"适用面为空"，少一个判"缩小了"），
  外加一条"config 在 CI 档也自起 webServer ＋ 工作流显式起 = 同一端口两个主人"判红；
  `test_e2e_frontend_server_gate.py`（22 例）是这条门的门，有名步骤顺序与无名步骤条数都由
  PyYAML 复算。建门时门自己纠正一次：`_playwright_ci_autostarts` 第一版按 `CI \? (\w+) :`
  匹配，读不出 CI 档自起的是对象字面量 ⇒ "双主人"那一支永不触发，改成压平后取第一个非空 token。
  诚实边界：本批只证"第一道死因已除"，**不证那 35 条会转绿**——登录态、seed 数据、mock LLM
  这些更高层失败要等下一次 push 的 e2e run 才分得清；60 秒探针预算在本机是 10.4 秒，
  runner 上是冷 npm 缓存，未量。
- [x] **上面那条边界在同批推送后就有了答案**（第一百一十一批·补证，run 38336201364 / commit `aaaf045b`）：
  `Start frontend dev server`＋`Wait for frontend dev server` 两步 success ⇒ 60 秒预算在冷 npm 缓存下够用；
  套件 `35 失败 / 28 通过 / 10 跳过` → **`4 失败 / 59 通过 / 10 跳过`**（合计 73），31 条确实死在 :3000
  没人监听。同一 push 的 `CI` run 38336201365 十一个 job 全绿，`static-consistency` 就是全跑档的
  `static-checks.py` ⇒ 检查 19 也第一次在 runner 上跑过。`e2e-smoke` 是 skipped，按 `e2e.yml:10`
  `if: github.event_name == 'pull_request'` 的设计，不是缺陷。
- [x] **e2e 轨剩下的 4 条红：最外一层已除（runner 复测 4→3→1），第三层被撤销、第二层改判竞态、
  第 4 条第一百一十五批处置**（第一百一十三批；
  原写作第一百一十二批，与上面那条 `eval-runtime` 可达性探针已占用的编号撞车，就地改号）
  取证（run 38343229817 的 `e2e-results-full` ＋ `playwright-traces`，全部三条 demo-data 的 retry1
  `trace.zip` 解出 `0-trace.network`）：报错都是 `page.waitForResponse: Timeout 10000ms exceeded`
  （`demo-data.spec.ts:23`/`:40`/`:72`），但 trace 显示请求**发出去了也回来了**，响应体是
  `{"code":403,"message":"演示数据功能已关闭（DEMO_ENDPOINTS_ENABLED=false）…"}` 配 HTTP **200**
  （traceId `d36804ec03644249b011b204d5d97713`／`ac1ca5cb04b74d84b64e47721f767fce`／
  `57e397cc38ac42c6adee633a75fafd49`）。同一条 trace 的时间轴还量到：`/api/demo/import` 起于
  `_monotonicTime 114340`、历时 121 ms（≈`114461` 落地），而 `waitForResponse` 在 `114773.2` 才注册
  ——waiter 比响应晚 312 ms。
  **runner 复测（改后三次，除 `stats` 外还逐条读每次 attempt 的 `results[].status`）**：
  改前 run 38343229817 是 **59 通过 / 4 失败 / 10 跳过**；第一百一十三批自己那笔 push（run
  38349608765）变 **60 / 3 / 10**，闭掉的正好是 `demo-data.spec.ts :: should import demo data
  successfully` 这一条，**没有新增红**；第一百一十四批的 push（run 38384435241）与上一条**同一组
  三条、`flaky 0`**（60/3/10，237.3 s，三条各 3/3 次尝试全红）；第一百一十四批补证那笔 docs-only
  push（run 38388749034，`e2e` 目录一个字没动）变 **61 通过 / 1 失败 / 1 flaky / 10 跳过**（213.3 s），
  真红只剩 `tools.spec.ts:11`。⇒ 最外那一层的结论不变，但"剩下三条稳定复现"**只对④成立**：
  两条 demo waiter 是竞态，`retry` 会把它们掩盖成绿。
  - [x] **最外一层（CI 侧，本批处置）**：`application.yml:177` 的
    `endpoints-enabled: ${DEMO_ENDPOINTS_ENABLED:false}` 默认关，`DemoController.java:39/44` 未开启时
    发 200 里的信封 403；dev 侧一直开着（`docker/docker-compose.yml:272`、`docker/.env:24`），
    只有 `e2e.yml` 两个 java env 块（`:84-105`、`:236-257`）没带这个键 ⇒ 两处补
    `DEMO_ENDPOINTS_ENABLED: "true"`。门禁：检查 20（`--e2e-backend-feature-flags`，已并入默认全跑档）
    ——键必须出现在"既 `spring-boot:run` 起后端、又跑 playwright"的那个 job 的 env 并集里且值为
    `true`，缺键／值不对／注释冒充／放错步骤各红一次，适用面为空或缩小都判红；
    `test_e2e_backend_feature_flag_gate.py`（18 例）是这条门的门，含一条 PyYAML oracle 与一条
    "workflow 钉值 == dev compose 钉值"的跨文件同源判定。建门时门自己纠正一次：
    "适用面缩小"分支第一版写成 `E2E_TEST_JOBS - set()`（恒真）⇒ 任何裁剪都判绿，改成拿本轮真扫到的
    job 集合作差。
  - [ ] **第二层（spec 侧，待拍板；定性是竞态——补证段那句"确定死因"判重了，已就地改）**：同族三处
    （`demo-data.spec.ts:23`/`:40`/`:71`）都是 `await importButton.click()` **之后**才 `waitForResponse`，
    响应先到就 10 秒空等。第一百一十三批登记时的判断是"开了关之后导入会真做播种、耗时大概率越过
    注册点 ⇒ 红会转绿，但那是时序运气不是修好"；本文件上一版把它写成"已被 runner 实测否掉、是剩下
    三条红里两条的**确定死因**"，依据是 run 38384435241 的 trace 里 `/api/demo/import` 只花
    **38.342 ms 与 31.011 ms**、`:40`/`:71` 各 3/3 次尝试全红。
    **第三条 run 把这句也否掉了**：run 38388749034（`39be2f27` 那笔 docs-only push，e2e 代码逐字节
    相同）是 **61 通过 / 1 失败 / 1 flaky / 10 跳过**（213.3 s）——`:71` 首次即过、`:40` 首败后
    retry 通过，而 retry1 的 trace 里同一个请求花 **49.422 ms**（HTTP 200），与 38.3／31.0 ms 同一
    量级。⇒ 定性回到**竞态（由 retry 掩盖的 flaky by construction）**：响应与注册点都在几十毫秒量级、
    谁先到不稳定，所以"会转绿、但那是时序运气不是修好"成立；要修的仍是顺序而不是运气，正确写法是
    先注册再点（`Promise.all` 或把 waiter 提到 `click()` 前）。`:23` 那一处在三条 run 上都是绿的，
    一条能解释的线索是"三条用例各点一次导入，`:23` 撞上真播种、`:40`/`:71` 撞上幂等跳过后的重复导入"，
    但**未量**（trace 只核到重复导入那几次，没核第一次播种的耗时，也没核 `skippedCount`）。
    **没动任何 `.spec.ts`**：改法涉及三条用例的写法，要拍板。
  - [x] **第三层（已撤销：判定取错了 service，runner 与代码两处都不支持它）**：第一百一十三批登记
    "`demo-data.spec.ts:29` 与 `:78` 等 `li:has-text("知识库文档")` 是期望陈旧"，依据写成
    `BidDemoImportServiceImpl.java:149-152` 发的 label 是「招标文件知识库／企业资质库／历史标书库／
    示例投标项目」。核对后两处都不成立：
    ① 用例点的是「导入演示数据」按钮，走 `DemoController.java:63` 的 `POST /api/demo/import`，
    由 `DemoImportServiceImpl.java:143` 发 `section("kb", "知识库文档", …)`（`:195/:200/:203` 同名字符串），
    招投标那条 `import-bid`（`DemoController.java:81`）是**另一个** service、另一套 label，
    113 把两侧读混了；
    ② `SetupChecklist.vue` 里唯一的 `<li>` 是 `:251` 的 `<li v-for="section in lastSections">`，
    `:224` 的"（知识库文档、回答方案…）"在 `<div><span>` 的引导文案里、不是列表项，
    所以 `li:has-text("知识库文档")` 只能命中 section label，而 section label 正是"知识库文档"。
    runner 侧同样不支持原判：含 `:29` 的 `should import demo data successfully` 在
    run 38349608765 与 38384435241 上**都是通过**，`:78` 那处从未执行到（同用例死在 `:71` 的 waiter）。
    ⇒ 期望与实现一致，**没有陈旧期望可改**；这一层从"待拍板"移到"已撤销"，剩下两条红的成因全部归到
    第二层与第 4 条。建条目时读侧的错法登记为语义漂移，按就地纠正处理，不再另立缺陷号。
  - [x] **第 4 条与开关无关（三条 run 里唯一每次都红的：各 3/3 次尝试全失败）——第一百一十五批按"改用例"处置**：
    `tools.spec.ts:11` 的 `getByText('搜索知识库', { exact: true })` 报 `element(s) not found`，而 `:9`/`:10`
    的静态文案都过；`Tools.vue:62` 是 `pageSize = 6` 的客户端分页。登记时缺的两个数（**CI 注册表条数**与
    `search_knowledge_base` 的**排序位置**）本轮量到了：
    ① 取数侧不按注册顺序出——`python-ai/app/api/tools.py:92-93` 把列表按
    `(status 档, **name 字母序**)` 排（`active` 档在前），`app/api/tools.py:30-34` 由 `agent_version` 推 status；
    ② CI 拓扑（`e2e.yml` 那组 env，python venv 里直接跑 `create_full_registry` ＋ `_build_tool_entry` ＋
    同一段 sort）注册表 **30 条**，其中 20 条 B3 沙箱演示业务工具在 `demo_business_tools.py:137` 写
    `agent_version="1.0"` ⇒ 与三条 V1 知识库工具同属 `active` 档、按字母序排在前面，
    `search_knowledge_base` 落**第 15 位** ⇒ 第 1 页渲染的是
    `add_device／apply_annual_leave／apply_sick_leave／cancel_auto_renew／create_incident／export_finance_report`，
    它在**第 3 / 5 页**。⇒ 这条不需要竞态假设，是确定性的"第 1 页没有它"，与三条 run 的 attempt 级结果
    一致（38349608765／38384435241／38388749034 上它各 3/3 全红，补证二那轮两条 demo 竞态转绿时它照样红）；
    ③ 活栈复测（第一百零九批那套 dev 栈，页面 aria 快照自报）：「全部能力 **32**／知识库 4／日常工具 27／
    联网能力 1／需要确认 2」＋`第 1 / 6 页` ⇒ **条数与页数本来就随拓扑变**（CI 30→5 页、dev 栈 32→6 页），
    写死的页数一定是陈旧的；
    ④ 反证那两行为什么曾自洽：摘掉 20 条演示工具 ⇒ 10 条 ⇒ 恰好 2 页、且第 1 页含 `search_knowledge_base`
    ⇒ `:11`（第 1 页可见）与 `:13`（写 `第 1 / 2 页`）是**演示工具进注册表之前**写的，两行互相咬合。
    **处置（用户拍板 A＝改用例，不动产品可见面）**：`:13` 的页数改成运行时推导——由页面自报的
    「全部能力 N」除以首屏实际渲染的卡片数（就是每页条数）得出，不再写死；`:11` 改成**翻页找到**
    `搜索知识库`（翻页上限＝推导出的页数）而不是假设它在第 1 页；`:20` 起"点『知识库』tab ⇒ `数学计算`
    不出现 ⇒ 点卡片看示例问法"那段原样保留，分组仍是判据。演示工具继续算公开能力面的一部分。
    对照组：`agent-operations.spec.ts:62` 的 `第 1 / 2 页` **不动**——那个页面走 `mockAgentApis(page)`，
    条数由 mock 定，写死是对的；差别就在"读活注册表"与"读 mock"。
    本地活栈复测：改前 `tools.spec.ts:11` 在活栈上以同一条报错红（与 CI 同形），改后该 spec 2 条全绿。
    **诚实边界**：① runner 侧要等下一次 push 的 e2e run，"CI 拓扑也绿"才算实测
    ——**第一百一十五批·补证跟进**：那"下一次 push"已经到了（`9a5b27da`，E2E run `38399840606`），但
    runner 判据**仍然没拿到**，因为那条 run 在 `Install Python dependencies`（`e2e.yml:211-213`）上被
    `e2e.yml:165` 的 `timeout-minutes: 20` 取消（12:46:57→13:07:16＝20m19 s），一个字节的用例都没执行；
    所以"CI 拓扑（30 条／5 页）下推导式页数绿"这一条**至今未实测**，本项的 ✅ 只到"改后在活栈拓扑上绿"；
    ② `e2e/` 不在任何
    tsconfig 的 `include` 里（`tsconfig.app.json:19` 只收 `src/**`），`npm run lint` 只跑 `src`，
    CI 的 `npm run build`（`vue-tsc -b`）同样不覆盖 ⇒ 用例的 TS 类型**没有门**，本轮的"过"只到
    "Playwright 真跑过"为止；③ 没有新增静态门禁——要机器化就得判"这个 spec 读的是活注册表还是 mock"，
    那是代理指标，按书面人工检查登记。
- [ ] **`--index-url` 钉在锁文件里 ⇒ 一个外部镜像的限流就能把 CI 与 e2e 两条轨同时卡死**（第一百一十五批·补证取证，未处置，**待拍板**）——
  取证（2026-10-13 一天内同形两轮）：CI run `38395206325`（commit `ad8eb2b0`）九绿二红，红的两个 job 各只红一步——
  `eval-offline :: Install dependencies`（12:09:26→12:52:45）与 `java :: Start Python AI service (smoke target)`
  （12:12:38→12:53:01），两条日志死在**同一个 URL**：
  `https://mirrors.aliyun.com/pypi/packages/3c/2c/c43c03eaf630435f023f1dc61ec4a4a78951ad5530a62c71cc89bde307b7/pypdf-6.19.0-py3-none-any.whl`，
  `ReadTimeoutError(... host='mirrors.aliyun.com', port=443): Read timed out. (read timeout=15)` 重试 5 次（`total=4→0`）后
  `error: connection-timeout` 退出码 1；同一阶段的带宽是 numpy 16.9 MB **68.0 kB/s 用 9m21 s**、pyarrow 50.1 MB
  **95.7 kB/s 用 8m41 s** ⇒ 那 44 分钟几乎全在下载，不是测试跑不完。
  对照（同一 run，判据是"读不读锁"）：`python-lint` 13 s、`docker-compose-validate` 10 s、`static-consistency` 11 s、
  `gitleaks` 12 s、`helm` 14 s、`frontend` 33 s 全绿——这些步骤不装锁里的包（`ci.yml:146` 的 `pip install ruff==0.16.3`
  走的是默认 index）；装锁的四个 job（`python`／`python-container`／`eval-offline`／`java` 的 smoke）全部被拖长，
  其中 `python` 在 12:52:50 侥幸装完转绿，另两个在同一个 wheel 上红。
  钉在哪：`python-ai/requirements.txt:12` 与 `python-ai/requirements-dev.txt:12-13` 的
  `--index-url https://mirrors.aliyun.com/pypi/simple/`（＋`--trusted-host`）——pip 会执行 requirements 文件里的选项行，
  所以 `ci.yml:168/196/248/366`、`e2e.yml:61/213`、`eval-nightly.yml:76/168`、`plugin-security.yml:24/136/165` 这 8 处安装
  全都走同一个源；仓库里**没有**任何 `--timeout`／`--retries`／`--extra-index-url`／`PIP_DEFAULT_TIMEOUT` 配置
  （`grep -rn "PIP_DEFAULT_TIMEOUT|extra-index-url|--retries" .github/workflows docker scripts/ci python-ai/requirements*.txt` 为空），
  于是韧性只剩 pip 默认的 15 s 读超时 × 5 次重试。
  e2e 轨的代价更直接：`e2e.yml:165` 给 `e2e-full` 设了 `timeout-minutes: 20`，装依赖一慢就被整 job 取消——
  当天 `9a5b27da`（第一百一十五批本体）的 E2E run `38399840606` 12:46:57→13:07:16（20m19 s）停在同一步，
  **一个用例都没跑**，所以第一百一十五批的 runner 判据（30 条拓扑下推导式页数＝5 页、`tools.spec.ts` 转绿）
  与 `demo-data` 竞态的第 4 个数据点**同时没拿到**；`ci.yml` 通篇不设 `timeout-minutes`，所以 CI 只是慢到 44 分钟、不被取消。
  **后续读数（第一百一十七批）**：同日 `0305bc25`（第一百一十六批本体）的 E2E run `38524739182` **过了**——
  `e2e-full` 06:51:59→07:11:29＝**19m30 s**，`61 passed / 2 flaky / 10 skipped`，`tools.spec` 在整份日志零命中，
  上面那两格（115 的 runner 判据、`demo-data.spec.ts:40`／`:71` 的第 4 个数据点）就此补上。
  但这不是"问题消失了"：装依赖那一步自己就吃到 07:07:14（≈15m15 s），**整个 job 离 20 分钟上限只剩约 30 秒**，
  同一条慢源波形再抖一档就会回到七条 `cancelled` 的那个形态；所以本条的严重度口径不变，
  候选 B／C 仍**待拍板**，只是"证据通道断了"从"必然"改成了"擦线"。
  **再一条读数（第一百一十八批）**：同日 `487e435c`（第一百一十七批本体）的 E2E run `38530095482`
  `e2e-full` 07:42:35Z→07:56:02Z＝**13m27 s**，其中装依赖约 6 min，跑完且给出用例级读数
  （`61 expected / 2 unexpected / 10 skipped`）⇒ 上一条的"擦线／只剩 30 秒"是**把 15m15 s 那一轮当成了基线**，
  实测这三条同 commit 集群的装依赖耗时是 6 min／15m15 s 两档，即慢源呈**波形**；上限本身没解除，
  抖到高位的轮次仍会整轨失明，候选 B／C 的优先级按"波形的高档"而不是"平均耗时"评估。
  **第三条读数＋口径统一（第一百一十九批）**：`15e93920`（第一百一十八批本体）的 E2E run `38568478864`
  `e2e-full` 13:02:13Z→13:14:07Z＝**11m54 s**、装依赖 423 s、套件 163 s、`63 passed / 0 unexpected /
  0 flaky / 10 skipped`。同时把上面两条旧数放到**同一把尺子**下核过（尺子＝`##[group]Run pip install -r
  requirements.txt` 到下一个步骤 group 的差，即 pip 步骤自身）：`38524739182` 的 **15m15 s 没有错，
  只是边界不同**——那是 job 起点→装依赖结束（06:51:59→07:07:14＝整 15m15 s），pip-only 是
  **876 s＝14m36 s**，差在前面 40 秒 setup；`38530095482` 的"约 **6 min**"则两种边界都对不上
  （pip-only **459 s＝7m39 s**，job 起点→装依赖结束 07:42:35→07:50:50＝**8m15 s**）
  ⇒ 那条是没量过的估值，就地按 459 s 改。⇒ 三档振幅 876／459／423 s，本条判据不变：**高档仍会整轨失明**。
  "余量约 30 秒"那条仍然成立（它按 job 总耗时 19m30 s 对 20 分钟上限算，与装依赖占多少无关），
  被修正的只是拆分口径。
  **第四条读数（第一百二十批）**：`b904efbe`（第一百一十九批本体）的 E2E run `38574242376` 的 `e2e-full`
  13:43:50Z→13:56:43Z＝**12m53 s**、pip-only **465 s**（13:44:51→13:52:35）、套件 **148 s**（13:54:08→13:56:36）、
  `63 expected / 0 unexpected / 0 flaky / 10 skipped`，attempt 级 73 行里 **`retry>0`＝0 行**；同 commit 的 CI run
  `38574242324` 十一 job 全绿 **13m42 s**（13:43:47Z→13:57:29Z）。⇒ 四档振幅 876／459／423／465 s：
  459 与 465 同档，说明**低档不是只出现一次的巧合**，而高档那轮（876 s）仍把余量压到约 30 s——本条判据不变，
  候选 B／C 仍按"波形的高档"评估。
  **第五条读数（第一百二十一批）**：`f97fd471`（第一百二十批本体）的 E2E run `38577643030` 的 `e2e-full`
  job 窗口 14:07:01Z→14:20:12Z＝**13m11 s**、pip-only **491.7 s ≈ 492 s**（`##[group]Run pip install
  -r requirements.txt` 14:07:50.476 → 下一个 group `Run python -m app.main &` 14:16:02.131）、
  套件 **162.7 s ≈ 163 s**（14:17:24.068→14:20:06.757，与 `stats.duration` 161694 ms 一致）、
  `63 expected / 0 unexpected / 0 flaky / 10 skipped`，attempt 级 73 行里 **`retry>0`＝0 行**（连续第三轮）；
  同 commit 的 CI run `38577643015` 十一 job 全绿 **12m54 s**（14:06:58Z→14:19:52Z）。
  ⇒ 五档振幅 876／459／423／465／492 s：这一条把上一条"459 与 465 同档"的**上沿抬到 492 s**，
  也就是低档内部还有约 70 s 抖动、它不是一个固定值；本轮按 job 总耗时算的余量是 **≈6m49 s**
  （比上一轮 ≈7m07 s 更少）⇒ **"落在低档"不等于"离上限安全"**，坏情况仍按历史最高档 876 s（约 30 s 余量）算，
  候选 B／C 的排序不变。上一条那句"低档不是只出现一次的巧合"是写作当时的区间，**但"这一档＝423～492 s"作为
  现行默认档已被第一百二十三批推翻（见下面三条读数），历史四条读数本身不改写**。
  **第六／七／八条读数（第一百二十三批——并发条件第一次可量，且本轮否掉了我自己的假设；**
  **括号里这两句已被第一百二十四批推翻，见本段末尾的纠正与第九条读数**）**：
  连续三笔 docs-only push 各自触发的 `e2e-full`：`38730439786`（`fe057e7b`）job 11:52:28Z→12:08:27Z＝**15m59 s**、
  pip-only **655.938 s**（11:53:14.360→12:04:10.289）、套件 **165.07 s**；`38731555698`（`f9449ee9`）job
  12:01:37Z→12:16:34Z＝**14m57 s**、pip-only **606.508 s**（12:02:19.994→12:12:26.503）、套件 **160.97 s**；
  `38735220260`（`9d6e52a5`）job 12:30:57Z→12:45:16Z＝**14m19 s**、pip-only **563.546 s**
  （12:31:48.090→12:41:11.629）、套件 **163.61 s**。三条都是 `63 expected / 0 unexpected / 0 flaky / 10 skipped`，
  attempt 级各摊平 73 行、**`retry>0`＝0 行**（从 `38568478864` 起连续第六轮）。
  两条 pip 窗口的**实际重叠只有 110.3 s**（＝前者的 16.8%、后者的 18.2%），第三条与谁都不重叠——它的 pip 窗口起点
  比上一条的终点晚 **19m22 s**（12:31:48.090 − 12:12:26.503）。⇒ 我原先写的"并发会抬高振幅"**不成立**：
  最慢的一条重叠占比并不最高，而**零重叠的对照组 563.5 s
  已经高于旧低档上沿 492 s**，这轮的抬高不需要并发就能解释；n＝3、重叠比 16.8／18.2／0% 也分不开这个自变量。
  **（第一百二十四批就地纠正：上面这段里"第三条与谁都不重叠"和"不需要并发就能解释"都不成立——那个 0 s 只比了
  `e2e-full` 对 `e2e-full`。把观察面换成"同一笔 push 触发的两条 run 里所有 pip 步骤"之后，第三条的 pip 窗口与
  同批 CI 侧 `python`／`python-container`／`eval-offline` 三条安装**重叠 563.5 s＝100%**、与 `java` 重叠 456.3 s＝81%，
  五笔 push 全是这个形态 ⇒ 并发从来没被当成自变量操作过，"并发假设被否"这句**一并作废**，正确判定是**不可测**；
  读数与配方见 `docs/CI_GATES.md` 第一百二十四批那段和本条下面的第九条读数。）**

  本条能钉住的只有：**八个点现在是 876 s（1 条）＋563～656 s（连续 3 条）＋423～492 s（早期 4 条）**，
  "低档"这个说法作为现行区间作废；风险口径照旧按 876 s 算（本轮最慢 655.938 s 若换成 876 s，那条 job＝959 s＋220.06 s
  ≈ 1179 s＝约 **19m39 s**，余量约 **21 s**），**候选 B／C 的排序不变**。要真判并发效应，得等重叠比拉得开的样本（一条 0%、一条 ≥80%）。
  **第九条读数（第一百二十四批）**：`1a5e0452`（第一百二十三批本体）的 E2E run `38742412892`
  `e2e-full` job 13:24:27Z→13:39:41Z＝**914 s＝15m14 s**、pip-only **616.407 s**（13:25:13.115→13:35:29.521）、
  `Install frontend dependencies` **5.209 s**、套件 **157.089 s**（13:36:57.02→13:39:34.11，`stats.duration` 155999.745 ms）、
  `63 expected / 0 unexpected / 0 flaky / 10 skipped`，attempt 级 73 行里 **`retry>0`＝0 行**（从 `38568478864` 起连续第七轮）；
  同 commit 的 CI run `38742412916` 十一 job 全绿 **17m11 s**（13:24:24Z→13:41:35Z），`gitleaks` 逐 job 数到**第八轮**
  （八个 run `38530095463`／`38568479058`／`38574242324`／`38577643015`／`38730439984`／`38731555673`／`38735220128`／`38742412916`
  的 `gitleaks` job 8/8 `success`）。九个点的分布＝876×1＋563～656×4＋423～492×4。
  本轮余量按 job 总耗时是 **286 s≈4m46 s**；坏情况仍按 876 s 换掉 616.407 s 算＝914＋259.593≈**1173.6 s＝19m34 s**、余量约 **26 s**。
  **这条读数的真正净新增是两条"解释被排除"，不是又一个振幅点**：
  ① **并发不可测**——把观察面从 e2e 轨内部换成"这笔 push 的两条 run 里全部 pip 步骤"之后，五笔 push 的每一条
  `e2e-full` pip 窗口都与同批 CI 的 `python`／`python-container`／`eval-offline` 三条安装**重叠 100%**、与 `java` 重叠
  **76.3～81.5%**（`python-lint` 的 ruff 只 1.6～1.9 s，永不落进窗口），含自身合计**五路安装流打同一个镜像**，
  而 `f97fd471` 那轮负载相同（100%／80.7%）pip-only 却只有 491.654 s ⇒ 振幅不是这五路造成的，
  **要判并发效应必须先让负载差开**（加 `concurrency:` 或单轨 `workflow_dispatch`）；这是 workflow 结构改动，**待拍板**。
  ② **pip 缓存不是解释**——`actions/setup-python@v5` 的 `cache: pip` 在两条轨都报
  `Cache restored from key: setup-python-...-pip-bda709e7…`，但同一步只复用**固定四个 wheel**
  （`faiss_cpu-1.14.3` 18.5 MB＋`uvloop-0.23.0` 4.0 MB＋`pypdf-6.19.0` 395 kB＋`urllib3-2.8.0` 135 kB＝**23.0 MB**），
  其余 `e2e-full` 重下 **72 包／107.4 MB**、`python` 重下 **97 包／121.8 MB** ⇒ 覆盖率按体积 ≈16～18%，
  **单个 pyarrow（50.1 MB）＝缓存全部内容的 2.2 倍**，所以档位差在结构上不可能来自缓存。
  ③ 时间的去处＝带宽：pip 步骤里 ≥20 s 的下载间隔合计占步骤 **74.3～81.4%**
  （本轮 `e2e-full` 501.5/616.407 s、`python` 545.1/708.759 s、`9d6e52a5` 的 `python` 498.5/655.467 s、
  低档那轮 `e2e-full` 365.1/491.654 s），被点名的就是同七八个 ≥4.7 MB 的 wheel，速率全在 **163～273 kB/s**。
  ⇒ 对本条处置口径的影响：**候选 B（`--timeout 60 --retries 10`）治不到这种形态**（它治超时与重试，这里没有超时发生，
  每段都在稳定慢速传输），B 的优先级应按"针对 connection-timeout 那两条历史红"而不是"针对本轮这种慢"来评估；
  能治的是 **C（换 index）**与"把大 wheel 移出每轮必装面"（后者还没登记为候选，需要先量化哪些包在产品依赖面里）。
  新出现的**候选 D＝在 runner 上加 `pip cache dir/info/list` 取证步**，只为把②的"为什么只复用四个包"钉死，
  不改变本条严重度，**待拍板**。
  **第十条读数（第一百二十五批）**：`c26703ef`（第一百二十四批本体）的 E2E run `38889773599`
  `e2e-full` job 10:49:42Z→11:00:13Z＝**631 s＝10m31 s**、pip-only **338.152 s**（10:50:23.797→10:56:01.949）、
  `npm ci` **5.281 s**、`npx playwright install` **19.732 s**、套件 **163.740 s**（`stats.duration` 162804.692 ms）、
  `63/0/0/10`、attempt 级 73 行 **`retry>0`＝0 行**；同 commit 的 CI run `38889773590` 十一 job 全绿 **10m48 s**，
  `gitleaks` 逐 job 数到**第九轮**（九条 run 9/9 `success`，序列加本轮 `38889773590`）。
  **十个点＝876×1＋563～656×4＋423～492×4＋338.152×1 ⇒ 这是一条 338～876 s 的连续谱，任何"档"都只是分箱**；
  本轮余量按 job 总耗时 **569 s≈9m29 s**，坏情况仍按 876 s 换掉 338.152 s 算＝631＋537.848≈**1168.8 s＝19m29 s**、
  余量约 **31 s** ⇒ "落在低点"照样不等于安全，**候选 B／C／D 排序不变**。本条读数的净新增是三件事：
  ④ **轮次级共同因子第一次有数**——同一笔 push 里三台 CI runner（`python`／`python-container`／`eval-offline`，
  各自独立 VM）装同一份 `requirements-dev.txt` 的窗口极差只有 **0.60～10.59%**（六轮里**三轮 ≤0.94%**、另两轮 4.6／5.3%、
  只有 `f97fd471` 那轮到 10.6%），
  而**跨轮**这三条的均值从 400.2 s 摆到 747.1 s（347 s）；e2e 的 pip-only 与同批 `python` 六轮相关系数 **0.997**、
  比值 **1.119～1.201**（体积比就是 121.8/107.4＝1.13）⇒ 快慢由"哪一轮"决定，不由"哪台 runner／哪条轨"决定，
  这把**候选 B 的作用面进一步压小**（它治单条流的超时与重试，治不到"整轮一起慢"）。
  ⑤ **候选 D 的问题从"为什么只复用四个包"变成可执行的探针**——本轮第一次读到 Post 步骤：四个 python job 全打印
  同一 key ＋ 同一 `Cache Size: ~146 MB (152908538 B)` ＋ `Cache restored successfully`，而 Post 一律是
  `Cache hit occurred on the primary key …, not saving cache.` ⇒ 只要 `python-ai/requirements.txt` 不变
  （最后改动 2026-10-11 `06ea5607`）这个条目**永不更新**＝**冻结快照**（跨 `f97fd471`→`c26703ef` 六轮字节数逐位相同；
  同一条 runner 上 maven `~136 MB (142672703 B)` 与 npm `~47 MB (49310164 B)` 两条同形态，故上一批"配额驱逐"那条候选也一并排除），
  **（第一百二十六批就地撤回这半句：`…-pip-cdb57277…`（152584972 B）是 10-11 那次保存 restore 的前一个 key，
  今天在仓库缓存列表的 385 条里**已不存在** ⇒ 驱逐发生过；总量 9.93 GB 里 buildkit 层占 9.34 GB＝94%，见下面第十一条读数②。）**
  于是上面②那句候选"保存步骤没写成功"改判为**"根本没尝试保存"**，矛盾精确成：**恢复 146 MB、pip 只认 23.0 MB（15.8%）、
  其余 107.4/121.8 MB 重新下载**。而**恢复不是成本项**：`Cache hit for:`（10:50:19.246）→
  `Received 152908538 of 152908538 (100.0%), **87.5 MBs/sec**`（10:50:21.120）→ `tar -xf`（10:50:21.134）→
  `Cache restored successfully`（10:50:21.290）＝**146 MB 拉＋解 2.04 s**；同一条 job 上 pip 从
  `mirrors.aliyun.com` 拉 107.4 MB 用 **338.152 s**（≈0.32 MB/s）⇒ **同一台 runner 上缓存通道比 index 通道快约 270 倍**
  （边界：这只证明慢的是 index 那条通道、不是 runner 的盘或出口；且缓存这条只有命中才走得到，要让那 123 MB 命中得先付一次上传，
  而这六轮的 Post 全是 `not saving cache`、从没付过 ⇒ 上传成本无读数）。
  上一批的两种解释也削掉一种：`pip cache dir` 是 setup-python 自己调的（10:50:17.579 → `/home/runner/.cache/pip`，
  10:50:19.004）再往里恢复 ⇒ "恢复目录不是 pip 查找目录"在路径层面不成立，只剩"快照里的 wheel 与今天这 72 个包不是同一批"
  （探针＝`du -sh /home/runner/.cache/pip`＋`pip cache list/info`＋与本轮 72 个下载包名做集合差）。**仍待拍板。**
  **（第一百二十六批：这条"只剩"也被否掉了**——集合差用只读通道做完了（写手那次 run 的 99 个下载包名 vs 本轮 72 个＝
  **70 条同名／97.2%**，只有 2 条版本漂移），问题精确成"**同名同版本为什么等于没命中**"；同时镜像侧实测**答 304**
  ⇒ "过期就得整包重下"这条也排除。详见下面第十一条读数③④与本批 ①～⑤。）**
  ⑥ **上一条①那句"与 `java` 重叠 76.3～81.5%、含自身合计五路安装流"要就地收窄**：`ci.yml:361-375` 那个 step
  （名叫 `Start Python AI service (smoke target)`）是**复合步骤**——`pip install -r requirements.txt -q` ＋ `nohup uvicorn`
  ＋ 60 次 curl 轮询，而 `-q` 让 pip 一行都不输出 ⇒ 它的安装时长**结构性不可测**，那个百分比是拿复合步骤当分母算的。
  本轮该 step 357.590 s（10:52:31.082→10:58:28.672，中间唯一可读行是 10:58:28.661 `…healthy (attempt 4)`），
  它与 e2e pip 窗口的重叠只能给界 **0～210.9 s**。⇒ 可测的并发安装流是 **4 条**（3 条 CI＋e2e 自身）而不是 5 条，
  但"三条 100% 覆盖"照旧支撑**并发不可测**这个判定，本条严重度与候选排序不变；要让 `java` 那条可测，得拆步骤或去掉
  `-q`＝**改 workflow，待拍板**。
  **第十一条读数（第一百二十六批——候选 D 用只读通道跑完，`.github/workflows/` 未动）**：
  ① **写手与上传成本第一次有数**——`GET /repos/…/actions/caches`（分页 385 条）里 pip 家族**只剩 1 条**
  `…-pip-bda709e7…`／`size_in_bytes` **152908538**／`created_at` **2026-10-11T14:48:53.064538Z**，那毫秒对应 CI run
  **`38145150155`（`06ea5607`）的 `eval-offline` job 114486827675**：三个 restore 过缓存的 job 里**只有它**打印 `Cache saved with the key`，
  保存跨度 `[command]/usr/bin/tar --posix -cf cache.tzst`（14:48:51.6727531）→`Cache saved`（14:48:53.0989797）＝**1.426 s**
  （自 `Post job cleanup` 起算 1.578 s）、自报 **174.2 MB/s** ⇒ 上一批"上传成本没有读数"这半句被补上：付过一次，很便宜。
  ② **配额驱逐这条候选回来了**：那次保存 restore 的是**前一个 key** `…-pip-cdb57277…`（152584972 B），它**不在今天的列表里**
  ⇒ 删过；面上 **9.93 GB** 总量中 `index-buildkit-*` **379 条／9.34 GB＝94.0%**，pip＋maven＋npm＋gitleaks 四条工具缓存共
  **0.593 GB＝6.0%**，`last_accessed_at == created_at`（写过没读过）**294 条／8.67 GB＝87.3%**，最老条目只剩六天
  （2026-10-10T05:00:03Z）⇒ 上一批"若是驱逐 key 不会恒命中"把"当前条目稳定"当成了"从未驱逐"。**"仓库级 10 GB 上限"这个数字是
  平台文档口径、本仓未取证**，量到的只有形态。
  **（第一百二十七批就地收窄这句：驱逐确实发生过，但机制量出来是**严格 LRU**、对象**只有 buildkit 层**——第二份快照里
  消失的 15 条 15/15 是 buildkit（被删里最新那条的 `last_accessed_at` 与幸存里最旧那条只差 **0.598 s**、零逆序、
  "还更旧却仍幸存"＝0 条），而 pip 那条每轮被四个 job 读、时间戳每轮刷新 ⇒ **它结构上是最后被剪的一批**，
  "下一个被驱逐的可能是 maven 或这条 pip 条目"不成立；详见下面第十二条读数①。）**
  ③ **"名单不是同一批"被否**：写手那次 run 的 99 个 `Downloading` 包名 vs 本轮 `e2e-full` 的 72 个 ⇒ **同名 70 条＝97.2%**、
  版本漂移 2 条（`cryptography-50.0.0`、`grpcio-1.83.1`）、快照侧多 29 条；本轮 4 条 `Using cached` 里 `faiss_cpu`／`uvloop`
  **不在 10-11 名单**（比这次保存更早就在目录里），反倒是唯二被复用的大件——这个反差没解释。**口径**：这是"下载名单 vs 下载名单"，
  不是归档内容枚举，够否掉"不相交"、不够断言"body 就在恢复出来的目录里"。
  ③b **新矛盾（未取证）**：条目只比它 restore 的那份大 **323,566 B＝0.21%**，而同一次运行带体积标注的 11 条下载合计 **110.6 MB**
  ⇒ "新下载的东西进了被归档的那份目录"这个模型对不上（`size_in_bytes` 是 tzst 后的量，可 wheel 本身已压缩，0.3 MB 不像压缩率）。
  ④ **镜像侧不存在"过期就得整包重下"这堵墙**：本机 `curl -s -o NUL -D -` 实测（2026-10-16 13:05Z）——
  index `simple/urllib3/` 与 wheel `urllib3-2.8.0-py3-none-any.whl` 都回 `Cache-Control: max-age=43200`，index 无 `ETag`
  但带 `Last-Modified`，两者**带 `If-Modified-Since` 的条件请求都答 304**（wheel 另有 `ETag: "6aa99c9e-21225"`）
  ⇒ pip 在 12 h 之后本可靠条件请求复用旧 body，"过期"不能解释③那 70 条整包重下；**边界**：读数来自本机到镜像 CDN 边缘，
  runner 落哪个边缘未知，pip 实际请求形态（`Range`／头集合）未量，所以这张表只否"镜像不支持条件请求"，不撑"pip 应该能命中"。
  ⑤ **候选 D 降级＋新登记候选 E**：D 从"待开的取证步"降成"**只差 runner 侧两行**"（恢复后 `pip cache list` 条数＋`du -sh`，
  再来一次 `pip install -vv` 看有没有 `Reusing / Cached response`）；**E＝buildkit 层缓存的保留期／清理**（`gh api -X DELETE`
  是写操作，本批未执行，**待拍板**）。E 附带一条可证伪预测：既然那 146 MB 对 107.4 MB 的下载几乎没帮忙，
  **pip 条目被驱逐之后 pip-only 时长应仍落在 338～876 s 这条谱上**；若冒出新的高档，③就要重开。
  **（第一百二十七批：这条预测短期不可用**——LRU 判出来 pip 那条是最不该被剪的，等不到它被驱逐；同时 E 的理由要换，
  不再是"顶到上限会误伤工具缓存"，而是 **94.3% 字节属 buildkit、其中 87.9% 写过再没被读过**＝清理收益面。见下面第十二条读数①②。）**
  ⇒ **本条严重度、风险口径与候选排序不变**：坏情况仍按 876 s 算＝**19m29 s／余量约 31 s**；**B／C／D／E 全部待拍板**。

  **第十二条读数（第一百二十七批——第二份缓存快照＋第十一轮 run，全程只读，`.github/workflows/` 未动）**：
  ① **驱逐机制第一次量得出来，且它剪不到工具缓存**：两次快照（12:13Z→13:54Z，1 h 41 m）之间
  **385→397 条／9.93→10.37 GB（净＋466,060,649 B）**，消失 **15 条 15/15 全是 buildkit**（`created_at` 全为 10-13、
  `last_accessed_at` 距今 3.00～3.03 天），新增 27 条也全是 buildkit。LRU 结构检验：被删里最新的 accessed
  `2026-10-13T13:52:33.717360Z` vs 幸存里最旧的 `13:52:34.315094Z`＝**差 0.598 s、零逆序**，"还更旧却仍幸存"＝**0 条**；
  按 accessed 从新到旧累加，越过 10 GB 的落点是一条 buildkit（154.1 MB）⇒ **四条工具缓存全在切点之内**，
  而 pip 那条每轮被四个 job 读、`last_accessed_at` 从 12:09:03 刷到 13:48:46 ⇒ 它是 LRU 下**最后**被剪的那一批。
  ⇒ 上一条④E 那条"pip 条目被驱逐后"的预测**短期不可用**；③b 那个矛盾的成因里"被配额剪过"这一项**摘除**。
  ② **"贴顶"这个口径撤回**：本仓已**越过** 10 GB 这个文档口径（10.37 GB）**而条目仍在净增** ⇒ 形态是"写入时按 LRU 剪旧、
  总量可超文档口径"，不是"贴顶就停"；写过没被读的比例 **294 条／87.3% → 305 条／87.9%**，收益面照旧全在 buildkit。
  ③ **第十一轮 run（CI `38910654094`／E2E `38910654163`，两条 `success`）pip-only 第 11 个点＝440.914 s**，
  仍落在 338～876 s 谱内（谱没变长）；同轮 CI 三条 515.989／518.198／518.560 s（极差 **0.50%**、连续第四轮 ≤1%），
  e2e 那 440.9 s 与三条**逐条 100.0% 重叠**（第六轮同形）⇒ **并发照旧不可测**；e2e 本轮恢复 **344.9 MB**
  （maven 142.7＋pip 152.9＋npm 49.3）仍重下 **98.4 MB／440.9 s**，③b 的矛盾没变软。
  ④ **包级吞吐是本批最硬的新增**：同名 wheel 在**四台独立 runner**上耗时几乎相同——
  `pyarrow` 187.0／186.2／187.2／186.0 s（极差 **0.7%**）、`numpy` 62.3／62.2／62.3／64.2、`pandas` 43.3／43.4／43.8／43.8、
  `lxml` 17.8／17.6／17.6／18.8、`pydantic_core` 7.4／7.4／7.4／7.8，自报吞吐全在 **257～295 kB/s** 窄带；
  ≥20 s 间隔占比 e2e **72.2%**、CI 68.5／68.2／69.0%。后果两条：上一批的"轮次级共同因子"**下沉到包级**
  （不是"一轮一个系数平移四条通道"，而是每只大包自己恒定）；**"某台 runner 被邻居挤"这个图景被排除**
  （若成立同名 wheel 只会在它那一份变慢）。多倍差异只剩 **20 只 ≤5 s 的小包**（成本在 index 往返不在体积）
  ⇒ **B（加超时重试）治不到这种慢**这条判定**更硬**了。尺子：间隔归给**该行自己**那只包、末条 `Downloading` 到
  `Installing collected packages` 的间隔也归它——第一版脚本归给了后一条，把 pyarrow 读成 46.7 s，已纠正。
  ⑤ **新登记：e2e 轨上一条 60 秒的固定成本（机制未取证，待拍板）**——手上 **9 份** `e2e-results-full` 工件（8 轮 runner＋1 轮本机）
  里 `document-lifecycle.spec.ts :: restore document makes it visible again` ＝
  60.420／60.048／60.470／60.134／60.466／60.016／60.304／60.005／60.143 s（**9/9 全在 60.0～60.5**、极差 0.77%），
  占该轮 e2e 墙钟 **36.6～40.8%**（本轮 60.1／148.0 s）。同文件用同一个 `pollRecycleBinHasDoc` 的姊妹用例
  在同样 9 份里是 **12.6～25.7 s** ⇒ **这 60 秒不是"等回收站可见"**；`pollDocIndexing` 的 60 s 默认值（`helpers.ts:306`）
  不在该用例路径上，Java 侧精确 60 s 的两个定时器与文档链路无关，删除任务调度器是 30 s（`DeletionTaskScheduler.java:28`）
  ⇒ **只登记读数、不写死因**（Playwright JSON 只有用例级 `duration`，落点未定位）。它记在本条名下是因为：这是该轨**唯一一条
  与缓存／镜像／并发无关**的固定开销，B／C／D／E 任何一条落地都碰不到它，而它一条＝本条那 31 s 余量的一倍。
  处置候选 **A＝先拆段定位**／**B＝挪出主轨**／**C＝只登记**，**待拍板**。
  **（第一百二十八批：A 已执行，落点与死因量到了——不是常量，是**两条删除腿各跨一个 30 s 调度 tick＋用例自锁相**；
  上面那句"这 60 秒不是等回收站可见"与"固定成本／常量"两处口径**就地收回**，读数与处置候选见本条末尾的第一百二十八批段。）**
  ⑥ 链：CI 十一 job 全绿 **14m42s**、`gitleaks` 逐 job 数到第十轮；E2E `e2e-full` success **12m11s**、
  `63/0/0/10`、attempt 级摊平 73 行 `retry>0`＝**0 行**（连续第十轮）。
  ⇒ **本条严重度、风险口径与候选排序不变**：坏情况仍按 876 s＝**19m29 s／余量约 31 s**；
  **B／C／D／E 与⑤的 A／B／C 全部待拍板**，本批**未执行任何写操作**（无 DELETE、无 workflow 改动）。

  第一百二十八批（⑤ 的 60 秒定位完成，＋一个新登记的 java 侧标签缺陷；全表见 `docs/CI_GATES.md` 该批段）：
  用户拍板 A＝拆段定位，在**活栈**上（dev compose 八台全 healthy）用一个**临时未提交、跑完即删**的探针 spec 逐段计时，
  另加一个按秒采样脚本分开量"库里那一行何时翻"与"回收站接口何时看得见"。**死因**：
  `DeletionTaskScheduler.java:28` 的 `@Scheduled(fixedDelay = 30_000)` 是那个 30 秒周期的来源；一条
  "删除→回收站可见"的腿必须等下一个 tick 去跑 `DeletionServiceImpl.java:381-393`（step 3 `markRecycled`）把
  `document.deleted` 翻成 1，因为查询侧要求 `d.deleted = 1`（`DocumentMapper.java:69`／`:78`），而
  `DocumentServiceImpl.java:291-297` 的 `delete()` 只同步写 `status=DELETING`、不碰 `deleted`。
  **为什么恰好是 60 而不是 0～60 的散布**：这条用例的每次 poll 都在 tick 上返回，随后的 restore＋get＋delete 只花
  0.17～0.80 s ⇒ 下一次删除仍落在"刚过 tick"处 ⇒ **两腿各等满一个整周期**，锁相自维持（连上一条用例的 poll 结束点也算在内）。
  实测三条 poll 收在 **03:58:00.018／03:58:30.025／03:59:00.123**，两腿 **29.564／29.928 s**。
  可证伪点都验掉了：单独跑该用例＝**44～45 s**（12.2＋30.3，两轮），按文件顺序跑（姊妹条在前）＝**60.7 s**，
  runner 13 轮＝**60.0～60.5 s**；本机有 Milvus＋worker、runner 两者皆无而同带 ⇒ 结论只挂在代码常量上。
  采样还排掉两个借口：回收站请求本身 **0.218～0.229 s**（不是慢查询），python 侧
  `app/core/vectorstore/` 四个实现按 `sleep|timeout|60|retry` grep **零命中**（不是向量库删除在等）。
  **新登记（与 60 秒无关，待拍板）**：DOCUMENT_DELETE 任务的 `step` 对所有成功删除都是 `DOC_NOT_FOUND`、
  且完成日志**一条没有**（实测 108／109／111／112 四条：`COMPLETED / step=DOC_NOT_FOUND / step_index=4 / retry_count=0`；
  两条 PURGE 则是 `step=COMPLETED / step_index=5` 且有日志）。机制＝链跑完 step 3 后 `advanceStep`
  （`DeletionServiceImpl.java:461-466`）把 index 推到 4、状态推回 PENDING，调度器循环（`DeletionTaskScheduler.java:40-45`）
  再进一次 `executeDocumentDeleteStep`，此时文档已被逻辑删除 ⇒ `selectById` 返回 null ⇒ 走 `:356-361` 的 not-found 分支，
  覆盖 `step`、置 COMPLETED，而这条分支**不调 `completeTask`、不打日志**。PURGE 幸免是因为入口用
  `selectIncludingDeleted`（`:400`）。处置 **甲＝让 index==4 的收尾走 `case 4`（或让 not-found 分支也打完成日志）**
  ／**乙＝只登记**／**丙＝顺手处理 `application.yml:124` 的 `python-ai.timeout: 60000`**（本批按 `@Value` 扫全仓 java 侧：
  `python-ai.*` 被读的只有 `internal-token／base-url／callback-secret／engine.url／callback-base-url` 五处，
  `python-ai.timeout` **零消费者** ⇒ 与第一百一十六批 `CALLBACK_SECRET` 空转声明同族）——**均待拍板，本批未动代码**。
  60 秒的处置候选随之更换：**A＝用例侧去掉第二腿**（省 ≈30 s，零生产风险；前提"purge 在 `deleted` 未翻转时幂等"纸面可行、**未实测**）、
  **B＝生产侧把"进回收站"改同步**（省 ≈60 s，但是用户可见的行为变更、且让 `DocumentStatus.DELETING` 中间态失去意义）、
  **C＝缩 tick／事件即时触发**（影响所有删除链，收益不匹配）、**D＝只登记**。**推荐 A**，本批未动任何用例与生产代码。
  风险口径不变（坏情况仍按 876 s＝19m29 s／余量约 31 s），且本条与候选 B／C／D／E 无交集——A 落地最多让 e2e 轨少 30 s。

  第一百二十八批·补证（把上面那句"前提未实测"取到数，顺带量到一条新的不对称；仍只在活栈，未动任何代码／workflow）：
  **① A 的前提被否掉一半**——`delete#2` 后 0.38 s（`status=4／deleted=0`）调 `DELETE /document/{id}/purge` ⇒
  **HTTP 400**、`回收站中不存在该文档`、0.228 s，任务表**没**新增 `DOCUMENT_PURGE` 行。门在 service 入口
  （`DocumentServiceImpl.java:357` 要求 `deleted==1`），`DeletionServiceImpl.java:400` 那条链侧的免疫**走不到**；
  上面"纸面可行"是把链的性质误安到入口上，**就地纠正**。⇒ **A 精确成 A1＝去掉第二次 poll＋purge，只留 `delete#2`＋`apiDeleteKB`
  fire-and-return**（实测卫生面成立：那条 `DOCUMENT_DELETE` 照旧在下个 tick 从 `PENDING/idx=0` 直接跳到 `COMPLETED/idx=4`，
  75 s 内无 `FAILED`、`retry_count` 恒 0，文档与知识库在列表里都不可见，残留是回收站行、7 天由 `RecycleBinCleanupScheduler` 收）。
  **② 新登记的不对称（与 60 秒无关）**：`DELETE /knowledge-base/{id}` 是**同步**的——`KnowledgeBaseServiceImpl.java:219-220`
  在请求里 `markRecycled`，实测 HTTP 200／0.223 s、返回即 `deleted=1`、任务表里**没有任何 KB_DELETE 行**；
  同一个"删除"动词文档侧等 30 s tick、知识库侧 0.2 s 进回收站 ⇒ **B 的性质从"新设计"变成"向仓内既有先例看齐"**。
  **③ 周期有同钟依据、相位本批不能定**：库内两个 `recycled_at` 是 04:18:31／04:19:01＝整 30 s（同一把钟），
  但宿主 Node 钟与 JVM 钟的 skew 未校，所以不能说"格子平移到了 :31/:01"。
  **④ 另一处尺子纠正**：第一百二十八批"按秒采样（doc 242）"那行的 `t+Ns` 是**循环次数不是秒**
  （每轮串行 `docker exec`＋`curl`，实测约 1.5 s／轮），不能用它判"可见先于翻转"；补证探针的时间戳改成现取 `date -u +%T.%3N`。
  待拍板清单不变，只是 **A→A1**、B 的理由变硬：**候选 B／C／D／E、60 秒的 A1／B／C／D、新缺陷的甲／乙／丙**。

  历史面：七条 `cancelled` 的 `e2e-full`（`38135767903`／`38137950016`／`38140336693`／`38145150097`／`38226782059`／
  `38395206533`／`38399840606`）**7/7 停在 `Install Python dependencies`**（取法见上面那条就地纠正），
  也就是说这一轨历史上不是"偶尔"被源拖死，而是**慢源一来就整轨失明**。
  **未处置的原因**：两条候选都要人拍板，不属于"测试卫生"。
  B＝给这 8 处安装加 `--timeout 60 --retries 10`（或 `env: PIP_DEFAULT_TIMEOUT`），index 不变、包版本不变，
  第一百一十四批的 SBOM 组件面门不受影响，但它是 CI 基础设施改动；
  C＝把 `--index-url` 换成 `pypi.org` 或补 `--extra-index-url https://pypi.org/simple`，能根治，
  但改的是被门钉住摘要的锁文件（第九十二批那套冻结基线），且"可复现性来源"本身变了。
  同日同 commit 的第三条读数（补上后一只鞋）：CI run `38399840634`（`9a5b27da`）**success、十一个 job 全绿**，
  但整轮 **36m32 s**（12:46:56→13:23:28），四个装锁的 job 是 `python` 33m26 s／`eval-offline` 32m07 s／
  `python-container` 28m58 s／`java` 36m32 s；源正常时同样四个 job 在 `38388749193` 上是 9m15 s／7m34 s／8m12 s／
  12m33 s ⇒ 慢 **4–5 倍**却一个不红。也就是说同一慢源下，不设上限的 `ci.yml` 只是慢，设了 20 分钟的 `e2e.yml:165`
  直接失明——本条的严重度按"证据通道"计，不按"测试红"计。
  **诚实边界**：①观测覆盖 2026-10-13 约 10:35–13:23 UTC 这一段：10:35 与 11:13 两轮源正常（e2e 全套 73 条 12m09 s 跑完）、
  12:09 那轮源慢到两个 job 红、12:46 那轮源慢 4–5 倍但 CI 全绿而 e2e 被超时取消 ⇒ **呈"退化—半恢复"波形，
  是否已进入常态仍需再量**，本条不写成"源坏了"；
  ②判据来自 runner 日志文本与 job 窗口，没有本地复测带宽；③本条不是"门红"，门（`static-checks.py` 全跑档）仍绿，
  它是**证据通道**的可用性缺陷，所以不并入检查 19/20，单列。
- [ ] **`scripts/*.py` 不在任何 lint 作用域里，`检查 21` 那处密钥形态红只有 runner 侧的 gitleaks 能抓**（第一百一十七批取证，未处置，**待拍板**）——
  `ci.yml:135-148` 的 `python-lint` job 带 `working-directory: python-ai`，命令是 `ruff check .` ⇒ 覆盖面对象是
  `python-ai/` 一棵；仓库根没有 `pyproject.toml`／`ruff.toml`／`setup.cfg`（`ls -a` 只有 `.ruff_cache/`），
  也没有任何 CI 步骤对 `scripts/` 跑 ruff。本轮实测：用 `python-ai/.venv` 里钉住的 ruff 0.16.3 手工扫
  `scripts/static-checks.py` 得 **18 条**（FURB167×8、ISC004×3、SIM114×2、PLW1510×2、RUF059、PIE810、F541），
  HEAD 版与工作区版**同为 18 条** ⇒ 第一百一十七批的改动没新增违规，但也说明这些违规一直存在而无人拦。
  后果是分层缺口：检查 21 的"门的门"（`static-checks.py` ＋ 18 例 pytest）都判不到密钥形态的字面量，
  上一轮正是靠 `gitleaks` 才抓到 `_strong_env_file_fixture()` 写死的那串假值。处置选项：
  A＝在 `ci.yml` 加一步对 `scripts/`（或仓库根）跑 ruff，并处理那 18 条存量；
  B＝把 ruff 的 `--select` 子集并进 `static-checks.py` 的检查里（本地与 CI 同一条命令，无需改 workflow）；
  C＝维持现状，接受 `scripts/` 靠 gitleaks 这类安全门兜、风格与 `PLW1510`（`subprocess.run` 未带 `check=`）无人管。
  三档都是门禁面扩张，**待拍板**。
- [ ] **弱默认值扫描覆盖面只有一个文件；`CALLBACK_SECRET` 在 python 侧是空转声明**（第一百一十六批取证，扫描器本体已修，这两点**未处置、待拍板**）——
  ① **覆盖面**：`scripts/rotate-secrets.sh --check` 只读 `ENV_FILE`（`:30`，默认 `docker/.env`，
  可用 `ROTATE_SECRETS_ENV_FILE` 指到别处，但一次只扫一个文件）。本轮实测三个 env 文件都在仓库工作区
  （`docker/.env`、`deploy/.env`、`python-ai/.env`），而检查 21 的负控输入写死是 `docker/.env.example`
  （`scripts/static-checks.py` 的 `DOCKER_ENV_EXAMPLE`）⇒ `deploy/.env.example:13` 那种
  `replace-with-long-random-token-2` 占位值**至今没有任何门扫它**。处置选项：让检查 21 逐个示例文件跑负控
  （三个 `.env.example` 都在库里，改动只在 python 侧），还是给脚本加多文件参数（改的是运维入口）。**待拍板**。
  ② **空转声明**：`CALLBACK_SECRET` 只有 Java 读——`application.yml:128` →
  `VectorizationServiceImpl.java:725-750` 把它写进发起向量化时的请求体；Python 全程只回显请求体里带来的那把
  钥匙去签名（`app/api/vectorization.py:245`、`:810-820`，透传链 `app/core/tasks/queue.py:39/57`、
  `app/models/document.py:27`），`grep -rn "environ.*CALLBACK_SECRET|getenv.*CALLBACK_SECRET"` 在
  `python-ai/app` **零命中**。⇒ `docker/docker-compose.yml:318`（python-ai）、`:400`（python-ai-worker）
  与 `deploy/docker-compose.prod.yml:236` 注进容器环境的那三行、外加 `python-ai/.env.example:42` 那一条，
  都是没人读的死声明（与第一百零九批 `UPLOAD_DIR` 同形）。删掉＝改 compose  env 面，
  不涉及现有门的判据（检查 18 规则②只钉 redis host＋密码成对，`grep CALLBACK_SECRET` 在
  `scripts/static-checks.py` 零命中）；保留＝每个读 compose 的人都会以为 python 侧也要配这把钥匙。
  **待拍板**。
  本轮已按语义漂移就地纠正、不再另立缺陷号的四处口径：`scripts/rotate-secrets.sh:15` 原写
  「Python → Java 回调 HMAC（两侧一致）」（方向反了，且"两侧各配一份"不成立，现改成单向分发口径并指回本条）；
  `docs/PRODUCTION_OPS.md:18` 的 `PLUGIN_RUNNER_SECRET_KEY` 是全仓零命中的键名（现行 `PLUGIN_RUNNER_TOKEN`，
  Java `application.yml:159` ↔ Python `app/core/plugin/container_runner.py:29`）；
  `docs/PRODUCTION_OPS.md:21` 的 Sa-Token JWT 密钥 `SA_TOKEN_JWT_SECRET_KEY` 同为虚构项
  （`application.yml:89-96` 的 sa-token 段只有 `token-name/timeout/active-timeout/is-concurrent/token-style: uuid/is-log`，
  没有签名密钥可配；`JwtUtils.java` 只是 `StpInterface` 的权限提供者，不读任何密钥），已标作废；
  `docs/PRODUCTION_OPS.md:16` 那句「`--check` 可扫描弱默认值」改成了带退出码与被钉住的完整口径。

- [ ] **演示数据播种直插 mapper，绕开知识库列表缓存的版本递增 ⇒ 刚导入的库最长 300 秒不可见**（第一百一十八批取证，未处置，**待拍板**）——
  `KnowledgeBaseServiceImpl.listByCurrentUser:315-359` 走 B3 热点读缓存：无名称筛选且 `page ≤ 10` 时可缓存，
  命中就直接返回缓存页（`:340-346`），数据键形如 `kb_list:{version}:tenant:t{tenant}:user:{uid}:p{page}:s{pageSize}`，
  版本键 `kb_list:ver:tenant:t{tenant}:user:{uid}`（`HotReadCacheService.java:73-91`），TTL 300 s ±20 % 抖动。
  写侧的四条正规入口都调 `bumpVersionAfterCommit`（`KnowledgeBaseServiceImpl.java:113` 新建、`:180` 更新、
  `:226`、`:270`），**唯独演示播种没有**：`DemoImportServiceImpl.java:316` 是
  `knowledgeBaseMapper.insert(kb)` 直插，不经过 `create()`，版本键因此不动。清除路径反而是对的
  （`:199` 调 `knowledgeBaseService.delete(...)`，会 bump）⇒ 播种与清除不对称。
  活栈取证（2026-10-14，dev compose，Redis/MySQL 长寿命）：`POST /api/demo/import` 于 10:35:56.569 返回
  200、`knowledgeBaseId=127`、「演示知识库／新增 12 项」；同用户 10:35:59.005 的
  `GET /api/knowledge-base/my?page=1&pageSize=9` 仍是 8 条且不含该库，而 MySQL 里 id 127
  `deleted=0, recycled_at IS NULL, status=0, user_id=1` 已落库；Redis 里
  `kb_list:ver:tenant:t1:user:1 = 6`，`kb_list:4/5/6:tenant:t1:user:1:p1:s9` 三份旧页并存。
  **在同一份改后代码上只 `DEL` 那个版本键**（代码一行不再动），之前红的用例 11.1 s 转过 ⇒
  死因是失效，不是权限也不是分页。同一断言在改前代码上也是 3/3 全红（改前 `:48`／改后 `:50`），
  形态与 e2e 的监听顺序无关——这条与第一百一十八批改的是两件事。
  影响面：任何绕过 service 写 KB 的路径都吃这个 TTL 窗口；CI 每轮是新 Redis 所以看不见，
  本地活栈/生产长寿命缓存才现形（这也补上了第一百一十五批"本地那 2 条 e2e 红＝拓扑差未取证"的机制）。
  处置选项，**待拍板**：A＝`DemoImportServiceImpl` 播种后调一次版本递增（把 bump 抽成可复用入口或在
  演示服务里注入 `HotReadCacheService`），改动在 java 侧一处、需要新增 IT/单测把它钉住；
  B＝改成走 `knowledgeBaseService.create(...)` 建库（语义最正，但演示播种要的正是绕过 create 的校验分支，
  改前要先确认 `create()` 会拒绝或改写哪些演示字段）；
  C＝立案不处置，只在文档钉住"演示播种后 5 分钟内列表可能不含新库"这条已知行为。
  本批没有动任何 Java 代码，只在 e2e 侧把监听顺序改对。要说清楚的是：**改后本地那三次绿并不证明这条
  缺陷消失了**——它们发生在我手工 `DEL` 过版本键之后，且期间清除路径本就每次 bump；把这条缓存缺陷
  留着不动，`demo-data.spec.ts:50` 在长寿命栈上仍然是可能红的（命中未过期的旧页就红），只是本轮没撞上。
- [ ] **e2e 那 10 条 skip 在 CI 里是永久的；其中挂在 SSE 旗标下的两条，头注释的归因已失效，实测一条过、一条红在写死的跨源 URL 上**（第一百一十九批取证，未处置，**待拍板**）——
  覆盖面事实（`docs/CI_GATES.md` 检查 20 一节有全表）：`grep -rn "HFUSIONHUB_RUN_SSE_LIVE\|
  HFUSIONHUB_RUN_APPROVAL_LIVE" .github/workflows/` **命中 0**，`HFUSIONHUB_RUN_PLUGIN_LIVE`
  （`plugin.spec.ts:9`）与 `PYTHON_AI_INTERNAL_TOKEN`（`write-note.spec.ts:14/:36`）同样没有任何 workflow 设置
  ⇒ **流式对话、插件安装/卸载、审批活链路、python 内部回调这四条路径 runner 上零 e2e 覆盖**，
  `63 passed / 0 flaky` 证明的是另外 63 条。
  头注释失效：`chat-sse.spec.ts:12-24` 把这 2 条 skip 归因给"`sseTaskExecutor` 是 JDK 21 虚拟线程、
  丢 Sa-Token 上下文 ⇒ 流在首个空事件后终止、没有 `[DONE]`"。而写这段注释的那笔提交 `1ce30072`
  （2026-08-17，提交信息含"SSE 修复"）**自己那一版**的 `ThreadPoolConfig.java:24-37` 就已经是
  `ThreadPoolTaskExecutor`＋`CallerRunsPolicy`，注释也是"不能用虚拟线程执行器"
  ⇒ 注释描述的是修复前的形态；现行 `application.yml:15-17` 的 `spring.threads.virtual.enabled`
  只管 Tomcat 请求线程与 `applicationTaskExecutor`，不是这个 bean。
  实测（本地活栈＋`HFUSIONHUB_RUN_SSE_LIVE=true`，`npx playwright test e2e/chat-sse.spec.ts`，19.5 s）：
  `:70`「SSE response contains [DONE] marker」**通过**（走 `javaApi`，node 侧不经浏览器）
  ⇒ 头注释那句"没有 `[DONE]`"在现行栈上直接否掉；`:93` 页面渲染**通过**；
  `:24`「send message and receive SSE response」**失败 `page.evaluate: TypeError: Failed to fetch`**，
  栈指向 `:31` 的 `fetch('http://localhost:8080/api/conversation/message/stream')`（页面在 `:3000`）。
  死因是同源策略，不是登录态：`curl -X OPTIONS` 带 `Origin: http://localhost:3000` 打到该端点回 **403、
  无 `Access-Control-Allow-Origin`**，只有 `Vary: Origin/Access-Control-Request-Method/
  Access-Control-Request-Headers`（`CorsFilter` 留下的）。而这个 CORS 默认值是**故意的安全姿态**——
  `CorsConfig.java:31`（`app.cors.allowed-origins` 默认空）＋`:39`（`app.cors.allow-any-origin` 默认 `false`）
  ⇒ 走 `:92-93`"注册空配置、仅放行同源"；应用侧不受影响，前端一律经 vite 同源代理
  （`vite.config.ts:44-47`）。也就是说：**红的是用例，安全默认值是对的**，不能靠放开 CORS 或
  `--disable-web-security` 把它蒙过去。
  处置选项，**待拍板**：A＝`chat-sse.spec.ts:31` 的绝对 URL 改成同源相对路径（`/api/...`，经 vite 代理），
  就地纠正头注释，并决定是否把 `HFUSIONHUB_RUN_SSE_LIVE=true` 写进 `e2e.yml`（打开＝runner 上第一次真正覆盖
  流式对话，代价是每轮 e2e 加时，且要和 `e2e.yml:165` 那条 20 分钟上限的既有风险叠加）；
  B＝只纠正头注释与文档口径（"后端 bug"→"用例写死跨源直连＋旗标从未打开"），覆盖面维持现状；
  C＝立案不处置。
  另外三条 skip（plugin／approval／write-note）本批**没有**逐个试开，只登记"它们在 runner 上是永久的"这一事实。
