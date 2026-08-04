package com.hfusionhub.controller;

import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.*;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.service.AgentStatusEventService;
import com.hfusionhub.service.AgentTaskService;
import com.hfusionhub.service.ApprovalEventSseManager;
import com.hfusionhub.service.impl.AgentTaskDecisionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * Agent 任务管理控制器
 *
 * @author HFusionHub Team
 */
@Slf4j
@Tag(name = "Agent任务管理", description = "Agent任务查询、重试、取消接口")
@RestController
@RequestMapping("/agent-task")
@RequiredArgsConstructor
public class AgentTaskController {

    private final AgentTaskService agentTaskService;
    private final AgentTaskDecisionService agentTaskDecisionService;
    private final AgentStatusEventService statusEventService;
    private final ApprovalEventSseManager approvalEventSseManager;

    @Operation(summary = "获取任务详情（含所有 Run 和 Step 时间线）")
    @GetMapping("/{taskId}")
    public R<AgentTaskDetailDTO> getTaskDetail(@PathVariable Long taskId) {
        AgentTaskDetailDTO detail = agentTaskService.getTaskDetail(taskId);
        if (detail == null) {
            return R.fail("任务不存在");
        }
        // 校验所有权
        if (!detail.getUserId().equals(JwtUtils.getCurrentUserId())) {
            return R.fail("无权查看此任务");
        }
        return R.ok(detail);
    }

    @Operation(summary = "按 request_id 查询任务详情")
    @GetMapping("/by-request/{requestId}")
    public R<AgentTaskDetailDTO> getTaskByRequestId(@PathVariable String requestId) {
        AgentTaskDetailDTO detail = agentTaskService.getTaskByRequestId(requestId);
        if (detail == null) {
            return R.fail("任务不存在");
        }
        if (!detail.getUserId().equals(JwtUtils.getCurrentUserId())) {
            return R.fail("无权查看此任务");
        }
        return R.ok(detail);
    }

    @Operation(summary = "查询当前用户的任务列表")
    @GetMapping("/list")
    public R<PageResult<AgentTaskSummaryDTO>> listTasks(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int pageSize) {
        Long userId = JwtUtils.getCurrentUserId();
        PageResult<AgentTaskSummaryDTO> result = agentTaskService.listUserTasks(userId, status, page, pageSize);
        return R.ok(result);
    }

    @Operation(summary = "重试失败或超时的任务")
    @PostMapping("/{taskId}/retry")
    public R<String> retryTask(@PathVariable Long taskId) {
        Long userId = JwtUtils.getCurrentUserId();
        agentTaskService.retryTask(taskId, userId);
        return R.ok("任务已重置为待执行状态，请重新发起对话请求");
    }

    @Operation(summary = "取消运行中的任务")
    @PostMapping("/{taskId}/cancel")
    public R<Boolean> cancelTask(@PathVariable Long taskId) {
        Long userId = JwtUtils.getCurrentUserId();
        boolean cancelled = agentTaskService.cancelTask(taskId, userId);
        return R.ok(cancelled);
    }

    // ================================================================
    // Agent V1 Step 5: 审批端点
    // ================================================================

    @Operation(summary = "查询任务的审批记录")
    @GetMapping("/{taskId}/approvals")
    public R<List<AgentApproval>> getApprovals(@PathVariable Long taskId) {
        // 校验所有权
        AgentTaskDetailDTO detail = agentTaskService.getTaskDetail(taskId);
        if (detail == null) return R.fail("任务不存在");
        if (!detail.getUserId().equals(JwtUtils.getCurrentUserId())) return R.fail("无权查看此任务");
        return R.ok(agentTaskService.getApprovalsByTaskId(taskId));
    }

    @Operation(summary = "审批决定（批准/拒绝工具调用）")
    @PostMapping("/{taskId}/approve")
    public R<AgentApproval> decideApproval(@PathVariable Long taskId, @Valid @RequestBody ApprovalDecisionDTO body) {
        Long userId = JwtUtils.getCurrentUserId();
        String approvalId = body.getApprovalId();
        String decision = body.getDecision();
        String reason = body.getReason();

        if ("denied".equals(decision) && !StringUtils.hasText(reason)) {
            return R.fail("拒绝时必须填写原因");
        }

        // 安全校验：审批记录必须属于该任务
        AgentApproval approval = agentTaskService.getApproval(approvalId);
        if (approval == null) return R.fail("审批记录不存在");
        if (!approval.getTaskId().equals(taskId)) return R.fail("审批记录不属于此任务");
        if (!approval.getUserId().equals(userId)) return R.fail("无权审批：审批目标用户不匹配");

        return R.ok(agentTaskDecisionService.decideApproval(approvalId, decision, userId, reason));
    }

    @Operation(summary = "当前用户的待审批列表")
    @GetMapping("/approvals/pending")
    public R<List<AgentApproval>> listPendingApprovals() {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(agentTaskService.listPendingApprovals(userId));
    }

