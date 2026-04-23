package com.hfusionhub.controller;

import com.hfusionhub.common.dto.FeatureFlagSnapshotDTO;
import com.hfusionhub.common.result.R;
import com.hfusionhub.service.FeatureFlagService;
import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Internal-only endpoints for service-to-service communication.
 * Protected by X-Internal-Token with constant-time comparison.
 * Excluded from Sa-Token login check in SaTokenConfig.
 */
@Hidden
@RestController
@RequestMapping("/internal/feature-flags")
@RequiredArgsConstructor
@Tag(name = "Internal Feature Flags", description = "Token-protected endpoints for Python AI sync")
public class FeatureFlagInternalController {

    private final FeatureFlagService featureFlagService;

    @Value("${app.internal-token:}")
    private String expectedToken;

    @GetMapping("/snapshot")
    @Operation(summary = "Feature flag snapshot for Python sync (internal only)")
    public R<List<FeatureFlagSnapshotDTO>> snapshot(HttpServletRequest request) {
        String provided = request.getHeader("X-Internal-Token");
        if (!constantTimeEquals(expectedToken, provided)) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }
        return R.ok(featureFlagService.getSnapshot());
    }

    /**
     * Constant-time string comparison to prevent timing attacks on token verification.
     * Compares all characters even when a mismatch is found early.
     */
    private static boolean constantTimeEquals(String expected, String provided) {
        if (expected == null || expected.isEmpty() || provided == null) {
            return false;
        }
        byte[] a = expected.getBytes(StandardCharsets.UTF_8);
        byte[] b = provided.getBytes(StandardCharsets.UTF_8);
        if (a.length != b.length) {
            // Still iterate through all bytes to avoid length-based timing leak
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
