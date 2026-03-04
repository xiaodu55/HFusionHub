# Agent V1 — 知识库研究 Agent 设计说明

> **契约版本**: `agent_v1_contract: "1.0"`
> 版本：1.0 | 状态：**Accepted** | 作者：HFusionHub | 日期：2026-07-29
>
> 本文档是 Agent V1 的**唯一权威范围定义**。所有前后端、Java/Python 实现必须与此文档一致。
> 任何偏离需先更新本文档并经过评审。

## 1. Agent 目标与非目标

### 1.1 目标（Goals）

Agent V1 是一个**只读研究型 Agent**，在用户选定一个知识库后，执行以下任务：

| 能力 | 说明 |
|------|------|
| **语义检索** | 在选定知识库内执行向量检索（Milvus Lite），返回最相关的文档分块 |
| **关键词检索** | 通过 BM25 倒排索引执行关键词级精确匹配（Hybrid 模式下自动融合） |
| **阅读理解** | 读取检索到的分块全文，理解其语义并提炼关键信息 |
| **多分块汇总** | 跨多个分块/文档综合信息，生成连贯回答 |
| **问答（QA）** | 根据用户问题，从知识库中找到答案并引用原文 |
| **摘要生成** | 对单篇文档或整个知识库生成结构化摘要 |
| **报告草稿** | 综合多来源信息，生成带章节结构和来源引用的报告初稿 |
| **来源引用** | 每个断言都附带 `document_id`、`chunk_id`、`title` 和 `excerpt` |
| **证据不足声明** | 当知识库中无法找到足够依据时，明确告知用户而非编造 |

### 1.2 非目标（Non-Goals / 明确禁止）

以下操作**不在 Agent V1 范围内**，任何开发者均可据此判断新功能是否属于 V1：

| 禁止的操作 | 原因 |
|-----------|------|
| **创建/修改/删除知识库** | 写操作属于 Java 后端权限边界 |
| **上传/修改/删除文档** | 同上，且涉及文件系统写操作 |
| **修改对话/消息记录** | 对话持久化由 Java 管理 |
| **调用外部 HTTP 服务** | Agent 不得访问互联网或第三方 API |
| **执行数据库写入** | MySQL/Redis/Milvus 写入均禁止 |
| **访问其他用户数据** | 仅限当前用户选定的知识库 |
| **访问未选定知识库的数据** | 每次调用必须绑定单一 `knowledge_base_id` |
| **执行代码或系统命令** | 无 shell/exec 权限 |
| **记忆持久化（跨会话）** | 会话记忆由上层 Java Memory 模块管理，Agent 不直接写入 |
| **多 Agent 协作** | 属于 P10 实验特性，不在 V1 范围 |
| **多模态处理（OCR/图片）** | 属于 P8 实验特性，不在 V1 范围 |

---

## 2. 输入/输出 JSON 契约

### 2.1 输入（Request）

```json
{
  "query": "string (必填) — 用户自然语言问题",
  "knowledge_base_id": "integer (必填) — 目标知识库 ID",
  "style": "string (可选) — 回答风格：concise | detailed | report，默认 detailed",
  "document_ids": ["integer (可选) — 限定检索的文档 ID 列表，空数组或省略表示全库检索"],
  "history": [
    {
      "role": "user | assistant",
      "content": "string"
    }
  ],
  "max_tool_steps": "integer (可选) — 最大 ReAct 步数，默认 5，范围 1–10",
  "temperature": "number (可选) — LLM 采样温度，默认 0.3"
}
```

字段说明：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | string | 是 | — | 用户自然语言问题 |
| `knowledge_base_id` | integer | 是 | — | 目标知识库 ID，Java 层已校验所有权 |
| `style` | enum | 否 | `"detailed"` | `concise`（≤200 字）、`detailed`（段落级）、`report`（章节结构） |
| `document_ids` | integer[] | 否 | `[]`（全库） | 限定检索范围，空数组表示不限定 |
| `history` | object[] | 否 | `[]` | 标准 OpenAI 多轮对话格式 |
| `max_tool_steps` | integer | 否 | `5` | ReAct 循环最大步数 |
| `temperature` | number | 否 | `0.3` | 低温度以抑制幻觉 |

