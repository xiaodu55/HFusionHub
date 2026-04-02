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
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.ByteArrayInputStream;
import java.math.BigDecimal;
import java.time.Duration;
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
    public Plugin installWithWheel(Map<String, Object> manifest, byte[] wheelData, String wheelFilename) {
        String artifactHash = (String) manifest.get("artifact_hash");
        if (artifactHash == null || artifactHash.isBlank()) {
            throw new IllegalArgumentException("manifest 缺少必填字段: artifact_hash");
        }

        String name = String.valueOf(manifest.get("name"));
        String version = String.valueOf(manifest.get("version"));

        String objectKey = artifactStore.uploadWheel(
                name, version, artifactHash,
                new ByteArrayInputStream(wheelData), wheelData.length);

        manifest.put("artifact_path", objectKey);

        String presignedUrl = artifactStore.getPresignedUrl(objectKey, Duration.ofHours(1));
        manifest.put("wheel_url", presignedUrl);

        return doInstall(manifest, objectKey, artifactHash);
    }

    private Plugin doInstall(Map<String, Object> manifest, String objectKey, String artifactHash) {
        for (String field : REQUIRED_MANIFEST_FIELDS) {
            if (!manifest.containsKey(field) || manifest.get(field) == null
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
        plugin.setStatus("active");
        plugin.setEnabled(true);
        plugin.setInstalledBy(JwtUtils.getCurrentUserId());
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
            return plugin;
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
        if (plugin.getArtifactPath() != null) {
            try {
                artifactStore.deleteWheel(plugin.getArtifactPath());
            } catch (Exception e) {
                log.warn("Failed to delete artifact from MinIO: {}", e.getMessage());
            }
        }
        writeAuditLog(plugin.getId(), plugin.getName(), "uninstall",
                JwtUtils.getCurrentUserId(),
                Map.of("status", plugin.getStatus(), "enabled", plugin.getEnabled()).toString(),
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
        writeAuditLog(plugin.getId(), plugin.getName(), "canary",
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
        writeAuditLog(plugin.getId(), plugin.getName(), "promote",
                JwtUtils.getCurrentUserId(),
                Map.of("canary_weight", plugin.getCanaryWeight(), "status", plugin.getStatus()).toString(),
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
        writeAuditLog(plugin.getId(), plugin.getName(), "rollback",
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
        return logs.stream().map(l -> {
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
        }).collect(Collectors.toList());
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
        List<Plugin> enabled = pluginMapper.selectEnabledPlugins();
        List<Map<String, Object>> specs = new ArrayList<>();
        for (Plugin p : enabled) {
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
