package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.BidProjectCreateDTO;
import com.hfusionhub.dto.BidProjectDetailDTO;
import com.hfusionhub.dto.BidProjectInfoDTO;
import com.hfusionhub.dto.BidProjectQueryDTO;
import com.hfusionhub.service.BidProjectService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 投标项目控制器（招投标垂直化）
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/bid/project")
@RequiredArgsConstructor
@Tag(name = "投标项目", description = "投标项目 CRUD 与招标解读")
public class BidProjectController {

    private final BidProjectService bidProjectService;

    @PostMapping
    @Operation(summary = "创建投标项目", description = "创建投标项目并关联招标文件知识库")
    public R<BidProjectInfoDTO> create(@Valid @RequestBody BidProjectCreateDTO createDTO) {
        return R.ok("创建成功", bidProjectService.create(createDTO));
    }

    @GetMapping("/list")
    @Operation(summary = "分页查询投标项目", description = "分页查询当前用户的投标项目")
    public R<PageResult<BidProjectInfoDTO>> list(BidProjectQueryDTO queryDTO) {
        return R.ok(bidProjectService.list(queryDTO));
    }

    @GetMapping("/{id}")
    @Operation(summary = "获取投标项目", description = "根据ID获取投标项目基本信息")
    public R<BidProjectInfoDTO> getById(@PathVariable Long id) {
        return R.ok(bidProjectService.getById(id));
    }

    @GetMapping("/{id}/detail")
    @Operation(summary = "获取投标项目详情", description = "项目 + 要素 + 评分办法 + 需求清单")
    public R<BidProjectDetailDTO> getDetail(@PathVariable Long id) {
        return R.ok(bidProjectService.getDetail(id));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除投标项目", description = "软删除投标项目")
    public R<Void> delete(@PathVariable Long id) {
        bidProjectService.delete(id);
        return R.ok();
    }

    @PutMapping("/{id}/status")
    @Operation(summary = "推进项目状态", description = "interpreting|requirements|drafting|checking|submitted|archived")
    public R<BidProjectInfoDTO> updateStatus(@PathVariable Long id, @RequestParam String status) {
        return R.ok(bidProjectService.updateStatus(id, status));
    }

    @PostMapping("/{id}/interpret")
    @Operation(summary = "触发招标解读", description = "调用 Python 解读工作流，生成要素/评分办法/需求清单")
    public R<BidProjectDetailDTO> interpret(@PathVariable Long id) {
        return R.ok("解读完成", bidProjectService.interpret(id));
    }

    @PutMapping("/{id}/requirements/{requirementId}/status")
    @Operation(summary = "更新需求状态", description = "人工确认/修正需求清单，含低置信 manual_review 确认")
    public R<Void> updateRequirementStatus(
            @PathVariable Long id, @PathVariable Long requirementId, @RequestParam String status) {
        bidProjectService.updateRequirementStatus(id, requirementId, status);
        return R.ok();
    }
}