### 2.2 输出（Response）

> **Java 兼容性**：`content` 是 Java `AiClient.ChatResponse.content` 的主字段；
> `answer` 是 V1 镜像字段（值始终与 `content` 相同）。
> `token_count` 是 Java `tokenCount` 的 JSON 键名；
> `token_usage` 是 V1 的结构化替代。

#### 2.2.1 正常完成

```json
{
  "content": "string — 最终回答（Markdown 格式，支持标题、列表、加粗、表格）",
  "answer": "string — 与 content 相同的 V1 镜像字段",
  "sources": [
    {
      "document_id": 4,
      "chunk_id": "4_chunk_0000",
      "title": "2025年度财务报告.pdf",
      "excerpt": "2025年全年营收达到12.8亿元，同比增长23.4%……",
      "score": 0.923
    }
  ],
  "status": "completed",
  "agent_run_id": "uuid — 此次运行的唯一标识",
  "model": "deepseek-v4-flash",
  "token_count": 1650,
  "token_usage": {
    "prompt_tokens": 1200,
    "completion_tokens": 450,
    "total_tokens": 1650
  },
  "tool_calls_count": 3,
  "style_used": "detailed",
  "max_tool_steps": 5
}
```

#### 2.2.2 证据不足

```json
{
  "content": "当前知识库中未检索到足够依据来回答该问题。建议：1) 确认知识库是否包含相关文档；2) 尝试更换关键词重新提问。",
  "answer": "当前知识库中未检索到足够依据来回答该问题。建议：1) 确认知识库是否包含相关文档；2) 尝试更换关键词重新提问。",
  "sources": [],
  "status": "insufficient_evidence",
  "agent_run_id": "uuid",
  "model": "",
  "token_count": 860,
  "token_usage": {
    "prompt_tokens": 800,
    "completion_tokens": 60,
    "total_tokens": 860
  },
  "tool_calls_count": 1,
  "style_used": "detailed"
}
```

#### 2.2.3 工具执行失败

```json
{
  "content": "抱歉，检索服务暂时不可用。请稍后重试或联系管理员。",
  "answer": "抱歉，检索服务暂时不可用。请稍后重试或联系管理员。",
  "sources": [],
  "status": "tool_error",
  "agent_run_id": "uuid",
  "error_detail": "Milvus search timeout after 5000ms",
  "failed_tool": "search_knowledge_base",
  "tool_calls_count": 1
}
```

#### 2.2.4 超时

```json
{
  "content": "处理超时。已执行的检索步骤结果如下：……",
  "answer": "处理超时。已执行的检索步骤结果如下：……",
  "sources": [
    {
      "document_id": 2,
      "chunk_id": "2_chunk_0003",
      "title": "产品手册v3.pdf",
      "excerpt": "……",
      "score": 0.87
    }
  ],
  "status": "timeout",
  "agent_run_id": "uuid",
  "token_usage": {
    "prompt_tokens": 1500,
    "completion_tokens": 200,
    "total_tokens": 1700
  },
  "tool_calls_count": 4,
  "max_tool_steps": 5
}
```

### 2.3 状态码（status）

| status | 含义 | sources 是否可能非空 |
|--------|------|---------------------|
| `completed` | 正常完成，回答基于检索到的证据 | 是 |
| `insufficient_evidence` | 检索完成但无足够依据 | 否（空数组） |
| `tool_error` | 工具调用失败（向量库不可用等） | 可能（部分结果） |
| `timeout` | 超过最大步数或时间限制 | 可能（中途结果） |

### 2.4 来源引用字段（sources[]）

| 字段 | 类型 | 说明 |
|------|------|------|
| `document_id` | integer | 文档 ID（MySQL 主键） |
| `chunk_id` | string | 分块 ID，格式 `{doc_id}_chunk_{seq:04d}` |
| `title` | string | 文档标题（从 Milvus metadata 读取，索引时写入） |
| `excerpt` | string | 支持该回答的原文片段（≤300 字） |
| `score` | number | 向量相似度分数（0–1，COSINE） |

