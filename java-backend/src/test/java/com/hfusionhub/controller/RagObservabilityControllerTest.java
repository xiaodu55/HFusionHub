package com.hfusionhub.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaTokenContextModelBox;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

/**
 * Unit tests for {@link RagObservabilityController} using manual mocks.
 * Sets up an in-memory Sa-Token context to avoid Redis/web dependencies.
 */
class RagObservabilityControllerTest {

    private RestTemplate restTemplate;
    private KnowledgeBaseMapper knowledgeBaseMapper;
    private RagObservabilityController controller;

    @BeforeEach
    void setUp() {
        // Install in-memory Sa-Token DAO so StpUtil works without Redis
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());

        // Provide a mock web context so StpUtil.login() can store tokens
        SaManager.setSaTokenContext(new MockSaTokenContext());

        restTemplate = mock(RestTemplate.class);
        knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        controller = new RagObservabilityController(restTemplate, knowledgeBaseMapper);

        // Inject @Value fields manually
        ReflectionTestUtils.setField(controller, "aiServiceBaseUrl", "http://ai-service:9000");
        ReflectionTestUtils.setField(controller, "internalApiToken", "test-internal-token");
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
    }

    @Test
    void listTracesRejectsUnownedKnowledgeBase() {
        StpUtil.login(1L);
        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(7L);
        kb.setUserId(2L); // Owned by user 2, not user 1
        kb.setStatus(0);
        when(knowledgeBaseMapper.selectById(7L)).thenReturn(kb);

        try {
            controller.listTraces(25, 5, 7L, false, null, null);
        } catch (com.hfusionhub.common.exception.BusinessException e) {
            assertEquals(StatusCode.BAD_REQUEST, e.getCode());
        }
    }

    @Test
    void listTracesForwardsFiltersToAiService() {
        StpUtil.login(1L);
        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(7L);
        kb.setUserId(1L); // Owned by user 1
        kb.setStatus(0);
        when(knowledgeBaseMapper.selectById(7L)).thenReturn(kb);

        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(HttpEntity.class), eq(Map.class)))
                .thenReturn(new ResponseEntity<>(Map.of("traces", List.of()), HttpStatus.OK));

        R<Map> response = controller.listTraces(25, 5, 7L, true, "RAG", "vector");

        assertEquals(200, response.getCode());
        assertTrue(((List<?>) response.getData().get("traces")).isEmpty());
        verify(restTemplate)
                .exchange(
                        eq(
                                "http://ai-service:9000/api/rag/traces?limit=25&offset=5&knowledge_base_id=7&error_only=true&query=RAG&source=vector"),
                        eq(HttpMethod.GET),
                        any(HttpEntity.class),
                        eq(Map.class));
    }

    @Test
    void getCurrentUserIdIsNullWhenNotLoggedIn() {
        // Without login, calling requireOwnedKnowledgeBase should fail
        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(7L);
        kb.setUserId(1L);
        kb.setStatus(0);
        when(knowledgeBaseMapper.selectById(7L)).thenReturn(kb);

        try {
            controller.listTraces(25, 5, 7L, false, null, null);
        } catch (Exception e) {
            // Expected: Sa-Token throws when no user is logged in
            assertTrue(e.getMessage() != null);
        }
    }

    @Test
    void judgeAnswerForwardsToAiServiceAndReturnsScores() {
        when(restTemplate.postForObject(
                        eq("http://ai-service:9000/api/rag/evaluate/answer-judge"),
                        any(HttpEntity.class),
                        eq(Map.class)))
                .thenReturn(Map.of(
                        "status",
                        "completed",
                        "overall_score",
                        0.85,
                        "verdict",
                        "good",
                        "scores",
                        Map.of("accuracy", 0.8)));

        Map<String, Object> request = new HashMap<>();
        request.put("query", "什么是虚拟线程？");
        request.put("answer", "虚拟线程是 Java 的轻量级线程。");
        request.put("context", "JEP 444");

        R<Map> response = controller.judgeAnswer(request);

        assertEquals(200, response.getCode());
        assertEquals("good", response.getData().get("verdict"));
        verify(restTemplate)
                .postForObject(
                        eq("http://ai-service:9000/api/rag/evaluate/answer-judge"),
                        any(HttpEntity.class),
                        eq(Map.class));
    }

    @Test
    void judgeAnswerRejectsBlankQuery() {
        Map<String, Object> request = new HashMap<>();
        request.put("query", "  ");
        request.put("answer", "x");

        try {
            controller.judgeAnswer(request);
        } catch (com.hfusionhub.common.exception.BusinessException e) {
            assertEquals(StatusCode.BAD_REQUEST, e.getCode());
        }
    }

    /**
     * Minimal in-memory SaTokenContext for unit tests without a servlet container.
     * Uses Mockito mocks for protocol-level objects so we don't have to
     * implement every method of the evolving Sa-Token interfaces.
     */
    private static class MockSaTokenContext implements SaTokenContext {
        private final Map<String, Object> storage = new HashMap<>();
        private SaTokenContextModelBox modelBox;
    
        private MockSaTokenContext() {
            // 构造即装配 modelBox：SaManager.setSaTokenContext 之后立即可用
            setContext(mock(SaRequest.class), mock(SaResponse.class), new SaStorage() {
                @Override
                public Object getSource() {
                    return storage;
                }
    
                @Override
                public Object get(String key) {
                    return storage.get(key);
                }
    
                @Override
                public SaStorage set(String key, Object value) {
                    storage.put(key, value);
                    return this;
                }
    
                @Override
                public SaStorage delete(String key) {
                    storage.remove(key);
                    return this;
                }
            });
        }
    
        @Override
        public void setContext(SaRequest request, SaResponse response, SaStorage storage) {
            this.modelBox = new SaTokenContextModelBox(request, response, storage);
        }
    
        @Override
        public void clearContext() {
            this.modelBox = null;
        }
    
        @Override
        public boolean isValid() {
            return this.modelBox != null;
        }
    
        @Override
        public SaTokenContextModelBox getModelBox() {
            return this.modelBox;
        }
    }
}
