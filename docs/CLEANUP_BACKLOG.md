# 冗余功能与死代码清理清单

> 2026-08-29 前端主题统一改造时盘点生成。本次**只登记不删除**，逐项评估后处理。
> 删除前先确认测试基线（Java 718 · Python 1916 · 前端 117）仍全绿。

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
