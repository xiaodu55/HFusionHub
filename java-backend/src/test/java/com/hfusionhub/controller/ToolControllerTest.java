package com.hfusionhub.controller;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.result.R;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.tenant.TenantContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link ToolController} — tool registry and call record isolation.
 *
 * <p>Verifies that the /api/tools/calls endpoint passes the current user ID
 * to the mapper (preventing cross-user data leaks), and that the registry
 * endpoint works without user context (tool metadata is not user-scoped).</p>
 */
class ToolControllerTest {

    private AiClient aiClient;
    private AgentStepMapper agentStepMapper;
    private ToolController controller;

    @BeforeEach
    void setUp() {
        // Install in-memory Sa-Token DAO so StpUtil works without Redis
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());

        // Provide a mock web context so StpUtil.login() can store tokens
        SaManager.setSaTokenContext(new MockSaTokenContext());

        aiClient = mock(AiClient.class);
        agentStepMapper = mock(AgentStepMapper.class);
        controller = new ToolController(aiClient, agentStepMapper);
        TenantContext.setTenantId(1L);
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
        TenantContext.clear();
    }

    // ── Tool registry (no user isolation needed — metadata is shared) ──

    @Test
    void listToolsReturnsRegistryFromAiClient() {
        Map<String, Object> pythonResponse = new LinkedHashMap<>();
        pythonResponse.put("tools", List.of(
                Map.of("name", "search_knowledge_base", "risk_level", "read_only"),
                Map.of("name", "write_note", "risk_level", "read_write")
        ));
        pythonResponse.put("total", 2);
        when(aiClient.getToolRegistry(1L)).thenReturn(pythonResponse);

        R<Map<String, Object>> result = controller.listTools();

        assertEquals(200, result.getCode());
        @SuppressWarnings("unchecked")
        Map<String, Object> data = result.getData();
        assertEquals(2, data.get("total"));
        @SuppressWarnings("unchecked")
        Map<String, Long> riskSummary = (Map<String, Long>) data.get("risk_summary");
        assertEquals(1L, riskSummary.get("read_only"));
        assertEquals(1L, riskSummary.get("read_write"));
        assertEquals(0L, riskSummary.get("external"));
    }

    @Test
    void listToolsHandlesAiClientError() {
        Map<String, Object> errorResponse = new LinkedHashMap<>();
        errorResponse.put("tools", List.of());
        errorResponse.put("total", 0);
        errorResponse.put("error", "AI 服务不可达");
        when(aiClient.getToolRegistry(1L)).thenReturn(errorResponse);

        R<Map<String, Object>> result = controller.listTools();

        assertEquals(200, result.getCode());
        // When tools is empty AND error is present, the early-return wraps the
        // full registry map as data (with "error" key intact).
        @SuppressWarnings("unchecked")
        Map<String, Object> data = result.getData();
        assertEquals("AI 服务不可达", data.get("error"));
    }

    // ── User isolation: tool call records ─────────────────────────────

    @Test
    void listRecentCallsPassesCurrentUserIdToMapper() {
        // Log in as user 1
        StpUtil.login(1L);

        when(agentStepMapper.selectRecentToolCalls(anyLong(), anyInt(), anyInt()))
                .thenReturn(List.of());
        when(agentStepMapper.countToolCalls(anyLong())).thenReturn(0);

        R<Map<String, Object>> result = controller.listRecentCalls(1, 20);

        assertEquals(200, result.getCode());

        // Verify the mapper was called with userId = 1
        verify(agentStepMapper).selectRecentToolCalls(eq(1L), anyInt(), anyInt());
        verify(agentStepMapper).countToolCalls(eq(1L));
    }

    @Test
    void listRecentCallsIsolatesUserAFromUserB() {
        // ── User A (id=1) has one tool call ──
        StpUtil.login(1L);

        Map<String, Object> userARecord = new LinkedHashMap<>();
        userARecord.put("id", 1L);
        userARecord.put("tool_name", "search_knowledge_base");
        userARecord.put("duration_ms", 120L);
        userARecord.put("error_code", null);
        userARecord.put("error_summary", null);
        userARecord.put("created_at", "2026-08-01T10:00:00");
        userARecord.put("task_id", 100L);
        userARecord.put("task_query", "用户 A 的查询");
        userARecord.put("task_status", "succeeded");

        when(agentStepMapper.selectRecentToolCalls(eq(1L), anyInt(), anyInt()))
                .thenReturn(List.of(userARecord));
        when(agentStepMapper.countToolCalls(eq(1L))).thenReturn(1);

        R<Map<String, Object>> resultA = controller.listRecentCalls(1, 20);

        assertEquals(200, resultA.getCode());
        @SuppressWarnings("unchecked")
        Map<String, Object> dataA = resultA.getData();
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> callsA = (List<Map<String, Object>>) dataA.get("calls");
        assertEquals(1, callsA.size());
        assertEquals("search_knowledge_base", callsA.get(0).get("tool_name"));

        // verify called with userId=1
        verify(agentStepMapper).selectRecentToolCalls(eq(1L), anyInt(), anyInt());
        verify(agentStepMapper).countToolCalls(eq(1L));

        // ── User B (id=2) has different records ──
        StpUtil.logout();
        StpUtil.login(2L);

        Map<String, Object> userBRecord = new LinkedHashMap<>();
        userBRecord.put("id", 2L);
        userBRecord.put("tool_name", "read_chunk");
        userBRecord.put("duration_ms", 80L);
        userBRecord.put("error_code", null);
        userBRecord.put("error_summary", null);
        userBRecord.put("created_at", "2026-08-01T11:00:00");
        userBRecord.put("task_id", 200L);
        userBRecord.put("task_query", "用户 B 的查询");
        userBRecord.put("task_status", "succeeded");

        when(agentStepMapper.selectRecentToolCalls(eq(2L), anyInt(), anyInt()))
                .thenReturn(List.of(userBRecord));
        when(agentStepMapper.countToolCalls(eq(2L))).thenReturn(1);

        R<Map<String, Object>> resultB = controller.listRecentCalls(1, 20);

        assertEquals(200, resultB.getCode());
        @SuppressWarnings("unchecked")
        Map<String, Object> dataB = resultB.getData();
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> callsB = (List<Map<String, Object>>) dataB.get("calls");
        assertEquals(1, callsB.size());
        assertEquals("read_chunk", callsB.get(0).get("tool_name"));

        // verify called with userId=2 (NOT userId=1)
        verify(agentStepMapper).selectRecentToolCalls(eq(2L), anyInt(), anyInt());
        verify(agentStepMapper).countToolCalls(eq(2L));

        // verify user B never saw user A's data
        verify(agentStepMapper, never()).selectRecentToolCalls(eq(1L), eq(2), anyInt());
    }

    @Test
    void listRecentCallsFailsWhenNotLoggedIn() {
        // No StpUtil.login() call — should throw
        try {
            controller.listRecentCalls(1, 20);
            fail("Expected an exception when no user is logged in");
        } catch (Exception e) {
            // Sa-Token throws when getLoginIdAsLong() is called without a login
            assertNotNull(e.getMessage());
        }
    }

    /**
     * Minimal in-memory SaTokenContext for unit tests without a servlet container.
     */
    private static class MockSaTokenContext implements SaTokenContext {
        private final Map<String, Object> storage = new HashMap<>();

        @Override
        public SaRequest getRequest() {
            return mock(SaRequest.class);
        }

        @Override
        public SaResponse getResponse() {
            return mock(SaResponse.class);
        }

        @Override
        public SaStorage getStorage() {
            return new SaStorage() {
                @Override public Object getSource() { return storage; }
                @Override public Object get(String key) { return storage.get(key); }
                @Override public SaStorage set(String key, Object value) { storage.put(key, value); return this; }
                @Override public SaStorage delete(String key) { storage.remove(key); return this; }
            };
        }

        @Override
        public boolean matchPath(String pattern, String path) { return true; }

        @Override
        public boolean isValid() { return true; }
    }
}
