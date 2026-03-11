package com.hfusionhub.service;

import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;

/**
 * Agent 任务队列服务 — Worker 核心：队列轮询、租约管理、执行调度、恢复。
 *
 * @author HFusionHub Team
 */
public interface AgentTaskQueueService {

    /**
     * 轮询并派发待执行的 Run（调度器调用）。
     * @return 本次派发的 Run 数量
     */
    int pollAndDispatch();

    /**
     * 综合恢复扫描：孤儿检测、超时看门狗、Task 收敛、死信到期处理。
     * 幂等，可重复调用。
     * @return 恢复处理的 Run 数量
     */
    int recoverAll();

    /**
     * 心跳续租所有正在执行中的 Run（定时器调用）。
     */
    void heartbeatInFlightRuns();

    // ================================================================
    // 死信 / 取代处理（供 AgentTaskService 和调度器调用）
    // ================================================================

    /**
     * 将任务标记为死信
     */
    void deadLetter(AgentTask task, String reason);

    /**
     * 将 Run 标记为被取代（新 Run 已创建，本 Run 不再有效）
     */
    void markSuperseded(AgentRun run);

    /**
     * 安排下一次尝试（创建新 pending Run + 退避时间）
     */
    AgentRun scheduleNextAttempt(AgentTask task);

    /**
     * 检查 Run 是否已被取消（Redis 标志）
     */
    boolean isRunCancelled(Long runId);
}
