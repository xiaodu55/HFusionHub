package com.hfusionhub.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.KnowledgeBase;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RagObservabilityControllerTest {

    @Test
    void listTracesForwardsFiltersToAiService() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        com.hfusionhub.mapper.KnowledgeBaseMapper knowledgeBaseMapper = mock(com.hfusionhub.mapper.KnowledgeBaseMapper.class);
        KnowledgeBase knowledgeBase = new KnowledgeBase();
        knowledgeBase.setUserId(1L);
        when(knowledgeBaseMapper.selectById(7L)).thenReturn(knowledgeBase);
        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(HttpEntity.class), eq(Map.class)))
                .thenReturn(new ResponseEntity<>(Map.of("traces", List.of()), HttpStatus.OK));
        RagObservabilityController controller = new RagObservabilityController(restTemplate, knowledgeBaseMapper);
        ReflectionTestUtils.setField(controller, "aiServiceBaseUrl", "http://ai-service:9000");
        ReflectionTestUtils.setField(controller, "internalApiToken", "test-internal-token");
        StpUtil.login(1L);

        try {
            R<Map> response = controller.listTraces(25, 5, 7L, true, "RAG", "vector");

            assertEquals(200, response.getCode());
            assertTrue(((List<?>) response.getData().get("traces")).isEmpty());
            verify(restTemplate).exchange(
                    "http://ai-service:9000/api/rag/traces?limit=25&offset=5&knowledge_base_id=7&error_only=true&query=RAG&source=vector",
                    HttpMethod.GET, any(HttpEntity.class), eq(Map.class)
            );
        } finally {
            StpUtil.logout();
        }
    }
}
