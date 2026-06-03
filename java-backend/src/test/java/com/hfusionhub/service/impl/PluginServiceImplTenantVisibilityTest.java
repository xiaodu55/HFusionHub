package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.hfusionhub.entity.Plugin;
import com.hfusionhub.mapper.PluginAuditLogMapper;
import com.hfusionhub.mapper.PluginDependencyMapper;
import com.hfusionhub.mapper.PluginMapper;
import com.hfusionhub.storage.MinioArtifactStore;
import com.hfusionhub.tenant.TenantContext;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/**
 * 平台内建插件（tenant_id 为 NULL）的租户可见性。
 *
 * <p>{@code plugin} 表已加入 {@code TENANT_IGNORE_TABLES}（不走租户行拦截器，
 * 否则租户拦截器会给插件查询追加 {@code tenant_id = ?} 把平台内建插件过滤掉）。
 * 可见性改由服务层过滤：平台内建插件（tenant_id NULL）对所有租户可见，
 * 租户自有插件仅对所属租户可见，系统作用域（管理后台）全量可见。
 */
class PluginServiceImplTenantVisibilityTest {

    private final PluginMapper pluginMapper = mock(PluginMapper.class);
    private final PluginAuditLogMapper auditLogMapper = mock(PluginAuditLogMapper.class);
    private final PluginDependencyMapper dependencyMapper = mock(PluginDependencyMapper.class);
    private final MinioArtifactStore artifactStore = mock(MinioArtifactStore.class);

    private final PluginServiceImpl service =
            new PluginServiceImpl(pluginMapper, auditLogMapper, dependencyMapper, artifactStore);

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    private Plugin plugin(Long tenantId, String pluginId, String name) {
        Plugin p = new Plugin();
        p.setId(1L);
        p.setPluginId(pluginId);
        p.setName(name);
        p.setVersion("1.0.0");
        p.setStatus("active");
        p.setEnabled(true);
        p.setTenantId(tenantId);
        return p;
    }

    @Test
    void listEnabledShowsPlatformAndOwnButNotOtherTenant() {
        Plugin platform = plugin(null, "bid_docx@1.0.0", "bid_docx");
        Plugin mine = plugin(10L, "mine@1.0.0", "mine");
        Plugin other = plugin(20L, "other@1.0.0", "other");
        when(pluginMapper.selectEnabledPlugins()).thenReturn(List.of(platform, mine, other));

        TenantContext.runAs(10L, () -> {
            List<Plugin> visible = service.listEnabled();
            assertEquals(2, visible.size(), "租户 10 应只见平台内建 + 自有插件");
            assertTrue(visible.stream().anyMatch(p -> p.getPluginId().equals("bid_docx@1.0.0")));
            assertTrue(visible.stream().anyMatch(p -> p.getPluginId().equals("mine@1.0.0")));
            assertFalse(visible.stream().anyMatch(p -> p.getPluginId().equals("other@1.0.0")));
        });
    }

    @Test
    void getByPluginIdAllowsPlatformAndOwnButBlocksCrossTenant() {
        Plugin platform = plugin(null, "bid_docx@1.0.0", "bid_docx");
        Plugin mine = plugin(10L, "mine@1.0.0", "mine");
        Plugin other = plugin(20L, "other@1.0.0", "other");
        when(pluginMapper.selectByPluginId("bid_docx@1.0.0")).thenReturn(platform);
        when(pluginMapper.selectByPluginId("mine@1.0.0")).thenReturn(mine);
        when(pluginMapper.selectByPluginId("other@1.0.0")).thenReturn(other);

        TenantContext.runAs(10L, () -> {
            assertNotNull(service.getByPluginId("bid_docx@1.0.0"));
            assertNotNull(service.getByPluginId("mine@1.0.0"));
            assertNull(service.getByPluginId("other@1.0.0"), "跨租户插件详情应不可见");
        });
    }

    @Test
    void systemScopeSeesEverything() {
        Plugin mine = plugin(10L, "mine@1.0.0", "mine");
        Plugin other = plugin(20L, "other@1.0.0", "other");
        when(pluginMapper.selectEnabledPlugins()).thenReturn(List.of(mine, other));

        TenantContext.runAsSystem(() -> assertEquals(2, service.listEnabled().size()));
    }
}
