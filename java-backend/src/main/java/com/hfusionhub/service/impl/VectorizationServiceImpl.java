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
import com.hfusionhub.service.VectorizationService;
import com.hfusionhub.tenant.TenantContext;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
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
    private final IndexChunkLedger indexChunkLedger;
    private final PlatformTransactionManager transactionManager;

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
            // 知识库缺失（如已删除）或被禁用是确定性失败：文档 + 历史 PROCESSING job
            // 一并标记 FAILED，否则 DocumentIndexRecoveryScheduler 每 5 分钟无限重试
            // （job 永不退出 PROCESSING，日志持续刷「恢复索引任务失败」）。
            failDocumentBeforeStart(document, "知识库已禁用，无法解析文档");
        }

        // 2. 检查状态 - 允许重新处理处于 PROCESSING 状态的文档（修复之前的卡住问题）
        if (document.getStatus() != null && document.getStatus() == DocumentStatus.PROCESSING.getCode()) {
            log.warn("文档 {} 处于处理中状态，允许重新处理", documentId);
        }

        ensureSourceFileAvailable(document);

        // V77/S5: 文档级行锁短事务 — supersede 旧 job + 释放预占 + 插入新 job 在同一
        // 事务内原子完成，并发重处理/恢复调度在同一文档上串行化；attempt 取
        // MAX(attempt)+1，配合行锁消除 count+1 的 TOCTOU。
        TransactionTemplate txTemplate = new TransactionTemplate(transactionManager);
        DocumentIndexJob job;
        try {
            job = txTemplate.execute(status -> {
                documentMapper.selectByIdForUpdate(documentId);
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
                    indexChunkLedger.release(document, superseded);
                }
                DocumentIndexJob newJob = new DocumentIndexJob();
                newJob.setDocumentId(documentId);
                newJob.setKnowledgeBaseId(document.getKnowledgeBaseId());
                newJob.setIndexVersion(UUID.randomUUID().toString());
                newJob.setEmbeddingModel(model != null ? model : "ollama");
                newJob.setStatus("PROCESSING");
                newJob.setAttempt(documentIndexJobMapper.selectMaxAttemptByDocumentId(documentId) + 1);
                newJob.setChunkCount(0);
                newJob.setStartedAt(LocalDateTime.now());
                documentIndexJobMapper.insert(newJob);

                // 用量账本：按文件大小估算分块数上界预占（幂等键为 index_chunks:<indexVersion>）。
                // 回调按实际 chunk 数结算；失败/超时/被取代时退回。恢复路径在 runAsSystem 中执行，
                // 无租户上下文，需按文档归属解析租户后预占。预占失败抛 BusinessException
                // → 整个事务回滚（旧 job 保持原状态，不产生半套 supersede/新 job）。
                indexChunkLedger.reserve(document, newJob);
                return newJob;
            });
        } catch (BusinessException e) {
            log.warn("索引配额预占失败: documentId={}，已回滚本次重处理", documentId, e);
            document.setStatus(DocumentStatus.FAILED.getCode());
            document.setErrorMessage(e.getMessage());
            documentMapper.updateById(document);
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
            indexChunkLedger.release(document, job);
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
    public void deleteDocumentIndex(Long documentId) {
        // 故意不加 @Transactional：上面的远程 HTTP 调用（读超时最长 120s）
        // 绝不能占住数据库连接。调用方（DeletionService 状态机）已按
        // "向量步骤在事务外执行" 的约定组织流程，且对远程失败逐条
        // try/catch 继续；本地两条删除幂等，各自短事务即可。
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
                indexChunkLedger.release(document, exhaustedJob);
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
    public int reconcileVectorCounts() {
        // 全局统计需跨租户：runAsSystem 下租户拦截器不注入 tenant_id 条件。
        List<Map<String, Object>> globalCounts =
                TenantContext.runAsSystem(() -> documentChunkMapper.countGroupByTenantAndKnowledgeBase());
        if (globalCounts.isEmpty()) {
            return 0;
        }
        Map<Long, Map<Long, Long>> byTenant = new LinkedHashMap<>();
        for (Map<String, Object> row : globalCounts) {
            Long tenantId = toLong(row.get("tenant_id"));
            Long kbId = toLong(row.get("knowledge_base_id"));
            Long count = toLong(row.get("cnt"));
            if (tenantId == null || kbId == null || count == null) {
                continue;
            }
            byTenant.computeIfAbsent(tenantId, k -> new HashMap<>()).put(kbId, count);
        }
        int mismatches = 0;
        for (Map.Entry<Long, Map<Long, Long>> entry : byTenant.entrySet()) {
            mismatches += TenantContext.runAs(entry.getKey(), () -> reconcileTenant(entry.getKey(), entry.getValue()));
        }
        return mismatches;
    }

    /**
     * 单个租户的对账：文档分块持久化计数 vs Python 返回的 Milvus 实体数。
     * Milvus 不可达或查询失败（-1）时跳过该 KB，不误报。
     */
    private int reconcileTenant(Long tenantId, Map<Long, Long> kbCounts) {
        Map<Long, Long> milvusCounts = fetchMilvusCounts(kbCounts.keySet());
        int mismatches = 0;
        for (Map.Entry<Long, Long> entry : kbCounts.entrySet()) {
            Long kbId = entry.getKey();
            long dbCount = entry.getValue();
            Long milvus = milvusCounts.get(kbId);
            if (milvus == null || milvus < 0) {
                continue;
            }
            if (dbCount != milvus) {
                mismatches++;
                log.error(
                        "向量库对账失配: tenantId={}, knowledgeBaseId={}, document_chunk={}, milvus={} — "
                                + "疑似向量库卷重建/数据漂移，该知识库检索将静默返回 0 sources，请核对卷挂载与数据一致性",
                        tenantId,
                        kbId,
                        dbCount,
                        milvus);
            }
        }
        return mismatches;
    }

    private Map<Long, Long> fetchMilvusCounts(Collection<Long> kbIds) {
        Map<Long, Long> result = new HashMap<>();
        if (kbIds.isEmpty()) {
            return result;
        }
        try {
            Map<String, Object> body = new HashMap<>();
            body.put("knowledge_base_ids", kbIds);
            ResponseEntity<String> response = restTemplate.exchange(
                    pythonEngineUrl + "/api/stats/vector-counts",
                    HttpMethod.POST,
                    new HttpEntity<>(body, internalHeaders()),
                    String.class);
            if (!response.getStatusCode().is2xxSuccessful() || response.getBody() == null) {
                log.warn("向量库对账: Python 统计返回状态 {}，跳过本轮", response.getStatusCode());
                return result;
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> payload = objectMapper.readValue(response.getBody(), Map.class);
            Object countsNode = payload.get("counts");
            if (countsNode instanceof Map<?, ?> counts) {
                for (Map.Entry<?, ?> entry : counts.entrySet()) {
                    Long kbId = toLong(entry.getKey());
                    Long value = toLong(entry.getValue());
                    if (kbId != null && value != null) {
                        result.put(kbId, value);
                    }
                }
            }
        } catch (Exception e) {
            log.warn("向量库对账: 调用 Python 统计失败，跳过本轮", e);
        }
        return result;
    }

    private Long toLong(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return number.longValue();
        }
        try {
            return Long.parseLong(String.valueOf(value).trim());
        } catch (NumberFormatException e) {
            return null;
        }
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
            String status = job == null ? VectorizationProgress.statusName(document.getStatus()) : job.getStatus();
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
            VectorizationProgress.enrichWithEstimatedProgress(response, document, job, status);
            if (!completedButMissingChunks) {
                mergePythonTaskStatus(response, documentId, job);
            }
            return objectMapper.writeValueAsString(response);
        } catch (Exception e) {
            log.error("获取任务状态失败: {}", documentId, e);
            return "{\"status\":\"ERROR\",\"message\":\"任务状态暂不可用\"}";
        }
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
            VectorizationProgress.copyIfPresent(response, pythonStatus, "stage");
            VectorizationProgress.copyIfPresent(response, pythonStatus, "progress");
            VectorizationProgress.copyIfPresent(response, pythonStatus, "elapsed_seconds");
            VectorizationProgress.copyIfPresent(response, pythonStatus, "estimated_seconds");
            VectorizationProgress.copyIfPresent(response, pythonStatus, "remaining_seconds");
            VectorizationProgress.copyIfPresent(response, pythonStatus, "processed_chunks");
            VectorizationProgress.copyIfPresent(response, pythonStatus, "total_chunks");
            VectorizationProgress.copyIfPresent(response, pythonStatus, "chunk_quality");
            VectorizationProgress.copyIfPresent(response, pythonStatus, "multimodal");
            Object message = pythonStatus.get("message");
            if (message != null && !String.valueOf(message).isBlank()) {
                response.put("message", message);
            }
        } catch (Exception e) {
            log.debug("Python task status unavailable for document {}: {}", documentId, e.getMessage());
        }
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
        // 源文件缺失是确定性失败：把历史 PROCESSING 任务一并标记 FAILED，
        // 否则 DocumentIndexRecoveryScheduler 会无限重试（job 永远留在 PROCESSING）。
        documentIndexJobMapper.update(
                null,
                new LambdaUpdateWrapper<DocumentIndexJob>()
                        .eq(DocumentIndexJob::getDocumentId, document.getId())
                        .eq(DocumentIndexJob::getStatus, "PROCESSING")
                        .set(DocumentIndexJob::getStatus, "FAILED")
                        .set(DocumentIndexJob::getErrorMessage, truncate(message, 1000))
                        .set(DocumentIndexJob::getCompletedAt, LocalDateTime.now()));
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
        Long tenantId = indexChunkLedger.resolveDocumentTenant(document);
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

    private String truncate(String value, int maxLength) {
        if (value == null) {
            return null;
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
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

}
