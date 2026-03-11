package com.hfusionhub.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.dto.AgentStatusEventDTO;
import com.hfusionhub.dto.AgentTaskDetailDTO;
import com.hfusionhub.dto.AgentTaskStatusDTO;
import com.hfusionhub.entity.AgentRun;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.*;

/**
 * SSE 管理中心 — 管理每个 Task 的 SSE 连接。
 * DB 为 source-of-truth，内存 fan-out 为延迟优化。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TaskEventSseManager {

    private final AgentTaskService agentTaskService;
    private final AgentStatusEventService statusEventService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${agent.status-event.sse-poll-delay-ms:1000}")
    private long pollDelayMs;

    /** 内存 fan-out：同实例内即时推送 */
    private final ConcurrentMap<Long, Set<SseEmitter>> taskEmitters = new ConcurrentHashMap<>();

    private final ScheduledExecutorService pollScheduler = Executors.newScheduledThreadPool(2, r -> {
        Thread t = new Thread(r, "sse-poll-");
        t.setDaemon(true);
        return t;
    });

    /**
     * 注册一个 SSE 连接并开始推送
     */
    public SseEmitter register(Long taskId, Long userId) {
        // Ownership check
        AgentTaskDetailDTO taskDetail = agentTaskService.getTaskDetail(taskId);
        if (taskDetail == null || !taskDetail.getUserId().equals(userId)) {
            SseEmitter rejected = new SseEmitter(0L);
            rejected.completeWithError(new RuntimeException("无权访问此任务"));
            return rejected;
        }

        SseEmitter emitter = new SseEmitter(300_000L); // 5 min timeout (matches existing stream pattern)

        taskEmitters.computeIfAbsent(taskId, k -> ConcurrentHashMap.newKeySet()).add(emitter);

        // Send initial snapshot
        try {
            AgentTaskStatusDTO snapshot = buildStatus(taskDetail);
            emitter.send(SseEmitter.event()
                    .name("snapshot")
                    .data(objectMapper.writeValueAsString(snapshot), MediaType.APPLICATION_JSON));
        } catch (Exception e) {
            log.warn("Failed to send SSE snapshot for task {}: {}", taskId, e.getMessage());
        }

        // Start DB poll loop
        long[] lastEventId = {0L};
        ScheduledFuture<?> pollTask = pollScheduler.scheduleWithFixedDelay(() -> {
            try {
                var events = statusEventService.listEvents(taskId, lastEventId[0], 100);
                for (AgentStatusEventDTO event : events) {
                    emitter.send(SseEmitter.event()
                            .name("status")
                            .data(objectMapper.writeValueAsString(event), MediaType.APPLICATION_JSON));
                    lastEventId[0] = Math.max(lastEventId[0], event.getId());
                }
            } catch (Exception e) {
                log.debug("SSE poll error for task {}: {}", taskId, e.getMessage());
            }
        }, 0, pollDelayMs, TimeUnit.MILLISECONDS);

        // Cleanup on completion/timeout/error
        emitter.onCompletion(() -> cleanup(taskId, emitter, pollTask));
        emitter.onTimeout(() -> cleanup(taskId, emitter, pollTask));
        emitter.onError(e -> cleanup(taskId, emitter, pollTask));

        return emitter;
    }

    /**
     * 向所有注册的 SSE 连接广播即时事件（内存 fan-out，延迟优化）
     */
    public void broadcast(Long taskId, AgentStatusEventDTO event) {
        Set<SseEmitter> emitters = taskEmitters.get(taskId);
        if (emitters == null || emitters.isEmpty()) return;
        try {
            String payload = objectMapper.writeValueAsString(event);
            for (SseEmitter emitter : emitters) {
                try {
                    emitter.send(SseEmitter.event()
                            .name("status")
                            .data(payload, MediaType.APPLICATION_JSON));
                } catch (Exception e) {
                    // Client disconnected — cleanup will remove on next iteration
                }
            }
        } catch (Exception ignored) {}
    }

    /**
     * 向所有注册的 SSE 连接广播内容块（实时流式内容，不持久化到 DB）
     */
    public void broadcastContentChunk(Long taskId, String content) {
        Set<SseEmitter> emitters = taskEmitters.get(taskId);
        if (emitters == null || emitters.isEmpty()) return;
        try {
            String payload = objectMapper.writeValueAsString(Map.of("content", content));
            for (SseEmitter emitter : emitters) {
                try {
                    emitter.send(SseEmitter.event()
                            .name("content")
                            .data(payload, MediaType.APPLICATION_JSON));
                } catch (Exception e) {
                    // Client disconnected
                }
            }
        } catch (Exception ignored) {}
    }

    /**
     * 向所有注册的 SSE 连接广播引用来源
     */
    public void broadcastSources(Long taskId, List<Map<String, Object>> sources) {
        Set<SseEmitter> emitters = taskEmitters.get(taskId);
        if (emitters == null || emitters.isEmpty()) return;
        try {
            String payload = objectMapper.writeValueAsString(Map.of("sources", sources));
            for (SseEmitter emitter : emitters) {
                try {
                    emitter.send(SseEmitter.event()
                            .name("content")
                            .data(payload, MediaType.APPLICATION_JSON));
                } catch (Exception e) {
                    // Client disconnected
                }
            }
        } catch (Exception ignored) {}
    }

    /**
     * 向所有注册的 SSE 连接广播流结束信号 [DONE]
     */
    public void broadcastDone(Long taskId) {
        Set<SseEmitter> emitters = taskEmitters.get(taskId);
        if (emitters == null || emitters.isEmpty()) return;
        for (SseEmitter emitter : emitters) {
            try {
                emitter.send(SseEmitter.event().name("done").data("[DONE]"));
            } catch (Exception e) {
                // Client disconnected
            }
        }
    }

    private void cleanup(Long taskId, SseEmitter emitter, ScheduledFuture<?> pollTask) {
        pollTask.cancel(false);
        Set<SseEmitter> emitters = taskEmitters.get(taskId);
        if (emitters != null) {
            emitters.remove(emitter);
            if (emitters.isEmpty()) {
                taskEmitters.remove(taskId);
            }
        }
        try { emitter.complete(); } catch (Exception ignored) {}
    }

    private AgentTaskStatusDTO buildStatus(AgentTaskDetailDTO detail) {
        AgentStatusEventDTO latestEvent = statusEventService.getLatestEvent(detail.getId());

        // Find current run info
        String currentRunStatus = null;
        java.time.LocalDateTime currentRunScheduledAt = null;
        Integer currentRunAttemptNumber = null;
        if (detail.getRuns() != null && !detail.getRuns().isEmpty()) {
            for (var runDTO : detail.getRuns()) {
                if (runDTO.getId().equals(detail.getCurrentRunId())) {
                    currentRunStatus = runDTO.getStatus();
                    currentRunScheduledAt = runDTO.getScheduledAt();
                    currentRunAttemptNumber = runDTO.getAttemptNumber();
                    break;
                }
            }
        }

        return AgentTaskStatusDTO.builder()
                .id(detail.getId())
                .requestId(detail.getRequestId())
                .userId(detail.getUserId())
                .conversationId(detail.getConversationId())
                .knowledgeBaseId(detail.getKnowledgeBaseId())
                .query(detail.getQuery())
                .status(detail.getStatus())
                .deadLetter(com.hfusionhub.common.constant.AgentConstants.STATUS_DEAD_LETTER.equals(detail.getStatus()))
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
    }
}
