package com.hfusionhub.service;

import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.service.AgentStatusEventService;
import com.hfusionhub.service.AgentTaskService;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * AgentStreamEventProcessor 单元测试 — SSE 解析、状态映射
 */
class AgentStreamEventProcessorTest {

    @Test
    void stripSsePrefixStandardFormat() {
        assertEquals("{\"key\":\"value\"}",
                AgentStreamEventProcessor.stripSsePrefix("data: {\"key\":\"value\"}"));
    }

    @Test
    void stripSsePrefixNoSpace() {
        assertEquals("{\"key\":\"value\"}",
                AgentStreamEventProcessor.stripSsePrefix("data:{\"key\":\"value\"}"));
    }

    @Test
    void stripSsePrefixDoneSentinel() {
        assertEquals("[DONE]",
                AgentStreamEventProcessor.stripSsePrefix("data: [DONE]"));
    }

    @Test
    void stripSsePrefixEmptyLine() {
        assertNull(AgentStreamEventProcessor.stripSsePrefix(""));
        assertNull(AgentStreamEventProcessor.stripSsePrefix("   "));
    }

    @Test
    void stripSsePrefixNullInput() {
        assertNull(AgentStreamEventProcessor.stripSsePrefix(null));
    }

    @Test
    void stripSsePrefixNonSseFormat() {
        // Non-SSE format — treat whole line as payload
        assertEquals("plain text", AgentStreamEventProcessor.stripSsePrefix("plain text"));
    }

    @Test
    void mapPythonStatusCompleted() {
        assertEquals(AgentConstants.STATUS_SUCCEEDED,
                AgentConstants.mapPythonStatus("completed"));
    }

    @Test
    void mapPythonStatusInsufficientEvidence() {
        assertEquals(AgentConstants.STATUS_SUCCEEDED,
                AgentConstants.mapPythonStatus("insufficient_evidence"));
    }

    @Test
    void mapPythonStatusTimeout() {
        assertEquals(AgentConstants.STATUS_TIMED_OUT,
                AgentConstants.mapPythonStatus("timeout"));
    }

    @Test
    void mapPythonStatusToolError() {
        assertEquals(AgentConstants.STATUS_FAILED,
                AgentConstants.mapPythonStatus("tool_error"));
    }

    @Test
    void mapPythonStatusAgentFailure() {
        assertEquals(AgentConstants.STATUS_FAILED,
                AgentConstants.mapPythonStatus("agent_failure"));
    }

    @Test
    void mapPythonStatusCancelled() {
        assertEquals(AgentConstants.STATUS_CANCELLED,
                AgentConstants.mapPythonStatus("cancelled"));
    }

    @Test
    void mapPythonStatusNull() {
        assertEquals(AgentConstants.STATUS_FAILED,
                AgentConstants.mapPythonStatus(null));
    }

    @Test
    void mapPythonStatusUnknown() {
        assertEquals(AgentConstants.STATUS_FAILED,
                AgentConstants.mapPythonStatus("some_unknown_status"));
    }

    @Test
    void runCompletedForwardsTokenUsageForDurableSettlement() {
        AgentTaskService taskService = mock(AgentTaskService.class);
        AgentStreamEventProcessor processor = new AgentStreamEventProcessor(
                taskService, mock(AgentStatusEventService.class));

        processor.handleLine("data: {\"event\":\"run_completed\",\"status\":\"completed\","
                + "\"tool_calls_count\":2,\"token_usage\":{\"prompt_tokens\":100,"
                + "\"completion_tokens\":40,\"total_tokens\":140}}", 9L);

        verify(taskService).completeRun(eq(9L), eq(AgentConstants.STATUS_SUCCEEDED), isNull(),
                eq(Map.of("prompt_tokens", 100, "completion_tokens", 40, "total_tokens", 140)),
                eq(2), eq(0L), isNull(), isNull(), isNull());
    }

    @Test
    void canTransitionPendingToDeadLetter() {
        assertTrue(AgentConstants.canTransition(
                AgentConstants.STATUS_PENDING, AgentConstants.STATUS_DEAD_LETTER));
    }

    @Test
    void canTransitionRunningToDeadLetter() {
        assertTrue(AgentConstants.canTransition(
                AgentConstants.STATUS_RUNNING, AgentConstants.STATUS_DEAD_LETTER));
    }

    @Test
    void deadLetterIsTerminal() {
        assertTrue(AgentConstants.TERMINAL_STATUSES.contains(AgentConstants.STATUS_DEAD_LETTER));
    }

    @Test
    void isRetryableErrorCodeWithDefaults() {
        assertTrue(AgentConstants.isRetryableErrorCode("timeout", null));
        assertTrue(AgentConstants.isRetryableErrorCode("connection_error", null));
        assertTrue(AgentConstants.isRetryableErrorCode("tool_error", null));
        assertTrue(AgentConstants.isRetryableErrorCode("internal_error", null));
        assertFalse(AgentConstants.isRetryableErrorCode("superseded", null));
        assertFalse(AgentConstants.isRetryableErrorCode(null, null));
    }
}
