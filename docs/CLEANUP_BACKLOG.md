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
- [ ] **`_reset_db()` 关连接不持锁，与后台 flush 线程竞争 ⇒ 解释器段错误**（第一百零三批实测踩到，
  未处置）—— `python-ai/app/core/plugin/audit.py:165-190` 的 `_db_conn.close()` 与
  `_DB_DIR/_DB_PATH` 换绑整段不在 `with _db_lock:` 内，而 `:128` 的连接是
  `check_same_thread=False`；`tests/conftest.py:126,128` 每条用例前后各调一次，
  `audit-flusher`（`:425`，daemon）与 `audit-shutdown-flush`（`:600`）都可能在
  `_do_flush`→`_increment_retry`（`:326`→`:258`）的 `execute` 中途被关连接。
  实测形态：同一镜像、同一缓存卷、同一命令，第一次 `pytest -q` 退出码 0，第二次 62% 处
  `Fatal Python error: Segmentation fault`（`PYTEST_EXIT=139`）——CI 的 `python` job 在同一把
  锁上给的是 `2056 passed / 7 skipped`，所以这是**低概率但真实存在**的窗口，不是环境问题。
  `app/` 下当前无 `_reset_db` 调用方（生产今天不受影响），但任何把"重定向审计库"接进运维路径
  的改动都会走进同一窗口。处置方向见第一百零三批 CHANGELOG 的 A/B/C（推荐 A：`_reset_db` 全程
  持 `_db_lock`，配一条确定性红判据——持有锁时起线程调 `_reset_db`，断言它尚未完成）。
- [ ] **`e2e.yml` 的 `e2e-full` 在 `Run Flyway migrations` 从诞生起就没过过：Flyway Maven 插件
  收的是 `SPRING_DATASOURCE_*`，而它只认 `flyway.url/-Dflyway.*`/`FLYWAY_*`**（第一百零四批取证，
  未处置）—— run 38221938525（＝ `8054f32e`）的 `e2e-full` job 死在这一步，日志原文：
  `FlywayException: Unable to connect to the database. Configure the url, user and password!`
  （scratch `ci_e2e_flyway.log` 第 617 行）。这一 `conclusion` 不是今天才有：2026-10-10 / 10-11（三次）/
  10-12 连续 **5** 条 run 的 `e2e-full` 都死在**同一个步骤**（逐 run 核过
  `gh run view <id> --json jobs --jq '.jobs[]|{name,conclusion,failed:[.steps[]|select(.conclusion=="failure")|.name]}'`），
  中间另有几次是"被新 run 取消"而非通过；更早的 2026-09-22、09-29 两次 `failure` 的失败原因不在
  step 列表里（`.steps` 全空），**本条没有把它们算进"同一步红"**，要归因得单独取日志。
  机理核对：`.github/workflows/e2e.yml:75-82` 给步骤设的三个变量是
  `SPRING_DATASOURCE_URL/USERNAME/PASSWORD`，而 `mvn --batch-mode flyway:migrate` 执行的是
  flyway-maven-plugin，它读 `-Dflyway.url/user/password`、`flyway.conf` 或 `FLYWAY_*` 环境变量，
  **不**读 Spring 的那三个名字；`java-backend/pom.xml` 里也**没有** `flyway-maven-plugin` 的
  `<configuration>`（`:103-108` 只有 `flyway-core` 与 `flyway-mysql` 两个依赖），于是插件从
  Maven central 前缀解析到最新版（日志里是 `flyway:11.7.2`，两次
  `Could not transfer metadata … HTTP Status: 401` 就是那次解析的噪声）并拿到空配置。
  ⇒ 与第一百零四批同族：**"runner 装了什么/工具读什么"与"门里写了什么"不同源**，而且这里的
  插件版本也未钉住。处置方向（不得靠删掉这一步或加 `continue-on-error` 变绿）：在 pom 里显式声明
  `flyway-maven-plugin` 钉版本，并把它该读的那三个值传给 `mvn -Dflyway.url=… -Dflyway.user=…`
  （或改由 Spring Boot 启动时自迁移，那一步就该删得有交代——两者都要先在 e2e 判据上证明迁移真发生）。
