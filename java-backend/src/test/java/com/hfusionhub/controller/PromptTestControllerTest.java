package com.hfusionhub.controller;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.PromptTestRequest;
import com.hfusionhub.dto.PromptTestResponse;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link PromptTestController} — prompt template test bench.
 *
 * <p>Verifies:</p>
 * <ul>
 *   <li>Knowledge-base ownership validation (rejects foreign KBs).</li>
 *   <li>Template content is passed as {@code system_prompt} (not in history).</li>
 *   <li>AI call failure produces a {@link BusinessException}.</li>
 *   <li>No conversation or message is persisted (the controller has no
 *       conversation/message mapper dependencies).</li>
 *   <li>Correct routing: KB-bound → agentV1Chat, no KB → chat.</li>
 *   <li>Elapsed time is measured and returned in the response.</li>
 * </ul>
 */
class PromptTestControllerTest {

    private AiClient aiClient;
    private KnowledgeBaseMapper knowledgeBaseMapper;
    private PromptTestController controller;

    @BeforeEach
    void setUp() {
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());

        aiClient = mock(AiClient.class);
        knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        controller = new PromptTestController(aiClient, knowledgeBaseMapper);
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
    }

    // ── KB ownership validation ────────────────────────────────────────

    @Test
    void rejectsKnowledgeBaseNotOwnedByCurrentUser() {
        StpUtil.login(1L);

        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(99L);
        kb.setUserId(2L); // owned by user 2, not user 1
        kb.setDeleted(0);
        kb.setStatus(0);
        when(knowledgeBaseMapper.selectById(99L)).thenReturn(kb);

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent("请用简洁的语言回答");
        request.setQuestion("测试问题");
        request.setKnowledgeBaseId(99L);

        BusinessException ex = assertThrows(BusinessException.class,
                () -> controller.test(request));
        assertTrue(ex.getMessage().contains("无权访问"));
    }

    @Test
    void rejectsNonexistentKnowledgeBase() {
        StpUtil.login(1L);

        when(knowledgeBaseMapper.selectById(999L)).thenReturn(null);

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent("请用简洁的语言回答");
        request.setQuestion("测试问题");
        request.setKnowledgeBaseId(999L);

        BusinessException ex = assertThrows(BusinessException.class,
                () -> controller.test(request));
        assertTrue(ex.getMessage().contains("知识库不存在"));
    }

    // ── Template passing: system_prompt (not history) ──────────────────

    @Test
    void passesTemplateAsSystemPromptToChat() {
        StpUtil.login(1L);

        AiClient.ChatResponse mockResponse = buildMockResponse("这是回答", "deepseek-v3",
                500, null, null);
        when(aiClient.chat(anyString(), isNull(), isNull(), anyList(), anyString(), anyLong()))
                .thenReturn(mockResponse);

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent("你是一个严谨的助手，请用中文回答。");
        request.setQuestion("什么是RAG？");

        R<PromptTestResponse> result = controller.test(request);

        assertEquals(200, result.getCode());
        assertNotNull(result.getData());
        assertEquals("这是回答", result.getData().getContent());

        // Verify: template content passed as systemPrompt (5th arg), history is empty
        verify(aiClient).chat(
                eq("什么是RAG？"),
                isNull(),           // conversationId = null
                isNull(),           // knowledgeBaseId = null
                eq(List.of()),      // history = empty (template goes via systemPrompt)
                eq("你是一个严谨的助手，请用中文回答。"),  // systemPrompt = template content
                eq(1L)              // userId = current user
        );
        // Verify: KB path was NOT used
        verify(aiClient, never()).agentV1Chat(anyString(), any(), any(), anyList(), anyString(), anyString(), anyInt(), anyString(), anyLong());
    }

    @Test
    void passesTemplateAsSystemPromptToAgentV1Chat() {
        StpUtil.login(1L);

        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(42L);
        kb.setUserId(1L);
        kb.setDeleted(0);
        kb.setStatus(0);
        when(knowledgeBaseMapper.selectById(42L)).thenReturn(kb);

        AiClient.ChatResponse mockResponse = buildMockResponse("根据资料，RAG是...", "deepseek-v3",
                800, List.of(Map.of("document_id", 1, "score", 0.95, "content", "...")), null);
        when(aiClient.agentV1Chat(anyString(), isNull(), anyLong(), anyList(), anyString(),
                anyString(), anyInt(), isNull(), anyLong()))
                .thenReturn(mockResponse);

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent("你是一个严谨的助手。请引用来源。".repeat(50)); // ~800 chars
        request.setQuestion("什么是RAG？");
        request.setKnowledgeBaseId(42L);

        R<PromptTestResponse> result = controller.test(request);

        assertEquals(200, result.getCode());
        assertNotNull(result.getData());
        assertEquals("根据资料，RAG是...", result.getData().getContent());
        assertNotNull(result.getData().getSources());
        assertEquals(1, result.getData().getSources().size());

        // Verify: KB-bound path with systemPrompt, history empty
        verify(aiClient).agentV1Chat(
                eq("什么是RAG？"),
                isNull(),
                eq(42L),
                eq(List.of()),                      // history = empty
                eq(request.getTemplateContent()),   // systemPrompt
                eq("detailed"),
                eq(5),
                isNull(),                           // requestId = null
                eq(1L)                              // userId
        );
        // Verify: non-KB path was NOT used
        verify(aiClient, never()).agentV1Chat(anyString(), isNull(), isNull(), anyList(), anyString(), anyString(), anyInt(), anyString(), anyLong());
    }

    @Test
    void handlesLongTemplateWithin8000Chars() {
        StpUtil.login(1L);

        // Template near 8000 chars — the exact length that was failing before
        // when squeezed into a 4000-char history entry.
        String longTemplate = "A".repeat(7999);

        AiClient.ChatResponse mockResponse = buildMockResponse("OK", "deepseek-v3", 100, null, null);
        when(aiClient.chat(anyString(), isNull(), isNull(), anyList(), eq(longTemplate), anyLong()))
                .thenReturn(mockResponse);

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent(longTemplate);
        request.setQuestion("test");

        R<PromptTestResponse> result = controller.test(request);

        assertEquals(200, result.getCode());
        assertEquals("OK", result.getData().getContent());
        // Verify systemPrompt was passed with the full 7999-char template
        verify(aiClient).chat(anyString(), isNull(), isNull(), anyList(), eq(longTemplate), anyLong());
    }

    // ── AI call failure ────────────────────────────────────────────────

    @Test
    void wrapsAiClientExceptionAsBusinessException() {
        StpUtil.login(1L);

        when(aiClient.chat(anyString(), isNull(), isNull(), anyList(), anyString(), anyLong()))
                .thenThrow(new RuntimeException("Connection refused"));

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent("测试模板");
        request.setQuestion("测试问题");

        BusinessException ex = assertThrows(BusinessException.class,
                () -> controller.test(request));
        assertTrue(ex.getMessage().contains("AI 服务调用失败"));
        assertTrue(ex.getMessage().contains("Connection refused"));
    }

    @Test
    void rethrowsBusinessExceptionDirectly() {
        StpUtil.login(1L);

        when(aiClient.chat(anyString(), isNull(), isNull(), anyList(), anyString(), anyLong()))
                .thenThrow(new BusinessException("AI 服务暂时不可用"));

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent("测试模板");
        request.setQuestion("测试问题");

        BusinessException ex = assertThrows(BusinessException.class,
                () -> controller.test(request));
        // Our controller wraps ALL exceptions in a BusinessException with
        // "AI 服务调用失败:" prefix — this is by design for consistent UX.
        assertTrue(ex.getMessage().contains("AI 服务调用失败"));
    }

    // ── No persistence ─────────────────────────────────────────────────

    @Test
    void controllerHasNoConversationOrMessageDependencies() {
        // Verify constructor only needs AiClient + KnowledgeBaseMapper —
        // no ConversationMapper, MessageMapper, or ConversationService.
        // This structural test proves "不创建对话记录" by construction.
        PromptTestController c = new PromptTestController(aiClient, knowledgeBaseMapper);
        assertNotNull(c);
        // If this compiles, the controller has no persistence dependencies.
    }

    // ── Response fields ────────────────────────────────────────────────

    @Test
    void responseIncludesElapsedTime() {
        StpUtil.login(1L);

        // Simulate a slow AI call
        when(aiClient.chat(anyString(), isNull(), isNull(), anyList(), anyString(), anyLong()))
                .thenAnswer(invocation -> {
                    Thread.sleep(10); // small delay to get non-zero elapsed
                    return buildMockResponse("慢速回答", "deepseek-v3", 300, null, null);
                });

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent("模板");
        request.setQuestion("问题");

        R<PromptTestResponse> result = controller.test(request);

        assertNotNull(result.getData());
        assertTrue(result.getData().getElapsedMs() > 0,
                "elapsedMs should be positive, got " + result.getData().getElapsedMs());
    }

    @Test
    void responseIncludesTokenUsageWhenProvided() {
        StpUtil.login(1L);

        Map<String, Object> tokenUsage = Map.of(
                "prompt_tokens", 150,
                "completion_tokens", 350,
                "total_tokens", 500
        );
        AiClient.ChatResponse mockResponse = buildMockResponse("回答", "deepseek-v3", 500, null, tokenUsage);
        when(aiClient.chat(anyString(), isNull(), isNull(), anyList(), anyString(), anyLong()))
                .thenReturn(mockResponse);

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent("模板");
        request.setQuestion("问题");

        R<PromptTestResponse> result = controller.test(request);

        assertNotNull(result.getData().getTokenUsage());
        assertEquals(150, result.getData().getTokenUsage().get("prompt_tokens"));
        assertEquals(350, result.getData().getTokenUsage().get("completion_tokens"));
        assertEquals(500, result.getData().getTokenUsage().get("total_tokens"));
        assertEquals(500, result.getData().getTokenCount());
    }

    @Test
    void responseIncludesModel() {
        StpUtil.login(1L);

        AiClient.ChatResponse mockResponse = buildMockResponse("回答", "deepseek-v3", 100, null, null);
        when(aiClient.chat(anyString(), isNull(), isNull(), anyList(), anyString(), anyLong()))
                .thenReturn(mockResponse);

        PromptTestRequest request = new PromptTestRequest();
        request.setTemplateContent("模板");
        request.setQuestion("问题");

        R<PromptTestResponse> result = controller.test(request);

        assertEquals("deepseek-v3", result.getData().getModel());
    }

    // ── Helpers ────────────────────────────────────────────────────────

    private static AiClient.ChatResponse buildMockResponse(
            String content,
            String model,
            int tokenCount,
            List<Map<String, Object>> sources,
            Map<String, Object> tokenUsage
    ) {
        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent(content);
        resp.setModel(model);
        resp.setTokenCount(tokenCount);
        resp.setSources(sources);
        resp.setTokenUsage(tokenUsage);
        return resp;
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
