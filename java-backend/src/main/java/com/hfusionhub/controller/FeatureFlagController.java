package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.dto.*;
import com.hfusionhub.common.result.R;
import com.hfusionhub.service.FeatureFlagService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/feature-flag")
@RequiredArgsConstructor
@Tag(name = "Feature Flag Management", description = "Dynamic feature flag CRUD, rules, and evaluation")
public class FeatureFlagController {

    private final FeatureFlagService featureFlagService;

    // ──────────── Flag CRUD (admin only) ────────────

    @PostMapping
    @SaCheckRole("admin")
    @Operation(summary = "Create feature flag (admin only)")
    public R<FeatureFlagInfoDTO> create(@Valid @RequestBody FeatureFlagCreateDTO dto) {
        return R.ok("Created", featureFlagService.create(dto));
    }

    @PutMapping("/{id}")
    @SaCheckRole("admin")
    @Operation(summary = "Update feature flag (admin only)")
    public R<FeatureFlagInfoDTO> update(@PathVariable Long id, @Valid @RequestBody FeatureFlagUpdateDTO dto) {
        return R.ok("Updated", featureFlagService.update(id, dto));
    }

    @DeleteMapping("/{id}")
    @SaCheckRole("admin")
    @Operation(summary = "Delete feature flag (admin only)")
    public R<Void> delete(@PathVariable Long id) {
        featureFlagService.delete(id);
        return R.ok();
    }

    @GetMapping("/{id}")
    @SaCheckRole("admin")
    @Operation(summary = "Get flag by ID (admin only)")
    public R<FeatureFlagInfoDTO> getById(@PathVariable Long id) {
        return R.ok(featureFlagService.getById(id));
    }

    @GetMapping("/key/{flagKey}")
    @SaCheckRole("admin")
    @Operation(summary = "Get flag by key (admin only)")
    public R<FeatureFlagInfoDTO> getByKey(@PathVariable String flagKey) {
        return R.ok(featureFlagService.getByKey(flagKey));
    }

    @GetMapping("/list")
    @SaCheckRole("admin")
    @Operation(summary = "List all flags paginated (admin only)")
    public R<PageResult<FeatureFlagInfoDTO>> list(
            @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) {
        return R.ok(featureFlagService.list(page, pageSize));
    }

    @GetMapping("/all")
    @SaCheckRole("admin")
    @Operation(summary = "List all flags unpaginated (admin only)")
    public R<List<FeatureFlagInfoDTO>> listAll() {
        return R.ok(featureFlagService.listAll());
    }

    // ──────────── Rules (admin only) ────────────

    @PostMapping("/{flagId}/rule")
    @SaCheckRole("admin")
    @Operation(summary = "Add override rule (admin only)")
    public R<FeatureFlagRuleInfoDTO> addRule(
            @PathVariable Long flagId, @Valid @RequestBody FeatureFlagRuleCreateDTO dto) {
        return R.ok("Rule added", featureFlagService.addRule(flagId, dto));
    }

    @PutMapping("/rule/{ruleId}")
    @SaCheckRole("admin")
    @Operation(summary = "Update a rule (admin only)")
    public R<FeatureFlagRuleInfoDTO> updateRule(
            @PathVariable Long ruleId, @Valid @RequestBody FeatureFlagRuleUpdateDTO dto) {
        return R.ok("Rule updated", featureFlagService.updateRule(ruleId, dto));
    }

    @DeleteMapping("/rule/{ruleId}")
    @SaCheckRole("admin")
    @Operation(summary = "Delete a rule (admin only)")
    public R<Void> deleteRule(@PathVariable Long ruleId) {
        featureFlagService.deleteRule(ruleId);
        return R.ok();
    }

    // ──────────── Evaluation (requires login) ────────────

    @PostMapping("/evaluate")
    @Operation(summary = "Evaluate a flag for a given context")
    public R<FeatureFlagEvaluateResultDTO> evaluate(@Valid @RequestBody FeatureFlagEvaluateDTO dto) {
        return R.ok(featureFlagService.evaluate(dto));
    }

    @PostMapping("/evaluate/batch")
    @Operation(summary = "Evaluate multiple flags in one call")
    public R<List<FeatureFlagEvaluateResultDTO>> evaluateBatch(@RequestBody List<FeatureFlagEvaluateDTO> dtos) {
        return R.ok(dtos.stream().map(featureFlagService::evaluate).toList());
    }
}
