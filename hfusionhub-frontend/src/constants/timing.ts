/**
 * 全局共享的轮询/重试时序常量（毫秒）。
 * 收敛散落在各页面的延时魔法数字，调整节奏时只改这里。
 */

/** 主布局：待审批数量轮询间隔 */
export const APPROVAL_POLL_INTERVAL_MS = 30_000
/** 主布局：未读公告数轮询间隔（每 2 个审批轮询周期触发一次） */
export const NOTICE_POLL_INTERVAL_MS = 60_000

/** 对话详情：会话重载延时 */
export const CHAT_RELOAD_DELAY_MS = 2_500
/** 对话详情：SSE 网络错误自动重试延时 */
export const CHAT_RETRY_DELAY_MS = 800
/** 对话详情：写入审批状态检查间隔 */
export const CHAT_APPROVAL_CHECK_INTERVAL_MS = 1_500

/** 回归用例：测试运行状态轮询间隔 */
export const TEST_RUN_POLL_INTERVAL_MS = 1_500

/** 文档处理：解析状态轮询间隔 */
export const DOCUMENT_PARSE_POLL_INTERVAL_MS = 2_000