**前后端/Java/Python 一致性约定**：
- `content` 是 Java `AiClient.ChatResponse.content` 反序列化的主字段（JSON key: `"content"`）
- `answer` 是 V1 镜像字段，值始终与 `content` 相同（JSON key: `"answer"`）
- `token_count` 是 Java `tokenCount` 的 JSON 键名（`@JsonProperty("token_count")`）
- `token_usage` 是 V1 的结构化替代（`{prompt_tokens, completion_tokens, total_tokens}`）
- `document_id` 对应 Java `Document` 实体和 MySQL `document` 表的 `id` 字段
- `chunk_id` 由 Python chunker 生成，格式固定为 `{doc_id}_chunk_{seq:04d}`
- `title` 来自 Milvus metadata 中的 `document_title`，在 Java 调用 Python 索引时传入
- `excerpt` 由 Python Agent 在组织最终回答时截取，不超过 300 字符
- `score` 使用 COSINE 距离，范围 [0, 1]，越高越相关

---

## 3. 允许的工具清单

Agent V1 仅可调用以下**白名单工具**。任何未列出的工具调用将被工作流运行时拒绝。

### 3.1 search_knowledge_base（核心工具）

| 属性 | 值 |
|------|-----|
| **功能** | 在选定知识库中执行向量检索（Hybrid 模式下融合 BM25） |
| **输入** | `query: string`, `top_k: int (默认 5, 最大 20)`, `knowledge_base_id: int` |
| **输出** | `[{content, score, document_id, document_name, chunk_id, outline_path}]` |
| **实现** | `app/core/tools/search_tool.py` → `vectorstore/milvus_store.py` |
| **限制** | `knowledge_base_id` 必须等于请求中的 `knowledge_base_id`，不允许跨库检索 |

### 3.2 read_chunk（读取分块全文）

| 属性 | 值 |
|------|-----|
| **功能** | 读取指定分块的完整文本内容 |
| **输入** | `chunk_id: string`, `knowledge_base_id: int` |
| **输出** | `{chunk_id, content, document_id, title, metadata}` |
| **实现** | 通过 Milvus 主键查询（`get_entity_by_id`） |
| **限制** | 单次仅读取一个分块；批量读取通过多次调用实现 |

### 3.3 list_document_chunks（列出文档所有分块）

| 属性 | 值 |
|------|-----|
| **功能** | 列出指定文档在知识库中的所有分块概览（不含全文） |
| **输入** | `document_id: int`, `knowledge_base_id: int` |
| **输出** | `[{chunk_id, excerpt（前200字）, score: null}]` |
| **实现** | Milvus 过滤查询 `document_id == {id}` |
| **限制** | 最多返回 100 条；超过时返回前 100 条并附带 `truncated: true` |

### 3.4 不在此列表中的工具明确禁止

以下工具在代码库中存在但**不属于 Agent V1 白名单**：
- `calculator_tool` — 通用计算，非知识库研究所需
- `time_tool` — 通用时间查询，非知识库研究所需
- `web_search_tool` — 涉及外部 HTTP 调用，禁止
- 任何未来新增工具均需更新本文档才能加入白名单

---

## 4. 权限边界

### 4.1 架构级权限模型

```
用户请求 → Java (Sa-Token JWT 鉴权)
              │
              ├─ 校验：用户是否拥有该 knowledge_base_id
              ├─ 校验：用户是否有该 KB 的读权限
              │
              ├─ 通过 → Python AI (:9000) + X-Internal-Token
              │           │
              │           └─ Agent V1 仅调用白名单工具
              │              仅访问 knowledge_base_id 绑定的 Milvus 分区
              │
              └─ 拒绝 → HTTP 403（不进入 Python 层）
```

### 4.2 安全约束清单

