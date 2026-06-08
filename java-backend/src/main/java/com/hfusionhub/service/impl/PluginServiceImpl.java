package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.Plugin;
import com.hfusionhub.entity.PluginAuditLog;
import com.hfusionhub.entity.PluginDependency;
import com.hfusionhub.mapper.PluginAuditLogMapper;
import com.hfusionhub.mapper.PluginDependencyMapper;
import com.hfusionhub.mapper.PluginMapper;
import com.hfusionhub.service.PluginService;
import com.hfusionhub.storage.MinioArtifactStore;
import com.hfusionhub.tenant.TenantContext;
import java.io.ByteArrayInputStream;
import java.math.BigDecimal;
import java.net.URI;
import java.time.Duration;
import java.util.*;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 工具插件服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PluginServiceImpl implements PluginService {

    private static final String[] REQUIRED_MANIFEST_FIELDS = {"name", "version", "description"};

    private final PluginMapper pluginMapper;
    private final PluginAuditLogMapper auditLogMapper;
    private final PluginDependencyMapper dependencyMapper;
    private final MinioArtifactStore artifactStore;

    @Value("${minio.bucket-name:hfusionhub}")
    private String bucketName;

    @Override
    @Transactional
    public Plugin install(Map<String, Object> manifest) {
        return doInstall(manifest, null, null);
    }

    @Override
    @Transactional
    @SuppressWarnings("unchecked")
    public Plugin createDeclarative(Map<String, Object> manifest) {
        String name = requireText(manifest, "name", 64);
        if (!name.matches("[a-z][a-z0-9_]{2,63}")) {
            throw new IllegalArgumentException("插件标识只能使用小写字母、数字和下划线，并以字母开头");
        }
        String version = requireText(manifest, "version", 32);
        if (!version.matches("[0-9]+[.][0-9]+[.][0-9]+(?:-[0-9A-Za-z.-]+)?")) {
            throw new IllegalArgumentException("版本号格式应为 1.0.0");
        }
        requireText(manifest, "description", 500);

        Object rawTools = manifest.get("tools");
        if (!(rawTools instanceof List<?> tools) || tools.isEmpty() || tools.size() > 10) {
            throw new IllegalArgumentException("每个插件需要包含 1 到 10 个工具");
        }

        List<Map<String, Object>> normalizedTools = new ArrayList<>();
        Set<String> names = new HashSet<>();
        for (Object rawTool : tools) {
            if (!(rawTool instanceof Map<?, ?> rawMap)) {
                throw new IllegalArgumentException("工具配置格式不正确");
            }
            Map<String, Object> tool = new LinkedHashMap<>();
            rawMap.forEach((key, value) -> tool.put(String.valueOf(key), value));

            String toolName = requireText(tool, "name", 64);
            if (!toolName.matches("custom_[a-z0-9_]{2,56}")) {
                throw new IllegalArgumentException("工具标识必须以 custom_ 开头，且只能使用小写字母、数字和下划线");
            }
            if (!names.add(toolName)) {
                throw new IllegalArgumentException("工具标识重复: " + toolName);
            }

            String endpoint = requireText(tool, "endpoint_url", 1000);
            validateDeclarativeEndpoint(endpoint);
            String method = String.valueOf(tool.getOrDefault("method", "GET")).toUpperCase(Locale.ROOT);
            if (!"GET".equals(method)) {
                throw new IllegalArgumentException("低代码工具目前只允许 GET 请求");
            }

            int timeout = parseBoundedInt(tool.get("timeout_seconds"), 10, 2, 30, "超时时间");
            Map<String, Object> inputSchema = tool.get("input_schema") instanceof Map<?, ?> schema
                    ? normalizeInputSchema(schema)
                    : Map.of("type", "object", "properties", Map.of());

            Map<String, Object> normalized = new LinkedHashMap<>();
            normalized.put("name", toolName);
            normalized.put("display_name", requireText(tool, "display_name", 100));
            normalized.put("description", requireText(tool, "description", 500));
            normalized.put(
                    "example", String.valueOf(tool.getOrDefault("example", "")).trim());
            normalized.put("input_schema", inputSchema);
            normalized.put("output_schema", Map.of("type", "object"));
            normalized.put("risk_level", "read_only");
            normalized.put("required_permissions", List.of());
            normalized.put("timeout_seconds", timeout);
            normalized.put("agent_version", "1.0");
            normalized.put("category", "external");
            normalized.put("execution", Map.of("type", "http_get", "url", endpoint));
            normalizedTools.add(normalized);
        }

        Map<String, Object> safeManifest = new LinkedHashMap<>(manifest);
        safeManifest.put("source", "builder");
        safeManifest.put("plugin_kind", "declarative");
        safeManifest.put("tool_specs", normalizedTools);
        safeManifest.put("permissions", List.of("external:http:get"));
        safeManifest.put("artifact_hash", computeManifestHash(safeManifest));
        return doInstall(safeManifest, null, null);
    }

    @Override
    @Transactional
    public Plugin installWithWheel(Map<String, Object> manifest, byte[] wheelData, String wheelFilename) {
        String artifactHash = (String) manifest.get("artifact_hash");
        if (artifactHash == null || artifactHash.isBlank()) {
            throw new IllegalArgumentException("manifest 缺少必填字段: artifact_hash");
        }

        String name = String.valueOf(manifest.get("name"));
        String version = String.valueOf(manifest.get("version"));

        String objectKey = artifactStore.uploadWheel(
                name, version, artifactHash, new ByteArrayInputStream(wheelData), wheelData.length);

        manifest.put("artifact_path", objectKey);

        String presignedUrl = artifactStore.getPresignedUrl(objectKey, Duration.ofHours(1));
        manifest.put("wheel_url", presignedUrl);

        return doInstall(manifest, objectKey, artifactHash);
    }

    private Plugin doInstall(Map<String, Object> manifest, String objectKey, String artifactHash) {
        for (String field : REQUIRED_MANIFEST_FIELDS) {
            if (!manifest.containsKey(field)
                    || manifest.get(field) == null
                    || String.valueOf(manifest.get(field)).isBlank()) {
                throw new IllegalArgumentException("manifest 缺少必填字段: " + field);
            }
        }

        String hash = artifactHash != null ? artifactHash : (String) manifest.get("artifact_hash");
        if (hash == null || hash.isBlank()) {
            throw new IllegalArgumentException("manifest 缺少必填字段: artifact_hash（供应链完整性校验）");
        }
        if (hash.length() != 64 || !hash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("artifact_hash 必须是64位十六进制SHA-256");
        }

        String name = String.valueOf(manifest.get("name"));
        String version = String.valueOf(manifest.get("version"));

        Plugin existing = pluginMapper.selectByNameVersionAny(name, version);
        if (existing != null) {
            throw new IllegalStateException("插件已存在: " + name + "@" + version);
        }

        Plugin plugin = new Plugin();
        plugin.setPluginId(UUID.randomUUID().toString());
        plugin.setName(name);
        plugin.setVersion(version);
        plugin.setDisplayName((String) manifest.getOrDefault("display_name", name));
        plugin.setDescription((String) manifest.getOrDefault("description", ""));
        plugin.setAuthor((String) manifest.get("author"));
        plugin.setAuthorEmail((String) manifest.get("author_email"));
        plugin.setLicense((String) manifest.get("license"));
        plugin.setMinHfusionhubVersion((String) manifest.get("min_hfusionhub_version"));
        plugin.setMaxHfusionhubVersion((String) manifest.get("max_hfusionhub_version"));
        plugin.setIconUrl((String) manifest.get("icon_url"));
        plugin.setSource((String) manifest.getOrDefault("source", "local"));
        plugin.setPluginKind((String) manifest.getOrDefault("plugin_kind", "package"));
        plugin.setStatus("active");
        plugin.setEnabled(true);
        plugin.setInstalledBy(JwtUtils.getCurrentUserId());
        plugin.setTenantId(com.hfusionhub.tenant.TenantContext.requireTenantId());
        plugin.setInstalledAt(java.time.LocalDateTime.now());
        plugin.setManifestHash(computeManifestHash(manifest));
        plugin.setArtifactHash(hash);

        String path = objectKey != null ? objectKey : (String) manifest.get("artifact_path");
        if (path != null) {
            plugin.setArtifactPath(path);
        }

        Map<String, Object> sandbox = (Map<String, Object>) manifest.get("sandbox");
        if (sandbox != null) {
            plugin.setSandboxConfig(toJson(sandbox));
        }

        List<String> perms = (List<String>) manifest.get("permissions");
        if (perms != null) {
            plugin.setPermissions(toJson(perms));
        }

        Object toolSpecs = manifest.get("tool_specs");
        if (toolSpecs != null) {
            plugin.setToolSpecsJson(toJson(toolSpecs));
        }

        pluginMapper.insert(plugin);

        List<Map<String, Object>> deps = (List<Map<String, Object>>) manifest.get("dependencies");
        if (deps != null) {
            for (Map<String, Object> dep : deps) {
                PluginDependency pd = new PluginDependency();
                pd.setPluginId(plugin.getId());
                pd.setDependencyName(String.valueOf(dep.get("name")));
                pd.setDependencyVersion((String) dep.get("version"));
                pd.setOptional(Boolean.TRUE.equals(dep.get("optional")));
                dependencyMapper.insert(pd);
            }
        }

        writeAuditLog(
                plugin.getId(), plugin.getName(), "install", JwtUtils.getCurrentUserId(), null, toJson(manifest), null);

        log.info("插件安装成功: {}@{}", name, version);
        return plugin;
    }

    @Override
    public Plugin getByPluginId(String pluginId) {
        Plugin plugin = pluginMapper.selectByPluginId(pluginId);
        return plugin != null && visibleToTenant(plugin) ? plugin : null;
    }

    @Override
    public PageResult<Plugin> list(int page, int pageSize, String status) {
        LambdaQueryWrapper<Plugin> wrapper = new LambdaQueryWrapper<>();
        if (status != null && !status.isBlank() && !"all".equals(status)) {
            wrapper.eq(Plugin::getStatus, status);
        }
        // plugin 表不走租户行拦截器（平台内建插件 tenant_id 可空）；
        // 租户查询须同时可见平台内建插件 + 自有插件。
        if (TenantContext.getTenantId() != null) {
            Long tenantId = TenantContext.getTenantId();
            wrapper.and(w -> w.isNull(Plugin::getTenantId).or().eq(Plugin::getTenantId, tenantId));
        }
        wrapper.orderByDesc(Plugin::getInstalledAt);
        Page<Plugin> pageResult = pluginMapper.selectPage(new Page<>(page, pageSize), wrapper);
        return PageResult.of(page, pageSize, pageResult.getTotal(), pageResult.getRecords());
    }

    @Override
    public List<Plugin> listEnabled() {
        return pluginMapper.selectEnabledPlugins().stream()
                .filter(this::visibleToTenant)
                .collect(java.util.stream.Collectors.toList());
    }

    @Override
    @Transactional
    public Plugin enable(String pluginId) {
        Plugin plugin = requirePlugin(pluginId);
        if (Boolean.TRUE.equals(plugin.getEnabled()) && "active".equals(plugin.getStatus())) {
            return plugin;
        }
        pluginMapper.updateEnabled(plugin.getId(), true);
        pluginMapper.updateStatus(plugin.getId(), "active");
        writeAuditLog(
                plugin.getId(),
                plugin.getName(),
                "enable",
                JwtUtils.getCurrentUserId(),
                Map.of("enabled", false, "status", plugin.getStatus()).toString(),
                Map.of("enabled", true, "status", "active").toString(),
                null);
        return pluginMapper.selectByPluginId(pluginId);
    }

    @Override
    @Transactional
    public Plugin disable(String pluginId, String reason) {
        Plugin plugin = requirePlugin(pluginId);
        pluginMapper.updateEnabled(plugin.getId(), false);
        pluginMapper.updateStatus(plugin.getId(), "disabled");
        writeAuditLog(
                plugin.getId(),
                plugin.getName(),
                "disable",
                JwtUtils.getCurrentUserId(),
                Map.of("enabled", true, "status", plugin.getStatus()).toString(),
                Map.of("enabled", false, "status", "disabled").toString(),
                reason);
        return pluginMapper.selectByPluginId(pluginId);
    }

    @Override
    @Transactional
    public Plugin updateStatus(String pluginId, String status) {
        Plugin plugin = requirePlugin(pluginId);
        String oldStatus = plugin.getStatus();
        pluginMapper.updateStatus(plugin.getId(), status);
        writeAuditLog(
                plugin.getId(),
                plugin.getName(),
                "update",
                JwtUtils.getCurrentUserId(),
                Map.of("status", oldStatus).toString(),
                Map.of("status", status).toString(),
                null);
        return pluginMapper.selectByPluginId(pluginId);
    }

    @Override
    @Transactional
    public void uninstall(String pluginId, String reason) {
        Plugin plugin = requirePlugin(pluginId);
        pluginMapper.deleteById(plugin.getId());
        if (plugin.getArtifactPath() != null) {
            try {
                artifactStore.deleteWheel(plugin.getArtifactPath());
            } catch (Exception e) {
                log.warn("Failed to delete artifact from MinIO: {}", e.getMessage());
            }
        }
        writeAuditLog(
                plugin.getId(),
                plugin.getName(),
                "uninstall",
                JwtUtils.getCurrentUserId(),
                Map.of("status", plugin.getStatus(), "enabled", plugin.getEnabled())
                        .toString(),
                Map.of("status", "deleted").toString(),
                reason);
        log.info("插件已卸载: {}@{}", plugin.getName(), plugin.getVersion());
    }

    @Override
    @Transactional
    public Plugin setCanary(String pluginId, BigDecimal weight) {
        Plugin plugin = requirePlugin(pluginId);
        if (weight.compareTo(BigDecimal.ZERO) < 0 || weight.compareTo(new BigDecimal("1.00")) > 0) {
            throw new IllegalArgumentException("canary_weight 必须在 0.00-1.00 之间");
        }
        pluginMapper.updateCanary(plugin.getId(), weight);
        writeAuditLog(
                plugin.getId(),
                plugin.getName(),
                "canary",
                JwtUtils.getCurrentUserId(),
                Map.of("canary_weight", plugin.getCanaryWeight()).toString(),
                Map.of("canary_weight", weight).toString(),
                null);
        return pluginMapper.selectByPluginId(pluginId);
    }

    @Override
    @Transactional
    public Plugin promoteCanary(String pluginId) {
        Plugin plugin = requirePlugin(pluginId);
        pluginMapper.updateCanary(plugin.getId(), BigDecimal.ZERO);
        pluginMapper.updateStatus(plugin.getId(), "active");
        pluginMapper.updateEnabled(plugin.getId(), true);
        writeAuditLog(
                plugin.getId(),
                plugin.getName(),
                "promote",
                JwtUtils.getCurrentUserId(),
                Map.of("canary_weight", plugin.getCanaryWeight(), "status", plugin.getStatus())
                        .toString(),
                Map.of("canary_weight", 0, "status", "active").toString(),
                null);
        return pluginMapper.selectByPluginId(pluginId);
    }

    @Override
    @Transactional
    public Plugin rollback(String pluginId) {
        Plugin plugin = requirePlugin(pluginId);
        if (plugin.getPreviousVersion() == null) {
            throw new IllegalStateException("插件没有可回滚的版本");
        }
        String oldVersion = plugin.getVersion();
        plugin.setVersion(plugin.getPreviousVersion());
        plugin.setPreviousVersion(oldVersion);
        pluginMapper.updateById(plugin);
        writeAuditLog(
                plugin.getId(),
                plugin.getName(),
                "rollback",
                JwtUtils.getCurrentUserId(),
                Map.of("version", oldVersion).toString(),
                Map.of("version", plugin.getPreviousVersion()).toString(),
                null);
        return pluginMapper.selectByPluginId(pluginId);
    }

    @Override
    public List<Map<String, Object>> exportAuditLogs(String pluginId, String format, int limit) {
        Plugin plugin = pluginId != null ? pluginMapper.selectByPluginId(pluginId) : null;
        Long dbPluginId = plugin != null ? plugin.getId() : null;
        List<PluginAuditLog> logs = auditLogMapper.selectByPluginId(dbPluginId, limit);
        return logs.stream()
                .map(l -> {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("id", l.getId());
                    m.put("event_id", l.getEventId());
                    m.put("plugin_name", l.getPluginName());
                    m.put("action", l.getAction());
                    m.put("operator_id", l.getOperatorId());
                    m.put("old_value", l.getOldValue());
                    m.put("new_value", l.getNewValue());
                    m.put("reason", l.getReason());
                    m.put("created_at", l.getCreatedAt());
                    return m;
                })
                .collect(Collectors.toList());
    }

    @Override
    public int countByUserId(Long userId) {
        return pluginMapper.countActiveByUserId(userId);
    }

    @Override
    public List<Map<String, Object>> getAuditLogs(Long pluginId, int limit) {
        List<PluginAuditLog> logs = auditLogMapper.selectByPluginId(pluginId, limit);
        return logs.stream()
                .map(l -> {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("id", l.getId());
                    m.put("plugin_name", l.getPluginName());
                    m.put("action", l.getAction());
                    m.put("operator_id", l.getOperatorId());
                    m.put("old_value", l.getOldValue());
                    m.put("new_value", l.getNewValue());
                    m.put("reason", l.getReason());
                    m.put("created_at", l.getCreatedAt());
                    return m;
                })
                .collect(Collectors.toList());
    }

    @Override
    public List<Map<String, Object>> getPluginVersions(Long pluginId) {
        Plugin plugin = pluginMapper.selectById(pluginId);
        if (plugin == null) {
            return List.of();
        }

        // Get all versions of this plugin (by name) for canary routing
        List<Plugin> allVersions = pluginMapper.selectVersionsByPluginName(plugin.getName());
        List<Map<String, Object>> result = new ArrayList<>();
        for (Plugin v : allVersions) {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("version", v.getVersion());
            entry.put("container_image", v.getContainerImage());
            entry.put("image_digest", v.getImageDigest());
            entry.put("canary_weight", v.getCanaryWeight());
            entry.put("status", v.getStatus());
            result.add(entry);
        }
        return result;
    }

    @Override
    public List<Map<String, Object>> getPluginToolSpecs() {
        List<Plugin> enabled = pluginMapper.selectEnabledPlugins().stream()
                .filter(this::visibleToTenant)
                .collect(java.util.stream.Collectors.toList());
        List<Map<String, Object>> specs = new ArrayList<>();
        for (Plugin p : enabled) {
            if ("declarative".equals(p.getPluginKind()) && p.getToolSpecsJson() != null) {
                for (Map<String, Object> tool : parseJsonMapList(p.getToolSpecsJson())) {
                    Map<String, Object> enriched = new LinkedHashMap<>(tool);
                    enriched.put("_plugin_id", p.getPluginId());
                    enriched.put("_plugin_name", p.getDisplayName() != null ? p.getDisplayName() : p.getName());
                    enriched.put("_plugin_version", p.getVersion());
                    enriched.put("_plugin_kind", "declarative");
                    enriched.put("_tenant_id", p.getTenantId());
                    specs.add(enriched);
                }
                continue;
            }
            Map<String, Object> spec = new LinkedHashMap<>();
            spec.put("plugin_id", p.getPluginId());
            spec.put("name", p.getName());
            spec.put("version", p.getVersion());
            spec.put("container_image", p.getContainerImage());
            spec.put("canary_weight", p.getCanaryWeight());
            if (p.getPermissions() != null) {
                spec.put("permissions", parseJsonList(p.getPermissions()));
            }
            specs.add(spec);
        }
        return specs;
    }

    // ── helpers ──

    private String requireText(Map<String, Object> source, String field, int maxLength) {
        String value = String.valueOf(source.getOrDefault(field, "")).trim();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("缺少必填字段: " + field);
        }
        if (value.length() > maxLength) {
            throw new IllegalArgumentException(field + " 长度不能超过 " + maxLength + " 个字符");
        }
        return value;
    }

    private int parseBoundedInt(Object raw, int defaultValue, int min, int max, String label) {
        int value = defaultValue;
        if (raw != null) {
            try {
                value = Integer.parseInt(String.valueOf(raw));
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException(label + "格式不正确");
            }
        }
        if (value < min || value > max) {
            throw new IllegalArgumentException(label + "必须在 " + min + " 到 " + max + " 之间");
        }
        return value;
    }

    private void validateDeclarativeEndpoint(String endpoint) {
        try {
            URI uri = URI.create(endpoint);
            String host = uri.getHost();
            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || host == null
                    || host.isBlank()
                    || uri.getUserInfo() != null
                    || host.equalsIgnoreCase("localhost")
                    || host.endsWith(".local")
                    || isPrivateHost(host)) {
                throw new IllegalArgumentException("接口地址必须是可公开访问的 HTTPS 地址");
            }
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("接口地址必须是可公开访问的 HTTPS 地址");
        }
    }

    /**
     * SSRF 防护（R15-19）：拒绝字面量私网/链路本地/保留地址，以及解析到
     * 这些地址的域名。安装时解析 DNS——运行时解析结果可能变化（DNS
     * rebinding），由调用方网络策略兜底；这里阻断的是把服务作为内网跳板
     * 的最直接路径。
     */
    private boolean isPrivateHost(String host) {
        // IPv4 字面量私网/保留段
        if (host.matches("\\d{1,3}(\\.\\d{1,3}){3}")) {
            return isPrivateIPv4(host);
        }
        // IPv6 字面量（含 [::1] 已被 getHost 剥离方括号）
        if (host.contains(":")) {
            String lower = host.toLowerCase();
            return lower.equals("::1") || lower.equals("::")
                    || lower.startsWith("fc") || lower.startsWith("fd")  // ULA fc00::/7
                    || lower.startsWith("fe80")                          // link-local
                    || lower.startsWith("::ffff:");                      // IPv4-mapped
        }
        // 域名：解析后校验全部地址
        try {
            java.net.InetAddress[] addresses = java.net.InetAddress.getAllByName(host);
            if (addresses.length == 0) {
                return true;
            }
            for (java.net.InetAddress address : addresses) {
                if (address.isLoopbackAddress()
                        || address.isLinkLocalAddress()
                        || address.isSiteLocalAddress()
                        || address.isAnyLocalAddress()
                        || isPrivateIPv4(address.getHostAddress())) {
                    return true;
                }
            }
            return false;
        } catch (java.net.UnknownHostException e) {
            // 无法解析的域名同样拒绝（不可公开访问）
            return true;
        }
    }

    private boolean isPrivateIPv4(String host) {
        try {
            String[] parts = host.split("\\.");
            if (parts.length != 4) {
                return true;
            }
            int a = Integer.parseInt(parts[0]);
            int b = Integer.parseInt(parts[1]);
            if (a == 10 || a == 127 || a == 0) return true;                  // 10/8, loopback, 0/8
            if (a == 172 && b >= 16 && b <= 31) return true;                 // 172.16/12
            if (a == 192 && b == 168) return true;                           // 192.168/16
            if (a == 169 && b == 254) return true;                           // link-local (含云元数据 169.254.169.254)
            if (a == 100 && b >= 64 && b <= 127) return true;                // CGNAT 100.64/10
            if (a >= 224) return true;                                       // multicast + reserved
            return false;
        } catch (NumberFormatException e) {
            return true;
        }
    }

    private Map<String, Object> normalizeInputSchema(Map<?, ?> rawSchema) {
        Object rawProperties = rawSchema.get("properties");
        Map<String, Object> properties = new LinkedHashMap<>();
        if (rawProperties instanceof Map<?, ?> props) {
            if (props.size() > 12) {
                throw new IllegalArgumentException("每个工具最多配置 12 个输入参数");
            }
            for (Map.Entry<?, ?> entry : props.entrySet()) {
                String name = String.valueOf(entry.getKey());
                if (!name.matches("[a-z][a-z0-9_]{0,31}")) {
                    throw new IllegalArgumentException("参数标识格式不正确: " + name);
                }
                Map<String, Object> definition = new LinkedHashMap<>();
                definition.put("type", "string");
                if (entry.getValue() instanceof Map<?, ?> valueMap && valueMap.get("description") != null) {
                    definition.put("description", String.valueOf(valueMap.get("description")));
                }
                properties.put(name, definition);
            }
        }
        List<String> required = new ArrayList<>();
        if (rawSchema.get("required") instanceof List<?> requiredItems) {
            for (Object item : requiredItems) {
                String name = String.valueOf(item);
                if (properties.containsKey(name)) required.add(name);
            }
        }
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        schema.put("properties", properties);
        schema.put("required", required);
        return schema;
    }

    private Plugin requirePlugin(String pluginId) {
        Plugin plugin = pluginMapper.selectByPluginId(pluginId);
        if (plugin == null) {
            throw new NoSuchElementException("插件不存在: " + pluginId);
        }
        if (!visibleToTenant(plugin)) {
            throw new NoSuchElementException("插件不存在: " + pluginId);
        }
        return plugin;
    }

    /**
     * 插件租户可见性：平台内建插件（tenant_id 为 NULL）对所有租户可见；
     * 租户自有插件仅对所属租户可见。系统作用域（管理后台）下全量可见。
     */
    private boolean visibleToTenant(Plugin plugin) {
        if (TenantContext.isSystemScope() || TenantContext.getTenantId() == null) {
            return true;
        }
        Long tenantId = TenantContext.getTenantId();
        return plugin.getTenantId() == null || tenantId.equals(plugin.getTenantId());
    }

    private void writeAuditLog(
            Long pluginId,
            String pluginName,
            String action,
            Long operatorId,
            String oldValue,
            String newValue,
            String reason) {
        PluginAuditLog logEntry = new PluginAuditLog();
        logEntry.setPluginId(pluginId);
        logEntry.setPluginName(pluginName);
        logEntry.setAction(action);
        logEntry.setOperatorId(operatorId);
        logEntry.setOldValue(oldValue);
        logEntry.setNewValue(newValue);
        logEntry.setReason(reason);
        auditLogMapper.insert(logEntry);
    }

    /**
     * 规范化 JSON 序列化（键递归排序），供 manifest hash 使用。
     * R15-23：旧实现按 {@code key:value,key:value} 拼接——值含 ":" / "," /
     * "=" 时会产生碰撞，且嵌套 Map 的 toString 顺序不保证稳定，导致同一
     * manifest 可能算出不同 hash（供应链校验锚点失效）。
     */
    private static final com.fasterxml.jackson.databind.ObjectMapper CANONICAL_MAPPER =
            new com.fasterxml.jackson.databind.ObjectMapper()
                    .enable(com.fasterxml.jackson.databind.SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    @SuppressWarnings("unchecked")
    private static String canonicalJson(Object value) {
        if (value instanceof Map<?, ?> map) {
            java.util.TreeMap<String, Object> sorted = new java.util.TreeMap<>();
            for (Map.Entry<?, ?> e : map.entrySet()) {
                sorted.put(String.valueOf(e.getKey()), canonicalJson(e.getValue()));
            }
            return CANONICAL_MAPPER.valueToTree(sorted).toString();
        }
        if (value instanceof List<?> list) {
            java.util.List<Object> out = new java.util.ArrayList<>(list.size());
            for (Object item : list) {
                out.add(canonicalJson(item));
            }
            return CANONICAL_MAPPER.valueToTree(out).toString();
        }
        return String.valueOf(value);
    }

    private String computeManifestHash(Map<String, Object> manifest) {
        try {
            java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(
                    canonicalJson(manifest).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }

    @SuppressWarnings("unchecked")
    private String toJson(Object obj) {
        if (obj == null) return null;
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            return mapper.writeValueAsString(obj);
        } catch (Exception e) {
            return String.valueOf(obj);
        }
    }

    @SuppressWarnings("unchecked")
    private List<String> parseJsonList(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            return mapper.readValue(json, mapper.getTypeFactory().constructCollectionType(List.class, String.class));
        } catch (Exception e) {
            return List.of();
        }
    }

    private List<Map<String, Object>> parseJsonMapList(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            return mapper.readValue(json, mapper.getTypeFactory().constructCollectionType(List.class, Map.class));
        } catch (Exception e) {
            log.warn("无法解析插件工具配置: {}", e.getMessage());
            return List.of();
        }
    }
}
