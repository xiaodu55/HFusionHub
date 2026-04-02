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
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;
import java.util.stream.Collectors;

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

    @Override
    @Transactional
    public Plugin install(Map<String, Object> manifest) {
        // Validate required fields
        for (String field : REQUIRED_MANIFEST_FIELDS) {
            if (!manifest.containsKey(field) || manifest.get(field) == null
                    || String.valueOf(manifest.get(field)).isBlank()) {
                throw new IllegalArgumentException("manifest 缺少必填字段: " + field);
            }
        }

        // Mandatory artifact_hash for supply chain integrity
        String artifactHash = (String) manifest.get("artifact_hash");
        if (artifactHash == null || artifactHash.isBlank()) {
            throw new IllegalArgumentException("manifest 缺少必填字段: artifact_hash（供应链完整性校验）");
        }
        if (artifactHash.length() != 64 || !artifactHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("artifact_hash 必须是64位十六进制SHA-256");
        }

        String name = String.valueOf(manifest.get("name"));
        String version = String.valueOf(manifest.get("version"));

        // Check duplicate (including logically deleted rows — unique per name+version)
        Plugin existing = pluginMapper.selectByNameVersionAny(name, version);
        if (existing != null) {
            throw new IllegalStateException("插件已存在: " + name + "@" + version);
        }

        // Create plugin entity
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
        plugin.setStatus("active");
        plugin.setEnabled(true);
        plugin.setInstalledBy(JwtUtils.getCurrentUserId());
        plugin.setInstalledAt(java.time.LocalDateTime.now());

        // Hash the manifest
        plugin.setManifestHash(computeManifestHash(manifest));

        // Artifact hash (mandatory for supply chain integrity)
        plugin.setArtifactHash(artifactHash);

        // Artifact path
        String artifactPath = (String) manifest.get("artifact_path");
        if (artifactPath != null) {
            plugin.setArtifactPath(artifactPath);
        }

        // Sandbox config
        Map<String, Object> sandbox = (Map<String, Object>) manifest.get("sandbox");
        if (sandbox != null) {
            plugin.setSandboxConfig(toJson(sandbox));
        }

        // Permissions
        List<String> perms = (List<String>) manifest.get("permissions");
        if (perms != null) {
            plugin.setPermissions(toJson(perms));
        }

        pluginMapper.insert(plugin);

        // Save dependencies
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

        // Audit log
        writeAuditLog(plugin.getId(), plugin.getName(), "install",
                JwtUtils.getCurrentUserId(), null, toJson(manifest), null);

        log.info("插件安装成功: {}@{}", name, version);
        return plugin;
    }

    @Override
    public Plugin getByPluginId(String pluginId) {
        return pluginMapper.selectByPluginId(pluginId);
    }

    @Override
    public PageResult<Plugin> list(int page, int pageSize, String status) {
        LambdaQueryWrapper<Plugin> wrapper = new LambdaQueryWrapper<>();
        if (status != null && !status.isBlank() && !"all".equals(status)) {
            wrapper.eq(Plugin::getStatus, status);
        }
        wrapper.orderByDesc(Plugin::getInstalledAt);
        Page<Plugin> pageResult = pluginMapper.selectPage(new Page<>(page, pageSize), wrapper);
        return PageResult.of(page, pageSize, pageResult.getTotal(), pageResult.getRecords());
    }

    @Override
    public List<Plugin> listEnabled() {
        return pluginMapper.selectEnabledPlugins();
    }

    @Override
    @Transactional
    public Plugin enable(String pluginId) {
        Plugin plugin = requirePlugin(pluginId);
        if (Boolean.TRUE.equals(plugin.getEnabled()) && "active".equals(plugin.getStatus())) {
            return plugin; // already enabled
        }
        pluginMapper.updateEnabled(plugin.getId(), true);
        pluginMapper.updateStatus(plugin.getId(), "active");
        writeAuditLog(plugin.getId(), plugin.getName(), "enable",
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
        writeAuditLog(plugin.getId(), plugin.getName(), "disable",
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
        writeAuditLog(plugin.getId(), plugin.getName(), "update",
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
        writeAuditLog(plugin.getId(), plugin.getName(), "uninstall",
                JwtUtils.getCurrentUserId(),
                Map.of("status", plugin.getStatus(), "enabled", plugin.getEnabled()).toString(),
                Map.of("status", "deleted").toString(),
                reason);
        log.info("插件已卸载: {}@{}", plugin.getName(), plugin.getVersion());
    }

    @Override
    public int countByUserId(Long userId) {
        return pluginMapper.countActiveByUserId(userId);
    }

    @Override
    public List<Map<String, Object>> getAuditLogs(Long pluginId, int limit) {
        List<PluginAuditLog> logs = auditLogMapper.selectByPluginId(pluginId, limit);
        return logs.stream().map(l -> {
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
        }).collect(Collectors.toList());
    }

    @Override
    public List<Map<String, Object>> getPluginToolSpecs() {
        List<Plugin> enabled = pluginMapper.selectEnabledPlugins();
        List<Map<String, Object>> specs = new ArrayList<>();
        for (Plugin p : enabled) {
            Map<String, Object> spec = new LinkedHashMap<>();
            spec.put("plugin_id", p.getPluginId());
            spec.put("name", p.getName());
            spec.put("version", p.getVersion());
            if (p.getPermissions() != null) {
                spec.put("permissions", parseJsonList(p.getPermissions()));
            }
            specs.add(spec);
        }
        return specs;
    }

    // ── helpers ──

    private Plugin requirePlugin(String pluginId) {
        Plugin plugin = pluginMapper.selectByPluginId(pluginId);
        if (plugin == null) {
            throw new NoSuchElementException("插件不存在: " + pluginId);
        }
        return plugin;
    }

    private void writeAuditLog(Long pluginId, String pluginName, String action,
                               Long operatorId, String oldValue, String newValue, String reason) {
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

    private String computeManifestHash(Map<String, Object> manifest) {
        // Deterministic JSON serialization then SHA-256
        String canonical = manifest.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .map(e -> e.getKey() + ":" + e.getValue())
                .collect(Collectors.joining(","));
        try {
            java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(canonical.getBytes(java.nio.charset.StandardCharsets.UTF_8));
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
        // Simple JSON serialization using Jackson if available, else toString
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
}
