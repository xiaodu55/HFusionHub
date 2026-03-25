package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.PromptTestCaseDTO;
import com.hfusionhub.dto.PromptTestCaseSaveDTO;
import com.hfusionhub.dto.PromptTestSetDTO;
import com.hfusionhub.dto.PromptTestSetDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunRequest;
import com.hfusionhub.dto.PromptTestSetRunResponse;
import com.hfusionhub.dto.PromptTestSetSaveDTO;
import com.hfusionhub.service.PromptTestSetService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 提示词测试用例集控制器 — 保存固定问题与变量值，批量运行同一组问题。
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/prompt-test-sets")
@RequiredArgsConstructor
@Tag(name = "提示词测试用例集", description = "保存固定问题与变量值，批量运行同一组问题，为不同模板/版本结果对比打基础")
public class PromptTestSetController {

    private final PromptTestSetService promptTestSetService;

    @Operation(summary = "列出我的测试用例集")
    @GetMapping
    public R<List<PromptTestSetDTO>> list() {
        return R.ok(promptTestSetService.listMine());
    }

    @Operation(summary = "创建测试用例集")
    @PostMapping
    public R<PromptTestSetDetailDTO> create(@Valid @RequestBody PromptTestSetSaveDTO dto) {
        return R.ok("测试用例集已创建", promptTestSetService.create(dto));
    }

    @Operation(summary = "获取测试用例集详情（含用例）")
    @GetMapping("/{id}")
    public R<PromptTestSetDetailDTO> detail(@PathVariable Long id) {
        return R.ok(promptTestSetService.getDetail(id));
    }

    @Operation(summary = "更新测试用例集")
    @PutMapping("/{id}")
    public R<PromptTestSetDetailDTO> update(@PathVariable Long id,
                                             @Valid @RequestBody PromptTestSetSaveDTO dto) {
        return R.ok("测试用例集已保存", promptTestSetService.update(id, dto));
    }

    @Operation(summary = "删除测试用例集（级联删除用例）")
    @DeleteMapping("/{id}")
    public R<Void> delete(@PathVariable Long id) {
        promptTestSetService.delete(id);
        return R.ok();
    }

    // ── Cases ─────────────────────────────────────────────────────────

    @Operation(summary = "在用例集中添加用例")
    @PostMapping("/{id}/cases")
    public R<PromptTestCaseDTO> addCase(@PathVariable Long id,
                                        @Valid @RequestBody PromptTestCaseSaveDTO dto) {
        return R.ok("测试用例已添加", promptTestSetService.addCase(id, dto));
    }

    @Operation(summary = "更新用例集中的用例")
    @PutMapping("/{id}/cases/{caseId}")
    public R<PromptTestCaseDTO> updateCase(@PathVariable Long id,
                                            @PathVariable Long caseId,
                                            @Valid @RequestBody PromptTestCaseSaveDTO dto) {
        return R.ok("测试用例已保存", promptTestSetService.updateCase(id, caseId, dto));
    }

    @Operation(summary = "删除用例集中的用例")
    @DeleteMapping("/{id}/cases/{caseId}")
    public R<Void> deleteCase(@PathVariable Long id, @PathVariable Long caseId) {
        promptTestSetService.deleteCase(id, caseId);
        return R.ok();
    }

    // ── Batch run ─────────────────────────────────────────────────────

    @Operation(summary = "批量运行用例集", description = "用同一模板对集内所有问题逐个运行，返回每个用例的结果。单例失败不中断整体。")
    @PostMapping("/{id}/run")
    public R<PromptTestSetRunResponse> run(@PathVariable Long id,
                                           @Valid @RequestBody PromptTestSetRunRequest request) {
        return R.ok("批量测试完成", promptTestSetService.run(id, request));
    }
}
