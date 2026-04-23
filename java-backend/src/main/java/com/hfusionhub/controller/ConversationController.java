package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.ConversationCreateDTO;
import com.hfusionhub.dto.ConversationInfoDTO;
import com.hfusionhub.dto.ConversationQueryDTO;
import com.hfusionhub.dto.MessageInfoDTO;
import com.hfusionhub.dto.MessageSendDTO;
import com.hfusionhub.service.ConversationService;
import com.hfusionhub.service.TaskEventSseManager;
import com.hfusionhub.tenant.TenantContext;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicBoolean;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 对话控制器
 *
 * @author HFusionHub Team
 */
@Slf4j
@Tag(name = "对话管理", description = "对话创建、消息发送、历史查询")
@RestController
@RequestMapping("/conversation")
@RequiredArgsConstructor
public class ConversationController {

    private final ConversationService conversationService;
    private final Executor sseTaskExecutor;
    private final TaskEventSseManager taskEventSseManager;

    @Value("${agent.queue.enabled:false}")
    private boolean agentQueueEnabled;

    @Operation(summary = "创建对话", description = "创建新的对话")
    @PostMapping
    public R<ConversationInfoDTO> create(@Valid @RequestBody ConversationCreateDTO dto) {
        ConversationInfoDTO info = conversationService.create(dto);
        return R.ok("创建成功", info);
    }

    @Operation(summary = "删除对话", description = "删除指定对话")
    @DeleteMapping("/{id}")
    public R<Void> delete(@Parameter(description = "对话ID") @PathVariable Long id) {
        conversationService.delete(id);
        return R.ok();
    }

    @Operation(summary = "重命名对话", description = "修改对话名称")
    @PutMapping("/{id}")
    public R<Void> rename(
            @Parameter(description = "对话ID") @PathVariable Long id, @RequestBody Map<String, String> body) {
        String title = body == null ? null : body.get("title");
        conversationService.rename(id, title);
        return R.ok("重命名成功", null);
    }

    @Operation(summary = "清空对话消息", description = "删除对话下的全部消息，保留对话本身")
    @DeleteMapping("/{id}/messages")
    public R<Void> clearMessages(@Parameter(description = "对话ID") @PathVariable Long id) {
        conversationService.clearMessages(id);
        return R.ok("已清空", null);
    }

    @Operation(summary = "删除单条消息", description = "删除对话中的一条消息（用于重新生成/重试去重）")
    @DeleteMapping("/{id}/messages/{messageId}")
    public R<Void> deleteMessage(
            @Parameter(description = "对话ID") @PathVariable Long id,
            @Parameter(description = "消息ID") @PathVariable Long messageId) {
        conversationService.deleteMessage(id, messageId);
        return R.ok("已删除", null);
    }

    @Operation(summary = "获取对话详情", description = "获取指定对话的详细信息")
    @GetMapping("/{id}")
    public R<ConversationInfoDTO> getById(@Parameter(description = "对话ID") @PathVariable Long id) {
        ConversationInfoDTO info = conversationService.getById(id);
        return R.ok(info);
    }

    @Operation(summary = "分页查询对话列表", description = "分页查询所有对话")
    @GetMapping("/list")
    public R<PageResult<ConversationInfoDTO>> list(ConversationQueryDTO queryDTO) {
        PageResult<ConversationInfoDTO> result = conversationService.list(queryDTO);
        return R.ok(result);
    }

    @Operation(summary = "获取我的对话列表", description = "获取当前用户的对话列表")
    @GetMapping("/my")
    public R<PageResult<ConversationInfoDTO>> listByCurrentUser(ConversationQueryDTO queryDTO) {
        PageResult<ConversationInfoDTO> result = conversationService.listByCurrentUser(queryDTO);
        return R.ok(result);
    }

    @Operation(summary = "发送消息", description = "向对话发送消息")
    @PostMapping("/message")
    public R<MessageInfoDTO> sendMessage(@Valid @RequestBody MessageSendDTO dto) {
        MessageInfoDTO info = conversationService.sendMessage(dto);
        return R.ok("发送成功", info);
    }

    @Operation(summary = "获取对话历史", description = "获取指定对话的所有消息")
    @GetMapping("/{id}/messages")
    public R<List<MessageInfoDTO>> getMessages(@Parameter(description = "对话ID") @PathVariable Long id) {
        List<MessageInfoDTO> messages = conversationService.getMessages(id);
        return R.ok(messages);
    }

    @Operation(summary = "发送消息（流式响应）", description = "向对话发送消息，返回SSE流式响应")
    @PostMapping(value = "/message/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter sendMessageStream(
            @Valid @RequestBody MessageSendDTO dto, jakarta.servlet.http.HttpServletResponse response)
            throws Exception {
        // 禁用 SSE 缓冲，确保实时推送
        response.setHeader("X-Accel-Buffering", "no");
        response.setHeader("Cache-Control", "no-cache");
        response.setHeader("Connection", "keep-alive");

        // 在请求线程中提取用户ID和租户上下文（线程池切换后 ThreadLocal 会丢失）
        Long currentUserId = JwtUtils.getCurrentUserId();
        Long currentTenantId = TenantContext.getTenantId();

        // ── V13: 队列模式 — 入队后通过 SSE 订阅状态变更 ──
        if (agentQueueEnabled) {
            try {
                Long taskId = conversationService.enqueueMessage(dto, currentUserId);
                log.info(
                        "Queue mode: task {} enqueued for conversation {}, returning SSE subscription",
                        taskId,
                        dto.getConversationId());
                return taskEventSseManager.register(taskId, currentUserId);
            } catch (Exception e) {
                log.error("Queue mode enqueue failed for conversation {}: {}", dto.getConversationId(), e.getMessage());
                SseEmitter errorEmitter = new SseEmitter(0L);
                errorEmitter.completeWithError(e);
                return errorEmitter;
            }
        }

        // ── 兼容模式：请求线程直连 Python ──
        SseEmitter emitter = new SseEmitter(300000L); // 5 minutes timeout

        // 创建取消标志，客户端断开时设为true
        AtomicBoolean cancelled = new AtomicBoolean(false);

        // 添加生命周期回调
        emitter.onCompletion(() -> {
            log.info("SSE completed for conversation {}", dto.getConversationId());
            cancelled.set(true);
        });

        emitter.onTimeout(() -> {
            log.warn("SSE timeout for conversation {}", dto.getConversationId());
            cancelled.set(true);
        });

        emitter.onError(e -> {
            log.error("SSE error for conversation {}: {}", dto.getConversationId(), e.getMessage());
            cancelled.set(true);
        });

        // 立即发送一个空事件，强制 Spring 刷新响应头，让前端 fetch() 能快速返回
        emitter.send(SseEmitter.event().data(""));

        // 使用线程池执行异步任务，通过 runAs 保留租户上下文
        sseTaskExecutor.execute(() -> {
            TenantContext.runAs(currentTenantId, () -> {
                try {
                    conversationService.sendMessageStream(dto, emitter, currentUserId, cancelled);
                } catch (Exception e) {
                    emitter.completeWithError(e);
                }
            });
        });

        return emitter;
    }

    @Operation(summary = "取消流式消息生成")
    @PostMapping("/message/stream/cancel")
    public R<Boolean> cancelMessageStream(@RequestBody Map<String, String> body) {
        String requestId = body == null ? null : body.get("requestId");
        if (requestId == null || requestId.isBlank()) {
            return R.fail("requestId 不能为空");
        }
        boolean cancelled = conversationService.cancelMessageStream(requestId, JwtUtils.getCurrentUserId());
        return R.ok(cancelled);
    }
}
