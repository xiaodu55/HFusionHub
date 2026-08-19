# HFusionHub 安全回归清单

> 每次发布 / 每个 PR 到 main 都应跑通以下安全回归。清单按 5 条硬性安全边界组织，
> 每条都标注了对应的**自动测试**（CI 门禁）与**人工检查项**。任何一条失败都阻断合并与发布。

自动回归入口：
```bash
# Java（H2，无需外部服务）
cd java-backend && mvn --batch-mode test
# Python（含容器沙箱专项，缺镜像/缺 Docker 即 FAIL）
cd python-ai && pytest -q tests --durations=20
pytest -q tests/test_plugin_container.py -rs   # 任一侧 skips 请人工确认
```
CI 已把 `java` / `python` / `python-container` / `eval-offline` / `helm` / `docker-build` /
`docker-compose-validate` 设为 push/PR 门禁（`.github/workflows/ci.yml`）。

---

## 1. 租户隔离

**目的**：多租户间硬隔离，后台/回调/调度不得越权访问他租户数据；客户端不能伪造租户。

自动测试（`java-backend`）：
- `TenantContextInterceptorTest`：
  - `unauthenticatedNonCallbackRejectedInStrictMode` — 严格模式未认证请求直接拒绝
  - `authenticatedUserUsesOwnTenantAndIgnoresXTenantId` — 登录用户忽略伪造的 X-Tenant-Id
  - `authenticatedUserWithoutMembershipRejected` — 非成员被拒
  - `callbackPathOutsideVectorizeRejected` — 非回调前缀不可信
  - `X-Target-Tenant` 系列（`invalidXTargetTenantReturns403` / `nonexistentXTargetTenantReturns404` /
    `inactiveXTargetTenantReturns404` / `activeXTargetTenantSwitchesContextAndSetsCrossTenant`）
    — 平台管理员跨租户也**无静默回退**
- `FeatureFlagSecurityTest` — 特性开关访问控制

人工检查：
- [ ] 登录后跨租户只读/写入均返回 403/404，绝不静默落到默认租户
- [ ] 队列 / 调度 / 回调线程无登录上下文时使用 `TenantContext.runAs(...)`，绝不依赖线程遗留租户

## 2. 回调签名

**目的**：Python→Java 的向量化回调必须被 HMAC 校验，未签名不得伪造租户。

自动测试：
- `CallbackSignatureFilterTest` — 密钥/签名不匹配即 `verified=false`
- `TenantContextInterceptorTest.unsignedCallbackCannotSetTenant` — 未签名回调无法设置租户
- `CallbackSignatureRealPathTest` — 真实过滤器+控制器端到端（缺 secret/签名 → 失败）
- `VectorizationServiceImplTest`（已完成/失败/过期版本回调）

人工检查：
- [ ] 回调 URL（`/vectorize/{id}/callback`）必须携带 `X-Callback-Secret` + `X-Callback-Signature`
- [ ] 常量时间比较（`MessageDigest.isEqual`）用于 secret 与签名
- [ ] 过期版本 / 已完成任务回调被幂等忽略（`V2` 文档 index 流程）

## 3. 插件沙箱 fail-closed

**目的**：插件容器被强制最小权限；Runner 连不到隔离引擎时拒绝执行而非静默降级。

自动：
- `python-container` 门禁（CI）：`test_plugin_container.py`
  - digest 校验、固定入口、网络策略、`cap_drop=ALL`、`pids_limit`、只读 rootfs
  - 连不到 Docker / 无基础镜像 → **FAIL，绝不静默跳过**
- `plugin-security.yml`（独立安全工作流）
- `PluginQuotaReservationReaperTest` — 插件配额预占回收
- Java 侧插件治理 / 审批：`AgentApprovalInternalControllerTest`

人工检查：
- [ ] plugin-runner 容器**不挂载 /var/run/docker.sock**，只走 TLS Engine
- [ ] `DOCKER_HOST` 不可达时 `/health` 返回 503（Runner fail-closed）
- [ ] 镜像 digest 登记后才会执行；未登记 / 不匹配返回 400
- [ ] 允许/禁止域名清单生效：元数据端点固定禁止
- [ ] 隔离 Dind 演练 exit 0 后执行 `scripts/plugin-e2e-acceptance.ps1`：正确/错误 digest、镜像白名单、资源限制和网络 allow/block 均通过

