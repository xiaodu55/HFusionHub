package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.PromptTemplateInfoDTO;
import com.hfusionhub.dto.PromptTemplateSaveDTO;
import com.hfusionhub.dto.PromptTemplateVersionDTO;
import com.hfusionhub.service.PromptTemplateService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/prompt-templates")
@RequiredArgsConstructor
public class PromptTemplateController {

    private final PromptTemplateService promptTemplateService;

    @GetMapping
    public R<List<PromptTemplateInfoDTO>> list() {
        return R.ok(promptTemplateService.listMine());
    }

    @GetMapping("/recycle-bin")
    public R<List<PromptTemplateInfoDTO>> listRecycleBin(
            @RequestParam(required = false) String keyword) {
        return R.ok(promptTemplateService.listRecycleBin(keyword));
    }

    @PostMapping
    public R<PromptTemplateInfoDTO> create(@Valid @RequestBody PromptTemplateSaveDTO dto) {
        return R.ok("提示词模板已创建", promptTemplateService.create(dto));
    }

    @PutMapping("/{id}")
    public R<PromptTemplateInfoDTO> update(@PathVariable Long id, @Valid @RequestBody PromptTemplateSaveDTO dto) {
        return R.ok("提示词模板已保存", promptTemplateService.update(id, dto));
    }

    @PostMapping("/{id}/publish")
    public R<PromptTemplateInfoDTO> publish(@PathVariable Long id,
                                           @RequestParam Integer expectedVersion) {
        return R.ok("模板已发布，可用于新建对话", promptTemplateService.publish(id, expectedVersion));
    }

    @PostMapping("/{id}/unpublish")
    public R<PromptTemplateInfoDTO> unpublish(@PathVariable Long id,
                                             @RequestParam Integer expectedVersion) {
        return R.ok("模板已撤回，不再用于新建对话", promptTemplateService.unpublish(id, expectedVersion));
    }

    @DeleteMapping("/{id}")
    public R<Void> delete(@PathVariable Long id) {
        promptTemplateService.delete(id);
        return R.ok("回答方案已移入回收站", null);
    }

    @PostMapping("/{id}/restore")
    public R<Void> restore(@PathVariable Long id) {
        promptTemplateService.restore(id);
        return R.ok("回答方案已恢复", null);
    }

    @DeleteMapping("/{id}/purge")
    public R<Void> purge(@PathVariable Long id) {
        promptTemplateService.purge(id);
        return R.ok("回答方案已永久删除", null);
    }

    // ── Version history ───────────────────────────────────────────────

    @GetMapping("/{id}/versions")
    public R<List<PromptTemplateVersionDTO>> listVersions(@PathVariable Long id) {
        return R.ok(promptTemplateService.listVersions(id));
    }

    @PostMapping("/{id}/rollback/{versionId}")
    public R<PromptTemplateInfoDTO> rollback(@PathVariable Long id,
                                              @PathVariable Long versionId,
                                              @RequestParam Integer expectedVersion) {
        PromptTemplateInfoDTO result = promptTemplateService.rollback(id, versionId, expectedVersion);
        return R.ok("已回滚到目标版本，当前为草稿。请确认内容后重新发布。", result);
    }
}
