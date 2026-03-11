package com.hfusionhub.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.*;

/**
 * AgentRetryPolicy 单元测试 — 退避公式、可重试码判断、死信边界
 */
class AgentRetryPolicyTest {

    private AgentRetryPolicy policy;

    @BeforeEach
    void setUp() {
        policy = new AgentRetryPolicy();
        ReflectionTestUtils.setField(policy, "maxAttempts", 3);
        ReflectionTestUtils.setField(policy, "baseDelaySeconds", 30L);
        ReflectionTestUtils.setField(policy, "backoffMultiplier", 2);
        ReflectionTestUtils.setField(policy, "maxDelaySeconds", 600L);
        ReflectionTestUtils.setField(policy, "retryableErrorCodesConfig", "timeout,connection_error,tool_error");
        ReflectionTestUtils.setField(policy, "maxDispatchCount", 3);
    }

    @Test
    void attempt1HasZeroBackoff() {
        assertEquals(0L, policy.backoffSeconds(1));
    }

    @Test
    void attempt2HasBaseDelay() {
        assertEquals(30L, policy.backoffSeconds(2));
    }

    @Test
    void attempt3Has60SecondsBackoff() {
        assertEquals(60L, policy.backoffSeconds(3));
    }

    @Test
    void attempt4Has120SecondsBackoff() {
        assertEquals(120L, policy.backoffSeconds(4));
    }

    @Test
    void backoffCapsAtMaxDelay() {
        // baseDelay 30 * 2^10 = 30720 > maxDelay 600 → capped at 600
        long delay = policy.backoffSeconds(20);
        assertEquals(600L, delay);
    }

    @Test
    void retryableErrorCodesMatchConfig() {
        assertTrue(policy.isRetryable("timeout"));
        assertTrue(policy.isRetryable("connection_error"));
        assertTrue(policy.isRetryable("tool_error"));
        assertFalse(policy.isRetryable("internal_error")); // not in config
        assertFalse(policy.isRetryable("superseded"));
        assertFalse(policy.isRetryable(null));
    }

    @Test
    void computeNextScheduledAtIsInFuture() {
        LocalDateTime scheduled = policy.computeNextScheduledAt(2);
        assertTrue(scheduled.isAfter(LocalDateTime.now()));
        // should be ~30s in future
        long diffSeconds = java.time.Duration.between(LocalDateTime.now(), scheduled).getSeconds();
        assertTrue(diffSeconds >= 25 && diffSeconds <= 35, "Expected ~30s, got " + diffSeconds);
    }

    @Test
    void shouldDeadLetterAtMaxAttempts() {
        assertFalse(policy.shouldDeadLetter(1));
        assertFalse(policy.shouldDeadLetter(2));
        assertTrue(policy.shouldDeadLetter(3));
        assertTrue(policy.shouldDeadLetter(4));
    }

    @Test
    void maxDispatchCountDefaultIs3() {
        assertEquals(3, policy.getMaxDispatchCount());
    }

    @Test
    void maxAttemptsDefaultIs3() {
        assertEquals(3, policy.getMaxAttempts());
    }

    @Test
    void defaultRetryableCodesUsedWhenConfigIsBlank() {
        ReflectionTestUtils.setField(policy, "retryableErrorCodesConfig", "");
        ReflectionTestUtils.setField(policy, "parsedRetryableCodes", null);
        // Should fall back to defaults: timeout, connection_error, tool_error, internal_error
        assertTrue(policy.isRetryable("timeout"));
        assertTrue(policy.isRetryable("tool_error"));
        assertTrue(policy.isRetryable("internal_error"));
    }
}
