package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.AgentTaskDetailDTO;
import com.hfusionhub.dto.AgentTaskSummaryDTO;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;
import java.util.List;
import java.util.Map;

/**
 * Agent 任务状态机服务接口
 *
 * @author HFusionHub Team
 */
public interface AgentTaskService {

    // ================================================================
    // 生命周期方法
    // ================================================================

    /**
     * 创建任务（幂等：相同 requestId 返回已有任务）
     *
     * @param requestId      客户端幂等键
     * @param userId         用户ID
     * @param conversationId 对话ID
     * @param kbId           知识库ID（可选）
     * @param query          原始问题
     * @return 任务实体
     */
    AgentTask createTask(String requestId, Long userId, Long conversationId, Long kbId, String query);

    /**
     * 开始一次运行（task: pending → running，创建 agent_run）
     *
     * @param taskId 任务ID
     * @param runUuid Python agent_run_id
     * @param model  模型名称
     * @param style  回答风格
     * @param maxToolSteps 最大工具步数
     * @return 运行实体
     */
    AgentRun startRun(Long taskId, String runUuid, String model, String style, int maxToolSteps);

    /**
     * 开始一次运行（带租约持有者）
     *
     * @param taskId      任务ID
     * @param runUuid     Python agent_run_id
     * @param model       模型名称
     * @param style       回答风格
     * @param maxToolSteps 最大工具步数
     * @param leaseHolder 租约持有者（流式路径传 "stream:..."，Worker 传 worker ID）
     * @return 运行实体
     */
    AgentRun startRun(Long taskId, String runUuid, String model, String style, int maxToolSteps, String leaseHolder);

    /**
     * 记录一个步骤
     *
     * @param runId        运行ID
     * @param sequence     步骤序号
     * @param stepType     步骤类型
     * @param action       动作名
     * @param inputSummary 输入摘要
     * @param outputSummary 输出摘要
     * @param sources      引用来源
     * @param durationMs   耗时(ms)
     * @param errorCode    错误码
     */
    void recordStep(
            Long runId,
            int sequence,
            String stepType,
            String action,
            String inputSummary,
            String outputSummary,
            List<Map<String, Object>> sources,
            long durationMs,
            String errorCode);

    /**
     * 完成一次运行（run → 终态，task → 终态）
     */
    void completeRun(
            Long runId,
            String status,
            String model,
            Map<String, Object> tokenUsage,
            int toolCallsCount,
            long durationMs,
            String errorCode,
            String errorDetail,
            String failedTool);

    /**
     * 标记运行失败并关闭任务
     */
    void failRun(Long runId, String errorCode, String errorDetail, String failedTool);

    /**
     * 标记运行被取消并关闭任务
     */
    void cancelRun(Long runId);

    /**
     * 预占 AGENT_TOKENS 用量（幂等，以 run_uuid 为键）。
     *
     * <p>在运行真正执行前调用：流式路径在 startRun，队列路径在 Worker 认领后。
     * 预占上界 = 输入估算 + 服务端最大输出 × (maxToolSteps + 1)。失败抛
     * QUOTA_EXCEEDED，已存在的重复预占幂等跳过。</p>
     *
     * @param runId 运行ID
     */
    void reserveAgentRunUsage(Long runId);

    /**
     * 结算/退回 AGENT_TOKENS 用量（幂等，以 run_uuid 为键）。
     *
     * <p>在每次终态转移处调用：{@link #completeRun}（含 failRun/cancelRun）、
     * 审批恢复、队列直接 completeRunGuarded 的超时/看门狗/孤儿、supersede 等。
     * status 为 succeeded 时按实际 total_tokens 结算（封顶预占），其余一律退回。</p>
     *
     * @param runId      运行ID
     * @param status     终态（succeeded 结算，其余退回）
     * @param tokenUsage 实际 token 用量（可为 null，此时结算 0）
     */
    void finalizeAgentRunUsage(Long runId, String status, java.util.Map<String, Object> tokenUsage);

    // ================================================================
    // 查询方法
    // ================================================================

