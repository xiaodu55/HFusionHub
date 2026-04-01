package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.service.AgentTaskService;
import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Internal-only endpoint for the durable one-time execution token.
 *
 * <p>The Python AI service calls this AFTER human approval and BEFORE running
 * an approved tool.  The consume is atomically guarded in MySQL so that only
 * the first caller can flip {@code issued → consumed}; every subsequent/replayed
 * call is rejected and the tool is NOT executed.  This makes MySQL the single
 * source of truth for "exactly one execution", independent of any in-memory
 * grant and stable across replicas/restarts.</p>
 *
 * Protected by {@code X-Internal-Token} (constant-time) and excluded from the
 * Sa-Token login check.
 */
@Slf4j
@Hidden
@RestController
@RequestMapping("/internal/agent")
@RequiredArgsConstructor
@Tag(name = "Internal Agent", description = "Token-protected endpoints for Python AI")
public class AgentApprovalInternalController {

    private final AgentTaskService agentTaskService;

    @Value("${python-ai.internal-token:}")
    private String expectedToken;

    @PostMapping("/approvals/consume")
    public R<Map<String, Object>> consume(@RequestBody Map<String, String> body,
                                          HttpServletRequest request) {
        String provided = request.getHeader("X-Internal-Token");
        if (!constantTimeEquals(expectedToken, provided)) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }

        String approvalId = body == null ? null : body.get("approval_id");
        String executionToken = body == null ? null : body.get("execution_token");
        if (approvalId == null || approvalId.isBlank() || executionToken == null) {
            return R.fail("approval_id and execution_token are required");
        }

        boolean consumed = agentTaskService.consumeExecutionToken(approvalId, executionToken);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("consumed", consumed);
        result.put("approval_id", approvalId);
        log.info("Internal execution-token consume request: approvalId={} consumed={}", approvalId, consumed);
        return R.ok(result);
    }

    /**
     * Constant-time string comparison to prevent timing attacks on token verification.
     */
    private static boolean constantTimeEquals(String expected, String provided) {
        if (expected == null || expected.isEmpty() || provided == null) {
            return false;
        }
        byte[] a = expected.getBytes(StandardCharsets.UTF_8);
        byte[] b = provided.getBytes(StandardCharsets.UTF_8);
        if (a.length != b.length) {
            int diff = 0;
            for (byte ignored : a) { diff |= ignored; }
            for (byte ignored : b) { diff |= ignored; }
            return false;
        }
        int diff = 0;
        for (int i = 0; i < a.length; i++) {
            diff |= a[i] ^ b[i];
        }
        return diff == 0;
    }
}