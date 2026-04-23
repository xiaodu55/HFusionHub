package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.PluginAuditLog;
import com.hfusionhub.mapper.PluginAuditLogMapper;
import com.hfusionhub.service.PluginService;
import com.hfusionhub.tenant.TenantContext;
import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/**
 * Internal-only endpoint for Python AI to query plugin ToolSpecs,
 * receive audit logs, and query sandbox config.
 *
 * <p>Protected by {@code X-Internal-Token} and excluded from Sa-Token login check.</p>
 */
@Slf4j
@Hidden
@RestController
@RequestMapping("/internal/plugin")
@RequiredArgsConstructor
@Tag(name = "Internal Plugin", description = "Token-protected endpoints for Python AI")
public class InternalPluginController {

    private final PluginService pluginService;
    private final PluginAuditLogMapper pluginAuditLogMapper;

    @Value("${python-ai.internal-token:}")
    private String expectedToken;

    @GetMapping("/tool-specs")
    public R<List<Map<String, Object>>> getPluginToolSpecs(@RequestParam Long tenantId, HttpServletRequest request) {
        if (!constantTimeEquals(expectedToken, request.getHeader("X-Internal-Token"))) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }
        if (tenantId == null || tenantId < 1) {
            return R.fail(400, "tenantId is required");
        }
        return R.ok(TenantContext.runAs(tenantId, pluginService::getPluginToolSpecs));
    }

    @GetMapping("/{pluginId}/versions")
    public R<List<Map<String, Object>>> getPluginVersions(@PathVariable String pluginId, HttpServletRequest request) {
        if (!constantTimeEquals(expectedToken, request.getHeader("X-Internal-Token"))) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }

        var plugin = pluginService.getByPluginId(pluginId);
        if (plugin == null) {
            return R.fail(404, "Plugin not found");
        }

        // Get all versions from version history (including current)
        List<Map<String, Object>> versions = pluginService.getPluginVersions(plugin.getId());
        return R.ok(versions);
    }

    @GetMapping("/sandbox-config")
    public R<Map<String, Object>> getSandboxConfig(@RequestParam String pluginId, HttpServletRequest request) {
        if (!constantTimeEquals(expectedToken, request.getHeader("X-Internal-Token"))) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }

        var plugin = pluginService.getByPluginId(pluginId);
        if (plugin == null || !Boolean.TRUE.equals(plugin.getEnabled())) {
            return R.fail(404, "Plugin not found or disabled");
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("plugin_id", pluginId);
        result.put("name", plugin.getName());
        result.put("version", plugin.getVersion());
        result.put("sandbox_config", plugin.getSandboxConfig());
        result.put("permissions", plugin.getPermissions());
        return R.ok(result);
    }

    /**
     * Receive audit log entries from Python AI service.
     * Idempotent: uses the entry's UUID as a natural dedup key.
     * Batch endpoint: accepts a list of entries for efficiency.
     */
    @PostMapping("/audit-logs")
    @Transactional
    public R<Map<String, Object>> receiveAuditLogs(
            @RequestBody List<Map<String, Object>> entries, HttpServletRequest request) {
        if (!constantTimeEquals(expectedToken, request.getHeader("X-Internal-Token"))) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }

        int inserted = 0;
        int skipped = 0;
        for (Map<String, Object> entry : entries) {
            try {
                // Idempotency: check for eventId to prevent duplicate inserts
                String eventId = (String) entry.get("eventId");
                if (eventId != null) {
                    // Skip if event already exists (idempotent retry)
                    if (pluginAuditLogMapper.selectByEventId(eventId) != null) {
                        skipped++;
                        continue;
                    }
                }

                PluginAuditLog log = new PluginAuditLog();
                log.setEventId(eventId);
                log.setPluginName((String) entry.getOrDefault("pluginName", ""));
                log.setAction((String) entry.getOrDefault("action", ""));
                log.setReason((String) entry.get("reason"));
                log.setOldValue((String) entry.get("oldValue"));
                log.setNewValue((String) entry.get("newValue"));

                // Resolve plugin_id from pluginId (UUID) to database ID
                String pluginUuid = (String) entry.get("pluginId");
                if (pluginUuid != null) {
                    var plugin = pluginService.getByPluginId(pluginUuid);
                    if (plugin != null) {
                        log.setPluginId(plugin.getId());
                    }
                }

                // Set operator_id if present
                Object operatorId = entry.get("operatorId");
                if (operatorId instanceof Number) {
                    log.setOperatorId(((Number) operatorId).longValue());
                }

                pluginAuditLogMapper.insert(log);
                inserted++;
            } catch (Exception e) {
                log.warn("Failed to insert audit log entry: {}", e.getMessage());
                skipped++;
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("inserted", inserted);
        result.put("skipped", skipped);
        result.put("total", entries.size());
        log.info("Received audit logs from Python: inserted={}, skipped={}", inserted, skipped);
        return R.ok(result);
    }

    private static boolean constantTimeEquals(String expected, String provided) {
        if (expected == null || expected.isEmpty() || provided == null) {
            return false;
        }
        byte[] a = expected.getBytes(StandardCharsets.UTF_8);
        byte[] b = provided.getBytes(StandardCharsets.UTF_8);
        if (a.length != b.length) {
            int diff = 0;
            for (byte ignored : a) {
                diff |= ignored;
            }
            for (byte ignored : b) {
                diff |= ignored;
            }
            return false;
        }
        int diff = 0;
        for (int i = 0; i < a.length; i++) {
            diff |= a[i] ^ b[i];
        }
        return diff == 0;
    }
}
