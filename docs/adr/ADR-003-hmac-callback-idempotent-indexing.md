# ADR-003: Python→Java HMAC 回调 + 版本化幂等索引账本

- 状态：已采纳（项目初期，2026-09-08 补写）
- 关联：`docs/ARCHITECTURE.md` §Key Design Decisions 1/2、
  `java-backend/.../webhook` 与 VectorizationCallbackService、
  `scripts/rotate-secrets.sh`（CALLBACK_SECRET 轮换）、
  [ADR-001](ADR-001-dual-language-cqrs-boundary.md)（跨语言边界）

## 背景

文档索引是跨语言异步任务：Java 受理上传（ACID 落库 PENDING）→
调 Python 解析/切片/嵌入/写 Milvus → Python 完成后**回调 Java** 更新
文档状态。回调若不设防，任何知道 URL 的调用方都能伪造"处理完成"，
绕过 Java 授权层直接改写业务状态；异步任务还天然存在三类脏结果：
崩溃 worker 的迟到回调、重复处理、以及"看起来成功实则没做"的幻影索引。

## 决策

1. **回调认证**：Python→Java 回调一律 HMAC-SHA256 签名，共享密钥
   `CALLBACK_SECRET`（仅存于两侧 .env，不入库不入代码；轮换走
   `scripts/rotate-secrets.sh`，Java 侧校验失败拒绝并审计）；
2. **回调幂等**：`document_index_job.index_version`（UUID）版本化账本——
   新索引请求到来时 Java 递增版本，版本随请求下发、随回调带回，
   **Java 只接受 `callback.version == job.index_version` 的回调**。
   一次性挡掉：崩溃 worker 的迟到旧版本回调、重复投递、幻影索引；
3. **兜底恢复**：`DocumentIndexRecoveryScheduler` 以 30 分钟 stale 阈值
   重派卡死任务（与 DELETING 状态的竞态已在第三十六批收口：删除中的
   文档 stale 任务直接置 FAILED，不重派，防孤儿向量复活）。

## 结果与测量

- 该契约稳定运行于全部索引/重索引/删除路径；第三十六批的
  "重索引 Milvus 重复插入"缺陷正是在"版本化账本 + upsert"两个机制的
  交界处（Python 侧 insert 不去重）被审查揪出并修复——机制分层使
  缺陷可定位；
- 伪造回调/未签名请求无法通过 Java 校验（HMAC 常量时间比较）。

## 后果与边界

- 双侧共享对称密钥：`CALLBACK_SECRET` 泄漏即回调面失守，故轮换脚本
  与 gitleaks 扫描是配套必选项；
- 回调是"最终通知"而非"分布式事务"——以 Java 账本状态机为准，
  Python 侧崩溃由恢复调度器兜底，不做跨语言 2PC；
- Java→Python 方向用 `X-Internal-Token`（另一密钥），两密钥职责分离，
  不可混用（R15-8 已将加密密钥回退复用列为禁止项）。