| 层级 | 约束 | 实施位置 |
|------|------|---------|
| **传输** | Java→Python 需带 `X-Internal-Token`，常量时间比较 | Python 中间件 |
| **知识库隔离** | 仅能访问请求中 `knowledge_base_id` 对应的 Milvus 分区 | SearchTool |
| **无写操作** | 不调用任何 MySQL/Redis/Milvus 写入方法 | 代码审查 + 工具白名单 |
| **无外部调用** | 不调用 `httpx`/`requests`/`aiohttp` 到外部 URL | 工具白名单 |
| **步数上限** | `max_tool_steps` 上限 10，硬编码在 WorkflowRuntime | Python Agent |
| **超时限制** | 单次 Agent 运行最长 45 秒（P9 已实现） | WorkflowRuntime |
| **重试策略** | 工具调用失败重试 1 次，间隔 0.2 秒（P9 已实现） | WorkflowRuntime |

---

## 5. 异常场景响应规范

### 5.1 无证据（insufficient_evidence）

**触发条件**：
- 所有检索返回的 chunk `score < 0.5`（低相似度阈值）
- 检索返回 0 条结果
- Agent 自我反思后判断无法回答

**响应**：见 §2.2.2。

**要求**：
- `sources` 必须为空数组 `[]`
- `answer` 必须包含建设性建议（换关键词、确认文档范围等）
- 禁止编造内容或引用不存在的来源

### 5.2 工具失败（tool_error）

**触发条件**：
- Milvus Lite 不可用（进程崩溃、文件锁）
- 向量检索超时（单次 >5s）
- Python 内部异常（OOM、索引损坏）

**响应**：见 §2.2.3。

**要求**：
- `status: "tool_error"`
- `failed_tool` 指明失败的工具名称
- `error_detail` 包含技术细节（供调试，不暴露敏感信息）
- 如果已有部分检索结果，可填充 `sources`
- `answer` 应是用户友好的错误提示，不含技术堆栈

### 5.3 超时（timeout）

**触发条件**：
- ReAct 循环达到 `max_tool_steps` 上限
- WorkflowRuntime 45 秒总超时触发

**响应**：见 §2.2.4。

**要求**：
- `status: "timeout"`
- 返回已完成的检索步骤中获得的 sources
- `answer` 应基于已有结果给出部分回答，而非仅报错
- 包含 `max_tool_steps` 字段告知用户限制

### 5.4 知识库为空

```json
{
  "answer": "该知识库中暂无文档。请先上传文档并等待索引完成后重试。",
  "sources": [],
  "status": "insufficient_evidence",
  "agent_run_id": "uuid",
  "tool_calls_count": 1
}
```

**触发条件**：知识库存在但无已索引文档（Milvus 分区为空）。

---

## 6. 典型用户场景与预期输出

### 场景 1：单文档事实查询

**用户输入**：
```json
{
  "query": "2025年Q3的销售总额是多少？",
  "knowledge_base_id": 1,
  "style": "concise"
}
```

**Agent 执行过程**：
1. ReAct Step 1 — `search_knowledge_base(query="2025年Q3 销售总额", top_k=5, knowledge_base_id=1)` → 返回 3 个相关 chunk
2. ReAct Step 2 — 判断 top-1 chunk 已包含明确数字，无需进一步检索
3. 生成回答

**预期输出**：
```json
{
  "answer": "2025年Q3销售总额为**3.42亿元**，环比增长8.7%。",
  "sources": [
    {
      "document_id": 7,
      "chunk_id": "7_chunk_0012",
      "title": "2025年季度销售汇总.xlsx",
      "excerpt": "第三季度实现销售额3.42亿元，较Q2的3.15亿元环比增长8.7%……",
      "score": 0.961
    }
  ],
  "status": "completed",
  "agent_run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "token_usage": { "prompt_tokens": 620, "completion_tokens": 80, "total_tokens": 700 },
  "tool_calls_count": 1,
  "style_used": "concise"
}
```

---

### 场景 2：跨文档综合分析（Report 风格）

