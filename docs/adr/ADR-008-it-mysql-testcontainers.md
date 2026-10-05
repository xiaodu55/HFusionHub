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
   （2026-09-05 用 connection-init-sql 把会话对齐到 +08:00 解决；
   2026-10-10 第九十四批撤掉——见下「时区口径的二次修正」）；
4. **FK 环 + 逻辑删除行**：`agent_task↔agent_run` 外键环叠加逻辑删除，
   MyBatis-Plus 的 update/delete 命不中逻辑删除行——清理需
   `JdbcTemplate` 裸 SQL + FK 免检 + `runAsSystem` 重试。

## 时区口径的二次修正（2026-10-10，第九十四批）
当年那句「MySQL 容器是 UTC、JVM 是 +8」把**开发机**的 JVM 时区当成了常量。
CI 的 ubuntu runner 与 maven 容器里的 JVM 都是 UTC，于是会话 +08:00 不再是
「对齐」，而是凭空造出 8 小时：库的 `NOW()` 比 Java 侧快 8 小时，
`recycle_expires_at = now + 1h` 的「未过期」行被判成过期——
`DocumentMapperRecycleTest` 在 CI 口径下恒红（本机无库时整类跳过，所以从未暴露）。
撤掉 `connection-init-sql` 后，会话取 MySQL 的 SYSTEM（=UTC），与容器/CI 一致。
余下的一侧脆性在判据本身：过期行留 1 天余量、未过期行只留 1 小时，
凡是「库比 JVM 快」的宿主（JVM 在库时区以西）都会红，因此把未过期余量也取 1 天，
使两个方向的偏移都被覆盖。四种宿主×会话组合实测见 `docs/CI_GATES.md`。

## 显示面口径的落定（2026-10-10，第九十五批）
上面几段管的是"写进库的是哪个钟"，本段管"读出来给人看时按哪个钟解释"。此前仓库里
**三套互相矛盾的 theory 并存**，各自能解释服务端的一种写法，合起来必然让同一份数据在
不同页面显示成不同时刻：

1. `hfusionhub-frontend/src/utils/date.ts` 注释断言"后端已存储北京时间（UTC+8）"，
   并把无偏移串按**本地墙钟**解析；
2. 8 个页面直接 `value.replace('T', ' ').slice(0, 16)`，即把服务端字面量当显示值，
   既不解释偏移也不做位移；
3. `src/pages/chat/Detail.vue` 手工 `+480` 分钟，把浏览器墙钟硬算成北京墙钟。

实测出的线上形状（同一瞬间的四种写法）：java 的 Jackson + `LocalDateTime` 发**无偏移**
ISO（`2026-10-10T11:58:12`）；python 的 `datetime.now(UTC).isoformat()` 带 `+00:00`、
`strftime(...Z)` 带 `Z`、少数 `strftime("%Y-%m-%dT%H:%M:%S")` 无偏移。数组形式
`[y,m,d,h,min,s]` 也在返回里。于是"统一 +8"这类整把偏移是错的（对已带偏移的值会二次位移），
正确的口径只有三条：**无偏移一律按 UTC 解释、带偏移按偏移解释、渲染交给浏览器本地时区**；
纯日期（`LocalDate`、日历日）不参与位移，按当地零点处理。

落点：解析入口收敛到 `src/utils/date.ts`，14 个页面/组件改用 `formatDateTime` /
`formatTime` / `formatDateOnly` / `parseServerTime`，防回潮由 `scripts/static-checks.py`
检查 12（`--frontend-time-entry`）以纯文本方式禁止上述两种旧写法回到 `pages/`、
`components/`、`api/`。契约用例在 `src/utils/__tests__/date.spec.ts`（16 例，红判据是
HEAD 的实现下 14 例红）。

