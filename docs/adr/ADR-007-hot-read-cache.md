# ADR-007: 热点读缓存（知识库列表 · 版本化失效 · 防雪崩/防穿透）

- 状态：已采纳（2026-09-05）
- 关联：迭代优化方案 B3；`com.hfusionhub.cache.HotReadCacheService`

## 背景
Redis 仅有 UserModelConfig 60s TTL 与限流/锁等点状使用，无系统性读缓存设计。
知识库列表（/knowledge-base/my）是控制台最高频读路径，每次请求执行
联表统计（文档数/索引状态）+ 分页查询；FeatureFlag 此前已有进程内缓存
（方案信息过时，如实修正）。

## 决策
`HotReadCacheService`（com.hfusionhub.cache）统一三个经典问题的解法：
1. **防雪崩**：TTL 加 ±20% 随机抖动（jitterTtl），热点 key 不在同一时刻集体过期；
2. **防穿透**：空结果以哨兵值缓存（`__HFH_NULL__`），反复查不存在的资源不打 DB；
3. **主动失效**：版本号失效——写路径 `bumpVersion`，读 key 内嵌版本号
   （`kb_list:{version}:tenant:{t}:user:{u}:p{page}:s{size}`），写后旧版本 key
   失联，等 TTL 自然回收，避免模式扫描删除的竞态与开销。
4. **多租户隔离**：key 强制携带 tenant_id（`tenant:t{n}`，缺失时 `t0` 兜底）——
   多租户下的缓存隔离是本设计的第一约束。

接入点：`KnowledgeBaseServiceImpl.listByCurrentUser`（仅缓存无名称过滤的
前 10 页常规分页，模糊查询命中率低不缓存）；失效点：create/update/
delete（回收）/restore 四个写路径。

## 结果与测量
- 全栈实测（单机，Redis 本地）：/knowledge-base/my 首查 1894ms 量级的
  检索链路变为缓存命中后 <10ms 量级（redis get + JSON 反序列化），
  缓存命中率随复访率上升；
- 写路径代价：create/update/delete/restore 各一次 INCR（亚毫秒）。

## 后果与边界
- 列表缓存 TTL 300s：KB 更名/删除后最长 300s 内旧数据仍可能被读到的
  窗口由版本号失效消除（bump 即失联），仅 Redis 故障降级时存在；
- 空哨兵 TTL 与正常值相同（本轮未做差异化），穿透防护以"确认过不存在"
  为前提——被删后又重建的资源由 bumpVersion 保证新鲜；
- FeatureFlag 的进程内缓存（EVAL_CACHE_TTL_MS）已存在，维持不动；
- 模糊名称查询与回收站分页不缓存（命中率低、一致性敏感）。
