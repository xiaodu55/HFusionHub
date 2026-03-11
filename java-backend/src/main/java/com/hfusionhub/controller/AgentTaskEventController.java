package com.hfusionhub.controller;

import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.service.TaskEventSseManager;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * Agent 任务事件 SSE 推送控制器
 *
 * @author HFusionHub Team
 */
@Slf4j
@Tag(name = "Agent任务事件推送", description = "Agent任务状态变更SSE推送")
@RestController
@RequestMapping("/agent-task")
@RequiredArgsConstructor
public class AgentTaskEventController {

    private final TaskEventSseManager sseManager;

    @Operation(summary = "订阅任务状态变更（SSE）")
    @GetMapping(value = "/{taskId}/events/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamEvents(@PathVariable Long taskId) {
        Long userId = JwtUtils.getCurrentUserId();
        log.debug("SSE event subscription requested for task {} by user {}", taskId, userId);
        return sseManager.register(taskId, userId);
    }
}
