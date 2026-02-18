package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.DocumentChunkCallbackDTO;
import com.hfusionhub.dto.DocumentIndexCallbackDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.DocumentChunk;
import com.hfusionhub.entity.DocumentIndexJob;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentChunkMapper;
import com.hfusionhub.mapper.DocumentIndexJobMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.service.VectorizationService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 向量化服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class VectorizationServiceImpl implements VectorizationService {

    private final DocumentMapper documentMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final DocumentIndexJobMapper documentIndexJobMapper;
    private final DocumentChunkMapper documentChunkMapper;
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    @Value("${python-ai.engine.url:http://localhost:8001}")
    private String pythonEngineUrl;

    @Value("${python-ai.callback-base-url:http://localhost:8080/api}")
    private String callbackBaseUrl;

    @Value("${python-ai.callback-secret:}")
    private String callbackSecret;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    @Value("${rag.index.stale-after-minutes:30}")
    private long staleAfterMinutes;

    @Value("${rag.index.max-attempts:3}")
    private int maxAttempts;

    @Override
    public void startVectorization(Long documentId, String model) {
        // 1. 查询文档
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }
        assertDocumentOwnerWhenUserRequest(document);

        // 2. 检查状态 - 允许重新处理处于 PROCESSING 状态的文档（修复之前的卡住问题）
        if (document.getStatus() != null && document.getStatus() == DocumentStatus.PROCESSING.getCode()) {
            log.warn("文档 {} 处于处理中状态，允许重新处理", documentId);
        }

        // A new request supersedes any callback from an older worker.  The
        // version is sent to Python and checked again when it calls back.
        documentIndexJobMapper.update(
                null,
                new LambdaUpdateWrapper<DocumentIndexJob>()
                        .eq(DocumentIndexJob::getDocumentId, documentId)
                        .eq(DocumentIndexJob::getStatus, "PROCESSING")
                        .set(DocumentIndexJob::getStatus, "SUPERSEDED")
                        .set(DocumentIndexJob::getCompletedAt, LocalDateTime.now())
        );
        DocumentIndexJob job = new DocumentIndexJob();
        job.setDocumentId(documentId);
        job.setKnowledgeBaseId(document.getKnowledgeBaseId());
        job.setIndexVersion(UUID.randomUUID().toString());
        job.setEmbeddingModel(model != null ? model : "ollama");
        job.setStatus("PROCESSING");
        job.setAttempt(documentIndexJobMapper.countByDocumentId(documentId) + 1);
        job.setChunkCount(0);
        job.setStartedAt(LocalDateTime.now());
        documentIndexJobMapper.insert(job);

        // 3. 更新状态为处理中
        document.setStatus(DocumentStatus.PROCESSING.getCode());
        document.setErrorMessage(null);
        documentMapper.updateById(document);

        // 4. 异步调用Python引擎进行处理
        try {
            callPythonEngine(document, job);
        } catch (Exception e) {
            log.error("调用Python引擎失败", e);
            document.setStatus(DocumentStatus.FAILED.getCode());
            document.setErrorMessage("调用AI引擎失败: " + e.getMessage());
            documentMapper.updateById(document);
            job.setStatus("FAILED");
            job.setErrorMessage(truncate(e.getMessage(), 1000));
            job.setCompletedAt(LocalDateTime.now());
            documentIndexJobMapper.updateById(job);
            throw new BusinessException("启动向量化失败: " + e.getMessage());
        }
    }

    @Override
    public String getDocumentChunks(Long documentId, Integer page, Integer size, String blockType) {
        try {
            assertDocumentOwnerWhenUserRequest(requireDocument(documentId));
            int safePage = page == null || page < 1 ? 1 : page;
            int safeSize = size == null || size < 1 ? 20 : Math.min(size, 100);
            long persistedCount = documentChunkMapper.countByDocumentId(documentId, blockType);
            if (persistedCount > 0) {
                List<DocumentChunk> chunks = documentChunkMapper.selectPageByDocumentId(
                        documentId, (safePage - 1) * safeSize, safeSize, blockType);
                Map<String, Object> response = new HashMap<>();
                response.put("success", true);
                response.put("document_id", String.valueOf(documentId));
                response.put("total_chunks", persistedCount);
                response.put("chunks", chunks.stream().map(this::toChunkResponse).toList());
                return objectMapper.writeValueAsString(response);
            }

            // Legacy documents created before V2 have no durable metadata yet.
            // Keep the old Python route as a temporary read fallback until they
            // are re-indexed.
            String url = pythonEngineUrl + "/api/chunks/" + documentId
                    + "?page=" + safePage
                    + "&size=" + safeSize;

            if (blockType != null && !blockType.isEmpty()) {
                url += "&block_type=" + blockType;
            }

            ResponseEntity<String> response = restTemplate.exchange(
                    url, HttpMethod.GET, new HttpEntity<>(internalHeaders()), String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("获取分块列表失败", e);
            return "{\"code\":500,\"error\":\"获取分块列表失败\"}";
        }
    }

    @Override
    public String getChunkDetail(String chunkId) {
        try {
            DocumentChunk persistedChunk = documentChunkMapper.selectById(chunkId);
            if (persistedChunk != null) {
                assertDocumentOwnerWhenUserRequest(requireDocument(persistedChunk.getDocumentId()));
                return objectMapper.writeValueAsString(toChunkResponse(persistedChunk));
            }
            throw new BusinessException("分块不存在；请重新索引旧文档后重试");
        } catch (Exception e) {
            log.error("获取分块详情失败", e);
            return "{\"code\":500,\"error\":\"获取分块详情失败\"}";
        }
    }

    @Override
    @Transactional
    public void updateDocumentStatus(Long documentId, DocumentIndexCallbackDTO callback) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            log.warn("文档不存在: {}", documentId);
            return;
        }

        DocumentIndexJob currentJob = documentIndexJobMapper.selectLatestByDocumentId(documentId);
        if (currentJob == null) {
            log.warn("忽略没有任务记录的索引回调: documentId={}", documentId);
            return;
        }
        if (callback.getIndexVersion() == null || !callback.getIndexVersion().equals(currentJob.getIndexVersion())) {
            log.warn("忽略过期索引回调: documentId={}, callbackVersion={}, currentVersion={}",
                    documentId, callback.getIndexVersion(), currentJob.getIndexVersion());
            return;
        }
        if (!"PROCESSING".equals(currentJob.getStatus())) {
            log.info("忽略已结束任务的重复索引回调: documentId={}, status={}", documentId, currentJob.getStatus());
            return;
        }

        DocumentStatus docStatus;
        try {
            docStatus = DocumentStatus.valueOf(callback.getStatus());
        } catch (Exception e) {
            throw new BusinessException("无效的索引回调状态: " + callback.getStatus());
        }
        int chunkCount = callback.getChunkCount() == null ? 0 : callback.getChunkCount();
        if (docStatus == DocumentStatus.COMPLETED
                && (callback.getChunks() == null || callback.getChunks().size() != chunkCount)) {
            throw new BusinessException("索引完成回调缺少完整的分块元数据");
        }

        document.setStatus(docStatus.getCode());
        document.setChunkCount(chunkCount);

        if (docStatus == DocumentStatus.COMPLETED) {
            document.setProcessedAt(LocalDateTime.now());
            document.setErrorMessage(null);
            // Replace metadata only after the worker has completed.  This is a
            // single database transaction, so citations never observe a mix of
            // an old and a new index version.
            documentChunkMapper.deleteByDocumentId(documentId);
            for (DocumentChunkCallbackDTO callbackChunk : callback.getChunks()) {
                documentChunkMapper.insert(toDocumentChunk(document, currentJob, callbackChunk));
            }
        } else if (docStatus == DocumentStatus.FAILED) {
            document.setErrorMessage(truncate(callback.getMessage(), 500));
        }

        documentMapper.updateById(document);
        currentJob.setStatus(docStatus.name());
        currentJob.setChunkCount(chunkCount);
        currentJob.setErrorMessage(docStatus == DocumentStatus.FAILED ? truncate(callback.getMessage(), 1000) : null);
        currentJob.setCompletedAt(LocalDateTime.now());
        documentIndexJobMapper.updateById(currentJob);
        log.info("文档状态已更新: {} -> {}", documentId, docStatus);
    }

    @Override
    @Transactional
    public void deleteDocumentIndex(Long documentId) {
        try {
            ResponseEntity<String> response = restTemplate.exchange(
                    pythonEngineUrl + "/api/documents/" + documentId + "/chunks",
                    HttpMethod.DELETE,
                    new HttpEntity<>(internalHeaders()),
                    String.class);
            if (!response.getStatusCode().is2xxSuccessful()) {
                throw new BusinessException("向量索引删除失败");
            }
        } catch (BusinessException e) {
            throw e;
        } catch (Exception e) {
            throw new BusinessException("无法删除向量索引: " + e.getMessage());
        }
        documentChunkMapper.deleteByDocumentId(documentId);
        documentIndexJobMapper.delete(new LambdaQueryWrapper<DocumentIndexJob>()
                .eq(DocumentIndexJob::getDocumentId, documentId));
    }

    @Override
    public int recoverStaleIndexJobs() {
        LocalDateTime staleBefore = LocalDateTime.now().minusMinutes(staleAfterMinutes);
        for (DocumentIndexJob exhaustedJob : documentIndexJobMapper.selectExhaustedProcessingJobs(staleBefore, maxAttempts)) {
            exhaustedJob.setStatus("FAILED");
            exhaustedJob.setErrorMessage("索引任务超过最大重试次数");
            exhaustedJob.setCompletedAt(LocalDateTime.now());
            documentIndexJobMapper.updateById(exhaustedJob);

            Document document = documentMapper.selectById(exhaustedJob.getDocumentId());
            if (document != null) {
                document.setStatus(DocumentStatus.FAILED.getCode());
                document.setErrorMessage("索引任务超过最大重试次数");
                documentMapper.updateById(document);
            }
        }

        List<DocumentIndexJob> staleJobs = documentIndexJobMapper.selectStaleProcessingJobs(staleBefore, maxAttempts);
        int recovered = 0;
        for (DocumentIndexJob staleJob : staleJobs) {
            try {
                log.warn("恢复超时索引任务: documentId={}, version={}, attempt={}", staleJob.getDocumentId(),
                        staleJob.getIndexVersion(), staleJob.getAttempt());
                startVectorization(staleJob.getDocumentId(), staleJob.getEmbeddingModel());
                recovered++;
            } catch (Exception e) {
                log.error("恢复索引任务失败: documentId={}", staleJob.getDocumentId(), e);
            }
        }
        return recovered;
    }

    @Override
    public void syncDocumentStatus(Long documentId) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }
        assertDocumentOwnerWhenUserRequest(document);
        DocumentIndexJob job = documentIndexJobMapper.selectLatestByDocumentId(documentId);
        if (job == null) {
            throw new BusinessException("文档没有持久化索引任务");
        }
        if ("SUPERSEDED".equals(job.getStatus())) {
            return;
        }
        try {
            DocumentStatus status = DocumentStatus.valueOf(job.getStatus());
            document.setStatus(status.getCode());
            document.setChunkCount(job.getChunkCount());
            if (status == DocumentStatus.COMPLETED && job.getCompletedAt() != null) {
                document.setProcessedAt(job.getCompletedAt());
            }
            if (status == DocumentStatus.FAILED) {
                document.setErrorMessage(job.getErrorMessage());
            }
            documentMapper.updateById(document);
        } catch (IllegalArgumentException e) {
            throw new BusinessException("无效的持久化索引任务状态: " + job.getStatus());
        }
    }

    @Override
    public int syncAllDocuments() {
        // 查询所有待处理或处理中的文档
        LambdaQueryWrapper<Document> wrapper = new LambdaQueryWrapper<>();
        wrapper.in(Document::getStatus,
                DocumentStatus.PENDING.getCode(),
                DocumentStatus.PROCESSING.getCode());
        List<Document> pendingDocs = documentMapper.selectList(wrapper);

        int updated = 0;
        for (Document doc : pendingDocs) {
            try {
                syncDocumentStatus(doc.getId());
                updated++;
            } catch (Exception e) {
                log.warn("同步文档状态失败: {}", doc.getId(), e);
            }
        }
        return updated;
    }

    @Override
    public void resetDocument(Long documentId) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }
        assertDocumentOwnerWhenUserRequest(document);

        // 只有处理中或失败的状态才允许重置
        if (document.getStatus() != null
                && document.getStatus() != DocumentStatus.PROCESSING.getCode()
                && document.getStatus() != DocumentStatus.FAILED.getCode()) {
            throw new BusinessException("当前状态不允许重置");
        }

        document.setStatus(DocumentStatus.PENDING.getCode());
        document.setErrorMessage(null);
        documentMapper.updateById(document);
        log.info("文档状态已重置为待解析: {}", documentId);
    }

    @Override
    public String getTaskStatus(Long documentId) {
        try {
            assertDocumentOwnerWhenUserRequest(requireDocument(documentId));
            String url = pythonEngineUrl + "/api/task-status/" + documentId;
            ResponseEntity<String> response = restTemplate.exchange(
                    url, HttpMethod.GET, new HttpEntity<>(internalHeaders()), String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("获取任务状态失败: {}", documentId, e);
            return "{\"status\":\"ERROR\",\"message\":\"任务状态暂不可用\"}";
        }
    }

    /**
     * 调用Python引擎
     */
    private void callPythonEngine(Document document, DocumentIndexJob job) {
        if (callbackSecret == null || callbackSecret.isBlank()) {
            throw new BusinessException("CALLBACK_SECRET 未配置");
        }
        String url = pythonEngineUrl + "/api/parse";

        // 构建回调URL，用于Python引擎处理完成后通知Java后端
        String callbackUrl = callbackBaseUrl + "/vectorize/" + document.getId() + "/callback";

        Map<String, Object> request = Map.of(
                "document_id", String.valueOf(document.getId()),
                "file_path", document.getFilePath(),
                "file_type", document.getFileType() != null ? document.getFileType() : "md",
                "knowledge_base_id", document.getKnowledgeBaseId() != null ? document.getKnowledgeBaseId() : 0,
                "document_title", document.getTitle(),
                "index_version", job.getIndexVersion(),
                "callback_url", callbackUrl,
                "callback_secret", callbackSecret,
                "embedding_model", job.getEmbeddingModel()
        );

        HttpHeaders headers = internalHeaders();

        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, headers);

        log.info("调用Python引擎: {}, 回调URL: {}, 模型: {}, 索引版本: {}", url, callbackUrl,
                job.getEmbeddingModel(), job.getIndexVersion());
        ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.POST, entity, String.class);
        log.info("Python引擎响应: {}", response.getBody());
    }

    private DocumentChunk toDocumentChunk(Document document, DocumentIndexJob job,
                                          DocumentChunkCallbackDTO callbackChunk) {
        if (callbackChunk.getChunkId() == null || callbackChunk.getChunkId().isBlank()) {
            throw new BusinessException("索引回调包含空 chunkId");
        }
        DocumentChunk chunk = new DocumentChunk();
        chunk.setChunkId(callbackChunk.getChunkId());
        chunk.setDocumentId(document.getId());
        chunk.setKnowledgeBaseId(document.getKnowledgeBaseId());
        chunk.setIndexVersion(job.getIndexVersion());
        chunk.setChunkIndex(callbackChunk.getIndex());
        chunk.setBlockType(callbackChunk.getBlockType());
        chunk.setOutlinePath(toJson(callbackChunk.getOutlinePath()));
        chunk.setContentExcerpt(truncate(callbackChunk.getContentExcerpt(), 1000));
        chunk.setCharCount(callbackChunk.getCharCount());
        chunk.setMetadata(toJson(callbackChunk.getMetadata()));
        return chunk;
    }

    private HttpHeaders internalHeaders() {
        if (internalApiToken == null || internalApiToken.isBlank()) {
            throw new BusinessException("PYTHON_AI_INTERNAL_TOKEN 未配置");
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Internal-Token", internalApiToken);
        return headers;
    }

    private Document requireDocument(Long documentId) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }
        return document;
    }

    private void assertDocumentOwnerWhenUserRequest(Document document) {
        // Recovery jobs and authenticated worker callbacks execute without a
        // user session.  Every browser path is protected by Sa-Token and is
        // therefore additionally checked against the document's KB owner.
        if (!JwtUtils.isLogin()) {
            return;
        }
        var knowledgeBase = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        if (knowledgeBase == null || !JwtUtils.getCurrentUserId().equals(knowledgeBase.getUserId())) {
            throw new BusinessException("无权访问该文档");
        }
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value == null ? Collections.emptyMap() : value);
        } catch (JsonProcessingException e) {
            throw new BusinessException("无法保存分块元数据");
        }
    }

    private Map<String, Object> toChunkResponse(DocumentChunk chunk) {
        Map<String, Object> response = new HashMap<>();
        response.put("chunk_id", chunk.getChunkId());
        response.put("index", chunk.getChunkIndex());
        response.put("content", chunk.getContentExcerpt());
        response.put("block_type", chunk.getBlockType());
        response.put("outline_path", fromJson(chunk.getOutlinePath()));
        response.put("metadata", fromJson(chunk.getMetadata()));
        return response;
    }

    private Object fromJson(String value) {
        if (value == null || value.isBlank()) {
            return Collections.emptyMap();
        }
        try {
            return objectMapper.readValue(value, Object.class);
        } catch (JsonProcessingException e) {
            return Collections.emptyMap();
        }
    }

    private String truncate(String value, int maxLength) {
        if (value == null) {
            return null;
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }
}
