package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.RagIntentNodeCreateDTO;
import com.hfusionhub.dto.RagIntentNodeInfoDTO;
import com.hfusionhub.dto.RagIntentNodeQueryDTO;
import com.hfusionhub.dto.RagIntentNodeUpdateDTO;
import com.hfusionhub.service.RagIntentNodeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
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

import java.util.List;

@RestController
@RequestMapping("/rag/intent-tree")
@RequiredArgsConstructor
@Tag(name = "RAG intent tree", description = "Intent tree management for RAG routing")
public class RagIntentTreeController {

    private final RagIntentNodeService ragIntentNodeService;

    @PostMapping
    @Operation(summary = "Create intent node")
    public R<RagIntentNodeInfoDTO> create(@Valid @RequestBody RagIntentNodeCreateDTO dto) {
        return R.ok("Created", ragIntentNodeService.create(dto));
    }

    @PutMapping("/{id}")
    @Operation(summary = "Update intent node")
    public R<RagIntentNodeInfoDTO> update(@PathVariable Long id,
                                          @Valid @RequestBody RagIntentNodeUpdateDTO dto) {
        return R.ok("Updated", ragIntentNodeService.update(id, dto));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "Delete intent node")
    public R<Void> delete(@PathVariable Long id) {
        ragIntentNodeService.delete(id);
        return R.ok();
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get intent node")
    public R<RagIntentNodeInfoDTO> getById(@PathVariable Long id) {
        return R.ok(ragIntentNodeService.getById(id));
    }

    @GetMapping("/list")
    @Operation(summary = "List intent nodes")
    public R<PageResult<RagIntentNodeInfoDTO>> list(RagIntentNodeQueryDTO queryDTO) {
        return R.ok(ragIntentNodeService.list(queryDTO));
    }

    @GetMapping("/tree")
    @Operation(summary = "Get intent tree")
    public R<List<RagIntentNodeInfoDTO>> tree(@RequestParam(required = false) Integer enabled) {
        return R.ok(ragIntentNodeService.tree(enabled));
    }
}
