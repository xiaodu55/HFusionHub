package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.ChunkDTO;
import com.hfusionhub.dto.ChunkPageDTO;
import com.hfusionhub.dto.DocumentChunkCallbackDTO;
import com.hfusionhub.dto.DocumentIndexCallbackDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.DocumentChunk;
import com.hfusionhub.entity.DocumentIndexJob;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.User;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentChunkMapper;
import com.hfusionhub.mapper.DocumentIndexJobMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.service.VectorizationService;
import com.hfusionhub.tenant.TenantContext;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;

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
    private final UserMapper userMapper;
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;
    private final UsageLedgerService usageLedgerService;

    @Value("${python-ai.engine.url:http://localhost:9000}")
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

    @Value("${hfusionhub.quota.index.bytes-per-chunk-estimate:300}")
    private long bytesPerChunkEstimate;

    @Override
    public void startVectorization(Long documentId, String model) {
        startVectorizationInternal(documentId, model, true);
    }

    private void startVectorizationInternal(Long documentId, String model, boolean enforceRequestOwner) {
        // 1. 查询文档
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }
        if (enforceRequestOwner) {
            assertDocumentOwnerWhenUserRequest(document);
        }
        KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        if (knowledgeBase == null
                || knowledgeBase.getStatus() == null
                || knowledgeBase.getStatus() != CommonConstants.KB_STATUS_NORMAL) {
            throw new BusinessException("知识库已禁用，无法解析文档");
        }

        // 2. 检查状态 - 允许重新处理处于 PROCESSING 状态的文档（修复之前的卡住问题）
        if (document.getStatus() != null && document.getStatus() == DocumentStatus.PROCESSING.getCode()) {
            log.warn("文档 {} 处于处理中状态，允许重新处理", documentId);
        }

        ensureSourceFileAvailable(document);

        // A new request supersedes any callback from an older worker.  The
        // version is sent to Python and checked again when it calls back.
        List<DocumentIndexJob> supersededJobs =
                documentIndexJobMapper.selectList(new LambdaQueryWrapper<DocumentIndexJob>()
                        .eq(DocumentIndexJob::getDocumentId, documentId)
                        .eq(DocumentIndexJob::getStatus, "PROCESSING"));
        documentIndexJobMapper.update(
                null,
                new LambdaUpdateWrapper<DocumentIndexJob>()
                        .eq(DocumentIndexJob::getDocumentId, documentId)
                        .eq(DocumentIndexJob::getStatus, "PROCESSING")
                        .set(DocumentIndexJob::getStatus, "SUPERSEDED")
                        .set(DocumentIndexJob::getCompletedAt, LocalDateTime.now()));
        // 退回被取代的索引任务预占
        for (DocumentIndexJob superseded : supersededJobs) {
            releaseIndexChunks(document, superseded);
        }
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

        // 用量账本：按文件大小估算分块数上界预占（幂等键为 index_chunks:<indexVersion>）。
        // 回调按实际 chunk 数结算；失败/超时/被取代时退回。恢复路径在 runAsSystem 中执行，
        // 无租户上下文，需按文档归属解析租户后预占。
        try {
            reserveIndexChunks(document, job);
        } catch (BusinessException e) {
            log.warn("索引配额预占失败: documentId={} version={}", documentId, job.getIndexVersion(), e);
            document.setStatus(DocumentStatus.FAILED.getCode());
            document.setErrorMessage(e.getMessage());
            documentMapper.updateById(document);
            job.setStatus("FAILED");
            job.setErrorMessage(truncate(e.getMessage(), 1000));
            job.setCompletedAt(LocalDateTime.now());
            documentIndexJobMapper.updateById(job);
            throw e;
        }

        // 3. 更新状态为处理中
        document.setStatus(DocumentStatus.PROCESSING.getCode());
        document.setErrorMessage(null);
        documentMapper.updateById(document);

        // 4. 异步调用Python引擎进行处理
        try {
            callPythonEngine(document, job);
        } catch (Exception e) {
            String failureMessage = describeEngineStartFailure(e);
            log.error("调用Python引擎失败", e);
            releaseIndexChunks(document, job);
            document.setStatus(DocumentStatus.FAILED.getCode());
            document.setErrorMessage(failureMessage);
            documentMapper.updateById(document);
            job.setStatus("FAILED");
            job.setErrorMessage(truncate(failureMessage, 1000));
            job.setCompletedAt(LocalDateTime.now());
            documentIndexJobMapper.updateById(job);
            throw new BusinessException(failureMessage);
        }
    }

    @Override
    public ChunkPageDTO getDocumentChunks(Long documentId, Integer page, Integer size, String blockType) {
        assertDocumentOwnerWhenUserRequest(requireDocument(documentId));
        int safePage = page == null || page < 1 ? 1 : page;
        int safeSize = size == null || size < 1 ? 20 : Math.min(size, 100);

        // Prefer durable metadata over legacy Python fallback
        long persistedCount = documentChunkMapper.countByDocumentId(documentId, blockType);
        if (persistedCount > 0) {
            List<DocumentChunk> chunks = documentChunkMapper.selectPageByDocumentId(
                    documentId, (safePage - 1) * safeSize, safeSize, blockType);
            return ChunkPageDTO.builder()
                    .documentId(documentId)
                    .totalChunks(persistedCount)
                    .chunks(chunks.stream().map(this::toChunkDTO).toList())
                    .build();
        }

        // Legacy documents created before V2 have no durable metadata yet.
        // Keep the old Python route as a temporary read fallback until they
        // are re-indexed.
        String url = pythonEngineUrl + "/api/chunks/" + documentId + "?page=" + safePage + "&size=" + safeSize;

        if (blockType != null && !blockType.isEmpty()) {
            url += "&block_type=" + blockType;
        }

        try {
            ResponseEntity<String> response =
                    restTemplate.exchange(url, HttpMethod.GET, new HttpEntity<>(internalHeaders()), String.class);
            @SuppressWarnings("unchecked")
            Map<String, Object> legacy = objectMapper.readValue(response.getBody(), Map.class);
            return legacyChunkPageFromPython(legacy, documentId);
        } catch (Exception e) {
            log.error("获取分块列表失败: documentId={}", documentId, e);
            throw new BusinessException("获取分块列表失败");
        }
    }

    @Override
    public ChunkDTO getChunkDetail(String chunkId) {
        // 显式 SQL，不依赖 MyBatis Plus 隐式映射
        DocumentChunk persistedChunk = documentChunkMapper.selectByChunkId(chunkId);
        if (persistedChunk == null) {
            throw new BusinessException(StatusCode.CHUNK_NOT_FOUND, "分块不存在");
        }
        assertDocumentOwnerWhenUserRequest(requireDocument(persistedChunk.getDocumentId()));
        return toChunkDTO(persistedChunk);
    }

    @Override
    @Transactional
    public void updateDocumentStatus(Long documentId, DocumentIndexCallbackDTO callback) {
        // Signed callbacks intentionally do not need a client-supplied tenant
        // header. Bootstrap the tenant from durable document ownership under a
        // narrowly scoped system lookup, then run all callback writes inside
        // that tenant boundary.
        Long tenantId = resolveDocumentTenantById(documentId);
        if (tenantId == null) {
            log.warn("Cannot resolve tenant for document callback: documentId={}", documentId);
            return;
        }
        TenantContext.runAs(tenantId, () -> {
            updateDocumentStatusInTenant(documentId, callback);
            return null;
        });
    }

    private void updateDocumentStatusInTenant(Long documentId, DocumentIndexCallbackDTO callback) {
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
            log.warn(
                    "忽略过期索引回调: documentId={}, callbackVersion={}, currentVersion={}",
                    documentId,
                    callback.getIndexVersion(),
                    currentJob.getIndexVersion());
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
        // 用量账本：完成按实际分块数结算，失败退回预占。
        // 回调线程无登录上下文，按文档归属租户解析后结算/退回。
        if (docStatus == DocumentStatus.COMPLETED) {
            settleIndexChunks(document, currentJob, chunkCount);
        } else if (docStatus == DocumentStatus.FAILED) {
            releaseIndexChunks(document, currentJob);
        }
        log.info("文档状态已更新: {} -> {}", documentId, docStatus);
    }

    @Override
    @Transactional(noRollbackFor = BusinessException.class)
    public void deleteDocumentIndex(Long documentId) {
        try {
            HttpHeaders headers = internalHeaders();
            Long tenantId = resolveDeletedDocumentTenantById(documentId);
            if (tenantId != null) {
                headers.set("X-Tenant-Id", String.valueOf(tenantId));
            }
            ResponseEntity<String> response = restTemplate.exchange(
                    pythonEngineUrl + "/api/documents/" + documentId + "/chunks",
                    HttpMethod.DELETE,
                    new HttpEntity<>(headers),
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
        documentIndexJobMapper.delete(
                new LambdaQueryWrapper<DocumentIndexJob>().eq(DocumentIndexJob::getDocumentId, documentId));
    }

    @Override
    public int recoverStaleIndexJobs() {
        LocalDateTime staleBefore = LocalDateTime.now().minusMinutes(staleAfterMinutes);
        for (DocumentIndexJob exhaustedJob :
                documentIndexJobMapper.selectExhaustedProcessingJobs(staleBefore, maxAttempts)) {
            exhaustedJob.setStatus("FAILED");
            exhaustedJob.setErrorMessage("索引任务超过最大重试次数");
            exhaustedJob.setCompletedAt(LocalDateTime.now());
            documentIndexJobMapper.updateById(exhaustedJob);

            Document document = documentMapper.selectById(exhaustedJob.getDocumentId());
            if (document != null) {
                document.setStatus(DocumentStatus.FAILED.getCode());
                document.setErrorMessage("索引任务超过最大重试次数");
                documentMapper.updateById(document);
                // 用量账本：重试耗尽，退回预占
                releaseIndexChunks(document, exhaustedJob);
            }
        }

        List<DocumentIndexJob> staleJobs = documentIndexJobMapper.selectStaleProcessingJobs(staleBefore, maxAttempts);
        int recovered = 0;
        for (DocumentIndexJob staleJob : staleJobs) {
            try {
                log.warn(
                        "恢复超时索引任务: documentId={}, version={}, attempt={}",
                        staleJob.getDocumentId(),
                        staleJob.getIndexVersion(),
                        staleJob.getAttempt());
                startVectorizationInternal(staleJob.getDocumentId(), staleJob.getEmbeddingModel(), false);
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
            int chunkCount = job.getChunkCount() == null ? 0 : job.getChunkCount();
            long persistedChunkCount = documentChunkMapper.countByDocumentId(documentId, null);
            if (status == DocumentStatus.COMPLETED
                    && (chunkCount <= 0 || persistedChunkCount <= 0 || persistedChunkCount < chunkCount)) {
                document.setStatus(DocumentStatus.PENDING.getCode());
                document.setChunkCount(0);
                document.setProcessedAt(null);
                document.setErrorMessage(
                        "\u7d22\u5f15\u4efb\u52a1\u66fe\u5b8c\u6210\uff0c\u4f46\u5206\u5757\u6570\u636e\u7f3a\u5931\uff0c\u8bf7\u91cd\u65b0\u5206\u5757");
                documentMapper.updateById(document);
                return;
            }
            document.setStatus(status.getCode());
            document.setChunkCount(chunkCount);
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
        // 要求登录
        if (!JwtUtils.isLogin()) {
            throw new BusinessException("未登录");
        }
        Long currentUserId = JwtUtils.getCurrentUserId();

        // 查询当前用户所有知识库
        LambdaQueryWrapper<KnowledgeBase> kbWrapper = new LambdaQueryWrapper<>();
        kbWrapper.eq(KnowledgeBase::getUserId, currentUserId);
        List<KnowledgeBase> userKbs = knowledgeBaseMapper.selectList(kbWrapper);

        if (userKbs.isEmpty()) {
            return 0;
        }

        List<Long> kbIds = userKbs.stream().map(KnowledgeBase::getId).collect(java.util.stream.Collectors.toList());

        // 仅查询当前用户知识库下待处理或处理中的文档
        LambdaQueryWrapper<Document> wrapper = new LambdaQueryWrapper<>();
        wrapper.in(Document::getKnowledgeBaseId, kbIds)
                .in(Document::getStatus, DocumentStatus.PENDING.getCode(), DocumentStatus.PROCESSING.getCode());
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
            Document document = requireDocument(documentId);
            assertDocumentOwnerWhenUserRequest(document);

            // The Python worker's in-memory task store disappears whenever it
            // restarts.  The UI must instead poll the durable job created by
            // startVectorization(), otherwise an already-running index task
            // is incorrectly displayed as NOT_FOUND or ERROR.
            DocumentIndexJob job = documentIndexJobMapper.selectLatestByDocumentId(documentId);
            Map<String, Object> response = new HashMap<>();
            String status = job == null ? statusName(document.getStatus()) : job.getStatus();
            int chunksCount = job == null
                    ? (document.getChunkCount() == null ? 0 : document.getChunkCount())
                    : (job.getChunkCount() == null ? 0 : job.getChunkCount());
            long persistedChunkCount = documentChunkMapper.countByDocumentId(documentId, null);
            boolean completedButMissingChunks = "COMPLETED".equals(status)
                    && (chunksCount <= 0 || persistedChunkCount <= 0 || persistedChunkCount < chunksCount);
            if (completedButMissingChunks) {
                status = "PENDING";
            }
            response.put("document_id", String.valueOf(documentId));
            response.put("status", status);
            response.put(
                    "message",
                    job == null ? "文档尚未开始索引" : (job.getErrorMessage() == null ? "索引任务状态已同步" : job.getErrorMessage()));
            response.put(
                    "chunks_count",
                    job == null
                            ? (document.getChunkCount() == null ? 0 : document.getChunkCount())
                            : job.getChunkCount());
            response.put("index_version", job == null ? null : job.getIndexVersion());
            if (completedButMissingChunks) {
                response.put(
                        "message",
                        "\u7d22\u5f15\u4efb\u52a1\u66fe\u5b8c\u6210\uff0c\u4f46\u5206\u5757\u6570\u636e\u7f3a\u5931\uff0c\u8bf7\u91cd\u65b0\u5206\u5757");
                response.put("chunks_count", 0);
            }
            enrichWithEstimatedProgress(response, document, job, status);
            if (!completedButMissingChunks) {
                mergePythonTaskStatus(response, documentId, job);
            }
            return objectMapper.writeValueAsString(response);
        } catch (Exception e) {
            log.error("获取任务状态失败: {}", documentId, e);
            return "{\"status\":\"ERROR\",\"message\":\"任务状态暂不可用\"}";
        }
    }

    private String statusName(Integer statusCode) {
        DocumentStatus status = DocumentStatus.fromCode(statusCode);
        return status == null ? "PENDING" : status.name();
    }

    private void enrichWithEstimatedProgress(
            Map<String, Object> response, Document document, DocumentIndexJob job, String status) {
        int initialEstimatedSeconds = estimateProcessingSeconds(document);
        int elapsedSeconds = elapsedSeconds(job);
        int progress = estimateProgress(status, elapsedSeconds, initialEstimatedSeconds);
        int estimatedSeconds = dynamicEstimatedSeconds(status, elapsedSeconds, progress, initialEstimatedSeconds);
        int remainingSeconds = isTerminalStatus(status) ? 0 : Math.max(1, estimatedSeconds - elapsedSeconds);

        response.put("stage", stageForStatus(status, progress));
        response.put("progress", progress);
        response.put("elapsed_seconds", elapsedSeconds);
        response.put("estimated_seconds", estimatedSeconds);
        response.put("initial_estimated_seconds", initialEstimatedSeconds);
        response.put("remaining_seconds", remainingSeconds);
    }

    private void mergePythonTaskStatus(Map<String, Object> response, Long documentId, DocumentIndexJob job) {
        if (job == null
                || !"PROCESSING".equals(job.getStatus())
                || internalApiToken == null
                || internalApiToken.isBlank()) {
            return;
        }
        try {
            ResponseEntity<String> pythonResponse = restTemplate.exchange(
                    pythonEngineUrl + "/api/task-status/" + documentId,
                    HttpMethod.GET,
                    new HttpEntity<>(internalHeaders()),
                    String.class);
            if (!pythonResponse.getStatusCode().is2xxSuccessful() || pythonResponse.getBody() == null) {
                return;
            }
            Map<String, Object> pythonStatus = objectMapper.readValue(pythonResponse.getBody(), Map.class);
            Object pythonIndexVersion = pythonStatus.get("index_version");
            if (pythonIndexVersion != null && !job.getIndexVersion().equals(String.valueOf(pythonIndexVersion))) {
                return;
            }
            if ("NOT_FOUND".equals(pythonStatus.get("status"))) {
                return;
            }
            copyIfPresent(response, pythonStatus, "stage");
            copyIfPresent(response, pythonStatus, "progress");
            copyIfPresent(response, pythonStatus, "elapsed_seconds");
            copyIfPresent(response, pythonStatus, "estimated_seconds");
            copyIfPresent(response, pythonStatus, "remaining_seconds");
            copyIfPresent(response, pythonStatus, "processed_chunks");
            copyIfPresent(response, pythonStatus, "total_chunks");
            copyIfPresent(response, pythonStatus, "chunk_quality");
            copyIfPresent(response, pythonStatus, "multimodal");
            Object message = pythonStatus.get("message");
            if (message != null && !String.valueOf(message).isBlank()) {
                response.put("message", message);
            }
        } catch (Exception e) {
            log.debug("Python task status unavailable for document {}: {}", documentId, e.getMessage());
        }
    }

    private void copyIfPresent(Map<String, Object> target, Map<String, Object> source, String key) {
        if (source.containsKey(key) && source.get(key) != null) {
            target.put(key, source.get(key));
        }
    }

    private int estimateProcessingSeconds(Document document) {
        long fileSize = document.getFileSize() == null ? 1024 * 1024 : document.getFileSize();
        long sizeMb = Math.max(1, (long) Math.ceil(fileSize / (1024.0 * 1024.0)));
        String fileType =
                document.getFileType() == null ? "" : document.getFileType().toLowerCase();
        int base =
                switch (fileType) {
                    case "pdf", ".pdf" -> 45;
                    case "docx", ".docx" -> 35;
                    case "txt", ".txt", "md", ".md" -> 15;
                    default -> 30;
                };
        long estimate = base + sizeMb * 25;
        return (int) Math.max(15, Math.min(900, estimate));
    }

    private int elapsedSeconds(DocumentIndexJob job) {
        if (job == null || job.getStartedAt() == null) {
            return 0;
        }
        LocalDateTime end = job.getCompletedAt() == null ? LocalDateTime.now() : job.getCompletedAt();
        return (int) Math.max(0, Duration.between(job.getStartedAt(), end).toSeconds());
    }

    private int estimateProgress(String status, int elapsedSeconds, int estimatedSeconds) {
        if ("COMPLETED".equals(status)) {
            return 100;
        }
        if ("FAILED".equals(status) || "ERROR".equals(status)) {
            return 100;
        }
        if (!"PROCESSING".equals(status)) {
            return 0;
        }
        if (estimatedSeconds <= 0) {
            return 10;
        }
        int progress = 5 + (int) Math.floor((elapsedSeconds / (double) estimatedSeconds) * 80);
        return Math.max(5, Math.min(90, progress));
    }

    private int dynamicEstimatedSeconds(String status, int elapsedSeconds, int progress, int initialEstimatedSeconds) {
        if (isTerminalStatus(status) || progress <= 5 || elapsedSeconds < 1) {
            return initialEstimatedSeconds;
        }

        double observedTotal = elapsedSeconds * 100.0 / Math.min(progress, 99);
        double dynamicTotal = Math.max(initialEstimatedSeconds * 0.75, observedTotal);
        return (int) Math.max(15, Math.min(900, Math.round(dynamicTotal)));
    }

    private String stageForStatus(String status, int progress) {
        if ("COMPLETED".equals(status)) {
            return "completed";
        }
        if ("FAILED".equals(status) || "ERROR".equals(status)) {
            return "failed";
        }
        if (!"PROCESSING".equals(status)) {
            return "queued";
        }
        if (progress < 25) {
            return "parsing";
        }
        if (progress < 40) {
            return "chunking";
        }
        if (progress < 90) {
            return "embedding";
        }
        return "storing";
    }

    private boolean isTerminalStatus(String status) {
        return "COMPLETED".equals(status) || "FAILED".equals(status) || "ERROR".equals(status);
    }

    private void ensureSourceFileAvailable(Document document) {
        String filePath = document.getFilePath();
        if (filePath == null || filePath.isBlank()) {
            failDocumentBeforeStart(
                    document,
                    "\u6587\u6863\u6e90\u6587\u4ef6\u8def\u5f84\u4e3a\u7a7a\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20\u540e\u518d\u89e3\u6790");
        }
        try {
            Path path = Path.of(filePath);
            if (!Files.isRegularFile(path)) {
                failDocumentBeforeStart(
                        document,
                        "\u6587\u6863\u6e90\u6587\u4ef6\u4e0d\u5b58\u5728\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20\u540e\u518d\u89e3\u6790");
            }
            if (!Files.isReadable(path)) {
                failDocumentBeforeStart(
                        document,
                        "\u6587\u6863\u6e90\u6587\u4ef6\u4e0d\u53ef\u8bfb\uff0c\u8bf7\u68c0\u67e5\u6743\u9650\u6216\u91cd\u65b0\u4e0a\u4f20");
            }
        } catch (InvalidPathException e) {
            failDocumentBeforeStart(
                    document,
                    "\u6587\u6863\u6e90\u6587\u4ef6\u8def\u5f84\u65e0\u6548\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20\u540e\u518d\u89e3\u6790");
        }
    }

    private void failDocumentBeforeStart(Document document, String message) {
        document.setStatus(DocumentStatus.FAILED.getCode());
        document.setChunkCount(0);
        document.setErrorMessage(message);
        documentMapper.updateById(document);
        throw new BusinessException(message);
    }

    private String describeEngineStartFailure(Exception e) {
        if (e instanceof BusinessException) {
            return e.getMessage();
        }
        if (e instanceof RestClientResponseException restError) {
            String responseBody = restError.getResponseBodyAsString();
            String extracted = extractErrorMessage(responseBody);
            if (extracted != null && !extracted.isBlank()) {
                return "\u542f\u52a8\u5411\u91cf\u5316\u5931\u8d25\uff1a" + extracted;
            }
        }
        String fallback = e.getMessage();
        if (fallback == null || fallback.isBlank()) {
            fallback = e.getClass().getSimpleName();
        }
        return "\u542f\u52a8\u5411\u91cf\u5316\u5931\u8d25\uff1a" + fallback;
    }

    private String extractErrorMessage(String responseBody) {
        if (responseBody == null || responseBody.isBlank()) {
            return null;
        }
        try {
            Map<?, ?> payload = objectMapper.readValue(responseBody, Map.class);
            Object detail = payload.get("detail");
            String detailMessage = extractErrorMessageValue(detail);
            if (detailMessage != null && !detailMessage.isBlank()) {
                return detailMessage;
            }
            return extractErrorMessageValue(payload.get("message"));
        } catch (Exception ignored) {
            return responseBody;
        }
    }

    private String extractErrorMessageValue(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Map<?, ?> map) {
            Object message = map.get("message");
            if (message == null) {
                message = map.get("error");
            }
            return message == null ? map.toString() : String.valueOf(message);
        }
        if (value instanceof List<?> list && !list.isEmpty()) {
            return extractErrorMessageValue(list.get(0));
        }
        return String.valueOf(value);
    }

    /**
     * 调用Python引擎
     */
    private void callPythonEngine(Document document, DocumentIndexJob job) {
        if (callbackSecret == null || callbackSecret.isBlank()) {
            throw new BusinessException(StatusCode.INTERNAL_ERROR, "CALLBACK_SECRET 未配置");
        }
        String url = pythonEngineUrl + "/api/parse";

        // 构建回调URL，用于Python引擎处理完成后通知Java后端
        String callbackUrl = callbackBaseUrl + "/vectorize/" + document.getId() + "/callback";

        Map<String, Object> request = Map.ofEntries(
                Map.entry("document_id", String.valueOf(document.getId())),
                Map.entry("file_path", document.getFilePath()),
                Map.entry("file_type", document.getFileType() != null ? document.getFileType() : "md"),
                Map.entry(
                        "knowledge_base_id", document.getKnowledgeBaseId() != null ? document.getKnowledgeBaseId() : 0),
                Map.entry("document_title", document.getTitle()),
                Map.entry("index_version", job.getIndexVersion()),
                Map.entry("callback_url", callbackUrl),
                Map.entry("callback_secret", callbackSecret),
                Map.entry("embedding_model", job.getEmbeddingModel()),
                Map.entry(
                        "embedding_dimension",
                        job.getEmbeddingDimension() != null ? job.getEmbeddingDimension() : 1024),
                Map.entry("embedding_version", job.getEmbeddingVersion() != null ? job.getEmbeddingVersion() : "v1"));

        HttpHeaders headers = internalHeaders();

        // Propagate the document tenant to Python so the hard tenant boundary
        // (TenantMiddleware + require_tenant) can validate the request.
        Long tenantId = resolveDocumentTenant(document);
        if (tenantId != null) {
            headers.set("X-Tenant-Id", String.valueOf(tenantId));
        }

        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, headers);

        log.info(
                "调用Python引擎: {}, 回调URL: {}, 模型: {}, 索引版本: {}, tenantId: {}",
                url,
                callbackUrl,
                job.getEmbeddingModel(),
                job.getIndexVersion(),
                tenantId);
        ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.POST, entity, String.class);
        log.info("Python引擎响应: {}", response.getBody());
    }

    private DocumentChunk toDocumentChunk(
            Document document, DocumentIndexJob job, DocumentChunkCallbackDTO callbackChunk) {
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
        chunk.setEmbeddingModel(callbackChunk.getEmbeddingModel());
        chunk.setEmbeddingDimension(callbackChunk.getEmbeddingDimension());
        chunk.setEmbeddingVersion(callbackChunk.getEmbeddingVersion());
        return chunk;
    }

    private HttpHeaders internalHeaders() {
        if (internalApiToken == null || internalApiToken.isBlank()) {
            throw new BusinessException(StatusCode.INTERNAL_ERROR, "PYTHON_AI_INTERNAL_TOKEN 未配置");
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Internal-Token", internalApiToken);
        // Propagate tenant context to Python AI service
        Long tenantId = com.hfusionhub.tenant.TenantContext.getTenantId();
        if (tenantId != null) {
            headers.set("X-Tenant-Id", tenantId.toString());
        }
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
        // 所有浏览器路径已由 Sa-Token 保护，回调路径通过 X-Callback-Secret 单独认证。
        // 此处始终要求已登录并校验文档所有权。
        if (!JwtUtils.isLogin()) {
            throw new BusinessException("未登录");
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

    private ChunkDTO toChunkDTO(DocumentChunk chunk) {
        return ChunkDTO.builder()
                .chunkId(chunk.getChunkId())
                .documentId(chunk.getDocumentId())
                .index(chunk.getChunkIndex())
                .content(chunk.getContentExcerpt())
                .blockType(chunk.getBlockType())
                .outlinePath(fromJsonList(chunk.getOutlinePath()))
                .metadata(fromJsonMap(chunk.getMetadata()))
                .build();
    }

    @SuppressWarnings("unchecked")
    private List<String> fromJsonList(String value) {
        if (value == null || value.isBlank()) {
            return List.of();
        }
        try {
            return objectMapper.readValue(value, List.class);
        } catch (JsonProcessingException e) {
            return List.of();
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> fromJsonMap(String value) {
        if (value == null || value.isBlank()) {
            return Collections.emptyMap();
        }
        try {
            return objectMapper.readValue(value, Map.class);
        } catch (JsonProcessingException e) {
            return Collections.emptyMap();
        }
    }

    /**
     * 将 Python 引擎返回的旧版分块 JSON 转为 {@link ChunkPageDTO}。
     * 仅用于未迁移到 V2 durable metadata 的遗留文档。
     */
    @SuppressWarnings("unchecked")
    private ChunkPageDTO legacyChunkPageFromPython(Map<String, Object> legacy, Long documentId) {
        Object chunksNode = legacy.get("chunks");
        List<ChunkDTO> chunks = List.of();
        if (chunksNode instanceof List<?> raw) {
            chunks = raw.stream()
                    .filter(Map.class::isInstance)
                    .map(item -> (Map<String, Object>) item)
                    .map(this::legacyChunkFromPythonItem)
                    .toList();
        }
        long total = chunks.size();
        if (legacy.get("total_chunks") instanceof Number n) {
            total = n.longValue();
        }
        return ChunkPageDTO.builder()
                .documentId(documentId)
                .totalChunks(total)
                .chunks(chunks)
                .build();
    }

    private ChunkDTO legacyChunkFromPythonItem(Map<String, Object> item) {
        return ChunkDTO.builder()
                .chunkId(safeString(item.get("chunk_id")))
                .index(safeInt(item.get("index")))
                .content(safeString(item.get("content")))
                .blockType(safeString(item.get("block_type")))
                .build();
    }

    private String safeString(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private Integer safeInt(Object value) {
        if (value instanceof Number n) {
            return n.intValue();
        }
        return null;
    }

    /** @deprecated replaced by {@link #toChunkDTO(DocumentChunk)} with typed DTO output */
    @Deprecated
    private Map<String, Object> toChunkResponse(DocumentChunk chunk) {
        Map<String, Object> response = new HashMap<>();
        response.put("chunk_id", chunk.getChunkId());
        response.put("index", chunk.getChunkIndex());
        response.put("content", chunk.getContentExcerpt());
        response.put("block_type", chunk.getBlockType());
        response.put("outline_path", fromJsonList(chunk.getOutlinePath()));
        response.put("metadata", fromJsonMap(chunk.getMetadata()));
        return response;
    }

    /** @deprecated replaced by {@link #fromJsonList(String)} and {@link #fromJsonMap(String)} */
    @Deprecated
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

    // ================================================================
    // 用量账本 — INDEX_CHUNKS
    // ================================================================

    /**
     * 按文件大小估算分块数上界（向上取整）。文件大小未知时退回到一个
     * 保守默认值，保证预占量 > 0（usage_ledger 对 amount <= 0 直接忽略）。
     * 使用 ceil 避免整数除法低估预占（如 301 bytes / 300 = 2 而非 1），
     * 防止索引越过额度门槛。
     */
    private long estimateIndexChunks(Document document) {
        Long fileSize = document.getFileSize();
        if (fileSize == null || fileSize <= 0) {
            return 100L;
        }
        long chunkBytes = Math.max(bytesPerChunkEstimate, 1);
        long estimate = (fileSize + chunkBytes - 1) / chunkBytes;
        return Math.max(1L, estimate);
    }

    private String indexReservationKey(String indexVersion) {
        return "INDEX_CHUNKS:" + indexVersion;
    }

    /**
     * 按文档归属租户解析。回调/恢复线程没有登录上下文，
     * 需经 document → knowledgeBase → user 解析 tenantId。
     */
    private Long resolveDocumentTenant(Document document) {
        KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        if (knowledgeBase == null || knowledgeBase.getUserId() == null) {
            return null;
        }
        User owner = userMapper.selectById(knowledgeBase.getUserId());
        return owner != null ? owner.getTenantId() : null;
    }

    private Long resolveDocumentTenantById(Long documentId) {
        return TenantContext.runAsSystem(() -> {
            Document document = documentMapper.selectById(documentId);
            return document == null ? null : resolveDocumentTenant(document);
        });
    }

    private Long resolveDeletedDocumentTenantById(Long documentId) {
        return TenantContext.runAsSystem(() -> {
            Document document = documentMapper.selectIncludingDeleted(documentId);
            if (document == null) {
                return null;
            }
            KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectIncludingDeleted(document.getKnowledgeBaseId());
            if (knowledgeBase == null || knowledgeBase.getUserId() == null) {
                return null;
            }
            User owner = userMapper.selectById(knowledgeBase.getUserId());
            return owner == null ? null : owner.getTenantId();
        });
    }

    private void reserveIndexChunks(Document document, DocumentIndexJob job) {
        Long tenantId = resolveDocumentTenant(document);
        if (tenantId == null) {
            log.warn("无法解析文档 {} 的租户，跳过索引预占", document.getId());
            return;
        }
        long estimate = estimateIndexChunks(document);
        TenantContext.runAs(tenantId, () -> {
            usageLedgerService.reserve(
                    UsageMeter.INDEX_CHUNKS,
                    indexReservationKey(job.getIndexVersion()),
                    estimate,
                    "document_index",
                    String.valueOf(document.getId()));
            return null;
        });
    }

    private void settleIndexChunks(Document document, DocumentIndexJob job, int actualChunks) {
        Long tenantId = resolveDocumentTenant(document);
        if (tenantId == null) {
            log.warn("无法解析文档 {} 的租户，跳过索引结算", document.getId());
            return;
        }
        TenantContext.runAs(tenantId, () -> {
            usageLedgerService.settle(
                    UsageMeter.INDEX_CHUNKS,
                    indexReservationKey(job.getIndexVersion()),
                    Math.max(actualChunks, 0),
                    "document_index",
                    String.valueOf(document.getId()));
            return null;
        });
    }

    private void releaseIndexChunks(Document document, DocumentIndexJob job) {
        Long tenantId = resolveDocumentTenant(document);
        if (tenantId == null) {
            log.warn("无法解析文档 {} 的租户，跳过索引退回", document.getId());
            return;
        }
        TenantContext.runAs(tenantId, () -> {
            usageLedgerService.release(UsageMeter.INDEX_CHUNKS, indexReservationKey(job.getIndexVersion()));
            return null;
        });
    }
}
