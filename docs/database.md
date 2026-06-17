# 数据库设计

> MySQL 8.0 + Flyway 迁移 + MyBatis-Plus ORM

## 概述

数据库 `hfusionhub` 由 Flyway 管理，迁移脚本位于 `java-backend/src/main/resources/db/migration/`，当前已应用到 **V75**。

## 迁移历史（V1–V75）

| 版本 | 文件 | 说明 |
|------|------|------|
| V1 | `V1__initial_schema.sql` | 核心表（sys_user / knowledge_base / document / conversation / message / document_index_job） |
| V2 | `V2__document_index_persistence.sql` | 文档索引任务持久化 |
| V3 | `V3__deletion_task_outbox.sql` | 异步删除 outbox |
| V4 | `V4__message_request_id.sql` | 消息幂等（request_id） |
| V5 | `V5__remove_default_admin.sql` | 移除硬编码默认管理员 |
| V6 | `V6__add_document_processed_at.sql` | 文档处理时间戳 |
| V7 | `V7__document_recycle_bin.sql` | 文档回收站 |
| V8 | `V8__persistent_memory.sql` | AI 记忆持久化 |
| V9 | `V9__system_notice.sql` | 系统公告 + 已读跟踪 |
| V10 | `V10__agent_task_state_machine.sql`（+`V10.1` 状态值修复） | Agent 任务状态机 |
| V11 | `V11__agent_approval.sql` | Agent 工具审批 |
| V12 | `V12__agent_observability.sql` | Agent 可观测 |
| V13 | `V13__agent_task_scheduling.sql` | Agent 调度/重试/租约 |
| V14 | `V14__memory_lifecycle.sql` | 记忆生命周期 |
| V15 | `V15__approval_raw_tool_input.sql` | 审批原始工具入参 |
| V16–V23 | `V16`–`V23` | 提示词模板/版本/测试集/批量运行 |
| V24–V25 | `V24`–`V25` | 功能开关（feature_flag + 规则） |
| V26 | `V26__embedding_metadata.sql` | 向量元数据 |
| V27–V28 | `V27`–`V28` | Agent 工具治理 + 审批风险等级 |
| V29–V31 | `V29`–`V31` | 插件沙箱/容器隔离/镜像摘要 |
| V32 | `V32__tenant_org_model.sql` | **多租户组织模型**（tenant_id 体系） |
| V33 | `V33__add_platform_admin.sql` | 平台管理员角色 |
| V34 | `V34__tenant_audit_log.sql` | 跨租户代操作审计 |
| V35 | `V35__usage_ledger.sql` | 租户配额账本 |
| V36 | `V36__cost_tracking.sql` | 模型成本追踪（model_usage_record） |
| V37 | `V37__webhook_system.sql` | Webhook 订阅/投递 |
| V38 | `V38__evaluation_gate_result.sql` | 评测门禁结果 |
| V39 | `V39__knowledge_base_recycle_bin.sql` | 知识库回收站 |
| V40–V42 | `V40`–`V42` | RAG 意图树（含租户/KB 引用） |
| V43 | `V43__rag_answer_feedback.sql` | RAG 回答反馈 |
| V44–V45 | `V44`–`V45` | 提示词模板回收站 + 名称唯一 |
| V46–V47 | `V46`–`V47` | 用户模型配置（含租户） |
| V48 | `V48__declarative_plugin_tools.sql` | 声明式插件工具 |
| V49–V51 | `V49`–`V51` | 平台角色 / 待分配用户 / AI 能力开关 |
| V52 | `V52__apps_and_api_keys.sql` | 开放 API 应用 + API Key |
| V53 | `V53__kb_share.sql` | 知识库共享 |
| V54 | `V54__audit_log.sql` | 操作审计日志 |
| V55 | `V55__note.sql` | **用户笔记（写笔记闭环）** |
| V56 | `V56__fix_tenant_id_share_and_apikey.sql` | **修复 kb_share/app_api_key 缺 tenant_id 列** |
| V57 | `V57__user_theme_preference.sql` | **用户主题偏好**（sys_user.theme_preference，light/dark/system） |
| V58–V60 | `V58`–`V60` | lexical 重排默认开启 / Multi-Agent 默认开启 / OIDC 绑定 |
| V61–V64 | `V61`–`V64` | **投标业务线**：bid_project（状态机）/ tender_element / bid_scoring_method / bid_requirement |
| V65 | `V65__knowledge_base_category.sql` | 知识库分类（tender / qualification / bid_history） |
| V66–V69 | `V66`–`V69` | bid_draft / bid_template / bid_check_report / bid_subscription |
| V70–V73 | `V70`–`V73` | 租户套餐绑定 / 投标模块开关 flags / 行业方案包 / 内建投标插件 |
| V74 | `V74__missing_tenant_indexes.sql` | 补齐缺失的 tenant_id 索引 |
| V75 | `V75__drop_uk_tender_element.sql` | 移除 tender_element 的 (project_id, element_key) 唯一键（同类别多行是解读工作流的预期数据形态） |

