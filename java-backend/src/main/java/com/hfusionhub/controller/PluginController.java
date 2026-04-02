package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.Plugin;
import com.hfusionhub.service.PluginService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

/**
 * 工具插件管理控制器（用户端）
 *
 * @author HFusionHub Team
 */
@Slf4j
@Tag(name = "工具插件管理", description = "插件安装、启用/禁用、卸载、审计日志")
@RestController
@RequestMapping("/plugin")
@RequiredArgsConstructor
public class PluginController {

    private final PluginService pluginService;

    @Operation(summary = "安装插件")
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

    @Operation(summary = "启用插件")
    @PostMapping("/{pluginId}/enable")
    public R<Plugin> enable(@PathVariable String pluginId) {
        try {
            return R.ok(pluginService.enable(pluginId));
        } catch (NoSuchElementException e) {
            return R.fail("插件不存在");
        }
    }

    @Operation(summary = "禁用插件")
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

    @Operation(summary = "卸载插件")
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
