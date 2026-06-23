package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.DocumentInfoDTO;
import com.hfusionhub.dto.DocumentNameDTO;
import com.hfusionhub.dto.DocumentQueryDTO;
import com.hfusionhub.dto.DocumentUpdateDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.User;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.DeletionService;
import com.hfusionhub.service.DocumentService;
import com.hfusionhub.service.VectorizationService;
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/**
 * 文档服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DocumentServiceImpl implements DocumentService {

    private final DocumentMapper documentMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final UserMapper userMapper;
    private final VectorizationService vectorizationService;
    private final DeletionService deletionService;
    private final com.hfusionhub.client.AiClient aiClient;

    private static final String UPLOAD_DIR = "uploads/documents";
    private static final long MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
    // 允许的文件扩展名（优先使用扩展名检查，比MIME类型更可靠）
    private static final List<String> ALLOWED_EXTENSIONS = List.of(".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx");
    // 允许的MIME类型（作为辅助验证）
    private static final List<String> ALLOWED_TYPES = List.of(
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/vnd.ms-excel",
            "application/octet-stream" // 允许通用二进制流（由扩展名验证）
            );

    @Override
    @Transactional
    public DocumentInfoDTO upload(MultipartFile file, String title, Long kbId) {
        // 1. 验证知识库存在且属于当前用户
        Long currentUserId = JwtUtils.getCurrentUserId();
        KnowledgeBase kb = knowledgeBaseMapper.selectById(kbId);
        if (kb == null) {
            throw new BusinessException("知识库不存在");
        }
        if (!kb.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权访问该知识库");
        }
        if (kb.getStatus() == null || kb.getStatus() != CommonConstants.KB_STATUS_NORMAL) {
            throw new BusinessException("知识库已禁用，无法上传文档");
        }

        // 2. 验证文件
        if (file == null || file.isEmpty()) {
            throw new BusinessException("文件不能为空");
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            throw new BusinessException("文件大小不能超过10MB");
        }
        // 验证文件扩展名（优先）和MIME类型（辅助）
        String originalFilename = file.getOriginalFilename();
        String contentType = file.getContentType();
        boolean fileValid = false;

        // 方法1: 检查文件扩展名
        if (originalFilename != null) {
            String lowerFilename = originalFilename.toLowerCase();
            for (String ext : ALLOWED_EXTENSIONS) {
                if (lowerFilename.endsWith(ext)) {
                    fileValid = true;
                    break;
                }
            }
        }

        // 方法2: 如果扩展名检查失败，检查MIME类型
        if (!fileValid && contentType != null) {
            fileValid = ALLOWED_TYPES.contains(contentType);
        }

        log.debug("文件验证: filename='{}', contentType='{}', valid={}", originalFilename, contentType, fileValid);

        if (!fileValid) {
            throw new BusinessException("不支持的文件类型: " + originalFilename + " (" + contentType + ")");
        }

        // 3. 保存文件到临时目录
        String tempPath = saveFile(file);

        // 4. 创建文档记录
        Document document = new Document();
        document.setKnowledgeBaseId(kbId);
        document.setTitle(title);
        // 转换为正式路径存入数据库
        String finalPath = tempToFinalPath(tempPath);
        document.setFilePath(finalPath);
        document.setFileType(getFileExtension(file.getOriginalFilename()));
        document.setFileSize(file.getSize());
        document.setStatus(DocumentStatus.PENDING.getCode()); // 待解析
        documentMapper.insert(document);

        // 5. 注册事务提交后的文件提交动作
        registerFileCommit(document.getId(), tempPath);

        // 6. 转换为 DTO
        return convertToInfoDTO(document, kb.getName());
    }

    @Override
    @Transactional
    public DocumentInfoDTO createFromUrl(String url, String title, Long kbId) {
        // 1. 验证知识库存在且属于当前用户
        Long currentUserId = JwtUtils.getCurrentUserId();
        KnowledgeBase kb = knowledgeBaseMapper.selectById(kbId);
        if (kb == null) {
            throw new BusinessException("知识库不存在");
        }
        if (!kb.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权访问该知识库");
        }
        if (kb.getStatus() == null || kb.getStatus() != CommonConstants.KB_STATUS_NORMAL) {
            throw new BusinessException("知识库已禁用，无法添加网页文档");
        }

        // 2. 校验 URL 基本格式
        if (url == null || url.isBlank()) {
            throw new BusinessException("网页地址不能为空");
        }
        String trimmedUrl = url.trim();

        // 3. 请求 Python AI 抓取网页并暂存为 markdown
        Map<String, Object> ingest = aiClient.ingestUrl(trimmedUrl, title);
        Object success = ingest.get("success");
        if (!Boolean.TRUE.equals(success)) {
            Object message = ingest.get("message");
            throw new BusinessException(message == null ? "网页抓取失败" : message.toString());
        }
        String filePath = String.valueOf(ingest.getOrDefault("file_path", ""));
        String effectiveTitle = String.valueOf(ingest.getOrDefault("title", trimmedUrl));
        if (filePath.isBlank()) {
            throw new BusinessException("网页抓取失败：AI 服务未返回文件路径");
        }

        // 4. 创建文档记录（待解析，与上传一致，用户可点击解析）
        Document document = new Document();
        document.setKnowledgeBaseId(kbId);
        document.setTitle(effectiveTitle);
        document.setFilePath(filePath);
        document.setFileType("md");
        Object contentLength = ingest.get("content_length");
        document.setFileSize(contentLength instanceof Number ? ((Number) contentLength).longValue() : 0L);
        document.setStatus(DocumentStatus.PENDING.getCode());
        documentMapper.insert(document);

        log.info("网页文档已创建: docId={}, url={}, title={}", document.getId(), trimmedUrl, effectiveTitle);
        return convertToInfoDTO(document, kb.getName());
    }

    @Override
    @Transactional
    public DocumentInfoDTO update(Long id, DocumentUpdateDTO dto) {
        // 1. 查询文档
        Document document = documentMapper.selectById(id);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }

        // 2. 验证权限
        Long currentUserId = JwtUtils.getCurrentUserId();
        KnowledgeBase kb = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        if (kb == null || !kb.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权修改该文档");
        }

        // 3. 更新文档
        boolean contentChanged = false;
        if (StringUtils.hasText(dto.getTitle())) {
            document.setTitle(dto.getTitle());
        }
        if (dto.getContent() != null) {
            document.setContent(dto.getContent());
            contentChanged = true;
        }
        documentMapper.updateById(document);

        // 4. 内容变更时标记为 PENDING，触发重新向量化
        if (contentChanged) {
            document.setStatus(DocumentStatus.PENDING.getCode());
            documentMapper.updateById(document);
            log.info("Document {} content updated, marked PENDING for re-index", document.getId());
        }

        // 5. 转换为 DTO
        return convertToInfoDTO(document, kb.getName());
    }

    @Override
    @Transactional
    public void delete(Long id) {
        // 1. 查询文档
        Document document = documentMapper.selectById(id);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }

        // 2. 验证权限
        Long currentUserId = JwtUtils.getCurrentUserId();
        KnowledgeBase kb = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        if (kb == null || !kb.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权删除该文档");
        }

        if (DocumentStatus.DELETING.getCode().equals(document.getStatus())) {
            return;
        }

        // 3. 删除动作交给 outbox 任务执行，避免 Python/Milvus 临时失败直接阻断用户删除。
        document.setStatus(DocumentStatus.DELETING.getCode());
        document.setErrorMessage(null);
        documentMapper.updateById(document);
        deletionService.createTask("DOCUMENT_DELETE", id);
    }

    @Override
    public PageResult<DocumentInfoDTO> listRecycleBin(DocumentQueryDTO queryDTO) {
        queryDTO.validate();
        Long currentUserId = JwtUtils.getCurrentUserId();
        String title =
                StringUtils.hasText(queryDTO.getTitle()) ? queryDTO.getTitle().trim() : null;
        long total = documentMapper.countRecycle(currentUserId, title);
        if (total == 0) {
            return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), 0, List.of());
        }

        List<Document> records = documentMapper.selectRecyclePage(
                currentUserId, title, (queryDTO.getPage() - 1) * queryDTO.getPageSize(), queryDTO.getPageSize());
        List<DocumentInfoDTO> result = records.stream()
                .map(document -> {
                    KnowledgeBase kb = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
                    return convertToInfoDTO(document, kb == null ? "已删除知识库" : kb.getName());
                })
                .collect(Collectors.toList());
        return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), total, result);
    }

    @Override
    @Transactional
    public void restore(Long id) {
        Document document = documentMapper.selectIncludingDeleted(id);
        if (document == null || document.getDeleted() == null || document.getDeleted() != 1) {
            throw new BusinessException("回收站中不存在该文档");
        }
        KnowledgeBase kb = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        assertOwnedKnowledgeBase(kb);
        if (document.getRecycleExpiresAt() != null
                && document.getRecycleExpiresAt().isBefore(LocalDateTime.now())) {
            throw new BusinessException("该文档已超过回收站保留期限");
        }
        if (documentMapper.restoreFromRecycle(id, DocumentStatus.PENDING.getCode()) != 1) {
            throw new BusinessException("恢复文档失败");
        }
    }

    @Override
    public void purge(Long id) {
        Document document = documentMapper.selectIncludingDeleted(id);
        if (document == null || document.getDeleted() == null || document.getDeleted() != 1) {
            throw new BusinessException("回收站中不存在该文档");
        }
        // A document may remain in the recycle bin after its knowledge base was deleted.
        // Permanent cleanup must still verify ownership against that logically deleted KB.
        KnowledgeBase kb = knowledgeBaseMapper.selectIncludingDeleted(document.getKnowledgeBaseId());
        assertOwnedKnowledgeBase(kb);
        deletionService.createTask("DOCUMENT_PURGE", id);
    }

    @Override
    public DocumentInfoDTO getById(Long id) {
        // 1. 查询文档
        Document document = documentMapper.selectById(id);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }

        // 2. 验证文档所属知识库属于当前用户
        KnowledgeBase kb = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        assertOwnedKnowledgeBase(kb);
        String kbName = kb.getName();

        // 3. 转换为 DTO
        return convertToInfoDTO(document, kbName);
    }

    @Override
    public String getContent(Long id) {
        Document document = documentMapper.selectById(id);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }
        assertOwnedKnowledgeBase(knowledgeBaseMapper.selectById(document.getKnowledgeBaseId()));
        return document.getContent();
    }

    @Override
    public PageResult<DocumentInfoDTO> list(DocumentQueryDTO queryDTO) {
        // A user-facing "all" list must still be scoped to that user's KBs.
        return listByCurrentUser(null, queryDTO);
    }

    @Override
    public PageResult<DocumentInfoDTO> listByKnowledgeBase(Long knowledgeBaseId, DocumentQueryDTO queryDTO) {
        // 1. 验证知识库存在
        KnowledgeBase kb = knowledgeBaseMapper.selectById(knowledgeBaseId);
        if (kb == null) {
            throw new BusinessException("知识库不存在");
        }
        assertOwnedKnowledgeBase(kb);

        // 2. 构建查询条件
        LambdaQueryWrapper<Document> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Document::getKnowledgeBaseId, knowledgeBaseId)
                .like(StringUtils.hasText(queryDTO.getTitle()), Document::getTitle, queryDTO.getTitle())
                .eq(queryDTO.getStatus() != null, Document::getStatus, queryDTO.getStatus())
                .orderByDesc(Document::getCreatedAt);

        // 3. 分页查询
        Page<Document> page = new Page<>(queryDTO.getPage(), queryDTO.getPageSize());
        Page<Document> result = documentMapper.selectPage(page, wrapper);

        if (result.getRecords().isEmpty()) {
            return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), result.getTotal(), List.of());
        }

        // 4. 批量预加载用户信息（避免N+1）
        User kbOwner = userMapper.selectById(kb.getUserId());
        String ownerUsername = kbOwner != null ? kbOwner.getUsername() : "unknown";
        Map<Long, String> usernameMap = Map.of(kb.getUserId(), ownerUsername);

        // 5. 转换为 DTO（使用预查询数据）
        String kbName = kb.getName();
        List<DocumentInfoDTO> records = result.getRecords().stream()
                .map(doc -> convertToInfoDTO(doc, kbName, kb, usernameMap))
                .collect(Collectors.toList());

        // 6. 返回分页结果
        return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), result.getTotal(), records);
    }

    @Override
    public PageResult<DocumentInfoDTO> listByCurrentUser(Long knowledgeBaseId, DocumentQueryDTO queryDTO) {
        Long currentUserId = JwtUtils.getCurrentUserId();

        // 如果 knowledgeBaseId 为 0 或 null，返回当前用户所有知识库的文档
        if (knowledgeBaseId == null || knowledgeBaseId == 0) {
            // 查询当前用户的所有知识库
            QueryWrapper<KnowledgeBase> kbQuery = new QueryWrapper<>();
            kbQuery.eq("user_id", currentUserId);
            List<KnowledgeBase> userKbs = knowledgeBaseMapper.selectList(kbQuery);

            if (userKbs.isEmpty()) {
                return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), 0, List.of());
            }

            // 查询这些知识库下的所有文档
            List<Long> kbIds = userKbs.stream().map(KnowledgeBase::getId).collect(Collectors.toList());
            QueryWrapper<Document> docQuery = new QueryWrapper<>();
            docQuery.in("knowledge_base_id", kbIds);
            if (queryDTO.getTitle() != null && !queryDTO.getTitle().isBlank()) {
                docQuery.like("title", queryDTO.getTitle());
            }
            if (queryDTO.getStatus() != null) {
                docQuery.eq("status", queryDTO.getStatus());
            }
            docQuery.orderByDesc("created_at");

            long total = documentMapper.selectCount(docQuery);
            IPage<Document> page =
                    documentMapper.selectPage(new Page<>(queryDTO.getPage(), queryDTO.getPageSize()), docQuery);

            // 构建知识库名称映射
            Map<Long, String> kbNameMap =
                    userKbs.stream().collect(Collectors.toMap(KnowledgeBase::getId, KnowledgeBase::getName));

            List<DocumentInfoDTO> records = page.getRecords().stream()
                    .map(doc -> convertToInfoDTO(doc, kbNameMap.get(doc.getKnowledgeBaseId())))
                    .collect(Collectors.toList());

            return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), total, records);
        }

        // 指定了具体知识库ID
        KnowledgeBase kb = knowledgeBaseMapper.selectById(knowledgeBaseId);
        if (kb == null) {
            throw new BusinessException("知识库不存在");
        }
        if (!kb.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权访问该知识库");
        }

        return listByKnowledgeBase(knowledgeBaseId, queryDTO);
    }

    @Override
    public DocumentNameDTO getDocumentName(Long id) {
        Document document = documentMapper.selectById(id);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }
        assertOwnedKnowledgeBase(knowledgeBaseMapper.selectById(document.getKnowledgeBaseId()));
        return DocumentNameDTO.builder()
                .id(document.getId())
                .name(document.getTitle())
                .build();
    }

    @Override
    public void parseDocument(Long id, String model) {
        // 1. 查询文档
        Document document = documentMapper.selectById(id);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }

        // 2. 验证权限
        Long currentUserId = JwtUtils.getCurrentUserId();
        KnowledgeBase kb = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        if (kb == null || !kb.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权操作该文档");
        }

        // 3. 调用向量化服务
        vectorizationService.startVectorization(id, model);
    }

    /**
     * 保存文件到临时目录，数据库提交后再原子移动到正式目录。
     * 返回临时路径；调用方在事务提交后再移动到正式目录。
     */
    private String saveFile(MultipartFile file) {
        try {
            String userDir = System.getProperty("user.dir");
            Path uploadPath = Paths.get(userDir, UPLOAD_DIR);
            Path tempPath = uploadPath.resolve("temp");
            if (!Files.exists(tempPath)) {
                Files.createDirectories(tempPath);
            }
            if (!Files.exists(uploadPath)) {
                Files.createDirectories(uploadPath);
            }

            // 生成唯一文件名
            String originalFilename = file.getOriginalFilename();
            String extension = "";
            if (originalFilename != null && originalFilename.contains(".")) {
                extension = originalFilename.substring(originalFilename.lastIndexOf("."));
            }
            String filename = UUID.randomUUID().toString() + extension;

            // 写入临时目录
            Path tempFile = tempPath.resolve(filename);
            Files.copy(file.getInputStream(), tempFile, java.nio.file.StandardCopyOption.REPLACE_EXISTING);

            log.info("文件写入临时目录: {}", tempFile);
            return tempFile.toString();
        } catch (IOException e) {
            log.error("文件保存失败", e);
            throw new BusinessException("文件保存失败");
        }
    }

    /**
     * 注册数据库事务提交后的文件提交动作。
     */
    private void registerFileCommit(Long documentId, String tempPath) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            commitFile(documentId, tempPath, true);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // M5: afterCommit 阶段 DB 已提交，抛出的异常会被 Spring 吞掉且 HTTP
                // 响应状态不确定 — 只标记文档失败并保留临时文件供人工排查/补交，不再抛出
                commitFile(documentId, tempPath, false);
            }

            @Override
            public void afterCompletion(int status) {
                if (status != STATUS_COMMITTED) {
                    deleteTempFile(tempPath);
                }
            }
        });
    }

    private void commitFile(Long documentId, String tempPath, boolean rethrow) {
        if (tempPath == null) return;
        try {
            Path tempFile = Path.of(tempPath);
            Path finalDir = tempFile.getParent().getParent(); // uploads/documents
            Path finalFile = finalDir.resolve(tempFile.getFileName());
            try {
                Files.move(
                        tempFile,
                        finalFile,
                        java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(tempFile, finalFile, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            }
            log.info("文件已提交到正式目录: {}", finalFile);
        } catch (IOException e) {
            log.error("文件提交失败: {}", tempPath, e);
            markUploadFailed(documentId, "文件提交失败");
            // 保留临时文件：此时 DB 行已失败，删除文件会造成 DB 与文件双丢失、无法对账
            if (rethrow) {
                throw new BusinessException(StatusCode.INTERNAL_ERROR, "文件提交失败");
            }
        }
    }

    private void markUploadFailed(Long documentId, String errorMessage) {
        Document failed = new Document();
        failed.setId(documentId);
        failed.setStatus(DocumentStatus.FAILED.getCode());
        failed.setErrorMessage(errorMessage);
        documentMapper.updateById(failed);
    }

    private void deleteTempFile(String tempPath) {
        if (tempPath == null) return;
        try {
            Files.deleteIfExists(Path.of(tempPath));
        } catch (IOException e) {
            log.warn("临时文件清理失败: {}", tempPath, e);
        }
    }

    private void assertOwnedKnowledgeBase(KnowledgeBase knowledgeBase) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        if (knowledgeBase == null || !knowledgeBase.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权访问该知识库");
        }
    }

    /**
     * 将临时路径转换为正式路径
     */
    private String tempToFinalPath(String tempPath) {
        if (tempPath == null) return null;
        Path tempFile = Path.of(tempPath);
        Path finalDir = tempFile.getParent().getParent(); // uploads/documents
        return finalDir.resolve(tempFile.getFileName()).toString();
    }

    /**
     * 获取文件扩展名
     */
    private String getFileExtension(String filename) {
        if (filename != null && filename.contains(".")) {
            return filename.substring(filename.lastIndexOf("."));
        }
        return "";
    }

    /**
     * Document 转换为 DocumentInfoDTO（使用预查询数据，避免 N+1）
     */
    private DocumentInfoDTO convertToInfoDTO(
            Document document, String knowledgeBaseName, KnowledgeBase kb, Map<Long, String> usernameMap) {
        String username = "unknown";
        if (kb != null) {
            username = usernameMap.getOrDefault(kb.getUserId(), "unknown");
        }

        return DocumentInfoDTO.builder()
                .id(document.getId())
                .knowledgeBaseId(document.getKnowledgeBaseId())
                .knowledgeBaseName(knowledgeBaseName)
                .title(document.getTitle())
                .fileType(document.getFileType())
                .fileSize(document.getFileSize())
                .chunkCount(document.getChunkCount())
                .status(document.getStatus())
                .statusDesc(getStatusDesc(document.getStatus()))
                .errorMessage(document.getErrorMessage())
                .username(username)
                .createdAt(document.getCreatedAt())
                .updatedAt(document.getUpdatedAt())
                .recycledAt(document.getRecycledAt())
                .recycleExpiresAt(document.getRecycleExpiresAt())
                .build();
    }

    /**
     * Document 转换为 DocumentInfoDTO（单文档版本，自动查询关联数据）
     */
    private DocumentInfoDTO convertToInfoDTO(Document document, String knowledgeBaseName) {
        KnowledgeBase kb = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        String username = "unknown";
        if (kb != null) {
            User user = userMapper.selectById(kb.getUserId());
            if (user != null) {
                username = user.getUsername();
            }
        }
        return convertToInfoDTO(document, knowledgeBaseName, kb, Map.of(kb != null ? kb.getUserId() : 0L, username));
    }

    /**
     * 获取状态描述
     */
    private String getStatusDesc(Integer status) {
        DocumentStatus docStatus = DocumentStatus.fromCode(status);
        return docStatus != null ? docStatus.getDescription() : "未知";
    }
}