**用户输入**：
```json
{
  "query": "总结公司2025年全年的财务表现、主要风险和市场策略",
  "knowledge_base_id": 1,
  "style": "report"
}
```

**Agent 执行过程**：
1. ReAct Step 1 — `search_knowledge_base("2025年 财务表现 营收 利润", top_k=5)` → 3 chunks
2. ReAct Step 2 — `search_knowledge_base("2025年 风险 挑战 行业", top_k=5)` → 2 chunks
3. ReAct Step 3 — `search_knowledge_base("2025年 市场策略 规划 目标", top_k=5)` → 3 chunks
4. ReAct Step 4 — 对关键 chunk 调用 `read_chunk` 获取完整上下文
5. ReAct Step 5 — 汇总并生成结构化报告

**预期输出**：
```json
{
  "answer": "## 2025年公司年度综合分析报告\n\n### 一、财务表现\n2025年全年营收达到12.8亿元，同比增长23.4%……\n\n### 二、主要风险\n1. **供应链风险**：原材料价格波动……\n2. **竞争风险**：……\n\n### 三、市场策略\n……\n\n---\n*本报告基于知识库中3份文档自动生成。*",
  "sources": [
    {
      "document_id": 4,
      "chunk_id": "4_chunk_0000",
      "title": "2025年度财务报告.pdf",
      "excerpt": "2025年全年营收达到12.8亿元，同比增长23.4%……",
      "score": 0.923
    },
    {
      "document_id": 4,
      "chunk_id": "4_chunk_0005",
      "title": "2025年度财务报告.pdf",
      "excerpt": "净利润2.1亿元，净利率16.4%……",
      "score": 0.891
    },
    {
      "document_id": 9,
      "chunk_id": "9_chunk_0002",
      "title": "风险管理季度评估-Q4.pdf",
      "excerpt": "主要风险包括原材料价格波动（影响毛利率约3个百分点）……",
      "score": 0.867
    },
    {
      "document_id": 12,
      "chunk_id": "12_chunk_0001",
      "title": "2026年市场战略规划.docx",
      "excerpt": "2025年执行的市场策略包括：渠道下沉、产品线扩展……",
      "score": 0.845
    }
  ],
  "status": "completed",
  "agent_run_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "token_usage": { "prompt_tokens": 2800, "completion_tokens": 950, "total_tokens": 3750 },
  "tool_calls_count": 5,
  "style_used": "report"
}
```

---

### 场景 3：知识库无相关文档

**用户输入**：
```json
{
  "query": "公司2025年在欧洲市场的具体营收数据",
  "knowledge_base_id": 3,
  "style": "detailed"
}
```

**知识库 3 内容**：仅包含国内市场的销售数据。

**Agent 执行过程**：
1. ReAct Step 1 — `search_knowledge_base("欧洲市场 营收 2025", top_k=5)` → 最高 score 0.31
2. ReAct Step 2 — `search_knowledge_base("海外 国际 欧洲 收入 2025", top_k=5)` → 最高 score 0.28
3. LLM 自我反思：无 chunk 达到相关度阈值（<0.5），无法回答

**预期输出**：
```json
{
  "answer": "当前知识库中未检索到关于2025年欧洲市场营收的具体数据。知识库中的文档主要覆盖国内市场销售情况。建议：1) 确认是否已上传欧洲市场的相关报告；2) 尝试使用"海外收入"或"国际市场"等关键词重新提问。",
  "sources": [],
  "status": "insufficient_evidence",
  "agent_run_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "token_usage": { "prompt_tokens": 720, "completion_tokens": 95, "total_tokens": 815 },
  "tool_calls_count": 2,
  "style_used": "detailed"
}
```

---

## 7. 与现有系统的关系

### 7.1 与 P9 Bounded Single-Agent Workflow 的关系

Agent V1 复用 P9（`RAG_AGENT_WORKFLOW_ENABLED`）的运行时基础设施：
- 工具白名单校验：`WorkflowRuntime` 的 `allowed_tools` 配置
- 超时控制：45 秒硬限制
- 重试策略：1 次重试，0.2 秒间隔
- 运行追踪：`agent_run_id` 全局唯一标识

