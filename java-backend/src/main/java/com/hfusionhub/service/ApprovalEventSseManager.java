package com.hfusionhub.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.mapper.AgentApprovalMapper;
import com.hfusionhub.tenant.TenantContext;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

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

        // 轮询跑在共享调度线程上（无租户上下文）。agent_approval 带 tenant_id 且
        // 不在 TENANT_IGNORE_TABLES——不恢复租户时轮询查询被哨兵 tenant 过滤成
        // 空列表，pending→approved 的实时事件全部丢失（只在 HTTP 线程的 snapshot
        // 正常）。在 HTTP 线程捕获租户，轮询体按其执行。
        final Long pollTenantId = TenantContext.getTenantId();

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
                    .data(objectMapper.writeValueAsString(Map.of("type", "snapshot", "data", approvals))));
        } catch (Exception e) {
            log.warn("Failed to send approvals SSE snapshot for user {}: {}", userId, e.getMessage());
        }

        // 2. DB poll loop: emit a record only when its status changed.
        ScheduledFuture<?> pollTask = pollScheduler.scheduleWithFixedDelay(
                () -> {
                    try {
                        TenantContext.runAs(pollTenantId, () -> {
                            try {
                                List<AgentApproval> fresh =
                                        approvalMapper.selectRecentByUserId(userId, SNAPSHOT_LIMIT);
                                for (AgentApproval a : fresh) {
                                    String prev = known.put(a.getApprovalId(), a.getStatus());
                                    if (prev == null || !prev.equals(a.getStatus())) {
                                        emitter.send(SseEmitter.event()
                                                .name("approval")
                                                .data(objectMapper.writeValueAsString(
                                                        Map.of("type", "approval", "data", a))));
                                    }
                                }
                            } catch (Exception e) {
                                log.debug("Approvals SSE poll error for user {}: {}", userId, e.getMessage());
                            }
                        });
                    } catch (Exception e) {
                        log.debug("Approvals SSE poll scope error for user {}: {}", userId, e.getMessage());
                    }
                },
                0,
                pollDelayMs,
                TimeUnit.MILLISECONDS);

        emitter.onCompletion(() -> pollTask.cancel(false));
        emitter.onTimeout(() -> pollTask.cancel(false));
        emitter.onError(e -> pollTask.cancel(false));

        return emitter;
    }
}
