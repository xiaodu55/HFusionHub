# Changelog

All notable changes to HFusionHub are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

> 版本脉络：`[1.0.0]`（2026-08-30，平台完整能力首次固化）→
> `[1.1.0]`（2026-09-09，评测双轨门禁 + 主体级 ACL + 招投标垂直化 +
> 大数据扩展包 + R16/R17 优化与 44 批自审修复）。批次粒度变更记录
> 保留于各版本小节内。

## [Unreleased]

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
