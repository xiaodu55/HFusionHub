# 发布渠道：可嵌入挂件与 IM 机器人（Batch 6）

> 三种对外发布形态共用同一套鉴权与计费底座：**开放 API Key（app_api_key）→ 已发布应用 → 绑定知识库**。
> 所有回调端点挂在 `/openapi/**`（无需登录态，Sa-Token 已放行），限流 60 次/分钟/Key，
> 每次调用写入 `app_call_log` 审计。

## 1. 可嵌入聊天挂件

**页面**：`/embed/chat?key=<开放API Key>`（Vue 3 独立路由，无需登录态，iframe 友好）。

**后端**：`POST /api/openapi/chat/stream`（SSE）— 与 `/openapi/chat` 同一套
Key 解析/限流/计费，流式经 Agent V1 通道转发（要求应用绑定知识库）。

**接入示例**：

```html
<iframe
  src="https://your-host/embed/chat?key=hfk_live_xxx"
  style="width:420px;height:640px;border:0;border-radius:12px"
  allow="clipboard-write"
></iframe>
```

事件契约（SSE `data:` 行）：
- `{"content":"分片文本",...}` — 内容增量（与 Python `agent/v1/chat/stream` 一致）
- `{"event":"run_completed","token_usage":{...}}` — 运行结束（计费提取点）
- `[DONE]` — 流终止

## 2. IM 机器人适配器

配置前缀 `bots.*`（`BotProperties`，**全部默认关闭**）。每个机器人绑定一个
开放 API Key 作为「回答服务」；应用绑定的知识库决定回答范围与风格。

### 钉钉（企业内部机器人 · HTTP 回调模式）

```yaml
bots:
  dingtalk:
    enabled: true
    app-key: hfk_live_xxx        # 开放 API Key
    app-secret: <加签密钥>        # 钉钉后台「消息接收模式」生成的 secret
```

- 端点：`POST /api/openapi/bots/dingtalk`
- 校验：请求头 `timestamp` + `sign`，`sign = Base64(HMAC-SHA256(secret, timestamp+"\n"+secret))`（常量时间比较）
- 回复：POST 回调体自带的 `sessionWebhook`（text 消息）

### 飞书（事件订阅 · 明文模式）

```yaml
bots:
  feishu:
    enabled: true
    app-key: hfk_live_xxx
    app-id: cli_xxx
    app-secret: xxx
    verification-token: xxx      # 事件订阅页的 Verification Token
```

- 端点：`POST /api/openapi/bots/feishu`
- 支持 `url_verification`（challenge 回显）与 `im.message.receive_v1`（文本消息）
- 校验：`header.token` 与 verification-token 常量时间比较
- 回复：飞书 IM API（tenant_access_token 进程内缓存 + 发送消息，receive_id_type=chat_id）
- 加密模式（encrypt_key）暂不支持

### 企业微信（自建应用回调）

```yaml
bots:
  wecom:
    enabled: true
    app-key: hfk_live_xxx
    corp-id: xxx
    corp-secret: xxx
    agent-id: 1000002
    token: xxx                   # 回调配置页 Token
    encoding-aes-key: xxx        # 43 位 EncodingAESKey
```

- 端点：`GET/POST /api/openapi/bots/wecom`
- 协议：官方加解密标准（SHA1 签名 + AES-256-CBC/PKCS7，纯 JDK 实现见 `WeComCrypto`，含 round-trip 测试）
- 回复：企业微信「应用消息」接口（access_token 进程内缓存）

## 3. 安全与运维要点

- **密钥来源**：`app-key`/`app-secret` 一律走环境变量或配置中心，禁止入库明文。
- **失效半径**：机器人 appKey 与普通开放 API Key 同源——在「应用中心」停用 Key 即可即时下线机器人回答能力。
- **审计**：每次回答在 `app_call_log` 留痕（调用方 = 对应应用），配额与计费走 `usage_ledger`。
- **默认关闭**：三个适配器 `enabled=false` 时不处理任何消息（直接返回 disabled）。
