package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.BidTemplate;
import com.hfusionhub.service.BidTemplateService;
import com.hfusionhub.tenant.TenantContext;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 标书模板控制器（招投标垂直化 · P2-7 行业方案包 / 模板商城）
 *
 * <p>租户可见平台级模板 + 自有模板；平台模板只读。</p>
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/bid/template")
@RequiredArgsConstructor
@Tag(name = "投标模板", description = "标书模板商城与行业方案包模板（P2-7）")
public class BidTemplateController {

    private final BidTemplateService templateService;

    @GetMapping("/list")
    @Operation(summary = "模板列表", description = "平台级 + 本租户自有模板，可按行业过滤")
    public R<List<BidTemplate>> list(@RequestParam(required = false) String industry) {
        return R.ok(templateService.listVisible(TenantContext.requireTenantId(), industry));
    }

    @GetMapping("/{id}")
    @Operation(summary = "模板详情", description = "仅平台级或本租户自有模板")
    public R<BidTemplate> getById(@PathVariable Long id) {
        return R.ok(templateService.getByIdVisible(id, TenantContext.requireTenantId()));
    }

    @PostMapping
    @Operation(summary = "新建租户私有模板")
    public R<BidTemplate> create(@RequestBody BidTemplate template) {
        return R.ok("模板已创建", templateService.create(
                template, TenantContext.requireTenantId(), JwtUtils.getCurrentUserId()));
    }

    @PutMapping
    @Operation(summary = "更新模板", description = "仅本租户私有模板")
    public R<Void> update(@RequestBody BidTemplate template) {
        templateService.update(template, TenantContext.requireTenantId());
        return R.ok("模板已更新", null);
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "归档模板", description = "仅本租户私有模板")
    public R<Void> archive(@PathVariable Long id) {
        templateService.archive(id, TenantContext.requireTenantId());
        return R.ok("模板已归档", null);
    }
}
