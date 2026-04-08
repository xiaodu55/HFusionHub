package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.Plugin;
import com.hfusionhub.service.PluginService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

/**
 * 工具插件管理控制器。
 * 读取端点对所有已认证用户开放；变更端点仅限管理员。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Tag(name = "工具插件管理", description = "插件安装、启用/禁用、卸载、金丝雀发布、回滚、审计日志")
@RestController
@RequestMapping("/plugin")
@RequiredArgsConstructor
public class PluginController {

    private final PluginService pluginService;

    private static final long MAX_WHEEL_SIZE = 50 * 1024 * 1024; // 50 MB

    // ── 管理员专属：变更端点 ────────────────────────────────────────────

    @SaCheckRole("admin")
    @Operation(summary = "安装插件（JSON manifest）— 管理员")
    @PostMapping("/install")
    public R<Plugin> install(@RequestBody Map<String, Object> manifest) {
        try {
            Plugin plugin = pluginService.install(manifest);
            return R.ok(plugin);
        } catch (IllegalArgumentException e) {
            return R.fail(400, e.getMessage());
        } catch (IllegalStateException e) {
            return R.fail(409, e.getMessage());
        }
    }

    @SaCheckRole("admin")
    @Operation(summary = "上传 wheel 文件并安装插件 — 管理员")
    @PostMapping("/install/upload")
    public R<Plugin> installWithWheel(
            @RequestPart("manifest") Map<String, Object> manifest,
            @RequestPart("wheel") MultipartFile wheel) {
        if (wheel.getSize() > MAX_WHEEL_SIZE) {
            return R.fail(400, "插件文件大小超过限制 (50 MB)");
        }
        try {
            byte[] wheelData = wheel.getBytes();
            String filename = wheel.getOriginalFilename();
            Plugin plugin = pluginService.installWithWheel(manifest, wheelData, filename);
            return R.ok(plugin);
        } catch (IllegalArgumentException e) {
            return R.fail(400, e.getMessage());
        } catch (IllegalStateException e) {
            return R.fail(409, e.getMessage());
        } catch (Exception e) {
            return R.fail(500, "上传失败: " + e.getMessage());
        }
    }

    @SaCheckRole("admin")
    @Operation(summary = "启用插件 — 管理员")
    @PostMapping("/{pluginId}/enable")
    public R<Plugin> enable(@PathVariable String pluginId) {
        try {
            return R.ok(pluginService.enable(pluginId));
        } catch (NoSuchElementException e) {
            return R.fail("插件不存在");
        }
    }

    @SaCheckRole("admin")
    @Operation(summary = "禁用插件 — 管理员")
    @PostMapping("/{pluginId}/disable")
    public R<Plugin> disable(@PathVariable String pluginId,
                             @RequestBody(required = false) Map<String, String> body) {
        try {
            String reason = body != null ? body.get("reason") : null;
            return R.ok(pluginService.disable(pluginId, reason));
        } catch (NoSuchElementException e) {
            return R.fail("插件不存在");
        }
    }

    @SaCheckRole("admin")
    @Operation(summary = "卸载插件 — 管理员")
    @PostMapping("/{pluginId}/uninstall")
    public R<Void> uninstall(@PathVariable String pluginId,
                             @RequestBody(required = false) Map<String, String> body) {
        try {
            String reason = body != null ? body.get("reason") : null;
            pluginService.uninstall(pluginId, reason);
            return R.ok();
        } catch (NoSuchElementException e) {
            return R.fail("插件不存在");
        }
    }

    @SaCheckRole("admin")
    @Operation(summary = "设置金丝雀流量权重 — 管理员")
    @PostMapping("/{pluginId}/canary")
    public R<Plugin> setCanary(
            @PathVariable String pluginId,
            @RequestBody Map<String, Object> body) {
        try {
            BigDecimal weight = new BigDecimal(String.valueOf(body.get("weight")));
            return R.ok(pluginService.setCanary(pluginId, weight));
        } catch (NoSuchElementException e) {
            return R.fail("插件不存在");
        } catch (IllegalArgumentException e) {
            return R.fail(400, e.getMessage());
        }
    }

    @SaCheckRole("admin")
    @Operation(summary = "提升金丝雀为正式版本 — 管理员")
    @PostMapping("/{pluginId}/canary/promote")
    public R<Plugin> promoteCanary(@PathVariable String pluginId) {
        try {
            return R.ok(pluginService.promoteCanary(pluginId));
        } catch (NoSuchElementException e) {
            return R.fail("插件不存在");
        }
    }

    @SaCheckRole("admin")
    @Operation(summary = "回滚到上一版本 — 管理员")
    @PostMapping("/{pluginId}/rollback")
    public R<Plugin> rollback(@PathVariable String pluginId) {
        try {
            return R.ok(pluginService.rollback(pluginId));
        } catch (NoSuchElementException e) {
            return R.fail("插件不存在");
        } catch (IllegalStateException e) {
            return R.fail(400, e.getMessage());
        }
    }

    @SaCheckRole("admin")
    @Operation(summary = "导出审计日志 — 管理员")
    @GetMapping("/audit-logs/export")
    public R<List<Map<String, Object>>> exportAuditLogs(
            @RequestParam(required = false) String pluginId,
            @RequestParam(defaultValue = "json") String format,
            @RequestParam(defaultValue = "100") int limit) {
        return R.ok(pluginService.exportAuditLogs(pluginId, format, limit));
    }

    // ── 所有已认证用户可访问 ──────────────────────────────────────────

    @Operation(summary = "获取插件详情")
    @GetMapping("/{pluginId}")
    public R<Plugin> getPlugin(@PathVariable String pluginId) {
        Plugin plugin = pluginService.getByPluginId(pluginId);
        if (plugin == null) {
            return R.fail("插件不存在");
        }
        return R.ok(plugin);
    }

    @Operation(summary = "分页查询插件列表")
    @GetMapping("/list")
    public R<PageResult<Plugin>> listPlugins(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize,
            @RequestParam(required = false) String status) {
        PageResult<Plugin> result = pluginService.list(page, pageSize, status);
        return R.ok(result);
    }

    @Operation(summary = "查询所有已启用插件")
    @GetMapping("/enabled")
    public R<List<Plugin>> listEnabled() {
        return R.ok(pluginService.listEnabled());
    }

    @Operation(summary = "获取插件审计日志")
    @GetMapping("/{pluginId}/audit-logs")
    public R<List<Map<String, Object>>> getAuditLogs(
            @PathVariable String pluginId,
            @RequestParam(defaultValue = "20") int limit) {
        Plugin plugin = pluginService.getByPluginId(pluginId);
        if (plugin == null) {
            return R.fail("插件不存在");
        }
        return R.ok(pluginService.getAuditLogs(plugin.getId(), limit));
    }

    @Operation(summary = "获取插件 ToolSpec 列表（供 Python AI 拉取）")
    @GetMapping("/tool-specs")
    public R<List<Map<String, Object>>> getToolSpecs() {
        return R.ok(pluginService.getPluginToolSpecs());
    }
}
