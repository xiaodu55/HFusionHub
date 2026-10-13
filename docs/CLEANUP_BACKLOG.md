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
- [ ] **`sbom-generation` 描述的对象不是产品依赖面（35 个组件 ＝ runner 自带环境），空组件表只打印
  `WARNING` 不判红**（第一百零四批 CI 补证时发现，未处置）—— 那个 job 全程没有
  `pip install -r requirements.txt`，`cyclonedx-py environment` 读的是当前解释器已装的包，
  于是产物里是 runner 的 35 个组件，而同一条流水线 `vulnerability-scan` 审的是 `requirements.txt`
  的 76 个包——两条产物不是同一个对象，SBOM 作为供应链凭证的价值目前是 0。
  本地对照实测：对 `python-ai/.venv` 生成的是 126 组件（scratch `b104_sbom_731.json`），
  数量差异本身就说明了对象错位。处置方向（第一百一十一批，原写作第一百一十批）：先装 `requirements.txt` 再生成
  （或显式把 `<python>` 指到一个装有产品依赖的环境），组件数与锁的 pin 数做一致性判定，
  同时把"空组件表"从 `WARNING` 改成退出码非 0。**改的是产物描述的对象，不是把门放宽。**
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
- [ ] **Flyway 迁移步骤在 `e2e.yml` / `eval-nightly.yml` 从诞生起就没过过：插件只认
  `-Dflyway.*`，而步骤给的是 `SPRING_DATASOURCE_*`（四处站点，`ci.yml` 里已有写对的那一份）**
  （第一百零四批取证，未处置）—— run 38221938525（＝ `8054f32e`）的 `e2e-full` job 死在这一步，日志原文：
  `FlywayException: Unable to connect to the database. Configure the url, user and password!`
  （scratch `ci_e2e_flyway.log` 第 617 行）。这一 `conclusion` 不是今天才有：2026-10-10 / 10-11（三次）/
  10-12 连续 **5** 条 run 的 `e2e-full` 都死在**同一个步骤**（逐 run 核过
  `gh run view <id> --json jobs --jq '.jobs[]|{name,conclusion,failed:[.steps[]|select(.conclusion=="failure")|.name]}'`），
  中间另有几次是 `cancelled` 而非通过——**取消来源不能从日志判定**：`e2e.yml` 里没有 `concurrency`
  键，日志里也没有 timeout 声明，所以这些 `cancelled` 既不能算"过"、也不能归因成"被新 run 挤掉"；
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
