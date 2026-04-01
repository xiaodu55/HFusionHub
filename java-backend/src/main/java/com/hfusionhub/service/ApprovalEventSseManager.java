package com.hfusionhub.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.mapper.AgentApprovalMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

/**
 * Global approvals SSE stream — current-user view with DB polling.
 *
 * <p>On connect, sends a {@code snapshot} event with the user's recent
 * approvals; then polls {@code agent_approval} and emits an {@code approval}
 * event whenever a record's status changes (waiting → approved / denied /
 * expired, and approved → executed / failed).  DB is the single source of
 * truth, so a disconnected client re-connects to a fresh snapshot and resumes
 * live updates ("断线后状态恢复").</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ApprovalEventSseManager {

    private final AgentApprovalMapper approvalMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${agent.status-event.sse-poll-delay-ms:1000}")
    private long pollDelayMs;

    private static final int SNAPSHOT_LIMIT = 200;

    private final ScheduledExecutorService pollScheduler = Executors.newScheduledThreadPool(2, r -> {
        Thread t = new Thread(r, "sse-approval-poll-");
        t.setDaemon(true);
        return t;
    });

    public SseEmitter register(Long userId) {
        SseEmitter emitter = new SseEmitter(300_000L);

        // Last-known status per approvalId — only diffs are pushed afterwards.
        Map<String, String> known = new ConcurrentHashMap<>();

        // 1. Initial snapshot (also seeds `known`).
        try {
            List<AgentApproval> approvals = approvalMapper.selectRecentByUserId(userId, SNAPSHOT_LIMIT);
            for (AgentApproval a : approvals) {
                known.put(a.getApprovalId(), a.getStatus());
            }
            emitter.send(SseEmitter.event()
                    .name("snapshot")
                    .data(objectMapper.writeValueAsString(Map.of(
                            "type", "snapshot",
                            "data", approvals))));
        } catch (Exception e) {
            log.warn("Failed to send approvals SSE snapshot for user {}: {}", userId, e.getMessage());
        }

        // 2. DB poll loop: emit a record only when its status changed.
        ScheduledFuture<?> pollTask = pollScheduler.scheduleWithFixedDelay(() -> {
            try {
                List<AgentApproval> fresh = approvalMapper.selectRecentByUserId(userId, SNAPSHOT_LIMIT);
                for (AgentApproval a : fresh) {
                    String prev = known.put(a.getApprovalId(), a.getStatus());
                    if (prev == null || !prev.equals(a.getStatus())) {
                        emitter.send(SseEmitter.event()
                                .name("approval")
                                .data(objectMapper.writeValueAsString(Map.of(
                                        "type", "approval",
                                        "data", a))));
                    }
                }
            } catch (Exception e) {
                log.debug("Approvals SSE poll error for user {}: {}", userId, e.getMessage());
            }
        }, 0, pollDelayMs, TimeUnit.MILLISECONDS);

        emitter.onCompletion(() -> pollTask.cancel(false));
        emitter.onTimeout(() -> pollTask.cancel(false));
        emitter.onError(e -> pollTask.cancel(false));

        return emitter;
    }
}
