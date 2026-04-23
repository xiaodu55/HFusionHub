package com.hfusionhub.webhook;

/**
 * Webhook 支持的事件类型常量
 *
 * @author HFusionHub Team
 */
public final class WebhookEventTypes {

    /** Agent 任务完成 */
    public static final String AGENT_TASK_COMPLETED = "agent.task.completed";

    /** Agent 任务失败 */
    public static final String AGENT_TASK_FAILED = "agent.task.failed";

    /** Agent 任务需要审批 */
    public static final String AGENT_APPROVAL_REQUIRED = "agent.approval.required";

    /** 文档索引完成 */
    public static final String DOCUMENT_INDEXED = "document.indexed";

    /** 离线评测完成 */
    public static final String EVALUATION_COMPLETED = "evaluation.completed";

    private WebhookEventTypes() {}
}
