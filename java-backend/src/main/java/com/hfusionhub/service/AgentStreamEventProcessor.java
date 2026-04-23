package com.hfusionhub.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.dto.AgentTaskDetailDTO;
import com.hfusionhub.entity.AgentRun;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

/**
 * Agent SSE 事件处理器 — 从 Python SSE 流中解析结构化事件并持久化。
 * Worker 和流式路径共用此处理器。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class AgentStreamEventProcessor {

    private final AgentTaskService agentTaskService;
    private final AgentStatusEventService statusEventService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public AgentStreamEventProcessor(
            @Lazy AgentTaskService agentTaskService, AgentStatusEventService statusEventService) {
        this.agentTaskService = agentTaskService;
        this.statusEventService = statusEventService;
    }

    /**
     * 处理一行 SSE 数据，持久化事件并返回解析后的 JSON 节点（供调用方转发前端）。
     *
     * @param rawChunk SSE 原始行
     * @param runId    当前 Run ID
     * @return 解析后的 JSON 节点，若不是有效事件则返回 empty
     */
    @SuppressWarnings("unchecked")
    public Optional<JsonNode> handleLine(String rawChunk, Long runId) {
        String data = stripSsePrefix(rawChunk);
        if (data == null || "[DONE]".equals(data)) {
            return Optional.empty();
        }

        try {
            JsonNode jsonNode = objectMapper.readTree(data);

            // Only handle structured events (those with an "event" field)
            if (!jsonNode.has("event")) {
                return Optional.of(jsonNode);
            }

            String eventType = jsonNode.get("event").asText();
            switch (eventType) {
                case "step_completed" -> handleStepCompleted(jsonNode, runId);
                case "run_completed" -> handleRunCompleted(jsonNode, runId);
                case "run_error" -> handleRunError(jsonNode, runId);
                case "approval_required" -> handleApprovalRequired(jsonNode, runId);
                case "run_started" -> {
                    /* no persistence needed — run created by startRun() */
                }
                default -> log.debug("Unknown agent event type: {}", eventType);
            }

            return Optional.of(jsonNode);
        } catch (Exception e) {
            log.warn("Failed to parse SSE chunk: {}", data, e);
            return Optional.empty();
        }
    }

    /**
     * Strip the SSE {@code data:} / {@code data: } prefix from a raw chunk line.
     * Returns the JSON / sentinel payload, or {@code null} if this line carries no data.
     */
    public static String stripSsePrefix(String rawChunk) {
        if (rawChunk == null) return null;
        String line = rawChunk.strip();
        if (line.isEmpty()) return null; // SSE separator (blank line)

        // Standard SSE: "data: {json}" or "data: [DONE]"
        if (line.startsWith("data: ")) {
            String payload = line.substring(6).strip();
            return payload.isEmpty() ? null : payload;
        }
        if (line.startsWith("data:")) {
            String payload = line.substring(5).strip();
            return payload.isEmpty() ? null : payload;
        }

        // Non-SSE or legacy format — treat the whole line as the payload
        return line;
    }

    // ================================================================
    // 事件处理方法
    // ================================================================

    private void handleStepCompleted(JsonNode eventNode, Long runId) {
        try {
            int sequence = eventNode.has("sequence") ? eventNode.get("sequence").asInt() : 0;
            String stepType =
                    eventNode.has("step_type") ? eventNode.get("step_type").asText() : "";
            String action = eventNode.has("action") && !eventNode.get("action").isNull()
                    ? eventNode.get("action").asText()
                    : null;
            String inputSummary = eventNode.has("input_summary")
                            && !eventNode.get("input_summary").isNull()
                    ? eventNode.get("input_summary").asText()
                    : null;
            String outputSummary = eventNode.has("output_summary")
                            && !eventNode.get("output_summary").isNull()
                    ? eventNode.get("output_summary").asText()
                    : null;
            List<Map<String, Object>> sources = null;
            if (eventNode.has("sources")
                    && !eventNode.get("sources").isNull()
                    && eventNode.get("sources").isArray()) {
                sources = objectMapper.treeToValue(eventNode.get("sources"), List.class);
            }
            long durationMs =
                    eventNode.has("duration_ms") ? eventNode.get("duration_ms").asLong() : 0L;
            String errorCode =
                    eventNode.has("error_code") && !eventNode.get("error_code").isNull()
                            ? eventNode.get("error_code").asText()
                            : null;

            agentTaskService.recordStep(
                    runId, sequence, stepType, action, inputSummary, outputSummary, sources, durationMs, errorCode);

            // Record status event
            AgentRun run = agentTaskService.getRunById(runId);
            if (run != null) {
                Long taskId = run.getTaskId();
                statusEventService.record(
                        taskId,
                        runId,
                        "STEP_RECORDED",
                        "running",
                        Map.of("sequence", sequence, "stepType", stepType, "action", action != null ? action : ""));
            }
        } catch (Exception e) {
            log.warn("Failed to handle step_completed event for run {}: {}", runId, e.getMessage());
        }
    }

    private void handleRunCompleted(JsonNode eventNode, Long runId) {
        try {
            String rawStatus = eventNode.has("status") ? eventNode.get("status").asText() : "completed";
            String status = AgentConstants.mapPythonStatus(rawStatus);
            int toolCalls = eventNode.has("tool_calls_count")
                    ? eventNode.get("tool_calls_count").asInt()
                    : 0;
            Map<String, Object> tokenUsage = null;
            if (eventNode.has("token_usage") && eventNode.get("token_usage").isObject()) {
                tokenUsage = objectMapper.convertValue(eventNode.get("token_usage"), Map.class);
            }
            agentTaskService.completeRun(runId, status, null, tokenUsage, toolCalls, 0, null, null, null);

            // Record status event
            AgentRun run = agentTaskService.getRunById(runId);
            if (run != null) {
                statusEventService.record(
                        run.getTaskId(),
                        runId,
                        "RUN_SUCCEEDED".equals(status) ? "RUN_SUCCEEDED" : "RUN_" + status.toUpperCase(),
                        status,
                        null);
            }
            log.info("Agent run {} completed via SSE event: rawStatus={} mappedStatus={}", runId, rawStatus, status);
        } catch (Exception e) {
            log.warn("Failed to handle run_completed event for run {}: {}", runId, e.getMessage());
        }
    }

    private void handleRunError(JsonNode eventNode, Long runId) {
        try {
            String rawStatus = eventNode.has("status") ? eventNode.get("status").asText() : "failed";
            String status = AgentConstants.mapPythonStatus(rawStatus);
            String errorCode =
                    eventNode.has("error_code") && !eventNode.get("error_code").isNull()
                            ? eventNode.get("error_code").asText()
                            : "internal_error";
            String errorDetail = eventNode.has("error_detail")
                            && !eventNode.get("error_detail").isNull()
                    ? eventNode.get("error_detail").asText()
                    : null;
            String failedTool = eventNode.has("failed_tool")
                            && !eventNode.get("failed_tool").isNull()
                    ? eventNode.get("failed_tool").asText()
                    : null;
            agentTaskService.completeRun(runId, status, null, null, 0, 0, errorCode, errorDetail, failedTool);

            // Record status event
            AgentRun run = agentTaskService.getRunById(runId);
            if (run != null) {
                statusEventService.record(
                        run.getTaskId(),
                        runId,
                        "RUN_" + status.toUpperCase(),
                        status,
                        Map.of(
                                "errorCode",
                                errorCode,
                                "errorDetail",
                                errorDetail != null ? errorDetail : "",
                                "failedTool",
                                failedTool != null ? failedTool : ""));
            }
            log.warn(
                    "Agent run {} failed via SSE event: rawStatus={} mappedStatus={} errorCode={}",
                    runId,
                    rawStatus,
                    status,
                    errorCode);
        } catch (Exception e) {
            log.warn("Failed to handle run_error event for run {}: {}", runId, e.getMessage());
        }
    }

    private void handleApprovalRequired(JsonNode eventNode, Long runId) {
        try {
            String toolName =
                    eventNode.has("tool_name") ? eventNode.get("tool_name").asText() : "";
            String toolInput =
                    eventNode.has("tool_input") ? eventNode.get("tool_input").toString() : "{}";
            String argumentsSummary = eventNode.has("arguments_summary")
                            && !eventNode.get("arguments_summary").isNull()
                    ? eventNode.get("arguments_summary").asText()
                    : "";
            String riskLevel =
                    eventNode.has("risk_level") && !eventNode.get("risk_level").isNull()
                            ? eventNode.get("risk_level").asText()
                            : "read_only";

            // Look up task context via the run
            AgentRun currentRun = agentTaskService.getRunById(runId);
            if (currentRun != null) {
                AgentTaskDetailDTO taskDetail = agentTaskService.getTaskDetail(currentRun.getTaskId());
                if (taskDetail == null || taskDetail.getUserId() == null) {
                    log.error("Refusing approval for run {}: task owner cannot be resolved", runId);
                    return;
                }
                Long taskUserId = taskDetail.getUserId();
                agentTaskService.pauseForApproval(
                        currentRun.getTaskId(), runId, taskUserId, toolName, toolInput, argumentsSummary, riskLevel);

                // Record status event
                statusEventService.record(
                        currentRun.getTaskId(),
                        runId,
                        "APPROVAL_REQUIRED",
                        "waiting_approval",
                        Map.of("toolName", toolName));
                log.info("Agent run {} requires approval: tool={} taskId={}", runId, toolName, currentRun.getTaskId());
            } else {
                log.warn("Cannot pause for approval: run {} not found", runId);
            }
        } catch (Exception e) {
            log.warn("Failed to handle approval_required event for run {}: {}", runId, e.getMessage());
        }
    }
}
