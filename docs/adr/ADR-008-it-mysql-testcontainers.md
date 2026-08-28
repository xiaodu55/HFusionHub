# ADR-008: 集成测试 H2 → Testcontainers 真实 MySQL 演进（C1）

- 状态：已采纳（2026-09-05）
- 关联：迭代优化方案 C1；`com.hfusionhub.support.AbstractItMySQLTest`；
  commit `2063a548`；[ADR-006](ADR-006-faithfulness-metric-recalibration.md)

## 背景
单元/切片层此前大量使用 H2 兼容模式，H2 与真实 MySQL 的行为差异会系统性
掩盖问题：列默认值、时间精度/时区、方言细节、外键与逻辑删除的交互都在
"测试全绿、线上现形"的风险敞口里。同时项目已有完整的 Flyway 迁移链
（V1..V85+），没有任何理由让集成测试跑在另一套 schema 方言上。

## 决策
引入 **it profile + Testcontainers 集成基类**，替代 H2 承担集成测试：

1. **`AbstractItMySQLTest`**（`@SpringBootTest(NONE)` + `@ActiveProfiles("it")`，
   `PER_CLASS` 生命周期）：
   - 数据源二选一：外部真实库（`HFH_IT_JDBC_URL` + 可选
     `HFH_IT_JDBC_USER`/`HFH_IT_JDBC_PASS`（注意变量名是 PASS 而非
     PASSWORD，与 `AbstractItMySQLTest` 的读取一致），默认容器里的
     `hfusionhub_it`）或 **Testcontainers `mysql:8.0`**；
   - Windows 上 Testcontainers 与 Docker Desktop 的兼容性不稳——环境探测
     失败时**整类跳过**（`Assumptions`），CI 无 Docker 不红；
   - 完整 Flyway V1..V85+ 迁移链在真库上重放，与生产 schema 同源；
   - 每类 `@BeforeAll` 全 schema 清空 + 重播核心种子，类间零状态泄漏；
   - Redis 与 test profile 一致保持 bean 级 mock（本 ADR 只收口数据库层）。
2. **存量 @SpringBootTest 逐个迁移**：6/8 个迁到真库全绿
   （PythonEngineSmokeTest / DocumentMapperRecycle /
   ConversationStreamingPersistence / ConversationStreamingUsage /
   PromptTemplateVersionIntegration / UsageLedgerService）；
   **PromptTestSet**（异步时序需 Awaitility 化）与 **CostWebhookGate**
   （需每类独立库隔离）两例暂缓并文档化，不阻塞本决策。
   - 2026-09-09（R16-12b）后记：两例已完成迁移，**8/8 收口、23/23 全绿**。
     两处根因都是测试线程未复刻生产语义，而非 MySQL 缺陷：
     ① PromptTestSet 的 worker/cancel 线程须持有租户上下文（生产调度器
     `TenantContext.runAs(run.tenantId)` 包装、生产 HTTP 请求由拦截器
     注入；it 下拦截器开启，裸线程的 requireOwnedRun 直接「运行记录
     不存在」）；② CostWebhookGate 的「混跑失败」实为 DATETIME(0) 秒级
     取整变体——`created_at <= endDate` 上界在秒末插入时被舍入越过
     （测试跨秒界后稳定）。

## H2 掩盖的 4 类问题（迁移过程实录，全部修复/绕行）
1. **逻辑删除 + 租户拦截器**：`sys_user` 在租户拦截器忽略表清单里，插入
   必须显式 `tenant_id`——H2 列默认值掩盖了这一点；
2. **DATETIME(0) 秒级取整**：`scheduled_at` 存库后四舍五入到下一秒，
   写后立即查询差 1 秒——H2 保留毫秒精度，测试通过、真库必挂；
3. **时区**：MySQL 容器 UTC vs JVM +8，`NOW()`/按天聚合差 8 小时
   （connection-init-sql 对齐时区解决）；
4. **FK 环 + 逻辑删除行**：`agent_task↔agent_run` 外键环叠加逻辑删除，
   MyBatis-Plus 的 update/delete 命不中逻辑删除行——清理需
   `JdbcTemplate` 裸 SQL + FK 免检 + `runAsSystem` 重试。

## 结果与测量
- 6/8 集成测试类在真实 MySQL 上全绿，`mvn test` 702 全过；
- 上述 4 类问题在迁移当轮即被揪出并修复——这正是本 ADR 的价值证明：
  它们任何一个溜到线上都是难排查的"环境差异"类缺陷。

## 后果与边界
- 集成测试依赖 Docker 或外部库：两者都不可用时静默跳过（可见性靠
  `[IT] Testcontainers unavailable` stderr 提示），**跳过不等于通过**——
  CI 报告需关注 IT 类的实际执行数；
  - 2026-09-08（R16-12a）补记：初版跳过机制依赖 `@BeforeAll` 的
    `Assumptions`，但 `@DynamicPropertySource` 的属性 supplier 在 Spring
    上下文加载期即被解析，容器未就绪时 context 直接 error——assume
    永无执行机会，Windows 无 Docker 的本机表现为 5 个 IT 类报错而非
    跳过。现改为 `RequireMySqlCondition`（JUnit `ExecutionCondition`）
    在实例创建与上下文加载之前裁决 enable/disable，跳过语义才真正成立；
- 新增 @SpringBootTest 默认应继承 `AbstractItMySQLTest` 走真库，
  H2 仅保留给纯 SQL 方言无关的mapper单元层；
- 暂缓的两类（PromptTestSet/CostWebhookGate）转 Awaitility 化与
  独立库隔离是后续小迭代，不改变本决策；
- MySQL 8 容器与生产版本对齐，方言漂移风险收敛到"容器 vs 生产小版本"。
