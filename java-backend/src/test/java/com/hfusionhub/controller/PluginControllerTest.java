package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.Plugin;
import com.hfusionhub.service.PluginService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link PluginController}.
 *
 * Verifies install validation, enable/disable/uninstall delegation, and the
 * wire envelope format consumed by the frontend.
 */
class PluginControllerTest {

    private PluginService pluginService;
    private PluginController controller;

    @BeforeEach
    void setUp() {
        pluginService = mock(PluginService.class);
        controller = new PluginController(pluginService);
    }

    @AfterEach
    void tearDown() {
        reset(pluginService);
    }

    private Plugin samplePlugin(String pluginId, String name, String version) {
        Plugin p = new Plugin();
        p.setId(1L);
        p.setPluginId(pluginId);
        p.setName(name);
        p.setDisplayName(name + " Display");
        p.setVersion(version);
        p.setDescription("A test plugin");
        p.setStatus("active");
        p.setEnabled(true);
        p.setSource("local");
        p.setManifestHash("abc123hash");
        return p;
    }

    private Map<String, Object> validManifest() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("name", "test_plugin");
        m.put("version", "1.0.0");
        m.put("description", "A test plugin");
        m.put("author", "testuser");
        m.put("artifact_hash", "a".repeat(64)); // mandatory SHA-256
        return m;
    }

    @Test
    void installSuccessReturns200WithPlugin() {
        Plugin plugin = samplePlugin("pid-1", "test_plugin", "1.0.0");
        when(pluginService.install(any())).thenReturn(plugin);

        R<Plugin> result = controller.install(validManifest());

        assertEquals(200, result.getCode());
        assertNotNull(result.getData());
        assertEquals("test_plugin", result.getData().getName());
        verify(pluginService).install(any());
    }

    @Test
    void installMissingFieldReturns400() {
        Map<String, Object> bad = new LinkedHashMap<>();
        bad.put("version", "1.0.0");
        when(pluginService.install(any())).thenThrow(new IllegalArgumentException("manifest 缺少必填字段: name"));

        R<Plugin> result = controller.install(bad);

        assertEquals(400, result.getCode());
        assertTrue(result.getMessage().contains("name"));
        verify(pluginService).install(any());
    }

    @Test
    void installMissingArtifactHashReturns400() {
        Map<String, Object> bad = new LinkedHashMap<>();
        bad.put("name", "test");
        bad.put("version", "1.0.0");
        bad.put("description", "desc");
        // no artifact_hash
        when(pluginService.install(any())).thenThrow(new IllegalArgumentException("缺少必填字段: artifact_hash"));

        R<Plugin> result = controller.install(bad);

        assertEquals(400, result.getCode());
        assertTrue(result.getMessage().contains("artifact_hash"));
    }

    @Test
    void installDuplicateReturns409() {
        when(pluginService.install(any())).thenThrow(new IllegalStateException("插件已存在"));

        R<Plugin> result = controller.install(validManifest());

        assertEquals(409, result.getCode());
        verify(pluginService).install(any());
    }

    @Test
    void getPluginReturnsPluginWhenFound() {
        Plugin plugin = samplePlugin("pid-1", "test_plugin", "1.0.0");
        when(pluginService.getByPluginId("pid-1")).thenReturn(plugin);

        R<Plugin> result = controller.getPlugin("pid-1");

        assertEquals(200, result.getCode());
        assertEquals("pid-1", result.getData().getPluginId());
    }

    @Test
    void getPluginReturnsErrorWhenNotFound() {
        when(pluginService.getByPluginId("nonexistent")).thenReturn(null);

        R<Plugin> result = controller.getPlugin("nonexistent");

        assertEquals(500, result.getCode());
        assertTrue(result.getMessage().contains("不存在"));
    }

    @Test
    void listPluginsReturnsPageResult() {
        List<Plugin> plugins = List.of(samplePlugin("pid-1", "p1", "1.0.0"));
        PageResult<Plugin> page = PageResult.of(1, 20, 1, plugins);
        when(pluginService.list(1, 20, "active")).thenReturn(page);

        R<PageResult<Plugin>> result = controller.listPlugins(1, 20, "active");

        assertEquals(200, result.getCode());
        assertEquals(1, result.getData().getTotal());
    }

    @Test
    void enableDelegatesToService() {
        Plugin plugin = samplePlugin("pid-1", "test_plugin", "1.0.0");
        when(pluginService.enable("pid-1")).thenReturn(plugin);

        R<Plugin> result = controller.enable("pid-1");

        assertEquals(200, result.getCode());
        verify(pluginService).enable("pid-1");
    }

    @Test
    void enableNotFoundReturns500() {
        when(pluginService.enable("nonexistent")).thenThrow(new NoSuchElementException("插件不存在"));

        R<Plugin> result = controller.enable("nonexistent");

        assertEquals(500, result.getCode());
        assertTrue(result.getMessage().contains("不存在"));
    }

    @Test
    void disablePassesReasonToService() {
        Plugin plugin = samplePlugin("pid-1", "test_plugin", "1.0.0");
        plugin.setStatus("disabled");
        plugin.setEnabled(false);
        when(pluginService.disable("pid-1", "security concern")).thenReturn(plugin);

        R<Plugin> result = controller.disable("pid-1", Map.of("reason", "security concern"));

        assertEquals(200, result.getCode());
        assertEquals("disabled", result.getData().getStatus());
        verify(pluginService).disable("pid-1", "security concern");
    }

    @Test
    void uninstallReturnsOkWhenSuccessful() {
        doNothing().when(pluginService).uninstall("pid-1", "no longer needed");

        R<Void> result = controller.uninstall("pid-1", Map.of("reason", "no longer needed"));

        assertEquals(200, result.getCode());
        verify(pluginService).uninstall("pid-1", "no longer needed");
    }

    @Test
    void getAuditLogsDelegatesToService() {
        List<Map<String, Object>> logs = List.of(
                Map.of("action", "install", "plugin_name", "test_plugin")
        );
        Plugin plugin = samplePlugin("pid-1", "test_plugin", "1.0.0");
        when(pluginService.getByPluginId("pid-1")).thenReturn(plugin);
        when(pluginService.getAuditLogs(1L, 10)).thenReturn(logs);

        R<List<Map<String, Object>>> result = controller.getAuditLogs("pid-1", 10);

        assertEquals(200, result.getCode());
        assertEquals(1, result.getData().size());
    }

    @Test
    void getToolSpecsReturnsPluginSpecs() {
        List<Map<String, Object>> specs = List.of(
                Map.of("plugin_id", "pid-1", "name", "test_plugin", "permissions", List.of("web"))
        );
        when(pluginService.getPluginToolSpecs()).thenReturn(specs);

        R<List<Map<String, Object>>> result = controller.getToolSpecs();

        assertEquals(200, result.getCode());
        assertEquals(1, result.getData().size());
    }
}
