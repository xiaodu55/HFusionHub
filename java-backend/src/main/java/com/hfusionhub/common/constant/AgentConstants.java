package com.hfusionhub.common.constant;

import java.util.Map;
import java.util.Set;

/**
 * Agent 任务状态机常量
 *
 * @author HFusionHub Team
 */
public interface AgentConstants {

    // ============================================================
    // 任务/Run 状态
    // ============================================================

    /** 待执行 */
    String STATUS_PENDING = "pending";

    /** 执行中 */
    String STATUS_RUNNING = "running";

    /** 等待审批（V1 read_only 暂不使用，预留给写入工具） */
    String STATUS_WAITING_APPROVAL = "waiting_approval";

    /** 执行成功 */
    String STATUS_SUCCEEDED = "succeeded";

    /** 执行失败 */
    String STATUS_FAILED = "failed";

    /** 用户取消 */
    String STATUS_CANCELLED = "cancelled";

    /** 执行超时 */
    String STATUS_TIMED_OUT = "timed_out";

    /** 终态集合 */
    Set<String> TERMINAL_STATUSES = Set.of(
            STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED, STATUS_TIMED_OUT
    );

    /** 可重试状态 */
    Set<String> RETRYABLE_STATUSES = Set.of(STATUS_FAILED, STATUS_TIMED_OUT);

    /**
     * 校验状态转移是否合法
     */
    static boolean canTransition(String from, String to) {
        if (from == null || to == null) return false;
        // 终态不可再转移
        if (TERMINAL_STATUSES.contains(from)) return false;
        return switch (from) {
            case STATUS_PENDING -> Set.of(STATUS_RUNNING, STATUS_CANCELLED).contains(to);
            case STATUS_RUNNING -> Set.of(STATUS_SUCCEEDED, STATUS_FAILED,
                    STATUS_CANCELLED, STATUS_TIMED_OUT, STATUS_WAITING_APPROVAL).contains(to);
            case STATUS_WAITING_APPROVAL -> Set.of(STATUS_RUNNING, STATUS_FAILED,
                    STATUS_CANCELLED, STATUS_TIMED_OUT).contains(to);
            default -> false;
        };
    }

    /**
     * 将 Python Agent 返回的状态映射到合约终态。
     * Python 侧使用 completed / timeout / tool_error 等自然语义，
     * 持久化层必须统一为合约值：succeeded / failed / cancelled / timed_out。
     *
     * @param pythonStatus Python SSE 事件中的 status 字段
     * @return 合约终态值
     */
    static String mapPythonStatus(String pythonStatus) {
        if (pythonStatus == null) return STATUS_FAILED;
        return switch (pythonStatus) {
            case "completed", "insufficient_evidence" -> STATUS_SUCCEEDED;
            case "timeout" -> STATUS_TIMED_OUT;
            case "tool_error", "agent_failure" -> STATUS_FAILED;
            case "cancelled" -> STATUS_CANCELLED;
            default -> {
                // 未识别状态 — 拒绝透传，记为 failed
                yield STATUS_FAILED;
            }
        };
    }

    /**
     * 校验 status 是否为合法的终态值（仅限合约定义的四态）。
     */
    static boolean isValidTerminalStatus(String status) {
        return status != null && TERMINAL_STATUSES.contains(status);
    }

    // ============================================================
    // 步骤类型
    // ============================================================

    /** 意图分类 */
    String STEP_INTENT_CLASSIFICATION = "intent_classification";

    /** 知识检索 */
    String STEP_RETRIEVAL = "retrieval";

    /** 工具调用 */
    String STEP_TOOL_CALL = "tool_call";

    /** 模型生成 */
    String STEP_MODEL_GENERATION = "model_generation";

    /** 自我反思 */
    String STEP_REFLECTION = "reflection";

    /** 基础性检查 */
    String STEP_GROUNDING_CHECK = "grounding_check";

    // ============================================================
    // 错误码
    // ============================================================

    /** 执行超时 */
    String ERR_TIMEOUT = "timeout";

    /** 连接错误 */
    String ERR_CONNECTION_ERROR = "connection_error";

    /** 工具执行错误 */
    String ERR_TOOL_ERROR = "tool_error";

    /** 内部错误 */
    String ERR_INTERNAL_ERROR = "internal_error";

    /** 用户取消 */
    String ERR_CANCELLED = "cancelled";

    // ============================================================
    // 摘要长度限制
    // ============================================================

    /** 输入摘要最大长度 */
    int INPUT_SUMMARY_MAX_LENGTH = 2000;

    /** 输出摘要最大长度 */
    int OUTPUT_SUMMARY_MAX_LENGTH = 2000;

    /** 查询摘要最大长度（列表展示） */
    int QUERY_SUMMARY_MAX_LENGTH = 100;
}
