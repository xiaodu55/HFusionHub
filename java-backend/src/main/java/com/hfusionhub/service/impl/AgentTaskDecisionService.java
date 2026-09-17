package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.entity.Message;
import com.hfusionhub.mapper.AgentApprovalMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.service.AgentStatusEventService;
import com.hfusionhub.service.AgentTaskService;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * 审批决定与恢复执行（自 AgentTaskServiceImpl 收口，第二十四批 God class 拆分）。
 *
 * <p>M2 语义保持：decideApproval 的 Phase 1（approval/task/run 三表更新 + 执行
 * 令牌签发）在同一事务内；Phase 2（Python 工具执行与收敛）经 afterCommit 在
 * 事务提交（行锁释放）后运行，不再占用行锁/连接。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
public class AgentTaskDecisionService {

    private final AgentStepMapper stepMapper;
    private final AgentApprovalMapper approvalMapper;
    private final AgentTaskMapper taskMapper;
    private final AgentRunMapper runMapper;
    private final AgentRunLifecycleService runLifecycle;
    private final AgentStatusEventService statusEventService;
    private final AiClient aiClient;
    private final MessageMapper messageMapper;
    private final AgentTaskService agentTaskService;

    public AgentTaskDecisionService(
            AgentStepMapper stepMapper,
            AgentApprovalMapper approvalMapper,
            AgentTaskMapper taskMapper,
            AgentRunMapper runMapper,
            AgentRunLifecycleService runLifecycle,
            AgentStatusEventService statusEventService,
            AiClient aiClient,
            MessageMapper messageMapper,
            @Lazy AgentTaskService agentTaskService) {
        this.stepMapper = stepMapper;
        this.approvalMapper = approvalMapper;
        this.taskMapper = taskMapper;
        this.runMapper = runMapper;
        this.runLifecycle = runLifecycle;
        this.statusEventService = statusEventService;
        this.aiClient = aiClient;
        this.messageMapper = messageMapper;
        this.agentTaskService = agentTaskService;
    }