**上限（不假装做过）**：本批只改显示面，API 与库里的值一字未动。当时写侧的
`-Duser.timezone` / MySQL `default-time-zone` **在任何部署面上都没有声明**（第九十六批推翻了
这一句，见下一节；此处按"当时测到的事实"保留，并记下核对方式：在第九十五批的提交上
`git grep -n -e user.timezone -e default-time-zone HEAD -- docker/ deploy/ java-backend/src`
返回 **0 处**，而同一条 `git grep serverTimezone` 返回 5 处、其中 4 处写的是
`Asia/Shanghai`、只有 helm 的 `templates/java.yaml` 写 `UTC`——三张钟面当时不仅没被钉，
而且已经互相不一致）。

## 写侧口径的钉住（2026-10-10，第九十六批）
前两节把"读出来给人看按哪个钟"和"it 会话别再自己偏移"定了下来，但库里到底写的是
哪个墙钟仍没人声明：`DATETIME` 存的是**不带时区的字面量**，谁写就用谁的钟——Java 侧
`LocalDateTime.now()` 取 JVM 默认时区，谓词里的 `NOW()`/`CURRENT_TIMESTAMP` 取**会话**
时区，两处都没被钉住，于是同一行的"是否过期"取决于这行由谁写、这次查询恰好落在哪条连接。

本批把三张钟面钉成同一个 UTC，并把判定改成会话免疫的写法：

- **判定 SQL**：`expires_at` / `recycle_expires_at` / `circuit_open_until` 三列的 7 处比较
  与 2 处写入（熔断冷却）一律用 `UTC_TIMESTAMP()`——它取的是 UTC 墙钟，会话挪不动它。
  审批过期清扫原有第二个钟（调用方把 JVM 的 `LocalDateTime.now()` 当 `#{now}` 传进谓词），
  该入参已删，`selectExpiredPending()` 现在无参，双钟在结构上不存在了。
- **JVM 默认时区**：`JAVA_TOOL_OPTIONS=-Duser.timezone=UTC`（两张 compose + helm 的
  `javaBackend.javaToolOptions`，模板里真的引用了那个键）。不用 `JAVA_OPTS`：
  `deploy/Dockerfile.java` 的 ENTRYPOINT 是 exec 形式，没有任何 shell 展开它，那行是死开关
  （已登记 `docs/CLEANUP_BACKLOG.md`，删掉或改入口是独立决策）。
- **MySQL 服务端**：`--default-time-zone=+00:00`（compose 的 `command` / helm 的 `args`）。
- **JDBC**：`serverTimezone=UTC`，把原先 4 处 `Asia/Shanghai` 与 1 处 `UTC` 的分歧收成一个。
- **Jackson `time-zone`**：一并改成 UTC，但它对 `LocalDateTime` 载荷是空转的
  （`date-format` 只作用于 `java.util.Date`，而 `src/main/java` 下普查不到任何
  `Date`/`Instant`/`OffsetDateTime`/`ZonedDateTime` 字段），改它只是为了不让配置里留一张
  指向别的方向的钟面。

判据两侧：`java-backend/src/test/java/com/hfusionhub/mapper/WriteClockCaliberTest`（真库，
4 例，红判据阶段 3 例红）断言三处判定都不随 `SET time_zone='+08:00'` 翻转；
`scripts/static-checks.py` 检查 13（`--write-clock-caliber`）是纯文本门禁，核对 10 张钟面
是否都归一到 UTC、helm 模板是否真的消费了那两个 values 键、以及判定列有没有又被拿去和
`NOW()` 比。

**上限**：检查 13 只读文本，不启动容器；IT 走的 JDBC URL 由 `@DynamicPropertySource`
注入（外部库或 Testcontainers），所以生产那条 URL 上的 `serverTimezone` 只有文本门禁在看。
"JVM 默认钟 == 库钟"也**没有**写成断言——那等于要求每台开发机的系统时区都是 UTC，
正是第九十四批刚从 `application-it.yml` 撤掉的那类宿主假设。python 侧仍不在本批口径内：
`python-ai/app/core/tools/time_tool.py:21` 的 `datetime.now()` 取容器时区，而容器没有声明 `TZ`
（已登记为独立缺陷）。

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
