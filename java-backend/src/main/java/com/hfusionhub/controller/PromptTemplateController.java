package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.PromptTemplateInfoDTO;
import com.hfusionhub.dto.PromptTemplateSaveDTO;
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

    @PostMapping
    public R<PromptTemplateInfoDTO> create(@Valid @RequestBody PromptTemplateSaveDTO dto) {
        return R.ok("提示词模板已创建", promptTemplateService.create(dto));
    }

    @PutMapping("/{id}")
    public R<PromptTemplateInfoDTO> update(@PathVariable Long id, @Valid @RequestBody PromptTemplateSaveDTO dto) {
        return R.ok("提示词模板已保存", promptTemplateService.update(id, dto));
    }

    @PostMapping("/{id}/publish")
    public R<PromptTemplateInfoDTO> publish(@PathVariable Long id) {
        return R.ok("模板已发布，可用于新建对话", promptTemplateService.publish(id));
    }

    @PostMapping("/{id}/unpublish")
    public R<PromptTemplateInfoDTO> unpublish(@PathVariable Long id) {
        return R.ok("模板已撤回，不再用于新建对话", promptTemplateService.unpublish(id));
    }

    @DeleteMapping("/{id}")
    public R<Void> delete(@PathVariable Long id) {
        promptTemplateService.delete(id);
        return R.ok();
    }
}