## 4. 配额账本幂等

**目的**：同一业务请求不重复计费 / 重复退费；预占状态机杜绝扣负。

自动：
- `UsageLedger` 幂等键 `(tenant_id, meter, request_id, operation)` 唯一
- Agent 计量：`AgentTaskQueueIntegrationTest`
  - `startRunReservesAgentTokensKeyedByRunUuid`
  - `completeRunSucceedsSettlesWithActualTokens`
  - `completeRunFailureReleasesReservation`
  - `recoveryWatchdogTimeoutReleasesReservation`
- 索引计量：`VectorizationServiceImplTest`
  - `startVectorizationReservesCeilingChunksWhenFileSizeNotDivisible`（301 bytes → 2 chunks，防低估）
- `PluginQuotaReservationReaperTest`

人工检查：
- [ ] 预占后 RESERVED → COMMITTED 或 RELEASED **原子单次转换**
- [ ] 结算/退回使用预占的 `window_key`，跨 UTC 零点不累计错天

## 5. Agent 不可解析租户 → 拒绝执行

**目的**：Agent 队列 / 后台执行拿不到任何租户时不静默放行、不免费运行。

自动：
- `AgentTaskQueueIntegrationTest.workerRejectsUnresolvableTenantBeforeCallingAi`
  → 租户不可解析时终态化 `failed`(错误码 `tenant_unresolvable`)，**两条 AI 调用均为零**（零交互断言）
- 状态机收敛：Python `completed/timeout/tool_error` 等映射为契约终态（`AgentConstants.mapPythonStatus`）

人工检查：
- [ ] Worker 路径（未走 `startRun` 的 `executeRun`）在 `runAs(null)` 下不得执行 AI
- [ ] `agent_run→agent_task→user.tenant_id` 归属链断裂时终态拒绝，而非静默执行
- [ ] 可重试错误 `timeout/connection_error/tool_error` 有上限与死信兜底

---

## 6. 主体级文档可见性（ACL，V85）

**目的**：受控文档（`visibility=confidential`）对低权限主体在**检索层**不可见
（fail-closed），不依赖模型自觉拒答；clearance 由调用方（Java 后端）经
`X-User-Clearance` 传播，Python 侧缺省按最低权限 general 处理，非法值拒绝。

自动测试（`python-ai/tests/test_subject_acl.py`，27 项）：
- 等级模型：`allowed_visibilities` / `build_acl_metadata_filter`（admin 全集 /
  general 仅 general / 未知值归最低权限）
- 存储层谓词：`_matches_metadata_filter` 集合成员语义 + visibility 缺失按
  general（存量向量免回填）
- 中间件：缺头 → general、非法头 → 400、admin 透传、请求间不泄漏
- 评测契约：`subject_for_case` permission 用例切低权限主体

人工检查：
- [ ] 新增检索入口（绕过 `MultiChannelRetriever` / `search_tool` 的直查路径）
      必须叠加 `build_acl_metadata_filter(get_clearance())`，或显式论证不需要
- [ ] chunk 级读取工具（read_chunk 等）如开放给外部主体，需补 ACL 判断
- [ ] Java 会话 → Python chat 的 clearance 注入接通前，admin 在聊天链路
      亦为 general（fail-closed，不构成泄漏）

---

## 汇总（发布清单）

| # | 安全边界 | 关键自动测试 | CI job |
|---|----------|---------------|--------|
| 1 | 租户隔离 | `TenantContextInterceptorTest` | `java` |
| 2 | 回调签名 | `CallbackSignatureFilterTest` / `RealPathTest` | `java` |
| 3 | 插件沙箱 | `test_plugin_container.py` | `python-container` |
| 4 | 账本幂等 | `AgentTaskQueueIntegrationTest`、`VectorizationServiceImplTest` | `java` |
| 5 | Agent 拒绝 | `workerRejectsUnresolvableTenantBeforeCalling` | `java` |
| 6 | 主体级文档可见性 | `test_subject_acl.py` | `python` |

发布前请执行 `scripts/staging-rehearsal.sh` 验证全链路健康，并对照
`docs/PRODUCTION_OPS.md` 第 6 节逐条打勾。
