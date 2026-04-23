package com.hfusionhub.controller;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Internal ledger boundary for sandboxed plugin executions. */
@Slf4j
@Hidden
@RestController
@RequestMapping("/internal/plugin/executions")
@RequiredArgsConstructor
@Tag(name = "Internal Plugin Quota", description = "Token-protected plugin execution accounting")
public class InternalPluginQuotaController {

    private final UsageLedgerService usageLedgerService;
    private final UserMapper userMapper;

    @Value("${python-ai.internal-token:}")
    private String expectedToken;

    @PostMapping("/quota")
    public R<Map<String, Object>> transition(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        if (!constantTimeEquals(expectedToken, request.getHeader("X-Internal-Token"))) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }

        Long requestedTenantId = positiveLong(body, "tenant_id");
        Long userId = positiveLong(body, "user_id");
        String executionId = text(body, "execution_id");
        String operation = text(body, "operation");
        String pluginId = text(body, "plugin_id");
        String toolName = text(body, "tool_name");
        if (requestedTenantId == null
                || userId == null
                || executionId == null
                || operation == null
                || pluginId == null
                || toolName == null) {
            return R.fail(400, "tenant_id, user_id, execution_id, operation, plugin_id and tool_name are required");
        }

        String normalizedOperation = operation.toUpperCase(Locale.ROOT);
        if (!"RESERVE".equals(normalizedOperation)
                && !"SETTLE".equals(normalizedOperation)
                && !"RELEASE".equals(normalizedOperation)) {
            return R.fail(400, "operation must be RESERVE, SETTLE, or RELEASE");
        }

        User user = TenantContext.runAsSystem(() -> userMapper.selectById(userId));
        if (user == null || user.getTenantId() == null || !requestedTenantId.equals(user.getTenantId())) {
            log.warn("Rejected plugin quota transition: user={} requestedTenant={}", userId, requestedTenantId);
            return R.fail(403, "User tenant does not match the requested tenant");
        }

        String refId = pluginId + ":" + toolName;
        try {
            TenantContext.runAs(user.getTenantId(), () -> {
                switch (normalizedOperation) {
                    case "RESERVE" -> usageLedgerService.reserve(
                            UsageMeter.PLUGIN_EXECUTIONS, executionId, 1L, "PLUGIN_TOOL", refId);
                    case "SETTLE" -> usageLedgerService.settle(
                            UsageMeter.PLUGIN_EXECUTIONS, executionId, 1L, "PLUGIN_TOOL", refId);
                    case "RELEASE" -> usageLedgerService.release(UsageMeter.PLUGIN_EXECUTIONS, executionId);
                    default -> throw new IllegalStateException("validated operation was not handled");
                }
            });
        } catch (BusinessException | IllegalStateException e) {
            log.warn(
                    "Plugin quota transition failed: operation={} executionId={} reason={}",
                    normalizedOperation,
                    executionId,
                    e.getMessage());
            int code = e instanceof BusinessException businessException ? businessException.getCode() : 500;
            return R.fail(code, e.getMessage());
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("operation", normalizedOperation.toLowerCase(Locale.ROOT));
        result.put("execution_id", executionId);
        result.put("tenant_id", user.getTenantId());
        return R.ok(result);
    }

    private static Long positiveLong(Map<String, Object> body, String key) {
        if (body == null || !(body.get(key) instanceof Number value) || value.longValue() < 1) {
            return null;
        }
        return value.longValue();
    }

    private static String text(Map<String, Object> body, String key) {
        if (body == null || body.get(key) == null) {
            return null;
        }
        String value = String.valueOf(body.get(key)).trim();
        return value.isEmpty() ? null : value;
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
