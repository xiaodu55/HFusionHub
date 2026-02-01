package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.Document;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.service.VectorizationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

/**
 * 向量化控制器
 *
 * @author HFusionHub Team
 */
@Slf4j
@Tag(name = "向量化管理", description = "文档向量化相关接口")
@RestController
@RequestMapping("/vectorize")
@RequiredArgsConstructor
public class VectorizationController {

    private final VectorizationService vectorizationService;
    private final DocumentMapper documentMapper;

    @Value("${python-ai.callback-secret:hfusionhub-callback-secret-key}")
    private String callbackSecret;

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
            @RequestBody java.util.Map<String, Object> body,
            @RequestHeader(value = "X-Callback-Secret", required = false) String secret) {
        // 验证回调密钥
        if (!callbackSecret.equals(secret)) {
            log.warn("回调密钥验证失败: documentId={}, secret={}", documentId, secret);
            return R.fail("回调密钥无效");
        }
        String status = body.get("status") != null ? String.valueOf(body.get("status")) : null;
        Object chunkCountObj = body.get("chunkCount");
        Integer chunkCount = chunkCountObj != null ? Integer.parseInt(String.valueOf(chunkCountObj)) : null;
        vectorizationService.updateDocumentStatus(documentId, status, chunkCount);
        return R.ok("状态已更新");
    }

    @Operation(summary = "同步文档状态 - 从Python引擎查询实际分块数更新状态")
    @PostMapping("/{documentId}/sync-status")
    public R<String> syncDocumentStatus(
            @Parameter(description = "文档ID") @PathVariable Long documentId) {
        vectorizationService.syncDocumentStatus(documentId);
        return R.ok("状态已同步");
    }

    @Operation(summary = "批量同步所有待解析/处理中文档的状态")
    @PostMapping("/sync-all")
    public R<String> syncAllDocuments() {
        java.util.List<Document> pendingDocs = documentMapper.selectList(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<Document>()
                        .in(Document::getStatus, 0, 1)); // PENDING(0) 和 PROCESSING(1)
        int updated = 0;
        for (Document doc : pendingDocs) {
            try {
                vectorizationService.syncDocumentStatus(doc.getId());
                updated++;
            } catch (Exception e) {
                // 跳过同步失败的文档
            }
        }
        return R.ok("同步完成，" + updated + "/" + pendingDocs.size() + " 个文档状态已更新");
    }

    @Operation(summary = "重置文档状态为待解析")
    @PostMapping("/{documentId}/reset")
    public R<String> resetDocument(
            @Parameter(description = "文档ID") @PathVariable Long documentId) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            return R.fail("文档不存在");
        }
        // 只有处理中或失败的状态才允许重置
        if (document.getStatus() != null
                && document.getStatus() != com.hfusionhub.enums.DocumentStatus.PROCESSING.getCode()
                && document.getStatus() != com.hfusionhub.enums.DocumentStatus.FAILED.getCode()) {
            return R.fail("当前状态不允许重置");
        }
        document.setStatus(com.hfusionhub.enums.DocumentStatus.PENDING.getCode());
        document.setErrorMessage(null);
        documentMapper.updateById(document);
        return R.ok("已重置为待解析状态");
    }
}
