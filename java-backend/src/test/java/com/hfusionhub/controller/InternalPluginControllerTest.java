package com.hfusionhub.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.result.R;
import com.hfusionhub.mapper.PluginAuditLogMapper;
import com.hfusionhub.service.PluginService;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/**
 * Contract tests for {@link InternalPluginController}.
 *
 * Verifies X-Internal-Token auth gate and wire format consumed by Python AI
 * for plugin ToolSpec and sandbox-config retrieval.
 */
class InternalPluginControllerTest {

    private static final String VALID_TOKEN = "test-internal-token-plugin-1";
    private InternalPluginController controller;
    private PluginService pluginService;
    private PluginAuditLogMapper pluginAuditLogMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        pluginService = mock(PluginService.class);
        pluginAuditLogMapper = mock(PluginAuditLogMapper.class);
        controller = new InternalPluginController(pluginService, pluginAuditLogMapper);
        ReflectionTestUtils.setField(controller, "expectedToken", VALID_TOKEN);
    }

    @AfterEach
    void tearDown() {
        reset(pluginService, pluginAuditLogMapper);
    }

    private HttpServletRequest req(String token) {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getHeader("X-Internal-Token")).thenReturn(token);
        return request;
    }

    @Test
    void toolSpecsReturns200WithValidToken() {
        List<Map<String, Object>> specs = List.of(
                Map.of("plugin_id", "pid-1", "name", "web_search", "version", "1.0.0")
        );
        when(pluginService.getPluginToolSpecs()).thenReturn(specs);

        R<List<Map<String, Object>>> r = controller.getPluginToolSpecs(req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals(1, r.getData().size());
        verify(pluginService).getPluginToolSpecs();
    }

    @Test
    void toolSpecsReturns403WithWrongToken() {
        R<List<Map<String, Object>>> r = controller.getPluginToolSpecs(req("wrong-token"));
        assertEquals(403, r.getCode());
        verifyNoInteractions(pluginService);
    }

    @Test
    void toolSpecsReturns403WithNullToken() {
        R<List<Map<String, Object>>> r = controller.getPluginToolSpecs(req(null));
        assertEquals(403, r.getCode());
        verifyNoInteractions(pluginService);
    }

    @Test
    void sandboxConfigReturnsConfigWhenPluginExists() {
        var plugin = new com.hfusionhub.entity.Plugin();
        plugin.setName("web_search");
        plugin.setVersion("1.0.0");
        plugin.setEnabled(true);
        plugin.setSandboxConfig("{\"network\":{\"allowed_domains\":[\"example.com\"]}}");
        plugin.setPermissions("[\"web_access\"]");
        when(pluginService.getByPluginId("pid-1")).thenReturn(plugin);

        R<Map<String, Object>> r = controller.getSandboxConfig("pid-1", req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals("pid-1", r.getData().get("plugin_id"));
        assertNotNull(r.getData().get("sandbox_config"));
    }

    @Test
    void sandboxConfigReturns404WhenPluginNotFound() {
        when(pluginService.getByPluginId("nonexistent")).thenReturn(null);

        R<Map<String, Object>> r = controller.getSandboxConfig("nonexistent", req(VALID_TOKEN));

        assertEquals(404, r.getCode());
    }

    @Test
    void sandboxConfigReturns404WhenPluginDisabled() {
        var plugin = new com.hfusionhub.entity.Plugin();
        plugin.setEnabled(false);
        when(pluginService.getByPluginId("pid-1")).thenReturn(plugin);

        R<Map<String, Object>> r = controller.getSandboxConfig("pid-1", req(VALID_TOKEN));

        assertEquals(404, r.getCode());
    }

    @Test
    void sandboxConfigReturns403WithWrongToken() {
        R<Map<String, Object>> r = controller.getSandboxConfig("pid-1", req("wrong"));
        assertEquals(403, r.getCode());
        verifyNoInteractions(pluginService);
    }

    @Test
    void wireFormatMatchesPythonClient() throws Exception {
        List<Map<String, Object>> specs = List.of(
                Map.of("plugin_id", "pid-1", "name", "web_search")
        );
        when(pluginService.getPluginToolSpecs()).thenReturn(specs);

        R<List<Map<String, Object>>> r = controller.getPluginToolSpecs(req(VALID_TOKEN));
        String wire = objectMapper.writeValueAsString(r);

        JsonNode envelope = objectMapper.readTree(wire);
        assertEquals(200, envelope.get("code").asInt());
        assertEquals("success", envelope.get("message").asText());
        assertTrue(envelope.get("data").isArray());
        assertEquals("web_search", envelope.get("data").get(0).get("name").asText());
    }

    // ── POST /internal/plugin/audit-logs ──────────────────────────────

    @Test
    void auditLogsReturns200WithValidToken() {
        var plugin = new com.hfusionhub.entity.Plugin();
        plugin.setId(100L);
        when(pluginService.getByPluginId("pid-1")).thenReturn(plugin);

        List<Map<String, Object>> entries = List.of(
                Map.of("pluginName", "web_search", "action", "install", "pluginId", "pid-1")
        );

        R<Map<String, Object>> r = controller.receiveAuditLogs(entries, req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals(1, r.getData().get("inserted"));
        assertEquals(0, r.getData().get("skipped"));
        verify(pluginAuditLogMapper, times(1)).insert(any());
    }

    @Test
    void auditLogsReturns403WithWrongToken() {
        List<Map<String, Object>> entries = List.of(
                Map.of("pluginName", "web_search", "action", "install")
        );

        R<Map<String, Object>> r = controller.receiveAuditLogs(entries, req("wrong"));

        assertEquals(403, r.getCode());
        verifyNoInteractions(pluginAuditLogMapper);
    }

    @Test
    void auditLogsReturns403WithNullToken() {
        List<Map<String, Object>> entries = List.of(
                Map.of("pluginName", "web_search", "action", "install")
        );

        R<Map<String, Object>> r = controller.receiveAuditLogs(entries, req(null));

        assertEquals(403, r.getCode());
        verifyNoInteractions(pluginAuditLogMapper);
    }

    @Test
    void auditLogsHandlesMultipleEntries() {
        when(pluginService.getByPluginId("pid-1")).thenReturn(null);

        List<Map<String, Object>> entries = List.of(
                Map.of("pluginName", "web_search", "action", "install", "pluginId", "pid-1"),
                Map.of("pluginName", "web_search", "action", "enable", "pluginId", "pid-1"),
                Map.of("pluginName", "calc", "action", "install", "pluginId", "pid-2")
        );

        R<Map<String, Object>> r = controller.receiveAuditLogs(entries, req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals(3, r.getData().get("inserted"));
        assertEquals(0, r.getData().get("skipped"));
        verify(pluginAuditLogMapper, times(3)).insert(any());
    }

    @Test
    void auditLogsSkipsFailedEntries() {
        when(pluginAuditLogMapper.insert(any()))
                .thenThrow(new RuntimeException("DB error"))
                .thenReturn(1);

        List<Map<String, Object>> entries = List.of(
                Map.of("pluginName", "web_search", "action", "install"),
                Map.of("pluginName", "calc", "action", "install")
        );

        R<Map<String, Object>> r = controller.receiveAuditLogs(entries, req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals(1, r.getData().get("inserted"));
        assertEquals(1, r.getData().get("skipped"));
        verify(pluginAuditLogMapper, times(2)).insert(any());
    }

    @Test
    void auditLogsSkipsDuplicateEventId() {
        // First entry with eventId "evt-1" — should be inserted
        var existingLog = new com.hfusionhub.entity.PluginAuditLog();
        existingLog.setEventId("evt-1");
        when(pluginAuditLogMapper.selectByEventId("evt-1")).thenReturn(existingLog);

        List<Map<String, Object>> entries = List.of(
                Map.of("pluginName", "web_search", "action", "install", "eventId", "evt-1")
        );

        R<Map<String, Object>> r = controller.receiveAuditLogs(entries, req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals(0, r.getData().get("inserted"));
        assertEquals(1, r.getData().get("skipped"));
        verify(pluginAuditLogMapper, never()).insert(any());
    }

    @Test
    void auditLogsInsertsNewEventId() {
        when(pluginAuditLogMapper.selectByEventId("evt-new")).thenReturn(null);

        List<Map<String, Object>> entries = List.of(
                Map.of("pluginName", "web_search", "action", "install", "eventId", "evt-new")
        );

        R<Map<String, Object>> r = controller.receiveAuditLogs(entries, req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals(1, r.getData().get("inserted"));
        assertEquals(0, r.getData().get("skipped"));
        verify(pluginAuditLogMapper, times(1)).insert(any());
    }
}