V1 在此基础上进一步**收窄工具白名单**，仅开放知识库研究相关工具。

### 7.2 与 MCP 协议的关系

Agent V1 的工具通过现有 MCP JSON-RPC 2.0 端点暴露（`/mcp`），`tools/call` 需带 `X-Internal-Token` + `X-HFusionHub-KB-ID`。前端可选择直接调用 MCP 端点或通过 Java SSE 代理。

### 7.3 与 Java 后端的关系

- Java 负责：鉴权、KB 所有权校验、对话持久化、SSE 转发
- Python 负责：检索、Agent 推理、LLM 调用、响应组装
- Agent V1 的 JSON 契约由 Python 组装，Java 透传（可能在 Java 侧做字段校验）

---

## 8. 验收标准（Acceptance Criteria）

1. **可判定性**：任意开发者能根据 §1 的目标/非目标列表判断某个新功能是否属于 Agent V1。
2. **写操作排除**：所有写操作（CRUD、上传、删除、外部调用）明确列在非目标中。
3. **字段一致性**：前后端、Java、Python 对 §2 中所有响应字段的含义理解一致：
   - `document_id` = MySQL `document.id`
   - `chunk_id` = `{doc_id}_chunk_{seq:04d}`
   - `status` 枚举值仅限 4 种
   - `sources[].score` 使用 COSINE 距离
4. **工具白名单完整**：§3 列出的工具与 WorkflowRuntime 白名单一致，未列出的工具不可调用。
5. **异常覆盖完整**：§5 覆盖了无证据、工具失败、超时、空知识库四种异常场景。
6. **场景可复现**：§6 中 3 个场景的输入可在当前系统中构造并验证输出格式。

---

## 9. 附录：字段对照表（Java ↔ Python ↔ 前端）

| 概念 | MySQL / Java | Python (Milvus metadata) | JSON Response 字段 |
|------|-------------|--------------------------|-------------------|
| 回答文本 (Java主) | `AiClient.ChatResponse.content` | `AgentResponse.content` | `content` |
| 回答文本 (V1镜像) | `AiClient.ChatResponse.answer` | `AgentResponse.answer` | `answer` |
| Token 计数 (Java) | `AiClient.ChatResponse.tokenCount` | `AgentResponse.token_count` | `token_count` |
| Token 明细 (V1) | `AiClient.ChatResponse.tokenUsage` | `AgentResponse.token_usage` | `token_usage` |
| 文档主键 | `document.id` (BIGINT) | `document_id` (int) | `sources[].document_id` |
| 分块标识 | 不直接存储 | `chunk_id` (str, 如 `4_chunk_0000`) | `sources[].chunk_id` |
| 文档标题 | `document.title` (VARCHAR) | `document_title` (metadata) | `sources[].title` |
| 分块内容 | 不直接存储 | `content` (VARCHAR) | `sources[].excerpt` (截取 ≤300 字) |
| 相似度 | — | COSINE distance | `sources[].score` (0–1) |
| 运行标识 | `AiClient.ChatResponse.agentRunId` | `agent_run_id` (UUID) | `agent_run_id` |
| 执行状态 | `AiClient.ChatResponse.status` | `status` (enum) | `status` |
| 工具调用次数 | `AiClient.ChatResponse.toolCallsCount` | `tool_calls_count` | `tool_calls_count` |
| 回答风格 | `AiClient.ChatResponse.styleUsed` | `style_used` | `style_used` |
| 最大步数 | `AiClient.ChatResponse.maxToolSteps` | `max_tool_steps` | `max_tool_steps` |
| 错误详情 | `AiClient.ChatResponse.errorDetail` | `error_detail` | `error_detail` |
| 失败工具 | `AiClient.ChatResponse.failedTool` | `failed_tool` | `failed_tool` |

---

*本文档为 Agent V1 的唯一权威范围定义。任何偏离本文档的行为需先更新本文档并经过评审。*
