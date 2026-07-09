package com.hfusionhub.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.MemoryEntry;
import com.hfusionhub.service.MemoryService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

class InternalMemoryControllerTest {

    private static final String TOKEN = "memory-internal-token";

    private MemoryService memoryService;
    private InternalMemoryController controller;

    @BeforeEach
    void setUp() {
        memoryService = mock(MemoryService.class);
        controller = new InternalMemoryController(memoryService);
        ReflectionTestUtils.setField(controller, "expectedToken", TOKEN);
    }

    // ── token 校验 ─────────────────────────────────────────────────────

    @Test
    void saveEntriesRejectsInvalidToken() {
        R<Map<String, Object>> response =
                controller.saveEntries(payload(), request("wrong-token"));

        assertEquals(403, response.getCode());
        verifyNoInteractions(memoryService);
    }

    @Test
    void relevantRejectsInvalidToken() {
        R<List<MemoryEntry>> response =
                controller.relevant(1L, "query", null, 8, request("wrong-token"));

        assertEquals(403, response.getCode());
        verifyNoInteractions(memoryService);
    }

    // ── 批量写入 ───────────────────────────────────────────────────────

    @Test
    void saveEntriesMapsFieldsAndDelegatesToService() {
        when(memoryService.saveBatchForUser(any(), any(), any(), anyList())).thenReturn(2);

        R<Map<String, Object>> response = controller.saveEntries(payload(), request(TOKEN));

        assertEquals(200, response.getCode());
        assertEquals(2, response.getData().get("saved"));
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<MemoryEntry>> captor = ArgumentCaptor.forClass(List.class);
        verify(memoryService)
                .saveBatchForUser(eq(7L), eq(42L), eq(5L), captor.capture());
        List<MemoryEntry> entries = captor.getValue();
        assertEquals(2, entries.size());
        assertEquals("用户偏好简洁回答", entries.get(0).getContent());
        assertEquals("user_preference", entries.get(0).getType());
        assertEquals(0.9, entries.get(0).getImportance(), 1e-9);
        assertEquals("团队在深圳办公", entries.get(1).getContent());
        assertEquals("entity_fact", entries.get(1).getType());
        // 缺省 importance 透传为 null，由 MemoryServiceImpl.saveBatchForUser 补默认 0.5
        assertNull(entries.get(1).getImportance());
    }

    @Test
    void saveEntriesRequiresUserId() {
        Map<String, Object> body = payload();
        body.remove("user_id");

        R<Map<String, Object>> response = controller.saveEntries(body, request(TOKEN));

        assertEquals(400, response.getCode());
        verifyNoInteractions(memoryService);
    }

    @Test
    void saveEntriesRejectsEmptyEntries() {
        Map<String, Object> body = new HashMap<>();
        body.put("user_id", 7L);
        body.put("entries", List.of());

        R<Map<String, Object>> response = controller.saveEntries(body, request(TOKEN));

        assertEquals(400, response.getCode());
        verifyNoInteractions(memoryService);
    }

    @Test
    void saveEntriesRejectsOversizedBatch() {
        Map<String, Object> body = payload();
        java.util.List<Map<String, Object>> tooMany = new java.util.ArrayList<>();
        for (int i = 0; i < 51; i++) {
            tooMany.add(Map.of("content", "fact-" + i, "type", "entity_fact"));
        }
        body.put("entries", tooMany);

        R<Map<String, Object>> response = controller.saveEntries(body, request(TOKEN));

        assertEquals(400, response.getCode());
        verifyNoInteractions(memoryService);
    }

    @Test
    void saveEntriesSkipsNonMapItems() {
        when(memoryService.saveBatchForUser(any(), any(), any(), anyList())).thenReturn(1);
        Map<String, Object> body = payload();
        body.put("entries", List.of("garbage", Map.of("content", "ok", "type", "entity_fact")));

        controller.saveEntries(body, request(TOKEN));

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<MemoryEntry>> captor = ArgumentCaptor.forClass(List.class);
        verify(memoryService).saveBatchForUser(eq(7L), any(), any(), captor.capture());
        assertEquals(1, captor.getValue().size());
        assertEquals("ok", captor.getValue().get(0).getContent());
    }

    // ── 相关性查询 ─────────────────────────────────────────────────────

    @Test
    void relevantDelegatesToService() {
        MemoryEntry entry = new MemoryEntry();
        entry.setContent("用户偏好简洁回答");
        entry.setType("user_preference");
        when(memoryService.getRelevantMemories(eq(7L), eq(5L), eq("偏好"), eq(8)))
                .thenReturn(List.of(entry));

        R<List<MemoryEntry>> response =
                controller.relevant(7L, "偏好", 5L, 8, request(TOKEN));

        assertEquals(200, response.getCode());
        assertEquals(1, response.getData().size());
        assertEquals("user_preference", response.getData().get(0).getType());
    }

    @Test
    void relevantRequiresPositiveUserId() {
        R<List<MemoryEntry>> response =
                controller.relevant(0L, "query", null, 8, request(TOKEN));

        assertEquals(400, response.getCode());
        verifyNoInteractions(memoryService);
    }

    // ── 辅助 ───────────────────────────────────────────────────────────

    private static Map<String, Object> payload() {
        Map<String, Object> body = new HashMap<>();
        body.put("user_id", 7L);
        body.put("conversation_id", 42L);
        body.put("knowledge_base_id", 5L);
        body.put(
                "entries",
                List.of(
                        Map.of("content", "用户偏好简洁回答", "type", "user_preference", "importance", 0.9),
                        Map.of("content", "团队在深圳办公", "type", "entity_fact")));
        return body;
    }

    private static HttpServletRequest request(String token) {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getHeader("X-Internal-Token")).thenReturn(token);
        return request;
    }
}