    @Operation(summary = "当前用户的审批实时流（SSE：snapshot + 状态变更 diff）")
    @GetMapping(value = "/approvals/stream", produces = "text/event-stream")
    public SseEmitter streamApprovals() {
        Long userId = JwtUtils.getCurrentUserId();
        return approvalEventSseManager.register(userId);
    }

    // ================================================================
    // V13: 调度状态、事件、重试历史、死信管理
    // ================================================================

    @Operation(summary = "获取任务完整状态（含调度信息）")
    @GetMapping("/{taskId}/status")
    public R<AgentTaskStatusDTO> getTaskStatus(@PathVariable Long taskId) {
        AgentTaskDetailDTO detail = agentTaskService.getTaskDetail(taskId);
        if (detail == null) return R.fail("任务不存在");
        if (!detail.getUserId().equals(JwtUtils.getCurrentUserId())) return R.fail("无权查看此任务");

        AgentStatusEventDTO latestEvent = statusEventService.getLatestEvent(taskId);

        // Find current run scheduling info
        String currentRunStatus = null;
        java.time.LocalDateTime currentRunScheduledAt = null;
        Integer currentRunAttemptNumber = null;
        if (detail.getRuns() != null && detail.getCurrentRunId() != null) {
            for (AgentRunDTO runDTO : detail.getRuns()) {
                if (runDTO.getId().equals(detail.getCurrentRunId())) {
                    currentRunStatus = runDTO.getStatus();
                    currentRunScheduledAt = runDTO.getScheduledAt();
                    currentRunAttemptNumber = runDTO.getAttemptNumber();
                    break;
                }
            }
        }

        AgentTaskStatusDTO status = AgentTaskStatusDTO.builder()
                .id(detail.getId())
                .requestId(detail.getRequestId())
                .userId(detail.getUserId())
                .conversationId(detail.getConversationId())
                .knowledgeBaseId(detail.getKnowledgeBaseId())
                .query(detail.getQuery())
                .status(detail.getStatus())
                .deadLetter(AgentConstants.STATUS_DEAD_LETTER.equals(detail.getStatus()))
                .deadLetterReason(detail.getDeadLetterReason())
                .currentRunId(detail.getCurrentRunId())
                .currentRunStatus(currentRunStatus)
                .currentRunScheduledAt(currentRunScheduledAt)
                .currentRunAttemptNumber(currentRunAttemptNumber)
                .totalRunCount(detail.getRuns() != null ? detail.getRuns().size() : 0)
                .latestEvent(latestEvent)
                .createdAt(detail.getCreatedAt())
                .updatedAt(detail.getUpdatedAt())
                .build();
        return R.ok(status);
    }

    @Operation(summary = "查询任务事件列表（支持断点续传 sinceId）")
    @GetMapping("/{taskId}/events")
    public R<List<AgentStatusEventDTO>> listEvents(
            @PathVariable Long taskId,
            @RequestParam(required = false) Long sinceId,
            @RequestParam(defaultValue = "50") int limit) {
        AgentTaskDetailDTO detail = agentTaskService.getTaskDetail(taskId);
        if (detail == null) return R.fail("任务不存在");
        if (!detail.getUserId().equals(JwtUtils.getCurrentUserId())) return R.fail("无权查看此任务");
        return R.ok(statusEventService.listEvents(taskId, sinceId, Math.min(limit, 200)));
    }

    @Operation(summary = "查询任务的重试历史")
    @GetMapping("/{taskId}/retries")
    public R<List<AgentRunDTO>> listRetries(@PathVariable Long taskId) {
        AgentTaskDetailDTO detail = agentTaskService.getTaskDetail(taskId);
        if (detail == null) return R.fail("任务不存在");
        if (!detail.getUserId().equals(JwtUtils.getCurrentUserId())) return R.fail("无权查看此任务");
        // Return all runs (each run = one attempt with scheduling info)
        return R.ok(detail.getRuns());
    }

    @Operation(summary = "查询当前用户的死信任务列表")
    @GetMapping("/dead-letter")
    public R<PageResult<AgentTaskSummaryDTO>> listDeadLetterTasks(
            @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "10") int pageSize) {
        Long userId = JwtUtils.getCurrentUserId();
        PageResult<AgentTaskSummaryDTO> result =
                agentTaskService.listUserTasks(userId, AgentConstants.STATUS_DEAD_LETTER, page, pageSize);
        return R.ok(result);
    }

    @Operation(summary = "恢复死信任务")
    @PostMapping("/{taskId}/requeue")
    public R<AgentRun> requeueTask(@PathVariable Long taskId) {
        Long userId = JwtUtils.getCurrentUserId();
        AgentRun newRun = agentTaskService.requeueTask(taskId, userId);
        return R.ok(newRun);
    }
}
