# ADR-004: 租户行级隔离——MyBatis-Plus 行拦截器 + CI 静态校验双保险

- 状态：已采纳（V32 引入租户模型，2026-09-08 补写）
- 关联：`java-backend/.../config/MybatisPlusConfig.java`（TenantLineInnerInterceptor）、
  `java-backend/.../tenant/`（TenantContext / TenantContextInterceptor）、
  `scripts/static-checks.py`（CI 租户列完整性校验）、
  `docs/adr/ADR-008-it-mysql-testcontainers.md`（H2 掩盖的租户插入问题）、
  `TenantInterceptorIsolationTest`（真库隔离回归）

## 背景

多租户 SaaS 的隔离层若只靠每个 service 手写 `WHERE tenant_id = ?`，
漏写一处即越权——这类缺陷无法靠 code review 稳定拦截（历史上
`kb_share`/`app_api_key` 建表漏 tenant_id 列导致整功能 500，V56 修复）。
需要机制级方案：默认隔离、例外显式、例外可审计、遗漏可被 CI 拦截。

## 决策

1. **默认隔离**：MyBatis-Plus `TenantLineInnerInterceptor` 对所有业务表
   自动注入 `tenant_id` 条件（写自动填充、读自动过滤），
   `TenantContextInterceptor` 从请求上下文解析当前租户；
2. **例外显式**：忽略表清单（如 `sys_user`）集中于拦截器配置——
   忽略表插入必须显式带 `tenant_id`（ADR-008 迁移实录第 1 条：
   H2 列默认值曾掩盖该约束，真库必挂）；
3. **跨租户操作走 `TenantContext.runAs/runAsSystem`**：开放 API key 解析
   （key hash 全局唯一，R15-3）、插件审计回调按插件租户落账（R15-4）
   等系统路径必须显式包裹，包裹本身即是代码中可审计的越权点；
4. **CI 静态门禁**：`scripts/static-checks.py` 校验业务表租户列完整性
   与 token 键一致性，建表漏列在 CI 即红，不再依赖线上暴露；
5. **真库回归**：`TenantInterceptorIsolationTest` 连真实 MySQL
   （完整 Flyway 迁移链）验证拦截器真实生效（ADR-008）。

## 结果与测量

- 租户列覆盖 V32 起系统性补齐（V56 补 kb_share/app_api_key、
  V74 补 8 张表的租户索引），静态校验持续绿；
- 隔离机制本身有真库测试兜底，而非仅靠约定。

## 后果与边界

- 新表必须带 `tenant_id` 且进拦截器清单，否则 CI 静态检查失败——
  这是刻意的摩擦；
- 拦截器默认填 `tenant_id=1` 的行为（无上下文时）意味着：**系统级
  路径漏包 runAsSystem 时会把数据错标到租户 1** 而不是报错——R15-3/4
  两处缺陷均属此模式，故新增内部路径时的必查项就是"上下文是谁"；
- 行级隔离不替代网络层/存储层隔离（MinIO per-tenant bucket 见
  R15-28、Milvus per-tenant collection 见 ADR-002），各层独立设防。
