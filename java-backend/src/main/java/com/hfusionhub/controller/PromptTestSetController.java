package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.PromptTestCaseDTO;
import com.hfusionhub.dto.PromptTestCaseSaveDTO;
import com.hfusionhub.dto.PromptTestSetCompareRequest;
import com.hfusionhub.dto.PromptTestSetCompareResponse;
import com.hfusionhub.dto.PromptTestSetDTO;
import com.hfusionhub.dto.PromptTestSetDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunDTO;
import com.hfusionhub.dto.PromptTestSetRunDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunRequest;
import com.hfusionhub.dto.PromptTestSetRunStatusDTO;
import com.hfusionhub.dto.PromptTestSetSaveDTO;
import com.hfusionhub.service.PromptTestSetService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

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
    public R<PromptTestSetDetailDTO> update(@PathVariable Long id, @Valid @RequestBody PromptTestSetSaveDTO dto) {
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
    public R<PromptTestCaseDTO> addCase(@PathVariable Long id, @Valid @RequestBody PromptTestCaseSaveDTO dto) {
        return R.ok("测试用例已添加", promptTestSetService.addCase(id, dto));
    }

    @Operation(summary = "更新用例集中的用例")
    @PutMapping("/{id}/cases/{caseId}")
    public R<PromptTestCaseDTO> updateCase(
            @PathVariable Long id, @PathVariable Long caseId, @Valid @RequestBody PromptTestCaseSaveDTO dto) {
        return R.ok("测试用例已保存", promptTestSetService.updateCase(id, caseId, dto));
    }

    @Operation(summary = "删除用例集中的用例")
    @DeleteMapping("/{id}/cases/{caseId}")
    public R<Void> deleteCase(@PathVariable Long id, @PathVariable Long caseId) {
        promptTestSetService.deleteCase(id, caseId);
        return R.ok();
    }

    // ── Batch run ─────────────────────────────────────────────────────

    @Operation(
            summary = "提交批量运行",
            description = "用同一模板对集内所有问题逐个运行。异步入队，立即返回任务状态，通过 /runs/{runId}/status 轮询进度，支持取消与失败重试。")
    @PostMapping("/{id}/run")
    public R<PromptTestSetRunStatusDTO> run(
            @PathVariable Long id, @Valid @RequestBody PromptTestSetRunRequest request) {
        return R.ok("批量测试已提交", promptTestSetService.run(id, request));
    }

    @Operation(summary = "查询批量运行任务状态", description = "轮询实时进度（progressCount/totalCases）与终态")
    @GetMapping("/runs/{runId}/status")
    public R<PromptTestSetRunStatusDTO> runStatus(@PathVariable Long runId) {
        return R.ok(promptTestSetService.getRunStatus(runId));
    }

    @Operation(summary = "取消批量运行", description = "取消排队中或执行中的任务；已完成的运行不能取消")
    @PostMapping("/runs/{runId}/cancel")
    public R<PromptTestSetRunStatusDTO> cancelRun(@PathVariable Long runId) {
        return R.ok("批量测试已取消", promptTestSetService.cancelRun(runId));
    }

    @Operation(summary = "重试失败的批量运行", description = "重新排队已失败/已取消的运行（attempt+1），清除旧结果")
    @PostMapping("/runs/{runId}/retry")
    public R<PromptTestSetRunStatusDTO> retryRun(@PathVariable Long runId) {
        return R.ok("已重新提交批量测试", promptTestSetService.retryRun(runId));
    }

    // ── Run history & comparison ──────────────────────────────────────

    @Operation(summary = "列出用例集的运行历史", description = "新到旧，含模板版本快照与成功/失败统计")
    @GetMapping("/{id}/runs")
    public R<List<PromptTestSetRunDTO>> listRuns(@PathVariable Long id) {
        return R.ok(promptTestSetService.listRuns(id));
    }

    @Operation(summary = "获取单次运行的详情", description = "含每个用例的回答、耗时、Token、来源")
    @GetMapping("/runs/{runId}")
    public R<PromptTestSetRunDetailDTO> runDetail(@PathVariable Long runId) {
        return R.ok(promptTestSetService.getRunDetail(runId));
    }

    @Operation(summary = "对比两次运行", description = "按同一用例逐项对比回答、耗时、Token 与成败")
    @PostMapping("/compare")
    public R<PromptTestSetCompareResponse> compare(@Valid @RequestBody PromptTestSetCompareRequest request) {
        return R.ok("对比完成", promptTestSetService.compare(request));
    }
}
