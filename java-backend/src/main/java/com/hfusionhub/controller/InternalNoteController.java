package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.InternalTokenGuard;
import com.hfusionhub.entity.Note;
import com.hfusionhub.service.NoteService;
import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 内部笔记写入端点 — 供 Python AI 的 write_note 工具回调。
 *
 * <p>受 X-Internal-Token（常量时间比较）保护，并在 SaTokenConfig 中从登录检查排除。
 * user_id 由 Python 的 AgentExecutionContext 注入（Java 会话认证后产生），
 * 模型无法伪造。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Hidden
@RestController
@RequestMapping("/internal/notes")
@RequiredArgsConstructor
@Tag(name = "Internal Notes", description = "Token-protected note write from Python AI")
public class InternalNoteController {

    private final NoteService noteService;

    @Value("${python-ai.internal-token:}")
    private String expectedToken;

    @PostMapping
    @Operation(summary = "Agent write_note 回调保存笔记（internal only）")
    public R<Map<String, Object>> create(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        if (!InternalTokenGuard.isAuthorized(expectedToken, request.getHeader("X-Internal-Token"))) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }

        Long userId = positiveLong(body.get("user_id"));
        if (userId == null) {
            return R.fail(400, "user_id is required");
        }
        String content = text(body.get("content"));
        if (content == null || content.isBlank()) {
            return R.fail(400, "content is required");
        }

        try {
            Note note = noteService.createNote(
                    userId,
                    positiveLong(body.get("tenant_id")),
                    positiveLong(body.get("knowledge_base_id")),
                    positiveLong(body.get("conversation_id")),
                    positiveLong(body.get("message_id")),
                    text(body.get("title")),
                    content,
                    text(body.get("source")) != null ? text(body.get("source")) : "agent_write_note");
            log.info("Internal note created by agent: userId={} noteId={}", userId, note.getId());
            return R.ok(Map.of("note_id", note.getId(), "title", note.getTitle() != null ? note.getTitle() : ""));
        } catch (Exception e) {
            log.warn("Internal note creation failed: {}", e.getMessage());
            return R.fail(500, "note creation failed: " + e.getMessage());
        }
    }

    private static Long positiveLong(Object value) {
        if (value == null) {
            return null;
        }
        try {
            long parsed = Long.parseLong(value.toString().trim());
            return parsed > 0 ? parsed : null;
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String text(Object value) {
        return value == null ? null : value.toString().trim();
    }

    /**
     * Constant-time string comparison to prevent timing attacks on token verification.
     */
}
