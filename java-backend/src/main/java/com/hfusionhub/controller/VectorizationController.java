package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.Document;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.service.VectorizationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 向量化控制器
 *
 * @author HFusionHub Team
 */
@Tag(name = "向量化管理", description = "文档向量化相关接口")
@RestController
@RequestMapping("/vectorize")
@RequiredArgsConstructor
public class VectorizationController {

    private final VectorizationService vectorizationService;
    private final DocumentMapper documentMapper;

    @Operation(summary = "触发文档向量化")
    @PostMapping("/{documentId}")
    public R<String> startVectorization(
            @Parameter(description = "文档ID") @PathVariable Long documentId) {
        vectorizationService.startVectorization(documentId);
        return R.ok("开始处理");
    }

    @Operation(summary = "查询文档处理状态")
    @GetMapping("/{documentId}/status")
    public R<Document> getStatus(
            @Parameter(description = "文档ID") @PathVariable Long documentId) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            return R.fail("文档不存在");
        }
        return R.ok(document);
    }

    @Operation(summary = "获取文档分块列表")
    @GetMapping("/{documentId}/chunks")
    public R<String> getDocumentChunks(
            @Parameter(description = "文档ID") @PathVariable Long documentId,
            @Parameter(description = "页码") @RequestParam(defaultValue = "1") Integer page,
            @Parameter(description = "每页大小") @RequestParam(defaultValue = "20") Integer size,
            @Parameter(description = "块类型筛选") @RequestParam(required = false) String blockType) {
        String result = vectorizationService.getDocumentChunks(documentId, page, size, blockType);
        // 直接返回Python引擎的响应
        return R.ok(result);
    }

    @Operation(summary = "获取单个分块详情")
    @GetMapping("/chunks/{chunkId}")
    public R<String> getChunkDetail(
            @Parameter(description = "分块ID") @PathVariable String chunkId) {
        String result = vectorizationService.getChunkDetail(chunkId);
        return R.ok(result);
    }

    @Operation(summary = "回调：更新文档处理状态")
    @PostMapping("/{documentId}/callback")
    public R<String> updateStatus(
            @Parameter(description = "文档ID") @PathVariable Long documentId,
            @RequestBody java.util.Map<String, Object> body) {
        String status = (String) body.get("status");
        Integer chunkCount = (Integer) body.get("chunkCount");
        vectorizationService.updateDocumentStatus(documentId, status, chunkCount);
        return R.ok("状态已更新");
    }
}
