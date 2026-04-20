package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.AppApiKeyInfoDTO;
import com.hfusionhub.dto.AppCreateDTO;
import com.hfusionhub.dto.AppInfoDTO;
import com.hfusionhub.service.AppService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 应用管理控制器（对外发布 Agent）
 *
 * @author HFusionHub Team
 */
@Tag(name = "应用管理", description = "创建/发布应用并管理 API Key")
@RestController
@RequestMapping("/app")
@RequiredArgsConstructor
public class AppController {

    private final AppService appService;
    private final com.hfusionhub.service.AuditLogService auditLogService;

    @Operation(summary = "创建应用")
    @PostMapping
    public R<AppInfoDTO> create(@Valid @RequestBody AppCreateDTO dto) {
        return R.ok("应用已创建", appService.create(dto));
    }

    @Operation(summary = "我的应用列表")
    @GetMapping
    public R<List<AppInfoDTO>> list() {
        return R.ok(appService.listMine());
    }

    @Operation(summary = "应用详情")
    @GetMapping("/{id}")
    public R<AppInfoDTO> get(@PathVariable Long id) {
        return R.ok(appService.get(id));
    }

    @Operation(summary = "更新应用")
    @PutMapping("/{id}")
    public R<AppInfoDTO> update(@PathVariable Long id, @Valid @RequestBody AppCreateDTO dto) {
        return R.ok("应用已更新", appService.update(id, dto));
    }

    @Operation(summary = "删除应用")
    @DeleteMapping("/{id}")
    public R<Void> delete(@PathVariable Long id) {
        appService.delete(id);
        auditLogService.record("app.delete", "app", String.valueOf(id), "删除应用");
        return R.ok("应用已删除", null);
    }

    @Operation(summary = "发布应用")
    @PostMapping("/{id}/publish")
    public R<AppInfoDTO> publish(@PathVariable Long id) {
        AppInfoDTO info = appService.publish(id);
        auditLogService.record("app.publish", "app", String.valueOf(id), "发布应用: " + info.getName());
        return R.ok("应用已发布", info);
    }

    @Operation(summary = "撤回应用")
    @PostMapping("/{id}/unpublish")
    public R<AppInfoDTO> unpublish(@PathVariable Long id) {
        AppInfoDTO info = appService.unpublish(id);
        auditLogService.record("app.unpublish", "app", String.valueOf(id), "撤回应用: " + info.getName());
        return R.ok("应用已撤回", info);
    }

    @Operation(summary = "创建 API Key", description = "返回的 key 明文仅展示一次")
    @PostMapping("/{id}/api-keys")
    public R<AppApiKeyInfoDTO> createApiKey(@PathVariable Long id, @RequestBody(required = false) Map<String, String> body) {
        AppApiKeyInfoDTO info = appService.createApiKey(id, body == null ? null : body.get("name"));
        auditLogService.record("api_key.create", "app_api_key", String.valueOf(info.getId()),
                "为应用 " + id + " 创建 API Key: " + info.getKeyPrefix() + "****");
        return R.ok("API Key 已创建", info);
    }

    @Operation(summary = "API Key 列表")
    @GetMapping("/{id}/api-keys")
    public R<List<AppApiKeyInfoDTO>> listApiKeys(@PathVariable Long id) {
        return R.ok(appService.listApiKeys(id));
    }

    @Operation(summary = "删除 API Key")
    @DeleteMapping("/{id}/api-keys/{keyId}")
    public R<Void> deleteApiKey(@PathVariable Long id, @PathVariable Long keyId) {
        appService.deleteApiKey(id, keyId);
        auditLogService.record("api_key.delete", "app_api_key", String.valueOf(keyId), "删除应用 " + id + " 的 API Key");
        return R.ok("API Key 已删除", null);
    }
}
