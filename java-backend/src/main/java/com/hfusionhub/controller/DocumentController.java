package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.DocumentInfoDTO;
import com.hfusionhub.dto.DocumentNameDTO;
import com.hfusionhub.dto.DocumentQueryDTO;
import com.hfusionhub.dto.DocumentUpdateDTO;
import com.hfusionhub.service.DocumentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/**
 * 文档控制器
 *
 * @author HFusionHub Team
 */
@Tag(name = "文档管理", description = "文档上传、查询、更新、删除")
@RestController
@RequestMapping("/document")
@RequiredArgsConstructor
public class DocumentController {

    private final DocumentService documentService;

    @Operation(summary = "上传文档", description = "上传文档到指定知识库")
    @PostMapping("/upload")
    public R<DocumentInfoDTO> upload(
            @Parameter(description = "文件") @RequestParam("file") MultipartFile file,
            @Parameter(description = "文档标题") @RequestParam("title") String title,
            @Parameter(description = "知识库ID") @RequestParam("knowledgeBaseId") Long knowledgeBaseId,
            @Parameter(description = "可见性等级：general/confidential，缺省 general")
            @RequestParam(value = "visibility", required = false) String visibility) {
        DocumentInfoDTO info = documentService.upload(file, title, knowledgeBaseId, visibility);
        return R.ok("上传成功", info);
    }

    @Operation(summary = "从网页 URL 创建文档", description = "抓取公开 HTTPS 网页并暂存为 markdown 文档（待解析）")
    @PostMapping("/from-url")
    public R<DocumentInfoDTO> createFromUrl(
            @Parameter(description = "知识库ID") @RequestParam("knowledgeBaseId") Long knowledgeBaseId,
            @Valid @RequestBody com.hfusionhub.dto.DocumentFromUrlDTO dto) {
        DocumentInfoDTO info = documentService.createFromUrl(dto.getUrl(), dto.getTitle(), knowledgeBaseId);
        return R.ok("网页已抓取，等待解析", info);
    }

    @Operation(summary = "更新文档", description = "更新文档信息")
    @PutMapping("/{id}")
    public R<DocumentInfoDTO> update(
            @Parameter(description = "文档ID") @PathVariable Long id, @Valid @RequestBody DocumentUpdateDTO dto) {
        DocumentInfoDTO info = documentService.update(id, dto);
        return R.ok("更新成功", info);
    }

    @Operation(summary = "删除文档", description = "删除指定文档")
    @DeleteMapping("/{id}")
    public R<Void> delete(@Parameter(description = "文档ID") @PathVariable Long id) {
        documentService.delete(id);
        return R.ok();
    }

    @Operation(summary = "回收站文档列表")
    @GetMapping("/recycle-bin")
    public R<PageResult<DocumentInfoDTO>> listRecycleBin(DocumentQueryDTO queryDTO) {
        return R.ok(documentService.listRecycleBin(queryDTO));
    }

    @Operation(summary = "恢复回收站文档")
    @PostMapping("/{id}/restore")
    public R<Void> restore(@Parameter(description = "文档ID") @PathVariable Long id) {
        documentService.restore(id);
        return R.ok();
    }

    @Operation(summary = "彻底删除回收站文档")
    @DeleteMapping("/{id}/purge")
    public R<Void> purge(@Parameter(description = "文档ID") @PathVariable Long id) {
        documentService.purge(id);
        return R.ok();
    }

    @Operation(summary = "获取文档详情", description = "获取指定文档的详细信息")
    @GetMapping("/{id}")
    public R<DocumentInfoDTO> getById(@Parameter(description = "文档ID") @PathVariable Long id) {
        DocumentInfoDTO info = documentService.getById(id);
        return R.ok(info);
    }

    @Operation(summary = "获取文档内容", description = "获取指定文档的内容")
    @GetMapping("/{id}/content")
    public R<String> getContent(@Parameter(description = "文档ID") @PathVariable Long id) {
        String content = documentService.getContent(id);
        return R.ok(content);
    }

    @Operation(summary = "分页查询文档列表", description = "分页查询所有文档")
    @GetMapping("/list")
    public R<PageResult<DocumentInfoDTO>> list(DocumentQueryDTO queryDTO) {
        PageResult<DocumentInfoDTO> result = documentService.list(queryDTO);
        return R.ok(result);
    }

    @Operation(summary = "获取知识库下的文档列表", description = "获取指定知识库下的文档列表")
    @GetMapping("/list/{knowledgeBaseId}")
    public R<PageResult<DocumentInfoDTO>> listByKnowledgeBase(
            @Parameter(description = "知识库ID") @PathVariable Long knowledgeBaseId, DocumentQueryDTO queryDTO) {
        PageResult<DocumentInfoDTO> result = documentService.listByKnowledgeBase(knowledgeBaseId, queryDTO);
        return R.ok(result);
    }

    @Operation(summary = "获取我的知识库下的文档列表", description = "获取当前用户知识库下的文档列表")
    @GetMapping("/my/{knowledgeBaseId}")
    public R<PageResult<DocumentInfoDTO>> listByCurrentUser(
            @Parameter(description = "知识库ID") @PathVariable Long knowledgeBaseId, DocumentQueryDTO queryDTO) {
        PageResult<DocumentInfoDTO> result = documentService.listByCurrentUser(knowledgeBaseId, queryDTO);
        return R.ok(result);
    }

    @Operation(summary = "获取文档名称", description = "根据文档ID获取文档名称，用于向量化搜索结果显示")
    @GetMapping("/{id}/name")
    public R<DocumentNameDTO> getDocumentName(@Parameter(description = "文档ID") @PathVariable Long id) {
        DocumentNameDTO nameDTO = documentService.getDocumentName(id);
        return R.ok(nameDTO);
    }

    @Operation(summary = "解析文档", description = "触发文档解析和向量化")
    @PostMapping("/{id}/parse")
    public R<String> parseDocument(
            @Parameter(description = "文档ID") @PathVariable Long id,
            @RequestBody(required = false) java.util.Map<String, String> body) {
        String model = body != null ? body.get("model") : null;
        documentService.parseDocument(id, model);
        return R.ok("开始解析");
    }
}