## 迁移规则

1. **历史迁移（V1–V75）不可修改**——修改会导致 Flyway checksum mismatch。
2. **所有新表结构变更必须使用 V76+ 脚本**。
3. **新表必须包含 `tenant_id` 列**（除非加入 `MybatisPlusConfig.TENANT_IGNORE_TABLES`）——租户拦截器会对非忽略表自动注入 `WHERE tenant_id=?`，缺列会导致整表功能 500（V52/V53 曾因此出问题，`scripts/static-checks.py` 在 CI 中静态校验）。
4. **生产环境**：禁止手动修改 `flyway_schema_history`。
5. **本地重置**：`cd docker && docker compose down -v && docker compose up -d`。

### 校验和不匹配修复（仅本地开发）

```powershell
cd docker
docker compose down -v   # ⚠️ 删除全部数据（含 Milvus 向量卷）
docker compose up -d
```

## 核心表

| 表 | 用途 |
|----|------|
| `sys_user` | 用户与认证 |
| `tenant` / `tenant_member` | 租户与成员（V32） |
| `knowledge_base` | 知识库元数据与归属 |
| `document` | 上传文档（状态跟踪） |
| `document_chunk` | 解析后分块文本 |
| `document_index_job` | 异步索引任务 |
| `conversation` / `message` | 对话与消息（含来源引用、token） |
| `memory_entry` | AI 记忆（偏好/事实/上下文） |
| `agent_task` / `agent_run` / `agent_step` | Agent 任务/运行/步骤 |
| `agent_approval` | 高风险工具审批 |
| `agent_status_event` | Agent 状态事件流 |
| `plugin` / `plugin_audit_log` | 插件与审计 |
| `prompt_template` / `prompt_test_set` | 提示词模板与测试集 |
| `feature_flag` | 能力开关（agent.enabled、write_tools、web_search 等） |
| `usage_counter` / `usage_event` / `usage_reservation` | 租户配额账本 |
| `model_usage_record` | 模型成本追踪（V36，/cost 页面） |
| `note` | **用户笔记（V55，写笔记闭环）** |
| `kb_share` | 知识库共享（V53，V56 补 tenant_id） |
| `app` / `app_api_key` / `app_call_log` | 开放 API（V52，V56 补 tenant_id） |
| `audit_log` / `tenant_audit_log` | 操作审计 / 跨租户审计 |
| `bid_project` / `tender_element` / `bid_scoring_method` / `bid_requirement` | 投标项目与解读产物（V61–V64，状态机 interpreting→requirements→drafting→checking→submitted/archived） |
| `bid_draft` / `bid_check_report` / `bid_template` | 标书草稿 / 自检报告 / 行业模板（V66–V68） |
| `bid_subscription` / `tenant_plan_binding` / `bid_plan_module_flags` / `bid_industry_packages` / `bid_plugin_builtins` | 投标商业化：订阅 / 套餐绑定 / 模块开关 / 行业方案包 / 内建插件（V69–V73） |
| `knowledge_base.category` | 知识库分类：tender（招标）/ qualification（资质）/ bid_history（历史标书），撰写标书时自动联动检索（V65） |

## 实体关系

```
sys_user (1) ──→ (N) knowledge_base
knowledge_base (1) ──→ (N) document
document (1) ──→ (N) document_chunk
document (1) ──→ (N) document_index_job
sys_user (1) ──→ (N) conversation
conversation (1) ──→ (N) message
sys_user (1) ──→ (N) note            （笔记归属）
knowledge_base (1) ──→ (N) kb_share  （共享记录）
sys_user (1) ──→ (N) app → (N) app_api_key
```

## 连接配置

见 `java-backend/src/main/resources/application.yml`：

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/hfusionhub?useUnicode=true&characterEncoding=utf-8&useSSL=false&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true
    username: ${DB_USERNAME:hfusionhub}
    password: ${DB_PASSWORD:}
```

容器化部署用 `SPRING_DATASOURCE_URL` 覆盖（如 `jdbc:mysql://mysql8:3306/hfusionhub?...`），生产 Compose 与 Helm 已配置。

## 可视化 Schema

使用任意 MySQL 客户端（DBeaver/DataGrip/Workbench）连接：
- 主机：`localhost`，端口：`3306`
- 数据库：`hfusionhub`，用户：`hfusionhub`
- 密码：`docker/.env` 的 `MYSQL_PASSWORD`
