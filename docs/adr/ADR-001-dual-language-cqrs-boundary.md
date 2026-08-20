# ADR-001: 双语言 CQRS-like 分层边界（Java 管写入、Python 管智能）

- 状态：已采纳（项目立项即定，2026-09-08 补写）
- 关联：`docs/ARCHITECTURE.md`（架构全景与白皮书合并稿）；
  [ADR-003](ADR-003-hmac-callback-idempotent-indexing.md)（跨语言回调契约）；
  `java-backend/.../client/AiClient.java`（Java→Python 代理层）

## 背景

RAG/Agent 生态（解析、嵌入、检索编排、LLM 交互）几乎全部长在 Python，
而生产级在线服务需要的东西恰恰是纯 Python 栈的短板：编译期类型检查、
成熟的事务与连接池基础设施（HikariCP/Flyway）、多租户鉴权的强边界。
若全栈 Python，授权靠路由装饰器（易漏）、事务靠手动 try/finally、
schema 演进靠 Alembic 手工排序——这类"授权/事务类"缺陷正是动态语言
最难在编译期拦截的。

## 决策

按读写路径切分语言边界，而不是按业务模块切分：

1. **Java（Spring Boot 3.5，:8080）独占写路径**：用户鉴权（Sa-Token）、
   知识库/文档/会话等全部 MySQL ACID 写入、持久化任务态
   （`document_index_job` 版本化索引账本、`deletion_task` 删除 outbox、
   回收站/孤儿恢复调度器）。每次数据库写都经过编译期类型检查的
   service 层，用户授权在任何 AI 工作开始前于 Java 边界完成。
2. **Python（FastAPI，:9000）独占读/智能路径**：文档解析、切片、
   embedding、Milvus 向量检索、BM25/图谱通道、意图分类、ReAct 循环、
   LLM 网关（DeepSeek/Ollama 降级链）、MCP。Python 可重启/崩溃/替换
   而不丢数据——真相源始终在 MySQL。
3. **边界协议**：Java→Python 走 HTTP + `X-Internal-Token`
   （常量时间比较）；SSE 由 Java `WebClient` 读 Flux 逐元素转发
   `SseEmitter` 到前端；Python→Java 结果回调走 HMAC 签名
   （见 ADR-003）。

## 理由对照（纯 Python RAG 的问题 → 本架构的解法）

| 关注点 | 纯 Python | HFusionHub |
|---|---|---|
| 授权 | 路由装饰器，易漏 | Java service 层编译期检查 |
| 事务 | SQLAlchemy 手动回滚 | `@Transactional` 自动回滚 |
| 连接池 | psycopg2/asyncpg 自管 | HikariCP |
| 迁移 | Alembic 手工排序 | Flyway 确定性版本链（V1–V85+） |
| 类型安全 | 仅 API 边界 Pydantic | 全层 Java 编译器 |
| 任务恢复 | Celery+Redis 复杂重试 | `@Scheduled` + 幂等版本化任务 |

## 后果与边界

- 代价是双部署单元与一条跨语言代理链（AiClient 1178 行 + 回调 +
  SSE 桥），排障需看两端日志（已由 trace_id 贯穿缓解）；
- Python 侧同样有少量必要写路径（co-store/chunk 存储、记忆、评测落库），
  但**业务真相源**（会话、文档状态、账本、审计）一律在 MySQL/Java；
- 适合"多租户 + 数据完整性优先"的场景；不适合 LLM 即全部应用的
  纯研究型项目（单语言更简单）。