    /**
     * 按任务ID查询详情（含所有 run 和 step 时间线）
     */
    AgentTaskDetailDTO getTaskDetail(Long taskId);

    /**
     * 按幂等键查询详情
     */
    AgentTaskDetailDTO getTaskByRequestId(String requestId);

    /**
     * 按用户ID分页查询任务列表
     */
    PageResult<AgentTaskSummaryDTO> listUserTasks(Long userId, String status, int page, int pageSize);

    /**
     * 按任务ID查所有 run（用于取消时查找活跃 run）
     */
    List<AgentRun> getRunsByTaskId(Long taskId);

    /**
     * 按 run ID 查询单个 run
     */
    AgentRun getRunById(Long runId);

    // ================================================================
    // 操作方法
    // ================================================================

    /**
     * 重试失败/超时任务
     *
     * @param taskId 任务ID
     * @param userId 操作用户ID（校验所有权）
     * @return 新创建的 AgentRun
     */
    AgentRun retryTask(Long taskId, Long userId);

    /**
     * 取消运行中的任务
     *
     * @param taskId 任务ID
     * @param userId 操作用户ID（校验所有权）
     * @return 是否成功取消
     */
    boolean cancelTask(Long taskId, Long userId);

    // ================================================================
    // Agent V1 Step 5: 审批方法
    // ================================================================

    /**
     * 暂停任务等待审批（running → waiting_approval）
     *
     * @param taskId           任务ID
     * @param runId            运行ID
     * @param userId           用户ID
     * @param toolName         工具名
     * @param toolInput        工具参数 JSON
     * @param argumentsSummary 参数摘要
     * @return 审批记录
     */
    AgentApproval pauseForApproval(
            Long taskId,
            Long runId,
            Long userId,
            String toolName,
            String toolInput,
            String argumentsSummary,
            String riskLevel);

    /**
     * 审批决定（批准/拒绝）
     *
     * @param approvalId 审批UUID
     * @param decision   "approved" | "denied"
     * @param decidedBy  审批人用户ID
     * @param reason     决定原因
     * @return 更新后的审批记录
     */
    AgentApproval decideApproval(String approvalId, String decision, Long decidedBy, String reason);

    /**
     * 查询用户的待审批列表
     * @param userId 用户ID
     */
    List<AgentApproval> listPendingApprovals(Long userId);

    /**
     * 按审批ID查询
     */
    AgentApproval getApproval(String approvalId);

    /**
     * 查询任务的审批记录
     */
    List<AgentApproval> getApprovalsByTaskId(Long taskId);

    /**
     * 超时自动拒绝（定时任务调用）
     */
    int expireApprovals();

    /**
     * 消耗一次性执行令牌（原子操作）。
     *
     * <p>仅当令牌处于 {@code issued} 状态时才返回 {@code true} 并将其置为
     * {@code consumed}；重复调用、令牌缺失或已消耗都会返回 {@code false}，
     * 从而保证“批准后恰好执行一次”。</p>
     *
     * @param approvalId 审批UUID
     * @param executionToken 批准时签发的一次性执行令牌
     * @return 是否成功消耗（首次成功；重复提交/错误令牌失败）
     */
    boolean consumeExecutionToken(String approvalId, String executionToken);

    /**
     * 查询审批记录（含执行令牌状态）——用于审计。
     */
    AgentApproval getApprovalWithToken(String approvalId);

    // ================================================================
    // V13: 队列调度
    // ================================================================

    /**
     * 创建待执行的 Run（PENDING 状态，scheduled_at=now），记录 QUEUED 事件。
     * 由 Worker 认领租约后改为 running 并调用 Python。
     *
     * @param taskId 任务ID（任务必须处于 pending 或 failed 状态）
     * @return 新创建的 pending Run
     */
    AgentRun enqueueRun(Long taskId);

    // ================================================================
    // V13: 死信恢复
    // ================================================================

    /**
     * 恢复死信任务：清除死信字段，task→pending，创建新 pending run
     *
     * @param taskId 任务ID
     * @param userId 操作用户ID（校验所有权）
     * @return 新创建的 Run
     */
    AgentRun requeueTask(Long taskId, Long userId);
}
