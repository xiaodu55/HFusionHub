package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.InternalTokenGuard;
import com.hfusionhub.entity.MemoryEntry;
import com.hfusionhub.service.MemoryService;
import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 内部长期记忆端点 — 供 Python AI 长期记忆闭环回调与查询。
 *
 * <p>受 X-Internal-Token（常量时间比较）保护，并在 SaTokenConfig 中从登录检查排除。
 * 写入：Python 记忆抽取（MemoryConsolidator）结果批量落 memory_entry 表；
 * 查询：Agent 组装上下文前的相关性记忆拉取（Java 侧按重要性+词命中排序）。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Hidden
@RestController
@RequestMapping("/internal/memory")
@RequiredArgsConstructor
@Tag(name = "Internal Memory", description = "Token-protected long-term memory bridge from Python AI")
public class InternalMemoryController {

    private static final int MAX_ENTRIES_PER_BATCH = 50;

    private final MemoryService memoryService;

    @Value("${python-ai.internal-token:}")
    private String expectedToken;

    @PostMapping("/entries")
    @Operation(summary = "长期记忆抽取结果批量落库（internal only）")
    public R<Map<String, Object>> saveEntries(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        if (!InternalTokenGuard.isAuthorized(expectedToken, request.getHeader("X-Internal-Token"))) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }
        Long userId = positiveLong(body.get("user_id"));
        if (userId == null) {
            return R.fail(400, "user_id is required");
        }
        Object rawEntries = body.get("entries");
        if (!(rawEntries instanceof List<?> list) || list.isEmpty()) {
            return R.fail(400, "entries must be a non-empty array");
        }
        if (list.size() > MAX_ENTRIES_PER_BATCH) {
            return R.fail(400, "entries exceed batch limit of " + MAX_ENTRIES_PER_BATCH);
        }

        List<MemoryEntry> entries = new ArrayList<>();
        for (Object item : list) {
            if (!(item instanceof Map<?, ?> raw)) {
                continue;
            }
            MemoryEntry entry = new MemoryEntry();
            String content = text(raw.get("content"));
            String type = text(raw.get("type"));
            entry.setContent(content);
            entry.setType(type);
            Object importance = raw.get("importance");
            if (importance instanceof Number number) {
                entry.setImportance(number.doubleValue());
            }
            entries.add(entry);
        }

        try {
            int saved = memoryService.saveBatchForUser(
                    userId,
                    positiveLong(body.get("conversation_id")),
                    positiveLong(body.get("knowledge_base_id")),
                    entries);
            log.info("Internal memory batch saved: userId={} saved={}/{}", userId, saved, entries.size());
            return R.ok(Map.of("saved", saved));
        } catch (Exception e) {
            log.warn("Internal memory save failed: {}", e.getMessage());
            return R.fail(500, "memory save failed: " + e.getMessage());
        }
    }

    @GetMapping("/relevant")
    @Operation(summary = "拉取与 query 相关的长期记忆（internal only）")
    public R<List<MemoryEntry>> relevant(
            @RequestParam("user_id") Long userId,
            @RequestParam(value = "query", required = false, defaultValue = "") String query,
            @RequestParam(value = "knowledge_base_id", required = false) Long knowledgeBaseId,
            @RequestParam(value = "limit", required = false, defaultValue = "8") int limit,
            HttpServletRequest request) {
        if (!InternalTokenGuard.isAuthorized(expectedToken, request.getHeader("X-Internal-Token"))) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }
        if (userId == null || userId <= 0) {
            return R.fail(400, "user_id is required");
        }
        try {
            return R.ok(memoryService.getRelevantMemories(userId, knowledgeBaseId, query, limit));
        } catch (Exception e) {
            log.warn("Internal memory relevant query failed: {}", e.getMessage());
            return R.fail(500, "memory query failed: " + e.getMessage());
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
}
