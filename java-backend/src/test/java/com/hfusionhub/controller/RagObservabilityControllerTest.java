package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RagObservabilityControllerTest {

    @Test
    void listTracesForwardsFiltersToAiService() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        when(restTemplate.getForObject(anyString(), eq(Map.class)))
                .thenReturn(Map.of("traces", List.of()));
        RagObservabilityController controller = new RagObservabilityController(restTemplate);
        ReflectionTestUtils.setField(controller, "aiServiceBaseUrl", "http://ai-service:9000");

        R<Map> response = controller.listTraces(25, 5, 7L, true, "RAG", "vector");

        assertEquals(200, response.getCode());
        assertTrue(((List<?>) response.getData().get("traces")).isEmpty());
        verify(restTemplate).getForObject(
                "http://ai-service:9000/api/rag/traces?limit=25&offset=5&knowledge_base_id=7&error_only=true&query=RAG&source=vector",
                Map.class
        );
    }
}