    // 评估 M2：approval/task/run 三条更新必须在同一事务内，进程崩溃时不允许
    // 出现 approval=approved 而 run 卡 waiting_approval 的中间态
    @Transactional
    public AgentApproval decideApproval(String approvalId, String decision, Long decidedBy, String reason) {
        AgentApproval approval = approvalMapper.selectByApprovalId(approvalId);
        if (approval == null) throw new BusinessException("审批记录不存在: " + approvalId);
        if (!"pending".equals(approval.getStatus())) throw new BusinessException("审批状态不允许决定: " + approval.getStatus());
        if (approval.getExpiresAt().isBefore(java.time.LocalDateTime.now())) throw new BusinessException("审批已过期");

        // ── Phase 1: MySQL updates（同一事务：approval/令牌/task/run，见类注解）──
        String newStatus = "approved".equals(decision) ? "approved" : "denied";
        int updated = approvalMapper.updateDecision(
                approval.getId(),
                newStatus,
                decidedBy,
                LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")),
                reason);
        if (updated != 1) {
            throw new BusinessException("审批已被其他请求处理");
        }

        // ── 执行令牌签发（durable one-time，M2 事务的一部分，第五十四批前移）──
        // 签发必须在 task/run 迁移之前完成并视为 Phase 1 的一部分：签发失败
        // （DB 异常或审批不在可签发状态）时整体抛出 → @Transactional 回滚本次
        // 决定（approval 回到 pending），绝不带着 null token 调 Python resume。
        // Python 侧消费本就是 fail-closed（空 token → 409 拒绝执行），Java 侧
        // 旧版静默降级只会把 approved 的 run/task 误收敛成 failed。
        // 只有首个 approve 能把令牌从 'none' → 'issued'（SQL 守卫防并发重复）；
        // 令牌在工具执行前经 Java consume 端点 / Python decide 消费，重放的
        // approve/resume 永远无法二次执行工具。
        String executionToken = null;
        if ("approved".equals(decision)) {
            executionToken = java.util.UUID.randomUUID().toString();
            int issued;
            try {
                issued = approvalMapper.issueExecutionToken(
                        approval.getId(),
                        executionToken,
                        AgentConstants.EXECUTION_TOKEN_ISSUED,
                        LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
            } catch (Exception e) {
                log.error("Failed to issue execution token for approval {}: {}", approvalId, e.getMessage(), e);
                throw new BusinessException("执行令牌签发失败，本次审批未生效（可重试）: " + approvalId);
            }
            if (issued != 1) {
                log.warn(
                        "Could not issue execution token for approval {} — approval not in issueable state",
                        approvalId);
                throw new BusinessException("执行令牌签发失败：审批状态异常，本次审批未生效: " + approvalId);
            }
        }

        AgentTask task = taskMapper.selectById(approval.getTaskId());
        AgentRun run = runMapper.selectById(approval.getRunId());

        if ("denied".equals(decision)) {
            if (task != null) {
                // 第五十四批：task 状态迁移同样走条件 UPDATE 守卫，与 run 的
                // failFromWaitingApproval 对齐，不再无条件覆盖
                boolean taskTransitioned = taskMapper.transitionTaskGuarded(
                                task.getId(),
                                AgentConstants.STATUS_FAILED,
                                List.of(AgentConstants.STATUS_WAITING_APPROVAL))
                        == 1;
                if (!taskTransitioned) {
                    log.warn(
                            "Task {} not transitioned to failed on deny (status={}) — skipping overwrite",
                            task.getId(),
                            task.getStatus());
                }
            }
            if (run != null) {
                // S3/M3 行锁升级：条件 UPDATE（WHERE status='waiting_approval'）原子完成
                // 迁移，与过期调度 expireApprovals 的竞态由数据库行级判定，不再依赖
                // check-then-act 的内存态守卫；仅真正迁移成功的一方结算用量
                boolean transitioned = runLifecycle.failFromWaitingApproval(
                        run.getId(),
                        "approval_denied",
                        "审批被拒绝: " + (reason != null ? reason : "无理由"));
                if (transitioned) {
                    // 用量账本：审批拒绝直接写终态，绕过 completeRun，退回预占
                    runLifecycle.finalizeAgentRunUsage(run.getId(), AgentConstants.STATUS_FAILED, null);
                }
            }
            // V13: record event
            statusEventService.record(
                    approval.getTaskId(),
                    approval.getRunId(),
                    "APPROVAL_DECIDED",
                    AgentConstants.STATUS_FAILED,
                    Map.of("decision", "denied", "toolName", approval.getToolName()));
            log.info(
                    "Approval {} DENIED by user {}: tool={} reason={}",
                    approvalId,
                    decidedBy,
                    approval.getToolName(),
                    reason);
        } else {
            // 第五十四批：task 的 check-then-act（canTransition + updateById）升级为
            // SQL 条件守卫——pending/waiting_approval → running 的合法迁移集合
            // 与 AgentConstants.canTransition 语义一致，并发下只有赢得迁移的一方生效
            if (task != null) {
                boolean taskTransitioned = taskMapper.transitionTaskGuarded(
                                task.getId(),
                                AgentConstants.STATUS_RUNNING,
                                List.of(AgentConstants.STATUS_PENDING, AgentConstants.STATUS_WAITING_APPROVAL))
                        == 1;
                if (!taskTransitioned) {
                    log.warn(
                            "Task {} not transitioned to running on approve (status={}) — skipping overwrite",
                            task.getId(),
                            task.getStatus());
                }
            }
            if (run != null) {
                // S3/M3 行锁升级：仅当仍处 waiting_approval 时原子迁移到 running，
                // 防止覆盖并发完成的终态
                boolean transitioned = runLifecycle.resumeFromWaitingApproval(run.getId());
                if (transitioned) {
                    run.setStatus(AgentConstants.STATUS_RUNNING);
                }
            }
            // V13: record event
            statusEventService.record(
                    approval.getTaskId(),
                    approval.getRunId(),
                    "APPROVAL_DECIDED",
                    AgentConstants.STATUS_RUNNING,
                    Map.of("decision", "approved", "toolName", approval.getToolName()));
            log.info(
                    "Approval {} APPROVED by user {}: tool={} (will call Python resume)",
                    approvalId,
                    decidedBy,
                    approval.getToolName());
        }

        approval.setStatus(newStatus);
        approval.setDecidedBy(decidedBy);
        approval.setReason(reason);

        // ── Phase 2: Call Python AFTER COMMIT ──
        // M2 的三表同事务保证只覆盖 Phase 1。LLM/工具执行（读超时 120s）绝不能
        // 留在事务内——否则 agent_approval/task/run 的行锁在整个工具执行期间被
        // 占用，并发 expireApprovals/cancelTask 全部阻塞，慢审批会拖垮连接池。
        // afterCommit 在提交（行锁已释放）后执行；无事务上下文（单测直调）时内联执行。
        if ("approved".equals(decision) && task != null && run != null) {
            final AgentApproval fApproval = approval;
            final AgentTask fTask = task;
            final AgentRun fRun = run;
            final String fExecutionToken = executionToken;
            Runnable resumeTask = () -> {
                try {
                    resumeAgentAfterApproval(fApproval, fTask, fRun, fExecutionToken);
                } catch (Exception e) {
                    String errorMsg = e.getClass().getSimpleName() + ": "
                            + (e.getMessage() != null ? e.getMessage() : "(null message)");
                    log.error("Failed to resume agent after approval {}: {}", approvalId, errorMsg, e);
                    // Converge run and task to failed so nothing is stuck
                    // in 'running' after a failed Python resume call.
                    try {
                        AgentRun checkRun = runMapper.selectById(fRun.getId());
                        if (checkRun != null) {
                            // M3 行锁升级：条件 UPDATE 仅在仍处非终态时收敛为 failed，
                            // 重读与写入之间即使 run 真实完成也不会被覆盖
                            boolean transitioned = runLifecycle.failUnlessTerminal(
                                    checkRun.getId(), "internal_error", "审批后恢复执行失败: " + errorMsg);
                            if (transitioned) {
                                runLifecycle.finalizeAgentRunUsage(checkRun.getId(), AgentConstants.STATUS_FAILED, null);
                                AgentTask checkTask = taskMapper.selectById(checkRun.getTaskId());
                                if (checkTask != null) {
                                    // 第五十四批：task 收敛同样走条件守卫，非终态才置 failed
                                    boolean taskSettled = taskMapper.transitionTaskGuarded(
                                            checkTask.getId(),
                                            AgentConstants.STATUS_FAILED,
                                            AgentConstants.NON_TERMINAL_STATUSES) == 1;
                                    if (!taskSettled) {
                                        log.warn(
                                                "Task {} already terminal — skipping failure convergence",
                                                checkTask.getId());
                                    }
                                }
                            }
                        } else {
                            // Even if the run can't be found now, converge the
                            // original reference via the guarded transition.
                            log.warn(
                                    "Could not re-read run {} after resume failure — converging original reference",
                                    fRun.getId());
                            boolean transitioned = runLifecycle.failUnlessTerminal(
                                    fRun.getId(), "internal_error", "审批后恢复执行失败: " + errorMsg);
                            if (transitioned) {
                                runLifecycle.finalizeAgentRunUsage(fRun.getId(), AgentConstants.STATUS_FAILED, null);
                            }
                            if (fTask != null) {
                                // 第五十四批：非终态才收敛，条件守卫防覆盖并发终态
                                taskMapper.transitionTaskGuarded(
                                        fTask.getId(),
                                        AgentConstants.STATUS_FAILED,
                                        AgentConstants.NON_TERMINAL_STATUSES);
                            }
                        }
                    } catch (Exception convergenceError) {
                        log.error(
                                "CRITICAL: Failed to converge run/task to failed after approval error. "
                                        + "Run {} may be stuck in non-terminal state. Error: {}",
                                fRun.getId(),
                                convergenceError.getMessage(),
                                convergenceError);
                    }
                }
            };
            if (TransactionSynchronizationManager.isSynchronizationActive()) {
                TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        resumeTask.run();
                    }
                });
            } else {
                // 无事务上下文（单元测试直调）：保持既有同步语义
                resumeTask.run();
            }
        }

        return approval;
    }

    private void resumeAgentAfterApproval(AgentApproval approval, AgentTask task, AgentRun run, String executionToken) {
        Long runId = run.getId();
        // Build chat history from messages
        List<Map<String, String>> history = List.of();
        Long conversationId = task.getConversationId();
        if (conversationId != null) {
            history = getChatHistoryForTask(conversationId);
        }

        // Resume with the exact JSON captured at pause time, never the redacted summary.
        String toolInput = approval.getToolInput() != null ? approval.getToolInput() : "{}";
        if (!AgentTaskSupport.canonicalToolInputHash(toolInput).equalsIgnoreCase(approval.getToolInputHash())) {
            throw new BusinessException("审批参数校验失败");
        }

        // Call Python to execute the approved tool and continue the agent loop
        AiClient.ChatResponse aiResponse = aiClient.decideApproval(
                approval.getApprovalId(),
                "approved",
                approval.getReason(),
                approval.getUserId(),
                task.getKnowledgeBaseId(),
                approval.getToolName(),
                toolInput,
                approval.getToolInputHash(),
                task.getQuery(),
                history,
                conversationId,
                run.getModel(),
                executionToken,
                approval.getUserRole());

        // Record step events from the resumed run
        if (aiResponse.getStepEvents() != null) {
            int seq = stepMapper.countByRunId(runId);
            for (Map<String, Object> stepEvent : aiResponse.getStepEvents()) {
                if (stepEvent == null) continue;
                seq++;
                String stepType = stepEvent.get("step_type") != null
                        ? stepEvent.get("step_type").toString()
                        : "tool_call";
                String action = stepEvent.get("action") != null
                        ? stepEvent.get("action").toString()
                        : null;
                String inputSummary = stepEvent.get("input_summary") != null
                        ? stepEvent.get("input_summary").toString()
                        : null;
                String outputSummary = stepEvent.get("output_summary") != null
                        ? stepEvent.get("output_summary").toString()
                        : null;
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> sources = stepEvent.get("sources") instanceof List
                        ? (List<Map<String, Object>>) stepEvent.get("sources")
                        : null;
                long durationMs = stepEvent.get("duration_ms") instanceof Number n ? n.longValue() : 0L;
                String errorCode = stepEvent.get("error_code") != null
                        ? stepEvent.get("error_code").toString()
                        : null;

                agentTaskService.recordStep(runId, seq, stepType, action, inputSummary, outputSummary, sources, durationMs, errorCode);
            }
        }

        // Complete the run based on Python response
        String pythonStatus = aiResponse.getStatus();
        if (pythonStatus == null) pythonStatus = "completed";
        String mappedStatus = AgentConstants.mapPythonStatus(pythonStatus);

        Map<String, Object> tokenUsage = null;
        if (aiResponse.getTokenUsage() != null) {
            Map<String, Object> usage = aiResponse.getTokenUsage();
            tokenUsage = Map.of(
                    "prompt_tokens", usage.getOrDefault("prompt_tokens", 0),
                    "completion_tokens", usage.getOrDefault("completion_tokens", 0),
                    "total_tokens", usage.getOrDefault("total_tokens", 0));
        }

        // Update the run and task directly.
        // The Python call may have taken several seconds, so HikariCP
        // connections may have been recycled.  Use a fresh lookup with
        // a single retry on MyBatisSystemException.
        // If the fresh lookup fails, fall back to the original reference
        // so the run NEVER stays non-terminal.
        AgentRun freshRun = null;
        for (int retry = 0; retry < 2 && freshRun == null; retry++) {
            try {
                freshRun = runMapper.selectById(runId);
            } catch (Exception selectEx) {
                if (retry == 0) {
                    log.warn(
                            "runMapper.selectById({}) failed on attempt {}: {} — retrying",
                            runId,
                            retry + 1,
                            selectEx.getMessage());
                    try {
                        Thread.sleep(200);
                    } catch (InterruptedException ignored) {
                    }
                } else {
                    log.error(
                            "runMapper.selectById({}) failed on final attempt — falling back to original reference",
                            runId);
                }
            }
        }
        if (freshRun == null) {
            log.warn("Could not re-read run {} after Python resume — updating original entity reference", runId);
            freshRun = run;
        }

        long actualDuration = AgentTaskSupport.clampDuration(0L, freshRun.getStartedAt());
        // 守护终态迁移（同 completeRun 约定）：仅当 run 仍处 running/waiting_approval
        // 时写入 completed/failed——无条件 updateById 会覆盖并发完成/取消的终态，
        // 且账本按被覆盖后的状态结算，导致账本与真实终态不一致
        boolean won = runMapper.completeRunGuarded(
                        freshRun.getId(), mappedStatus, null, null, null, LocalDateTime.now())
                == 1;
        if (won) {
            runMapper.updateCompletionMetadata(
                    freshRun.getId(),
                    aiResponse.getModel(),
                    tokenUsage,
                    aiResponse.getToolCallsCount(),
                    actualDuration);
            // 用量账本：仅真正赢得终态迁移的一方结算/退回（同 runLifecycle 约定）
            runLifecycle.finalizeAgentRunUsage(freshRun.getId(), mappedStatus, tokenUsage);
        } else {
            log.warn(
                    "Run {} terminal state was settled concurrently — skipping overwrite/usage settle",
                    freshRun.getId());
        }

        // 第五十四批：task 终态回写同样走条件守卫（与 run 的 completeRunGuarded
        // 对齐）——只在任务仍为非终态时生效，不再无条件覆盖并发取消/完成的终态；
        // 重读失败时退回原引用的 id，守卫语义不变
        AgentTask freshTask = taskMapper.selectById(freshRun.getTaskId());
        Long targetTaskId = freshTask != null ? freshTask.getId() : task.getId();
        boolean taskSettled = taskMapper.transitionTaskGuarded(
                        targetTaskId, mappedStatus, AgentConstants.NON_TERMINAL_STATUSES)
                == 1;
        if (!taskSettled) {
            log.warn(
                    "Task {} terminal state settled concurrently — skipping overwrite to {}",
                    targetTaskId,
                    mappedStatus);
        }

        String contentPreview = "";
        if (aiResponse.getContent() != null && aiResponse.getContent().length() > 0) {
            contentPreview = aiResponse
                    .getContent()
                    .substring(0, Math.min(100, aiResponse.getContent().length()));
        }

        // Record the approval's execution outcome so the UI/audit can show
        // executed / failed (not just approved).  Guarded to 'approved' state.
        String outcomeStatus = AgentConstants.STATUS_SUCCEEDED.equals(mappedStatus) ? "executed" : "failed";
        int outcomeRows = approvalMapper.updateExecutionOutcome(approval.getId(), outcomeStatus);
        if (outcomeRows == 1) {
            log.info(
                    "Approval {} execution outcome recorded: {} (run mapped={})",
                    approval.getApprovalId(),
                    outcomeStatus,
                    mappedStatus);
        } else {
            log.warn(
                    "Approval {} execution outcome NOT recorded (status != approved): {}",
                    approval.getApprovalId(),
                    outcomeStatus);
        }

        log.info(
                "Agent run {} resumed after approval {}: status={} answer={}",
                runId,
                approval.getApprovalId(),
                mappedStatus,
                contentPreview);
    }

    /**
     * Get recent chat history for a conversation.
     */
    private List<Map<String, String>> getChatHistoryForTask(Long conversationId) {
        if (conversationId == null) return List.of();
        try {
            LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
            wrapper.eq(Message::getConversationId, conversationId)
                    .orderByDesc(Message::getCreatedAt)
                    .last("LIMIT 20");
            List<Message> messages = messageMapper.selectList(wrapper);
            java.util.Collections.reverse(messages);
            return messages.stream()
                    .filter(m -> m.getContent() != null && !m.getContent().isBlank())
                    .map(m -> {
                        Map<String, String> map = new HashMap<>();
                        map.put("role", m.getRole());
                        map.put("content", m.getContent());
                        return map;
                    })
                    .collect(Collectors.toList());
        } catch (Exception e) {
            log.warn("Failed to get chat history for conversation {}: {}", conversationId, e.getMessage());
            return List.of();
        }
    }

}
